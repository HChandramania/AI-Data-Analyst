"""Bounded dashboard orchestration over the authenticated analysis pipeline."""

import asyncio
import json
from datetime import UTC
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.analysis import (
    MessageInput,
    _conversation,
    _datasets,
    _execution_settings,
    _public_analysis,
    _versions,
    run_analysis,
)
from app.auth import current_user
from app.config import RuntimeConfigError
from app.joins import JoinKey, validate_keys
from app.models import Analysis, Dashboard, User
from app.observability import emit
from app.planner import DashboardPlan, GeminiProvider, ProviderFailure, ProviderMalformed, ProviderUnavailable

router = APIRouter(prefix="/api/v1/dashboards")
DASHBOARD_DEADLINE = 90


class DashboardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    conversation_id: UUID
    prompt: str = Field(
        default="Suggest a useful overview using supported metrics and charts.", min_length=1, max_length=800
    )
    analysis_ids: list[UUID] = Field(default_factory=list, max_length=6)
    generate: bool = True
    join_confirmation: UUID | None = None
    accept_multiplication: bool = False

    @model_validator(mode="after")
    def selections(self):
        if len(set(self.analysis_ids)) != len(self.analysis_ids) or (not self.generate and not self.analysis_ids):
            raise ValueError("Select distinct saved analyses or generate cards.")
        return self


def evidence(db, user, analysis_id):
    item = db.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == user.id))
    if not item:
        raise HTTPException(404)
    versions = json.loads(item.dataset_versions_json)
    sources = _datasets(db, user, [UUID(v["id"]) for v in versions])
    if _versions(sources) != versions:
        raise HTTPException(409)
    result = _public_analysis(item)
    result["created_at"] = item.created_at.replace(tzinfo=UTC).isoformat()
    return result


def owned_dashboard(db, user, dashboard_id):
    item = db.scalar(select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.owner_id == user.id))
    if not item:
        raise HTTPException(404)
    return item


def public_dashboard(db, user, item):
    cards = []
    for stored in json.loads(item.cards_json):
        card = dict(stored)
        try:
            versions = card.get("dataset_versions", json.loads(item.dataset_versions_json))
            sources = _datasets(db, user, [UUID(v["id"]) for v in versions])
            if _versions(sources) != versions:
                raise HTTPException(409)
        except HTTPException:
            card.update(status="unavailable", error="Source or saved evidence is no longer available.")
            cards.append(card)
            continue
        if card.get("analysis_id"):
            try:
                card["evidence"] = evidence(db, user, UUID(card["analysis_id"]))
                card["status"] = card["evidence"]["status"]
            except HTTPException:
                card.update(status="unavailable", error="Source or saved evidence is no longer available.")
        cards.append(card)
    complete = sum(c["status"] == "complete" for c in cards)
    return {
        "id": str(item.id),
        "title": item.title,
        "created_at": item.created_at.replace(tzinfo=UTC).isoformat(),
        "dataset_versions": json.loads(item.dataset_versions_json),
        "cards": cards,
        "complete_cards": complete,
        "total_cards": len(cards),
        "status": "complete" if complete == len(cards) else "partial" if complete else "failed",
    }


@router.get("")
def listing(request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        items = db.scalars(
            select(Dashboard).where(Dashboard.owner_id == user.id).order_by(Dashboard.created_at.desc()).limit(50)
        ).all()
        return {
            "request_id": request.state.request_id,
            "data": [{k: v for k, v in public_dashboard(db, user, item).items() if k != "cards"} for item in items],
        }


@router.get("/{dashboard_id}")
def detail(dashboard_id: UUID, request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        return {
            "request_id": request.state.request_id,
            "data": public_dashboard(db, user, owned_dashboard(db, user, dashboard_id)),
        }


@router.post("", status_code=201)
async def create(body: DashboardInput, request: Request, user: User = Depends(current_user)):
    operation_started = perf_counter()
    with request.app.state.sessions() as db:
        conversation = _conversation(db, user, body.conversation_id)
        versions = json.loads(conversation.selected_dataset_versions_json)
        datasets = _datasets(db, user, [UUID(v["id"]) for v in versions])
        if _versions(datasets) != versions:
            raise HTTPException(409)
        confirmed = []
        if body.join_confirmation:
            saved = evidence(db, user, body.join_confirmation)
            proposal = saved.get("join_proposal")
            if saved["conversation_id"] != str(conversation.id) or not proposal or proposal["versions"] != versions:
                raise HTTPException(409)
            if proposal["requires_multiplication"] and not body.accept_multiplication:
                raise HTTPException(409)
            confirmed = [
                j.model_dump(mode="json")
                for j in validate_keys([JoinKey.model_validate(j) for j in proposal["joins"]], datasets)
            ]
        cards = []
        for aid in body.analysis_ids:
            saved = evidence(db, user, aid)
            if saved["status"] != "complete" or any(v not in versions for v in saved["dataset_versions"]):
                raise HTTPException(422)
            cards.append(
                {
                    "title": saved["question"][:160],
                    "analysis_id": str(aid),
                    "status": "complete",
                    "dataset_versions": saved["dataset_versions"],
                }
            )

    # One dashboard at a time process-wide; one card at a time, one provider call, no retries.
    try:
        await asyncio.wait_for(request.app.state.dashboard_capacity.acquire(), timeout=0.1)
    except TimeoutError:
        raise HTTPException(429) from None
    planned_cards = []
    try:
        try:
            async with asyncio.timeout(DASHBOARD_DEADLINE):
                if body.generate and len(cards) < 6:
                    context = [
                        {
                            "id": str(d.id),
                            "table": f"dataset_{d.id.hex}",
                            "name": d.display_name,
                            "version": d.version,
                            "columns": [
                                {"id": col["id"], "name": col["name"], "type": col["type"]}
                                for col in json.loads(d.schema_json)
                            ],
                            "row_count": d.row_count,
                        }
                        for d in datasets
                    ]
                    context[0]["confirmed_joins"] = confirmed
                    context[0]["maximum_cards"] = 6 - len(cards)
                    provider = request.app.state.provider
                    settings = _execution_settings(request)
                    kwargs = {"settings": settings} if isinstance(provider, GeminiProvider) else {}
                    plan = DashboardPlan.model_validate(
                        await asyncio.wait_for(
                            provider.dashboard(body.prompt, context, **kwargs),
                            timeout=settings.provider_timeout_seconds,
                        )
                    )
                    if len(plan.cards) + len(cards) > 6:
                        raise ProviderMalformed("Too many cards")
                    planned_cards = plan.cards
                    for card in planned_cards:
                        result = await run_analysis(
                            body.conversation_id,
                            MessageInput(
                                question=card.title,
                                join_confirmation=body.join_confirmation,
                                accept_multiplication=body.accept_multiplication,
                            ),
                            request,
                            user,
                            planned=card.plan,
                        )
                        if isinstance(result, JSONResponse):
                            cards.append(
                                {
                                    "title": card.title,
                                    "status": "failed",
                                    "error": json.loads(result.body)["error"]["message"],
                                }
                            )
                        else:
                            saved = result["data"]
                            cards.append({"title": card.title, "status": saved["status"], "analysis_id": saved["id"]})
        except TimeoutError:
            remaining = planned_cards[len(cards) - len(body.analysis_ids) :] if planned_cards else []
            cards.extend(
                {"title": c.title, "status": "failed", "error": "Generation time limit reached."} for c in remaining
            )
            if not remaining and len(cards) < 6:
                cards.append({"title": "Generation", "status": "failed", "error": "Generation time limit reached."})
        except (ProviderFailure, ProviderUnavailable, ProviderMalformed, RuntimeConfigError, ValueError):
            cards.append(
                {
                    "title": "Generation",
                    "status": "failed",
                    "error": "Dashboard planning failed. Check provider configuration and try generating again.",
                }
            )
        except HTTPException:
            remaining = planned_cards[len(cards) - len(body.analysis_ids) :]
            for title in [card.title for card in remaining] or ["Generation"]:
                cards.append(
                    {"title": title, "status": "unavailable", "error": "Source or confirmation became unavailable."}
                )
        with request.app.state.sessions() as db:
            for card in cards:
                card.setdefault("dataset_versions", versions)
            item = Dashboard(
                owner_id=user.id,
                title=body.title,
                dataset_versions_json=json.dumps(versions),
                cards_json=json.dumps(cards[:6]),
            )
            db.add(item)
            db.commit()
            return {"request_id": request.state.request_id, "data": public_dashboard(db, user, item)}
    finally:
        request.app.state.dashboard_capacity.release()
        emit("dashboard", duration_ms=round((perf_counter() - operation_started) * 1000))
