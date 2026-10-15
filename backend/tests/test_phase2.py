import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings
from app.executor import QueryBusy, QueryFailure, QueryTimeout, execute
from app.main import create_app
from app.models import Dataset
from app.planner import AnalysisPlan, GeminiProvider, ProviderFailure, ProviderTimeout
from app.sql_policy import SqlRejected, validate_sql


class KnownFixtureProvider:
    async def plan(self, question: str, datasets: list[dict]) -> AnalysisPlan:
        item = datasets[0]
        table = item["table"]
        if "region" in question:
            sql = (
                f"SELECT c5 AS region, SUM(c8) AS revenue_usd FROM {table} "
                "GROUP BY c5 ORDER BY revenue_usd DESC LIMIT 1"
            )
        elif "month" in question:
            sql = (
                f"SELECT DATE_TRUNC('month', CAST(c2 AS DATE)) AS month, "
                f"SUM(c8) AS revenue_usd FROM {table} GROUP BY month ORDER BY month"
            )
        elif "customer" in question:
            sql = (
                f"SELECT c3 AS customer_id, SUM(c8) AS revenue_usd FROM {table} "
                "GROUP BY c3 ORDER BY revenue_usd DESC, customer_id ASC LIMIT 5"
            )
        else:
            return AnalysisPlan(action="clarify", dataset_ids=[], question="Which measure should I use?")
        return AnalysisPlan(action="query", dataset_ids=[UUID(item["id"])], sql=sql)


@pytest.fixture
def phase2_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DBO_DATA_DIR", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    app = create_app(Settings(_env_file=None, allow_insecure_cookies=True), KnownFixtureProvider())
    with TestClient(app) as client:
        yield client


def headers(client):
    token = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    return {"Origin": "http://localhost:3000", "X-CSRF-Token": token}


def setup(client):
    client.post(
        "/api/v1/auth/register",
        headers=headers(client),
        json={"email": "phase2@example.test", "password": "strong-password"},
    )
    fixture = Path(__file__).resolve().parents[2] / "sample_data" / "analysis_flat.csv"
    upload = client.post(
        "/api/v1/datasets",
        headers=headers(client),
        files=[("files", ("analysis_flat.csv", fixture.read_bytes(), "text/csv"))],
    )
    dataset = upload.json()["data"][0]["dataset"]
    conversation = client.post(
        "/api/v1/conversations", headers=headers(client), json={"dataset_ids": [dataset["id"]]}
    ).json()["data"]
    return dataset, conversation


def test_known_answers_persistence_and_deletion(phase2_client):
    client = phase2_client
    dataset, conversation = setup(client)
    route = f"/api/v1/conversations/{conversation['id']}/messages"
    region = client.post(route, headers=headers(client), json={"question": "Highest revenue region?"})
    assert region.status_code == 200, region.text
    assert region.json()["data"]["table"]["rows"][0] == {"region": "South", "revenue_usd": "1800.00"}
    month = client.post(route, headers=headers(client), json={"question": "Revenue by month?"})
    assert month.status_code == 200, month.text
    assert [row["revenue_usd"] for row in month.json()["data"]["table"]["rows"]] == ["360.00", "1000.00", "2400.00"]
    top = client.post(route, headers=headers(client), json={"question": "Top customers?"})
    assert top.status_code == 200, top.text
    assert [row["customer_id"] for row in top.json()["data"]["table"]["rows"]] == ["C06", "C05", "C04", "C03", "C02"]
    saved = client.get(f"/api/v1/conversations/{conversation['id']}").json()["data"]
    assert len(saved["messages"]) == 6 and len(saved["analyses"]) == 3
    assert client.get(f"/api/v1/analyses/{region.json()['data']['id']}").status_code == 200
    assert client.delete(f"/api/v1/datasets/{dataset['id']}", headers=headers(client)).status_code == 200
    assert client.get(f"/api/v1/conversations/{conversation['id']}").status_code == 404
    assert client.get(f"/api/v1/analyses/{region.json()['data']['id']}").status_code == 404


def test_conversation_titles_follow_first_question_and_support_legacy_history(phase2_client):
    from app.models import Conversation

    client = phase2_client
    _, conversation = setup(client)
    route = f"/api/v1/conversations/{conversation['id']}"
    assert conversation["title"] == "New analysis"
    for question in ("Highest revenue region?", "Revenue by month?"):
        response = client.post(route + "/messages", headers=headers(client), json={"question": question})
        assert response.status_code == 200, response.text
        assert client.get(route).json()["data"]["conversation"]["title"] == "Highest revenue region?"
    with client.app.state.sessions() as db:
        record = db.get(Conversation, UUID(conversation["id"]))
        assert record.title == "Highest revenue region?"
        record.title = "New analysis"
        db.commit()
    assert client.get(route).json()["data"]["conversation"]["title"] == "Highest revenue region?"
    assert client.get("/api/v1/conversations").json()["data"][0]["title"] == "Highest revenue region?"


def test_query_titles_normalize_whitespace_and_limit_length():
    from app.conversation_titles import query_title

    assert query_title("  Revenue\n by   region? ") == "Revenue by region?"
    title = query_title("Monthly revenue " * 20)
    assert len(title) <= 80 and title.endswith("...")


def test_month_query_allows_safe_duckdb_date_formatting():
    registry = {"dataset_fixture": {"c2", "c8"}}
    sql = (
        "SELECT strftime(date_trunc('month', try_cast(c2 AS DATE)), '%Y-%m') AS month, "
        "SUM(c8) AS total_revenue_usd FROM dataset_fixture GROUP BY month ORDER BY month"
    )
    assert validate_sql(sql, registry).lower() == sql.lower()


def test_clarification_and_owner_isolation(phase2_client):
    client = phase2_client
    _, conversation = setup(client)
    route = f"/api/v1/conversations/{conversation['id']}/messages"
    response = client.post(route, headers=headers(client), json={"question": "Help with an ambiguous metric"})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "clarification"
    assert response.json()["data"]["sql"] is None
    client.post("/api/v1/auth/logout", headers=headers(client))
    assert client.get(f"/api/v1/conversations/{conversation['id']}").status_code == 401
    client.post(
        "/api/v1/auth/register",
        headers=headers(client),
        json={"email": "other@example.test", "password": "strong-password"},
    )
    assert client.get(f"/api/v1/conversations/{conversation['id']}").status_code == 404
    assert client.post(route, headers=headers(client), json={"question": "Top customers?"}).status_code == 404


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM secret_table",
        "SELECT fake FROM dataset_abc",
        "SELECT c1 FROM dataset_abc; DROP TABLE dataset_abc",
        "WITH x AS (DELETE FROM dataset_abc RETURNING c1) SELECT * FROM x",
        "SELECT current_setting('secret') AS value FROM dataset_abc",
        "SELECT c1 FROM dataset_abc JOIN dataset_abc b ON c1=b.c1",
        "SELECT * FROM (SELECT * FROM secret_table) AS x",
        "SELECT * FROM dataset_abc WHERE c1 IN (SELECT c1 FROM secret_table)",
    ],
)
def test_sql_boundary_rejects_forbidden(sql):
    with pytest.raises(SqlRejected):
        validate_sql(sql, {"dataset_abc": {"c1", "c2"}})


def test_safe_cte_and_capacity():
    assert validate_sql("WITH x AS (SELECT c1 FROM dataset_abc) SELECT c1 FROM x", {"dataset_abc": {"c1"}})

    async def run():
        capacity = asyncio.Semaphore(0)
        with pytest.raises(QueryBusy):
            await execute("SELECT c1 FROM dataset_abc", [], 1, capacity)

    asyncio.run(run())


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_code"),
    [
        (ProviderFailure("down"), 502, "PROVIDER_FAILED"),
        (ProviderTimeout("slow"), 504, "PROVIDER_TIMEOUT"),
    ],
)
def test_provider_failures_are_saved_safely(phase2_client, failure, expected_status, expected_code):
    client = phase2_client
    _, conversation = setup(client)

    class FailingProvider:
        async def plan(self, question, datasets):
            raise failure

    client.app.state.provider = FailingProvider()
    route = f"/api/v1/conversations/{conversation['id']}/messages"
    response = client.post(route, headers=headers(client), json={"question": "Total revenue?"})
    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    saved = client.get(f"/api/v1/conversations/{conversation['id']}").json()["data"]
    assert saved["analyses"][0]["status"] == "failed"
    assert saved["analyses"][0]["table"] is None


def test_missing_credentials_and_malformed_provider_output(phase2_client):
    client = phase2_client
    _, conversation = setup(client)
    route = f"/api/v1/conversations/{conversation['id']}/messages"
    client.app.state.provider = GeminiProvider(Settings(_env_file=None, gemini_api_key=None))
    missing = client.post(route, headers=headers(client), json={"question": "Total revenue?"})
    assert missing.status_code == 503
    assert missing.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"

    class MalformedProvider:
        async def plan(self, question, datasets):
            return {"action": "query", "dataset_ids": []}

    client.app.state.provider = MalformedProvider()
    invalid = client.post(route, headers=headers(client), json={"question": "Total revenue?"})
    assert invalid.status_code == 502
    assert invalid.json()["error"]["code"] == "PROVIDER_INVALID"


def test_query_timeout_releases_capacity_and_child():
    async def run():
        capacity = asyncio.Semaphore(1)
        with pytest.raises(QueryTimeout):
            await execute("SELECT SUM(i) FROM range(1000000000) AS t(i)", [], 1, capacity)
        with pytest.raises(QueryFailure, match="safely"):
            await execute("SELECT missing FROM dataset_abc", [], 3, capacity)

    asyncio.run(run())


def test_result_row_and_byte_limits(tmp_path):
    table_name = f"dataset_{uuid4().hex}"
    path = tmp_path / "bounded.parquet"
    pq.write_table(pa.table({"c1": list(range(600)), "c2": ["x" * 3000] * 600}), path)

    async def run():
        capacity = asyncio.Semaphore(1)
        source = [(table_name, str(path))]
        small = await execute(f"SELECT c1 FROM {table_name} ORDER BY c1", source, 5, capacity)
        assert small["returned_rows"] == 500
        assert small["truncated"] is True
        assert small["rows"][0]["c1"] == 0
        with pytest.raises(QueryFailure, match="1 MiB"):
            await execute(f"SELECT c2 FROM {table_name}", source, 5, capacity)

    asyncio.run(run())


def test_source_removed_during_execution_does_not_expose_result(phase2_client, monkeypatch):
    client = phase2_client
    dataset, conversation = setup(client)

    async def remove_source(sql, sources, timeout, capacity):
        with client.app.state.sessions() as db:
            db.delete(db.get(Dataset, UUID(dataset["id"])))
            db.commit()
        return {
            "columns": ["revenue_usd"],
            "rows": [{"revenue_usd": "3760.00"}],
            "returned_rows": 1,
            "truncated": False,
        }

    monkeypatch.setattr("app.analysis.execute", remove_source)
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers(client),
        json={"question": "Highest revenue region?"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SOURCE_DELETED"
    assert "3760" not in response.text
