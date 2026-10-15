"""Owner-scoped conversation API and evidence-backed analytical flow."""

import asyncio
import json
import re
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

import sqlglot
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import or_, select

from app.anomalies import detect
from app.auth import current_user
from app.charts import build_chart
from app.config import RuntimeConfigError
from app.conversation_titles import conversation_title, query_title
from app.execution_cache import cache_key, reusable_sql
from app.executor import QueryBusy, QueryFailure, QueryTimeout, execute, source_paths
from app.joins import JoinKey, diagnostics, fanout_warning, validate_keys
from app.models import Analysis, Conversation, Dataset, Message, User
from app.observability import emit
from app.planner import (
    AnalysisPlan,
    GeminiProvider,
    ProviderConfigurationError,
    ProviderFailure,
    ProviderMalformed,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.sql_policy import SqlRejected, validate_sql

router = APIRouter(prefix="/api/v1")


def _execution_settings(request: Request):
    provider = request.app.state.provider
    return provider.current_settings() if isinstance(provider, GeminiProvider) else request.app.state.settings


class ConversationInput(BaseModel):
    dataset_ids: list[UUID] = Field(min_length=1, max_length=5)


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    join_confirmation: UUID | None = None
    accept_multiplication: bool = False
    anomaly_group_confirmation: str | None = Field(default=None, pattern=r"^c[0-9]{1,2}$")


class JoinInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    joins: list[JoinKey] = Field(min_length=1, max_length=4)


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"request_id": request.state.request_id, "error": {"code": code, "message": message, "details": {}}},
    )


def _conversation(db, user: User, conversation_id: UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.owner_id == user.id)
    )
    if not conversation:
        raise HTTPException(404)
    return conversation


def _datasets(db, user: User, ids: list[UUID]) -> list[Dataset]:
    if len(ids) != len(set(ids)):
        raise HTTPException(422)
    datasets = db.scalars(
        select(Dataset).where(Dataset.id.in_(ids), Dataset.owner_id == user.id, Dataset.status == "ready")
    ).all()
    by_id = {item.id: item for item in datasets}
    if len(by_id) != len(ids):
        raise HTTPException(404)
    return [by_id[item] for item in ids]


def _versions(datasets: list[Dataset]):
    return [
        {
            "id": str(item.id),
            "version": item.version,
            "content_hash": item.content_hash,
            "display_name": item.display_name,
        }
        for item in datasets
    ]


def _public_conversation(item: Conversation):
    return {
        "id": str(item.id),
        "title": item.title,
        "selected_dataset_versions": json.loads(item.selected_dataset_versions_json),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _public_analysis(item: Analysis):
    result = json.loads(item.result_json)
    return {
        "id": str(item.id),
        "conversation_id": str(item.conversation_id),
        "status": item.status,
        "question": item.question,
        "sql": item.sql,
        "dataset_versions": json.loads(item.dataset_versions_json),
        "method": json.loads(item.method_json),
        "timings_ms": json.loads(item.timings_json),
        "cache_hit": json.loads(item.timings_json).get("cache_hit", False),
        "answer": result.get("answer"),
        "table": result.get("table"),
        "clarification": result.get("clarification"),
        "error": result.get("error"),
        "charts": result.get("charts", []),
        "chart_error": result.get("chart_error"),
        "anomalies": result.get("anomalies"),
        "join_proposal": result.get("join_proposal"),
        "intent": json.loads(item.plan_json).get("intent"),
        "created_at": item.created_at.isoformat(),
    }


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationInput, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        datasets = _datasets(db, user, body.dataset_ids)
        item = Conversation(
            owner_id=user.id, title="New analysis", selected_dataset_versions_json=json.dumps(_versions(datasets))
        )
        db.add(item)
        db.commit()
        return {"request_id": request.state.request_id, "data": _public_conversation(item)}


@router.get("/conversations")
def list_conversations(request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        items = db.scalars(
            select(Conversation)
            .where(Conversation.owner_id == user.id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
        ).all()
        return {
            "request_id": request.state.request_id,
            "data": [{**_public_conversation(item), "title": conversation_title(db, item)} for item in items],
        }


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: UUID, body: ConversationInput, request: Request, user: User = Depends(current_user)
):
    with request.app.state.sessions() as db:
        item = _conversation(db, user, conversation_id)
        item.selected_dataset_versions_json = json.dumps(_versions(_datasets(db, user, body.dataset_ids)))
        item.updated_at = datetime.now(UTC)
        db.commit()
        return {"request_id": request.state.request_id, "data": _public_conversation(item)}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        item = _conversation(db, user, conversation_id)
        messages = db.scalars(
            select(Message).where(Message.conversation_id == item.id).order_by(Message.created_at, Message.id)
        ).all()
        analyses = db.scalars(
            select(Analysis)
            .where(Analysis.conversation_id == item.id, Analysis.owner_id == user.id)
            .order_by(Analysis.created_at, Analysis.id)
        ).all()
        return {
            "request_id": request.state.request_id,
            "data": {
                "conversation": {**_public_conversation(item), "title": conversation_title(db, item)},
                "messages": [
                    {"id": str(m.id), "role": m.role, "content": m.content, "status": m.status} for m in messages
                ],
                "analyses": [_public_analysis(a) for a in analyses],
            },
        }


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: UUID, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        item = db.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == user.id))
        if not item:
            raise HTTPException(404)
        return {"request_id": request.state.request_id, "data": _public_analysis(item)}


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: UUID, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        item = db.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == user.id))
        if not item:
            raise HTTPException(404)
        # SearchDocument cascades on deletion. Dashboard references are reauthorized on read/export.
        db.delete(item)
        db.commit()
    return {"request_id": request.state.request_id, "data": {"deleted": True}}


def _method(sql: str, datasets: list[Dataset], truncated: bool) -> dict:
    tree = sqlglot.parse_one(sql, read="duckdb")
    group = tree.args.get("group")
    where = tree.args.get("where")
    return {
        "calculation": ", ".join(part.sql(dialect="duckdb") for part in tree.expressions),
        "filters": where.this.sql(dialect="duckdb") if where else "None",
        "grouping": ", ".join(part.sql(dialect="duckdb") for part in group.expressions) if group else "None",
        "ordering": tree.args["order"].sql(dialect="duckdb") if tree.args.get("order") else "None",
        "assumptions": ["Only authorized selected snapshots were queried. Nulls follow DuckDB aggregate semantics."]
        + (["The displayed table is truncated to 500 rows."] if truncated else []),
        "sources": _versions(datasets),
        "stages": [
            {
                "name": node.parent.alias
                if isinstance(node.parent, (sqlglot.exp.CTE, sqlglot.exp.Subquery))
                else "result",
                "metrics": [p.sql(dialect="duckdb") for p in node.expressions],
                "filters": node.args["where"].sql(dialect="duckdb") if node.args.get("where") else "None",
                "grouping": node.args["group"].sql(dialect="duckdb") if node.args.get("group") else "None",
                "ordering": node.args["order"].sql(dialect="duckdb") if node.args.get("order") else "None",
            }
            for node in tree.find_all(sqlglot.exp.Select)
        ],
    }


def _answer(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return "The validated query returned no rows."
    if len(rows) == 1 and not result["truncated"]:
        facts = ", ".join(f"{key}: {value if value is not None else 'null'}" for key, value in rows[0].items())
        return f"Calculated result — {facts}."
    suffix = " (first 500 shown)" if result["truncated"] else ""
    return f"Calculated {len(rows)} result rows{suffix}. The supporting table contains the values."


def _save_outcome(
    request: Request,
    user: User,
    conversation_id: UUID,
    question: str,
    status: str,
    plan: dict,
    sql: str | None,
    versions: list[dict],
    result: dict,
    method: dict,
    timings: dict,
) -> Analysis:
    with request.app.state.sessions() as db:
        conversation = _conversation(db, user, conversation_id)
        fresh = _datasets(db, user, [UUID(v["id"]) for v in versions])
        if _versions(fresh) != versions or json.loads(conversation.selected_dataset_versions_json) != versions:
            raise HTTPException(409, "Sources changed before evidence could be saved.")
        item = Analysis(
            owner_id=user.id,
            conversation_id=conversation_id,
            question=question,
            plan_json=json.dumps(plan),
            sql=sql,
            dataset_versions_json=json.dumps(versions),
            result_json=json.dumps(result),
            method_json=json.dumps(method),
            status=status,
            timings_json=json.dumps(timings),
        )
        db.add(item)
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=result.get("answer") or result.get("clarification") or result.get("error", "Analysis failed."),
                status=status,
            )
        )
        conversation.updated_at = datetime.now(UTC)
        db.commit()
        return item


@router.post("/conversations/{conversation_id}/joins")
async def preview_joins(conversation_id: UUID, body: JoinInput, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        conversation = _conversation(db, user, conversation_id)
        selected = json.loads(conversation.selected_dataset_versions_json)
        datasets = _datasets(db, user, [UUID(v["id"]) for v in selected])
        if _versions(datasets) != selected:
            return _error(request, 409, "SOURCE_CHANGED", "Dataset versions changed. Review your selection.")
    try:
        if len(datasets) > 5:
            raise SqlRejected("New join configurations support at most five datasets.")
        ordered = validate_keys(body.joins, datasets)
        execution_settings = _execution_settings(request)
        facts = await diagnostics(
            ordered,
            source_paths(execution_settings.data_dir, datasets),
            execution_settings,
            request.app.state.query_capacity,
        )
        proposal = {
            "joins": [j.model_dump(mode="json") for j in ordered],
            "diagnostics": facts,
            "requires_multiplication": any(f["multiplies_left_rows"] or f["multiplies_right_rows"] for f in facts),
            "versions": selected,
            "fanout_warning": fanout_warning(facts),
        }
        with request.app.state.sessions() as db:
            fresh = _datasets(db, user, [d.id for d in datasets])
            current = _conversation(db, user, conversation_id)
            if _versions(fresh) != selected or json.loads(current.selected_dataset_versions_json) != selected:
                return _error(request, 409, "SOURCE_CHANGED", "Selection changed. Review join keys again.")
        saved = _save_outcome(
            request,
            user,
            conversation_id,
            "Review explicit join keys",
            "clarification",
            {},
            None,
            selected,
            {"clarification": "Review diagnostics and confirm these exact joins.", "join_proposal": proposal},
            {},
            {},
        )
        return {"request_id": request.state.request_id, "data": _public_analysis(saved)}
    except SqlRejected as exc:
        return _error(request, 422, "JOIN_INVALID", str(exc))
    except RuntimeConfigError:
        return _error(request, 503, "RUNTIME_CONFIG_INVALID", "Runtime settings are unavailable or invalid.")
    except QueryFailure:
        return _error(request, 503, "JOIN_DIAGNOSTICS_FAILED", "Join diagnostics could not complete. Try again.")


@router.post("/conversations/{conversation_id}/messages")
async def ask(conversation_id: UUID, body: MessageInput, request: Request, user: User = Depends(current_user)):
    return await run_analysis(conversation_id, body, request, user)


@router.post("/analyses/{analysis_id}/rerun")
async def rerun(analysis_id: UUID, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        item = db.scalar(
            select(Analysis).where(
                Analysis.id == analysis_id, Analysis.owner_id == user.id, Analysis.status == "complete"
            )
        )
        if not item:
            raise HTTPException(404)
        conversation = _conversation(db, user, item.conversation_id)
        if json.loads(item.dataset_versions_json) != json.loads(conversation.selected_dataset_versions_json):
            return _error(request, 409, "SOURCE_CHANGED", "Saved sources changed. Start a new analysis.")
        stored_plan = json.loads(item.plan_json)
        stored_plan.pop("intent", None)
        plan = AnalysisPlan.model_validate(stored_plan)
        if plan.action != "query" or len(plan.dataset_ids) != 1:
            return _error(request, 422, "RERUN_UNAVAILABLE", "Only single-source queries can be rerun.")
        conversation_id, question = item.conversation_id, item.question
    return await run_analysis(conversation_id, MessageInput(question=question), request, user, planned=plan)


async def run_analysis(
    conversation_id: UUID, body: MessageInput, request: Request, user: User, planned: AnalysisPlan | None = None
):
    question = body.question.strip()
    if not question:
        raise HTTPException(422)
    started = perf_counter()
    with request.app.state.sessions() as db:
        conversation = _conversation(db, user, conversation_id)
        selected = json.loads(conversation.selected_dataset_versions_json)
        datasets = _datasets(db, user, [UUID(entry["id"]) for entry in selected])
        if _versions(datasets) != selected:
            return _error(request, 409, "SOURCE_CHANGED", "Selected dataset changed. Start a new conversation.")
        previous = db.scalar(
            select(Analysis)
            .where(
                Analysis.conversation_id == conversation_id, Analysis.owner_id == user.id, Analysis.status == "complete"
            )
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
            .limit(1)
        )
        prior_intent = json.loads(previous.plan_json).get("intent") if previous else None
        recent = db.scalars(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                or_(Message.role == "user", Message.status == "clarification"),
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(4)
        ).all()
        recent_context = [{"role": m.role, "content": m.content[:500]} for m in reversed(recent)]
        context_changed = previous is not None and json.loads(previous.dataset_versions_json) != selected
        confirmed = []
        join_facts = []
        if body.join_confirmation:
            proposal_record = db.scalar(
                select(Analysis).where(
                    Analysis.id == body.join_confirmation,
                    Analysis.owner_id == user.id,
                    Analysis.conversation_id == conversation_id,
                )
            )
            proposal = json.loads(proposal_record.result_json).get("join_proposal") if proposal_record else None
            if not proposal or proposal["versions"] != selected:
                return _error(request, 409, "JOIN_CONFIRMATION_INVALID", "Join confirmation is stale or unavailable.")
            if proposal["requires_multiplication"] and not body.accept_multiplication:
                return _error(
                    request, 409, "JOIN_MULTIPLICATION", "Explicitly accept row multiplication before analysis."
                )
            confirmed = [JoinKey.model_validate(j) for j in proposal["joins"]]
            confirmed = validate_keys(confirmed, datasets)
            join_facts = proposal["diagnostics"]
        conversation = _conversation(db, user, conversation_id)
        if conversation.title == "New analysis":
            previous_title = conversation_title(db, conversation)
            conversation.title = query_title(question) if previous_title == "New analysis" else previous_title
        db.add(Message(conversation_id=conversation_id, role="user", content=question, status="saved"))
        db.commit()
    context = [
        {
            "id": str(item.id),
            "table": f"dataset_{item.id.hex}",
            "name": item.display_name,
            "version": item.version,
            "columns": [
                {"id": col["id"], "name": col["name"], "type": col["type"]} for col in json.loads(item.schema_json)
            ][:50],
            "row_count": item.row_count,
        }
        for item in datasets
    ]
    plan_data = {}
    timings = {}
    try:
        execution_settings = _execution_settings(request)
        reference = bool(re.search(r"\b(that|those|it|same|previous|now|them)\b", question, re.I))
        if planned is not None:
            plan = AnalysisPlan.model_validate(planned)
        elif reference and (not prior_intent or context_changed):
            plan = AnalysisPlan(
                action="clarify",
                dataset_ids=[],
                question="Which measure and filters should I use? Prior intent is unavailable or sources changed.",
            )
        else:
            context[0]["prior_intent"] = prior_intent if not context_changed else None
            context[0]["confirmed_joins"] = [j.model_dump(mode="json") for j in confirmed]
            context[0]["recent_messages"] = recent_context if not context_changed else []
            provider = request.app.state.provider
            if isinstance(provider, GeminiProvider):
                planned = await provider.plan(question, context, settings=execution_settings)
            else:
                planned = await provider.plan(question, context)
            plan = AnalysisPlan.model_validate(planned)
        plan_data = plan.model_dump(mode="json")
        chosen_ids = set(plan.dataset_ids)
        if not chosen_ids.issubset({item.id for item in datasets}):
            raise SqlRejected("Plan selected an unauthorized dataset.")
        if plan.action in {"query", "anomalies"}:
            if not chosen_ids:
                raise SqlRejected("Select a source.")
            if (len(chosen_ids) > 1 and not confirmed) or (plan.action == "anomalies" and len(chosen_ids) != 1):
                result = {
                    "clarification": "Review and confirm explicit join keys/type. Anomalies require one selected file."
                }
                status = "clarification"
                sql = None
                method = {}
            elif (
                plan.action == "anomalies"
                and reference
                and prior_intent
                and (
                    prior_intent["filters"] != "None"
                    or any(stage["filters"] != "None" for stage in prior_intent.get("stages", []))
                )
            ):
                result = {
                    "clarification": "IQR evaluates a full snapshot. Start a new unfiltered request; "
                    "the prior filters cannot be silently dropped."
                }
                status, sql, method = "clarification", None, {}
            elif (
                plan.action == "anomalies"
                and plan.anomaly.group
                and body.anomaly_group_confirmation != plan.anomaly.group
            ):
                result = {"clarification": f"Confirm column {plan.anomaly.group} to evaluate anomalies per group."}
                status, sql, method = "clarification", None, {}
            else:
                chosen = [item for item in datasets if item.id in chosen_ids]
                registry = {
                    f"dataset_{item.id.hex}": {col["id"] for col in json.loads(item.schema_json)} for item in chosen
                }
                sources = source_paths(execution_settings.data_dir, chosen)
                query_started = perf_counter()
                if plan.action == "anomalies":
                    anomaly = await detect(
                        chosen[0], plan.anomaly, sources, execution_settings, request.app.state.query_capacity
                    )
                    table, sql = anomaly.pop("table"), anomaly.pop("sql")
                    method = {
                        "calculation": anomaly["rule"],
                        "filters": "Null measure values excluded",
                        "grouping": anomaly["group"] or "None",
                        "assumptions": anomaly["caveats"],
                    }
                    result = {
                        "answer": f"IQR flagged {anomaly['flagged_count']} records. See group verdicts and caveats.",
                        "table": table,
                        "anomalies": anomaly,
                    }
                else:
                    sql = validate_sql(plan.sql or "", registry, confirmed if len(chosen) > 1 else None)
                    lookup_started = perf_counter()
                    try:
                        key = cache_key(user.id, chosen, sql, sources)
                    except OSError:
                        raise QueryFailure("Selected dataset snapshot is unavailable.") from None
                    reusable = reusable_sql(sql)
                    table, reason = request.app.state.execution_cache.get(key) if reusable else (None, "bypass")
                    timings["cache_lookup_ms"] = round((perf_counter() - lookup_started) * 1000, 2)
                    timings["cache_hit"] = table is not None
                    emit("cache", duration_ms=timings["cache_lookup_ms"], cache_hit=table is not None, reason=reason)
                    if table is None:
                        table = await execute(
                            sql, sources, execution_settings.query_timeout_seconds, request.app.state.query_capacity
                        )
                        emit("query", duration_ms=round((perf_counter() - query_started) * 1000), outcome="success")
                    try:
                        current_key = cache_key(user.id, chosen, sql, sources)
                    except OSError:
                        raise QueryFailure("Selected dataset snapshot is unavailable.") from None
                    if current_key != key:
                        raise QueryFailure("Selected snapshot changed during execution.")
                    method = _method(sql, chosen, table["truncated"])
                    if len(chosen) > 1:
                        method["joins"] = join_facts
                        warning = fanout_warning(join_facts)
                        if warning:
                            method["assumptions"].append(warning)
                        method["assumptions"].append(
                            "Confirmed join keys/type used. See join diagnostics for unmatched rows and multiplication."
                        )
                    result = {"answer": _answer(table), "table": table}
                    if len(chosen) > 1 and fanout_warning(join_facts):
                        result["answer"] += (
                            " Warning: fanout can inflate aggregates; confirmation does not correct them."
                        )
                    if plan.chart:
                        try:
                            result["charts"] = [build_chart(plan.chart, table)]
                        except ValueError as exc:
                            result["chart_error"] = str(exc)
                with request.app.state.sessions() as db:
                    try:
                        _conversation(db, user, conversation_id)
                        refreshed = _datasets(db, user, [item.id for item in datasets])
                    except HTTPException:
                        return _error(
                            request, 409, "SOURCE_DELETED", "The selected source was deleted during analysis."
                        )
                    if (
                        _versions(refreshed) != selected
                        or json.loads(_conversation(db, user, conversation_id).selected_dataset_versions_json)
                        != selected
                    ):
                        raise QueryFailure("Selected source is no longer available.")
                status = "complete"
                intent = {
                    "sources": _versions(chosen),
                    "filters": method["filters"],
                    "grouping": method["grouping"],
                    "metrics": method["calculation"],
                    "ordering": method.get("ordering", "None"),
                    "stages": method.get("stages", []),
                }
                # Keep complete intent or omit it; never truncate into an ambiguous expression.
                plan_data["intent"] = intent if len(json.dumps(intent)) <= 4000 else None
                timings["query_ms"] = round((perf_counter() - query_started) * 1000)
        else:
            status = "clarification"
            sql = None
            method = {}
            result = {"clarification": plan.question or "This question is not supported by the selected data."}
        timings["total_ms"] = round((perf_counter() - started) * 1000)
        saved = _save_outcome(
            request, user, conversation_id, question, status, plan_data, sql, selected, result, method, timings
        )
        if status == "complete":
            if plan.action == "query" and reusable and reason != "hit":
                request.app.state.execution_cache.put(key, table, user.id, chosen)
            from app.search import index_analysis

            await index_analysis(request.app, saved.id, user.id)
        emit(
            "analysis",
            duration_ms=timings["total_ms"],
            outcome="success" if status == "complete" else "unavailable",
            cache_hit=timings.get("cache_hit", False),
        )
        return {"request_id": request.state.request_id, "data": _public_analysis(saved)}
    except (RuntimeConfigError, ProviderConfigurationError):
        code, message, http_status = "RUNTIME_CONFIG_INVALID", "Runtime settings are unavailable or invalid.", 503
    except ProviderUnavailable:
        code, message, http_status = "PROVIDER_UNAVAILABLE", "Configure a planning provider to analyze questions.", 503
    except (ProviderMalformed, ValidationError):
        code, message, http_status = "PROVIDER_INVALID", "The provider returned an invalid plan.", 502
    except ProviderTimeout:
        code, message, http_status = "PROVIDER_TIMEOUT", "The provider timed out.", 504
    except ProviderFailure:
        code, message, http_status = "PROVIDER_FAILED", "The provider could not plan this question.", 502
    except SqlRejected:
        code, message, http_status = "SQL_REJECTED", "The proposed query was rejected safely.", 422
    except QueryBusy:
        code, message, http_status = "QUERY_BUSY", "Query capacity reached. Try again.", 429
    except QueryTimeout:
        code, message, http_status = "QUERY_TIMEOUT", "The query timed out.", 504
    except QueryFailure:
        code, message, http_status = "QUERY_FAILED", "The query could not be completed safely.", 503
    except asyncio.CancelledError:
        raise
    result = {"error": message}
    emit("analysis", duration_ms=round((perf_counter() - started) * 1000), outcome="failure")
    try:
        _save_outcome(
            request,
            user,
            conversation_id,
            question,
            "failed",
            plan_data,
            None,
            selected,
            result,
            {},
            {"total_ms": round((perf_counter() - started) * 1000)},
        )
    except HTTPException:
        return _error(request, 409, "SOURCE_DELETED", "The selected source was deleted during analysis.")
    return _error(request, http_status, code, message)
