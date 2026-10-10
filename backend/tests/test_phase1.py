from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import Settings
from app.main import create_app
from app.models import Session


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DBO_DATA_DIR", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(_env_file=None, allow_insecure_cookies=True)
    with TestClient(create_app(settings)) as client:
        yield client, settings


def secure_headers(client):
    token = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    return {"Origin": "http://localhost:3000", "X-CSRF-Token": token}


def register(client, email):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "strong-password"},
        headers=secure_headers(client),
    )


def test_auth_lifecycle_csrf_origin_and_cookie(client):
    client, _ = client
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/register", json={}).status_code == 403
    headers = secure_headers(client)
    assert (
        client.post("/api/v1/auth/register", json={}, headers={**headers, "Origin": "https://evil.test"}).status_code
        == 403
    )
    response = register(client, "A@EXAMPLE.TEST")
    assert response.status_code == 201
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/me").json()["data"]["email"] == "a@example.test"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "a@example.test", "password": "wrong-pass"},
            headers=secure_headers(client),
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "a@example.test", "password": "strong-password"},
            headers=secure_headers(client),
        ).status_code
        == 200
    )


def test_upload_profile_ownership_and_delete(client):
    client, settings = client
    register(client, "first@example.test")
    headers = secure_headers(client)
    response = client.post(
        "/api/v1/datasets",
        headers=headers,
        files=[
            (
                "files",
                (
                    "good.csv",
                    b"code,date,value\n001,01/02/2026,\n001,01/02/2026,\n002,03/04/2026,7\n",
                    "text/csv",
                ),
            ),
            ("files", ("bad.csv", b"a,a\n1,2\n", "text/csv")),
        ],
    )
    assert response.status_code == 200, response.text
    accepted, rejected = response.json()["data"]
    assert accepted["status"] == "accepted"
    assert rejected["status"] == "rejected"
    dataset = accepted["dataset"]
    assert dataset["profile"]["row_count"] == 3
    assert dataset["profile"]["duplicate_row_count"] == 1
    assert dataset["profile"]["columns"][0]["type"] == "text"
    assert dataset["profile"]["columns"][2]["missing_count"] == 2
    dataset_id = dataset["id"]
    preview = client.get(f"/api/v1/datasets/{dataset_id}/preview").json()["data"]
    assert preview["rows"][0]["c1"] == "001"
    snapshot = settings.data_dir / "datasets" / dataset_id / "snapshot.parquet"
    assert snapshot.exists() and pq.read_table(snapshot).num_rows == 3
    client.post("/api/v1/auth/logout", headers=headers)
    assert client.get("/api/v1/datasets").status_code == 401
    register(client, "second@example.test")
    assert client.get("/api/v1/datasets").json()["data"] == []
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 404
    assert client.get(f"/api/v1/datasets/{dataset_id}/preview").status_code == 404
    assert client.delete(f"/api/v1/datasets/{dataset_id}", headers=secure_headers(client)).status_code == 404
    client.post("/api/v1/auth/logout", headers=secure_headers(client))
    client.post(
        "/api/v1/auth/login",
        json={"email": "first@example.test", "password": "strong-password"},
        headers=secure_headers(client),
    )
    assert client.delete(f"/api/v1/datasets/{dataset_id}", headers=secure_headers(client)).status_code == 200
    assert not Path(snapshot).exists()


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"a,b\n",
        b"a,a\n1,2\n",
        b",b\n1,2\n",
        b"a,b\n1\n",
        b"a,b\n1,2,3\n",
        b"a\n\xff\n",
        b'a,b\n"x,2\n',
    ],
)
def test_invalid_csv_files_are_rejected(client, raw):
    client, _ = client
    register(client, "test@example.test")
    result = client.post(
        "/api/v1/datasets",
        headers=secure_headers(client),
        files=[("files", ("bad.csv", raw, "text/csv"))],
    )
    assert result.status_code == 200
    assert result.json()["data"][0]["status"] == "rejected"
    assert client.get("/api/v1/datasets").json()["data"] == []


def test_expiry_secure_cookie_and_login_throttle(client):
    client, settings = client
    register(client, "expiry@example.test")
    with DbSession(client.app.state.engine) as db:
        session = db.scalar(select(Session).order_by(Session.expires_at.desc()))
        session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.clear()
    headers = secure_headers(client)
    statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": "none@example.test", "password": "wrong-pass"}, headers=headers
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10 and statuses[10] == 429
    from app.auth import attempts

    attempts.clear()
    secure_settings = Settings(_env_file=None, data_dir=settings.data_dir, allow_insecure_cookies=False)
    with TestClient(create_app(secure_settings), base_url="https://testserver") as secure_client:
        response = register(secure_client, "secure@example.test")
        assert "secure" in response.headers["set-cookie"].lower()


def test_upload_limits_and_recovery(client):
    client, settings = client
    register(client, "limits@example.test")
    invalid = [
        b"a\n" + b"1\n" * 100001,
        (",".join(f"c{i}" for i in range(51)) + "\n" + ",".join("x" for _ in range(51)) + "\n").encode(),
        b"a\n" + b"x" * (10 * 1024 * 1024) + b"\n",
    ]
    for raw in invalid:
        result = client.post(
            "/api/v1/datasets", headers=secure_headers(client), files=[("files", ("bad.csv", raw, "text/csv"))]
        )
        assert result.status_code == 200, result.text
        assert result.json()["data"][0]["status"] == "rejected"
    good = client.post(
        "/api/v1/datasets",
        headers=secure_headers(client),
        files=[("files", ("good.csv", b"id,value\n001,1.25\n002,2.50\n", "text/csv"))],
    )
    assert good.json()["data"][0]["status"] == "accepted"
    assert good.json()["data"][0]["dataset"]["profile"]["columns"][1]["type"] == "decimal"
    assert not list((settings.data_dir / "datasets").glob("tmp*"))
