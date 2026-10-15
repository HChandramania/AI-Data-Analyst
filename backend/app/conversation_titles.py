"""Deterministic conversation labels without an extra provider call."""

from sqlalchemy import select

from app.models import Message


def query_title(question: str) -> str:
    text = " ".join(question.split())
    return text if len(text) <= 80 else text[:77].rstrip() + "..."


def conversation_title(db, conversation) -> str:
    if conversation.title != "New analysis":
        return conversation.title
    question = db.scalar(
        select(Message.content)
        .where(Message.conversation_id == conversation.id, Message.role == "user")
        .order_by(Message.created_at, Message.id)
        .limit(1)
    )
    return query_title(question) if question else conversation.title
