"""Cookie sessions and request forgery controls."""

import hashlib
import secrets
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from time import monotonic

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.database import get_session
from app.models import Session, User

router = APIRouter(prefix="/api/v1/auth")
hasher = PasswordHasher()
attempts: dict[str, deque[float]] = defaultdict(deque)
SESSION_SECONDS = 86400


class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if len(value) > 320 or "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Invalid email")
        return value


def csrf_cookie(request: Request, response: Response) -> str:
    token = request.cookies.get("dbo_csrf")
    if not token or len(token) != 43:
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            "dbo_csrf",
            token,
            max_age=SESSION_SECONDS,
            samesite="lax",
            secure=not request.app.state.settings.allow_insecure_cookies,
            httponly=False,
            path="/",
        )
    return token


@router.get("/csrf")
def csrf(request: Request, response: Response):
    return {
        "request_id": request.state.request_id,
        "data": {"csrf_token": csrf_cookie(request, response)},
    }


def current_user(request: Request, db: DbSession = Depends(get_session)) -> User:
    token = request.cookies.get("dbo_session")
    if not token:
        raise HTTPException(401)
    digest = hashlib.sha256(token.encode()).hexdigest()
    session = db.scalar(select(Session).where(Session.token_digest == digest))
    if not session or session.revoked_at or session.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
        raise HTTPException(401)
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401)
    return user


def issue_session(request: Request, response: Response, db: DbSession, user: User):
    token = secrets.token_urlsafe(32)
    db.add(
        Session(
            user_id=user.id,
            token_digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_SECONDS),
        )
    )
    db.commit()
    response.set_cookie(
        "dbo_session",
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=not request.app.state.settings.allow_insecure_cookies,
        path="/",
    )
    return {
        "request_id": request.state.request_id,
        "data": {"id": str(user.id), "email": user.email},
    }


@router.post("/register", status_code=201)
def register(
    credentials: Credentials,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_session),
):
    user = User(email=credentials.email.strip().lower(), password_hash=hasher.hash(credentials.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409) from None
    return issue_session(request, response, db, user)


@router.post("/login")
def login(
    credentials: Credentials,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_session),
):
    key = request.client.host if request.client else "unknown"
    now = monotonic()
    if len(attempts) > 1024:
        for address in list(attempts):
            if not attempts[address] or attempts[address][-1] < now - 300:
                del attempts[address]
        if len(attempts) > 1024 and key not in attempts:
            raise HTTPException(429)
    recent = attempts[key]
    while recent and recent[0] < now - 300:
        recent.popleft()
    if len(recent) >= 10:
        raise HTTPException(429)
    recent.append(now)
    user = db.scalar(select(User).where(User.email == credentials.email.strip().lower()))
    try:
        valid = bool(user and hasher.verify(user.password_hash, credentials.password))
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(401)
    recent.clear()
    return issue_session(request, response, db, user)


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)):
    return {
        "request_id": request.state.request_id,
        "data": {"id": str(user.id), "email": user.email},
    }


@router.post("/logout")
def logout(request: Request, response: Response, db: DbSession = Depends(get_session)):
    token = request.cookies.get("dbo_session")
    if token:
        session = db.scalar(select(Session).where(Session.token_digest == hashlib.sha256(token.encode()).hexdigest()))
        if session:
            session.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie("dbo_session", path="/")
    response.delete_cookie("dbo_csrf", path="/")
    return {"request_id": request.state.request_id, "data": {"signed_out": True}}
