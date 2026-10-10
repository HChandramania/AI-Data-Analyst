import hashlib
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from app.config import Settings
from app.database import create_database_engine
from app.main import create_app
from app.models import Session, User


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DBO_DATA_DIR", str(tmp_path / "data"))
    return Settings(_env_file=None)


def migrate():
    command.upgrade(Config("alembic.ini"), "head")


def test_live_without_dependencies_and_no_implicit_migrations(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/live").json()["data"]["status"] == "alive"
        assert client.get("/api/v1/health/ready").status_code == 503
    assert not settings.database_path.exists()


def test_explicit_migration_readiness_restart_and_schema_drift(settings):
    migrate()
    migrate()  # Setup is idempotent.
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users DROP COLUMN password_hash"))
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/ready").status_code == 503


def test_unwritable_directory_and_database_failure(settings):
    migrate()
    with TestClient(create_app(settings)) as client:
        with patch("app.main.tempfile.TemporaryFile", side_effect=PermissionError("private path")):
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 503
            assert "private path" not in response.text
        with client.app.state.engine.begin() as connection:
            connection.execute(text("DROP TABLE alembic_version"))
        assert client.get("/api/v1/health/ready").status_code == 503
        assert client.get("/api/v1/health/live").status_code == 200


@pytest.mark.parametrize(
    "values",
    [
        {"environment": "invalid"},
        {"data_dir": " "},
        {"sqlite_busy_timeout_ms": 0},
        {"sqlite_busy_timeout_ms": "invalid"},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_request_ids_errors_and_private_log_content(settings, caplog):
    app = create_app(settings)

    @app.get("/test/failure")
    def failure():
        raise RuntimeError("private-secret")

    @app.get("/test/validation")
    def validation(count: int):
        return count

    caplog.set_level(logging.INFO, logger="dbo.requests")
    with TestClient(app) as client:
        responses = [
            client.get(
                "/private-secret?token=private-secret",
                headers={"Cookie": "private-secret", "X-Request-ID": "private-secret"},
            ),
            client.get("/test/failure"),
            client.get("/test/validation?count=private-secret"),
            client.post("/api/v1/health/live", content="private-secret"),
        ]
    assert [r.status_code for r in responses] == [404, 500, 422, 403]
    assert len({r.headers["X-Request-ID"] for r in responses}) == 4
    for response in responses:
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
        assert response.json()["error"]["details"] == {}
        assert "private-secret" not in response.text
    assert "private-secret" not in " ".join(
        record.message for record in caplog.records if record.name == "dbo.requests"
    )


def test_identity_constraints_and_persistence(settings):
    migrate()
    engine = create_database_engine(settings)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    with DatabaseSession(engine) as session:
        user = User(email="synthetic@example.invalid", password_hash="future-argon2-hash")
        session.add(user)
        session.commit()
        user_id = user.id
        session.add(
            Session(
                user_id=user_id,
                token_digest=hashlib.sha256(b"test-only-token").hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
        session.commit()
        session.add(Session(user_id=uuid4(), token_digest="a" * 64, expires_at=datetime.now(UTC)))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(Session(user_id=user_id, token_digest="plaintext-token", expires_at=datetime.now(UTC)))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    engine.dispose()
    engine = create_database_engine(settings)
    with DatabaseSession(engine) as session:
        user = session.get(User, user_id)
        assert user is not None
        session.delete(user)
        session.commit()
        assert session.query(Session).count() == 0
    assert "token" not in {c["name"] for c in inspect(engine).get_columns("sessions")}
    engine.dispose()
