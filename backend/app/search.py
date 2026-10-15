"""Bounded owner-scoped semantic lookup over persisted saved-analysis embeddings."""

import asyncio
import hashlib
import json
import math
import struct
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.auth import current_user
from app.conversation_titles import conversation_title
from app.models import Analysis, Conversation, Dataset, SearchDocument, User
from app.observability import emit
from app.planner import GeminiProvider

router = APIRouter(prefix="/api/v1/search")
MODEL_REVISION = "gemini-embedding-001:768:v1"
MAX_CANDIDATES = 500
# Initial relevance floor calibrated against the synthetic sales acceptance queries.
# Cosine similarity is not a probability; re-evaluate this when changing embeddings.
MIN_SIMILARITY = 0.60


def _provider_available(provider):
    if not hasattr(provider, "embed"):
        return False
    if isinstance(provider, GeminiProvider):
        try:
            key = provider.current_settings().gemini_api_key
            return key is not None and bool(key.get_secret_value())
        except ValueError:
            return False
    return True


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


def _error(request, status, code, message):
    return JSONResponse(
        status_code=status,
        content={"request_id": request.state.request_id, "error": {"code": code, "message": message, "details": {}}},
    )


def _text(analysis, conversation):
    result = json.loads(analysis.result_json)
    titles = " ".join(str(c.get("title", ""))[:150] for c in result.get("charts", [])[:2])
    sources = " ".join(v.get("display_name", "")[:100] for v in json.loads(analysis.dataset_versions_json)[:10])
    answer = result.get("answer") or ""
    return f"{conversation.title[:200]}\n{analysis.question[:1000]}\n{answer[:1000]}\n{titles}\n{sources}"[:3000]


def _vector(values):
    if len(values) != 768 or any(not math.isfinite(float(v)) for v in values):
        raise ValueError("Invalid embedding")
    norm = math.sqrt(sum(float(v) ** 2 for v in values))
    if norm <= 0 or not math.isfinite(norm):
        raise ValueError("Empty embedding")
    return struct.pack("<768f", *(float(v) / norm for v in values))


def _eligible(db, owner, analysis):
    if analysis.status != "complete":
        return False
    versions = json.loads(analysis.dataset_versions_json)
    if not versions or len(versions) > 10:
        return False
    sources = db.scalars(
        select(Dataset).where(
            Dataset.owner_id == owner, Dataset.id.in_([UUID(v["id"]) for v in versions]), Dataset.status == "ready"
        )
    ).all()
    actual = {str(s.id): (s.version, s.content_hash) for s in sources}
    return all(actual.get(v["id"]) == (v["version"], v["content_hash"]) for v in versions)


async def index_analysis(app, analysis_id, owner):
    started = perf_counter()
    provider = app.state.provider
    if not hasattr(provider, "embed"):
        return False
    with app.state.sessions() as db:
        analysis = db.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == owner))
        if not analysis or not _eligible(db, owner, analysis):
            return False
        conversation = db.scalar(
            select(Conversation).where(Conversation.id == analysis.conversation_id, Conversation.owner_id == owner)
        )
        if not conversation:
            return False
        content = _text(analysis, conversation)
        digest = hashlib.sha256(content.encode()).hexdigest()
        existing = db.scalar(
            select(SearchDocument).where(SearchDocument.analysis_id == analysis_id, SearchDocument.owner_id == owner)
        )
        if existing and existing.content_hash == digest and existing.model_revision == MODEL_REVISION:
            return True
    try:
        async with app.state.embedding_capacity:
            raw = await asyncio.wait_for(provider.embed(content, task_type="RETRIEVAL_DOCUMENT"), timeout=35)
        vector = _vector(raw)
        with app.state.sessions() as db:
            analysis = db.scalar(select(Analysis).where(Analysis.id == analysis_id, Analysis.owner_id == owner))
            if not analysis or not _eligible(db, owner, analysis):
                return False
            row = db.scalar(
                select(SearchDocument).where(
                    SearchDocument.analysis_id == analysis_id, SearchDocument.owner_id == owner
                )
            )
            if row is None:
                row = SearchDocument(
                    analysis_id=analysis_id,
                    owner_id=owner,
                    model_revision=MODEL_REVISION,
                    content_hash=digest,
                    embedding=vector,
                )
                db.add(row)
            else:
                row.model_revision, row.content_hash, row.embedding = MODEL_REVISION, digest, vector
            db.commit()
        emit("index", duration_ms=round((perf_counter() - started) * 1000), outcome="success")
        return True
    except Exception:
        emit("index", duration_ms=round((perf_counter() - started) * 1000), outcome="failure")
        return False


@router.post("/index")
async def index_history(request: Request, user: User = Depends(current_user)):
    with request.app.state.sessions() as db:
        items = db.scalars(
            select(Analysis)
            .where(Analysis.owner_id == user.id, Analysis.status == "complete")
            .order_by(Analysis.created_at.desc())
            .limit(MAX_CANDIDATES)
        ).all()
        documents = {
            d.analysis_id: d
            for d in db.scalars(
                select(SearchDocument).where(
                    SearchDocument.owner_id == user.id, SearchDocument.analysis_id.in_([a.id for a in items])
                )
            ).all()
        }
        pending = []
        missing = 0
        for item in items:
            conversation = db.scalar(
                select(Conversation).where(Conversation.id == item.conversation_id, Conversation.owner_id == user.id)
            )
            if conversation and _eligible(db, user.id, item):
                digest = hashlib.sha256(_text(item, conversation).encode()).hexdigest()
                document = documents.get(item.id)
                if not document or document.content_hash != digest or document.model_revision != MODEL_REVISION:
                    missing += 1
                    if len(pending) < 20:
                        pending.append(item.id)
    completed = 0
    if pending and not _provider_available(request.app.state.provider):
        return _error(request, 503, "SEARCH_UNAVAILABLE", "Semantic search provider is unavailable.")
    try:
        async with asyncio.timeout(60):
            for analysis_id in pending:
                completed += await index_analysis(request.app, analysis_id, user.id)
    except TimeoutError:
        pass
    if pending and completed == 0:
        return _error(request, 503, "SEARCH_UNAVAILABLE", "Semantic indexing is temporarily unavailable.")
    return {
        "request_id": request.state.request_id,
        "data": {"indexed": completed, "remaining": max(0, missing - completed)},
    }


@router.post("")
async def search(body: SearchInput, request: Request, user: User = Depends(current_user)):
    started = perf_counter()
    with request.app.state.sessions() as db:
        candidates = db.execute(
            select(SearchDocument, Analysis, Conversation)
            .join(Analysis, SearchDocument.analysis_id == Analysis.id)
            .join(Conversation, Analysis.conversation_id == Conversation.id)
            .where(
                SearchDocument.owner_id == user.id,
                Analysis.owner_id == user.id,
                Conversation.owner_id == user.id,
                Analysis.status == "complete",
                SearchDocument.model_revision == MODEL_REVISION,
            )
            .order_by(Analysis.created_at.desc())
            .limit(MAX_CANDIDATES)
        ).all()
        deadline = perf_counter() + 5
        candidates = [(d, a, c) for d, a, c in candidates if perf_counter() < deadline and _eligible(db, user.id, a)]
    if not candidates:
        with request.app.state.sessions() as db:
            recent = db.scalars(
                select(Analysis)
                .where(Analysis.owner_id == user.id, Analysis.status == "complete")
                .order_by(Analysis.created_at.desc())
                .limit(MAX_CANDIDATES)
            ).all()
            has_history = any(_eligible(db, user.id, item) for item in recent)
        if has_history and not _provider_available(request.app.state.provider):
            emit("search", duration_ms=round((perf_counter() - started) * 1000), outcome="unavailable")
            return _error(request, 503, "SEARCH_UNAVAILABLE", "Semantic search provider is unavailable.")
        emit("search", duration_ms=round((perf_counter() - started) * 1000), outcome="success")
        return {"request_id": request.state.request_id, "data": [], "meta": {"candidates": 0}}
    provider = request.app.state.provider
    if not _provider_available(provider):
        return _error(request, 503, "SEARCH_UNAVAILABLE", "Semantic search provider is unavailable.")
    try:
        async with request.app.state.embedding_capacity:
            query = _vector(
                await asyncio.wait_for(provider.embed(body.query.strip(), task_type="RETRIEVAL_QUERY"), timeout=35)
            )
    except Exception:
        emit("search", duration_ms=round((perf_counter() - started) * 1000), outcome="unavailable")
        return _error(request, 503, "SEARCH_UNAVAILABLE", "Semantic search is temporarily unavailable.")
    query_values = struct.unpack("<768f", query)
    ranked = []
    with request.app.state.sessions() as db:
        deadline = perf_counter() + 5
        for document, analysis, conversation in candidates:
            if perf_counter() >= deadline:
                break
            current = db.scalar(
                select(Analysis).where(
                    Analysis.id == analysis.id, Analysis.owner_id == user.id, Analysis.status == "complete"
                )
            )
            if not current or not _eligible(db, user.id, current) or len(document.embedding) != 3072:
                continue
            values = struct.unpack("<768f", document.embedding)
            score = sum(a * b for a, b in zip(query_values, values, strict=True))
            if not math.isfinite(score) or score < MIN_SIMILARITY:
                continue
            ranked.append(
                {
                    "analysis_id": str(analysis.id),
                    "conversation_id": str(conversation.id),
                    "title": conversation_title(db, conversation),
                    "question": analysis.question,
                    "summary": json.loads(analysis.result_json).get("answer", "")[:300],
                    "score": round(max(-1, min(1, score)), 4),
                    "href": f"/analyze?conversation={conversation.id}&analysis={analysis.id}",
                }
            )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    emit("search", duration_ms=round((perf_counter() - started) * 1000), outcome="success")
    return {
        "request_id": request.state.request_id,
        "data": ranked[: body.limit],
        "meta": {"candidates": len(candidates)},
    }
