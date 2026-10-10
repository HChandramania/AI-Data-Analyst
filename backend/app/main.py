import asyncio
import json
import logging
import secrets
import tempfile
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from app.auth import router as auth_router
from app.config import Settings
from app.database import create_database_engine
from app.datasets import router as datasets_router
from app.models import Base

logger = logging.getLogger("dbo.requests")
SCHEMA_REVISION = "0002"


class HealthData(BaseModel):
    status: Literal["alive", "ready"]
    phase: Literal[1] = 1


class HealthResponse(BaseModel):
    request_id: str
    data: HealthData


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, str]


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail


def error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            request_id=request.state.request_id,
            error=ErrorDetail(code=code, message=message, details={}),
        ).model_dump(),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_database_engine(settings)
        app.state.engine = engine
        app.state.sessions = sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Digital Back Office", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    intake_capacity = asyncio.Semaphore(2)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        # Generate locally: incoming IDs can contain private data or log injection.
        request.state.request_id = str(uuid4())
        started = perf_counter()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("origin") != settings.public_origin:
                response = error(request, 403, "ORIGIN_REJECTED", "Request origin rejected.")
                response.headers["X-Request-ID"] = request.state.request_id
                return response
            header = request.headers.get("x-csrf-token", "")
            cookie = request.cookies.get("dbo_csrf", "")
            if not cookie or not secrets.compare_digest(header, cookie):
                response = error(request, 403, "CSRF_REJECTED", "Request token rejected.")
                response.headers["X-Request-ID"] = request.state.request_id
                return response
        limit = 32 * 1024 * 1024
        if request.url.path == "/api/v1/datasets" and request.method == "POST":
            try:
                await asyncio.wait_for(intake_capacity.acquire(), timeout=0.1)
            except TimeoutError:
                response = error(request, 429, "INTAKE_BUSY", "Upload capacity reached.")
                response.headers["X-Request-ID"] = request.state.request_id
                return response
        else:
            limit = 1024 * 1024
        received = 0
        original_receive = request._receive

        async def bounded_receive():
            nonlocal received
            message = await original_receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise ValueError("Request body too large")
            return message

        request._receive = bounded_receive
        try:
            if request.url.path == "/api/v1/datasets" and request.method == "POST":
                response = await asyncio.wait_for(call_next(request), timeout=60)
            else:
                response = await call_next(request)
        except TimeoutError:
            response = error(request, 504, "INTAKE_TIMEOUT", "Upload timed out.")
        except ValueError:
            response = error(request, 413, "REQUEST_TOO_LARGE", "Request exceeds size limit.")
        except Exception:
            response = error(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
        finally:
            if request.url.path == "/api/v1/datasets" and request.method == "POST":
                intake_capacity.release()
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "request_id": request.state.request_id,
                    "route": getattr(route, "path", "unmatched"),
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error(
            request,
            exc.status_code,
            f"HTTP_{exc.status_code}",
            "Resource not found." if exc.status_code == 404 else "Request rejected.",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        return error(request, 422, "INVALID_INPUT", "Request input is invalid.")

    @app.get("/api/v1/health/live", response_model=HealthResponse)
    def live(request: Request):
        return HealthResponse(request_id=request.state.request_id, data=HealthData(status="alive"))

    @app.get(
        "/api/v1/health/ready",
        response_model=HealthResponse,
        responses={503: {"model": ErrorResponse}},
    )
    def ready(request: Request):
        try:
            with tempfile.TemporaryFile(dir=settings.data_dir) as probe:
                probe.write(b"ready")
                probe.flush()
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                inspector = inspect(connection)
                for table in Base.metadata.sorted_tables:
                    columns = {column["name"] for column in inspector.get_columns(table.name)}
                    if not set(table.columns.keys()).issubset(columns):
                        raise ValueError("Schema incomplete")
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if revision != SCHEMA_REVISION:
                    raise ValueError("Migration required")
        except (OSError, SQLAlchemyError, ValueError):
            return error(
                request,
                503,
                "DEPENDENCY_UNAVAILABLE",
                "Storage is not ready. Check directory permissions and run migrations.",
            )
        return HealthResponse(request_id=request.state.request_id, data=HealthData(status="ready"))

    app.include_router(auth_router)
    app.include_router(datasets_router)
    return app
