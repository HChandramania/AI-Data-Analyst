"""Phase 5 behavior through authenticated API paths and deterministic provider doubles."""

import json
import logging
import math
from uuid import UUID, uuid4

import pytest
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture

from app.execution_cache import ExecutionCache, cache_key
from app.models import Analysis, Dataset, SearchDocument
from app.observability import SafeJsonFormatter
from app.planner import AnalysisPlan, ProviderFailure

phase2_client = client_fixture


class SemanticProvider:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def plan(self, question, datasets):
        self.calls += 1
        source = datasets[0]
        return AnalysisPlan(
            action="query",
            dataset_ids=[source["id"]],
            sql=f"SELECT c5 AS region, SUM(c8) AS revenue_usd FROM {source['table']} GROUP BY c5 ORDER BY c5",
        )

    async def embed(self, content, *, task_type):
        if self.fail:
            raise ProviderFailure("secret key: never expose")
        vector = [0.0] * 768
        vector[0 if any(w in content.lower() for w in ("region", "territory", "geography")) else 1] = 1.0
        return vector


def ask(client, conversation, question="Revenue by territory?"):
    return client.post(
        f"/api/v1/conversations/{conversation['id']}/messages", headers=headers(client), json={"question": question}
    )


def search(client, query="Regional performance", limit=5):
    return client.post("/api/v1/search", headers=headers(client), json={"query": query, "limit": limit})


def test_search_retrieves_reopens_and_excludes_deleted_and_other_owner(phase2_client):
    client = phase2_client
    dataset, conversation = setup(client)
    provider = SemanticProvider()
    client.app.state.provider = provider
    saved = ask(client, conversation)
    assert saved.status_code == 200, saved.text
    analysis = saved.json()["data"]
    result = search(client)
    assert result.status_code == 200
    assert result.json()["data"][0]["analysis_id"] == analysis["id"]
    assert result.json()["data"][0]["href"].startswith("/analyze?conversation=")
    assert client.get(f"/api/v1/conversations/{conversation['id']}").status_code == 200
    assert search(client, limit=11).status_code == 422
    client.post("/api/v1/auth/logout", headers=headers(client))
    assert search(client).status_code == 401
    client.post(
        "/api/v1/auth/register",
        headers=headers(client),
        json={"email": "second-phase5@example.test", "password": "strong-password"},
    )
    assert search(client).json()["data"] == []
    assert client.get(f"/api/v1/analyses/{analysis['id']}").status_code == 404
    client.post("/api/v1/auth/logout", headers=headers(client))
    client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "phase2@example.test", "password": "strong-password"},
    )
    assert client.delete(f"/api/v1/datasets/{dataset['id']}", headers=headers(client)).status_code == 200
    assert search(client).json()["data"] == []


@pytest.mark.parametrize("similarity,expected", [(0.54, 0), (0.5999, 0), (0.6001, 1), (0.71, 1)])
def test_search_relevance_floor_filters_before_returning_results(phase2_client, similarity, expected):
    client = phase2_client
    _, conversation = setup(client)

    class Provider(SemanticProvider):
        async def embed(self, content, *, task_type):
            vector = [0.0] * 768
            if task_type == "RETRIEVAL_DOCUMENT":
                vector[0] = 1.0
            else:
                vector[0], vector[1] = similarity, math.sqrt(1 - similarity**2)
            return vector

    client.app.state.provider = Provider()
    saved = ask(client, conversation).json()["data"]
    response = search(client, "Employee vacation balances and leave approvals")
    assert response.status_code == 200
    assert response.json()["meta"]["candidates"] == 1
    assert len(response.json()["data"]) == expected
    assert client.get(f"/api/v1/analyses/{saved['id']}").status_code == 200


def test_individual_analysis_deletion_removes_search_and_invalidates_dashboard_export(phase2_client):
    client = phase2_client
    dataset, conversation = setup(client)
    client.app.state.provider = SemanticProvider()
    first = ask(client, conversation).json()["data"]
    second = ask(client, conversation, "Regional totals?").json()["data"]
    dashboard = client.post(
        "/api/v1/dashboards",
        headers=headers(client),
        json={
            "title": "Saved results",
            "conversation_id": conversation["id"],
            "analysis_ids": [first["id"], second["id"]],
            "generate": False,
        },
    ).json()["data"]
    route = f"/api/v1/analyses/{first['id']}"
    assert client.delete(route).status_code == 403  # CSRF remains required.
    client.post("/api/v1/auth/logout", headers=headers(client))
    assert client.delete(route, headers=headers(client)).status_code == 401
    client.post(
        "/api/v1/auth/register",
        headers=headers(client),
        json={"email": "delete-other@example.test", "password": "strong-password"},
    )
    assert client.delete(route, headers=headers(client)).status_code == 404
    client.post("/api/v1/auth/logout", headers=headers(client))
    client.post(
        "/api/v1/auth/login",
        headers=headers(client),
        json={"email": "phase2@example.test", "password": "strong-password"},
    )
    assert client.delete(route, headers=headers(client)).status_code == 200
    assert client.delete(route, headers=headers(client)).status_code == 404
    assert client.get(route).status_code == 404
    assert client.post(route + "/rerun", headers=headers(client)).status_code == 404
    assert [item["analysis_id"] for item in search(client).json()["data"]] == [second["id"]]
    with client.app.state.sessions() as db:
        assert db.get(SearchDocument, UUID(first["id"])) is None
    assert client.post("/api/v1/search/index", headers=headers(client)).json()["data"]["indexed"] == 0
    saved = client.get(f"/api/v1/dashboards/{dashboard['id']}").json()["data"]
    assert saved["status"] == "partial" and saved["complete_cards"] == 1
    assert saved["cards"][0]["status"] == "unavailable" and "evidence" not in saved["cards"][0]
    for selection, status in (
        ({"analysis_ids": [first["id"]]}, 404),
        ({"dashboard_ids": [dashboard["id"]]}, 409),
        ({"analysis_ids": [second["id"]]}, 200),
    ):
        assert client.post("/api/v1/reports/export", headers=headers(client), json=selection).status_code == status
    assert client.get(f"/api/v1/datasets/{dataset['id']}").status_code == 200
    detail = client.get(f"/api/v1/conversations/{conversation['id']}").json()["data"]
    assert [a["id"] for a in detail["analyses"]] == [second["id"]]
    assert len(detail["messages"]) == 4  # Saved-artifact deletion preserves conversation text.


def test_search_failure_does_not_corrupt_saved_analysis(phase2_client):
    client = phase2_client
    _, conversation = setup(client)
    provider = SemanticProvider()
    provider.fail = True
    client.app.state.provider = provider
    saved = ask(client, conversation)
    assert saved.status_code == 200
    assert saved.json()["data"]["status"] == "complete"
    assert search(client).json()["data"] == []
    assert client.post("/api/v1/search/index", headers=headers(client)).status_code == 503
    provider.fail = False
    indexed = client.post("/api/v1/search/index", headers=headers(client))
    assert indexed.json()["data"]["indexed"] == 1
    provider.fail = True
    unavailable = search(client)
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "SEARCH_UNAVAILABLE"
    assert client.get(f"/api/v1/analyses/{saved.json()['data']['id']}").status_code == 200


def test_query_cache_hit_rerun_and_source_change(phase2_client):
    client = phase2_client
    dataset, conversation = setup(client)
    provider = SemanticProvider()
    client.app.state.provider = provider
    first = ask(client, conversation).json()["data"]
    second = ask(client, conversation, "Regional totals?").json()["data"]
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert first["table"] == second["table"]
    calls = provider.calls
    replay = client.post(f"/api/v1/analyses/{first['id']}/rerun", headers=headers(client)).json()["data"]
    assert replay["cache_hit"] is True and provider.calls == calls
    assert replay["sql"] == first["sql"] and replay["table"] == first["table"]
    with client.app.state.sessions() as db:
        source = db.get(Dataset, __import__("uuid").UUID(dataset["id"]))
        source.version += 1
        db.commit()
    assert client.post(f"/api/v1/analyses/{first['id']}/rerun", headers=headers(client)).status_code == 409
    assert ask(client, conversation).status_code == 409
    assert client.delete(f"/api/v1/datasets/{dataset['id']}", headers=headers(client)).status_code == 200
    assert len(client.app.state.execution_cache.entries) == 0


def test_cache_key_dependency_and_expiry(tmp_path):
    class Source:
        id = uuid4()
        version = 1
        content_hash = "a" * 64

    source = Source()
    path = tmp_path / "snapshot.parquet"
    path.write_bytes(b"a")
    sql = f"SELECT SUM(c8) FROM dataset_{source.id.hex}"
    sources = [(f"dataset_{source.id.hex}", str(path))]
    a = cache_key("owner-1", [source], sql, sources)
    assert a != cache_key("owner-2", [source], sql, sources)
    source.version = 2
    assert a != cache_key("owner-1", [source], sql, sources)
    source.version = 1
    path.write_bytes(b"changed snapshot")
    assert a != cache_key("owner-1", [source], sql, sources)
    clock = [0]
    cache = ExecutionCache(ttl=2, clock=lambda: clock[0])
    table = {"columns": [], "rows": [], "returned_rows": 0, "truncated": False}
    cache.put(a, table, "owner-1", [source])
    assert cache.get(a)[0] == table
    clock[0] = 3
    assert cache.get(a) == (None, "expired")
    table["truncated"] = True
    cache.put(a, table, "owner-1", [source])
    assert cache.get(a)[0] is None

    class SecondSource:
        id = uuid4()
        version = 1
        content_hash = "b" * 64

    second = SecondSource()
    second_path = tmp_path / "second.parquet"
    second_path.write_bytes(b"second")
    joined = sources + [(f"dataset_{second.id.hex}", str(second_path))]
    joined_sql = f"SELECT a.c8 FROM dataset_{source.id.hex} AS a JOIN dataset_{second.id.hex} AS b ON a.c1 = b.c1"
    joined_key = cache_key("owner-1", [source, second], joined_sql, joined)
    cache.put(joined_key, {**table, "truncated": False}, "owner-1", [source, second])
    second.version = 2
    assert joined_key != cache_key("owner-1", [source, second], joined_sql, joined)
    cache.invalidate("owner-1", second.id)
    assert cache.get(joined_key)[0] is None


def test_safe_logs_request_ids_and_health(phase2_client, caplog):
    caplog.set_level(logging.INFO, logger="dbo.operations")
    client = phase2_client
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200
    secret = "never-log-my-secret-token"
    response = client.post(
        "/api/v1/auth/login", headers=headers(client), json={"email": "absent@example.test", "password": secret}
    )
    assert response.headers["X-Request-ID"] == response.json()["request_id"]
    logs = [json.loads(r.message) for r in caplog.records if r.name == "dbo.operations"]
    assert any(r["event"] == "request" and r.get("status") == response.status_code for r in logs)
    assert all(secret not in json.dumps(r) and "absent@example.test" not in json.dumps(r) for r in logs)
    third_party = logging.LogRecord("google.sdk", logging.ERROR, __file__, 1, "token=" + secret, (), None)
    assert secret not in SafeJsonFormatter().format(third_party)
    assert client.get("/api/v1/health/metrics").status_code == 401


def test_search_excludes_failed_and_stale_records(phase2_client):
    client = phase2_client
    _, conversation = setup(client)
    provider = SemanticProvider()
    client.app.state.provider = provider
    valid = ask(client, conversation).json()["data"]
    with client.app.state.sessions() as db:
        item = db.get(Analysis, __import__("uuid").UUID(valid["id"]))
        item.status = "failed"
        db.commit()
    assert search(client).json()["data"] == []
