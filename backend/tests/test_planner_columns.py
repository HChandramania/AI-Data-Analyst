import pytest
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture
from test_phase3 import conversation, preview, upload

from app.config import Settings
from app.joins import JoinKey
from app.planner import AnalysisPlan, GeminiProvider
from app.planner_columns import join_column_context, physical_join_sql
from app.sql_policy import SqlRejected, validate_sql

phase2_client = client_fixture


def test_unique_join_tokens_do_not_mutate_source_context():
    sources = [
        {
            "id": "a",
            "table": "dataset_a",
            "columns": [{"id": "c1", "name": "customer"}],
            "confirmed_joins": [{"left": "a", "right": "b", "left_key": "c1", "right_key": "c1"}],
        },
        {"id": "b", "table": "dataset_b", "columns": [{"id": "c1", "name": "customer"}]},
    ]
    context, refs = join_column_context(sources)
    assert sources[0]["columns"][0]["id"] == "c1"
    assert context[0]["confirmed_joins"][0]["right_key"] == "s2_c1"
    assert refs == {"s1_c1": ("dataset_a", "c1"), "s2_c1": ("dataset_b", "c1")}


def test_translation_preserves_projection_name_and_wrong_source():
    refs = {"s1_c1": ("dataset_a", "c1")}
    assert physical_join_sql("SELECT s1_c1 FROM dataset_a a", refs) == "SELECT a.c1 AS s1_c1 FROM dataset_a AS a"
    assert "b.s1_c1" in physical_join_sql("SELECT b.s1_c1 FROM dataset_b b", refs)
    assert physical_join_sql("SELECT c1 FROM dataset_a", {}) == "SELECT c1 FROM dataset_a"
    assert physical_join_sql("SELECT c1 FROM dataset_a; DROP TABLE dataset_a", refs).endswith("DROP TABLE dataset_a")


def test_provider_boundary_translates_join_tokens_before_execution(phase2_client, monkeypatch):
    client = phase2_client
    setup(client)
    left = upload(client, "sales.csv", b"customer_id,quantity,unit_price\nA,2,10\nB,3,20\n")
    right = upload(client, "customers.csv", b"customer_id,region\nA,North\nB,South\n")
    cid = conversation(client, [left, right])
    key = {"left": left["id"], "right": right["id"], "left_key": "c1", "right_key": "c1", "type": "inner"}
    proposal = preview(client, cid, [key])
    provider = GeminiProvider(Settings(_env_file=None, gemini_api_key="test-only"))
    client.app.state.provider = provider

    async def generate(prompt, schema, settings, timeout):
        assert '"id": "s2_c2"' in prompt
        assert '"right_key": "s2_c1"' in prompt
        return AnalysisPlan(
            action="query",
            dataset_ids=[left["id"], right["id"]],
            sql=(
                f"SELECT s2_c2 AS region, SUM(s1_c2*s1_c3) AS revenue FROM dataset_{left['id'].replace('-', '')} s "
                f"INNER JOIN dataset_{right['id'].replace('-', '')} c ON s1_c1=s2_c1 "
                "GROUP BY s2_c2 ORDER BY revenue DESC"
            ),
        )

    monkeypatch.setattr(provider, "_gemini_generate", generate)
    response = client.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers(client),
        json={"question": "Revenue by region", "join_confirmation": proposal["id"], "accept_multiplication": True},
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["table"]["rows"] == [{"region": "South", "revenue": 60}, {"region": "North", "revenue": 20}]
    assert "s.c1 = c.c1" in result["sql"]
    registry = {
        f"dataset_{left['id'].replace('-', '')}": {"c1", "c2", "c3"},
        f"dataset_{right['id'].replace('-', '')}": {"c1", "c2"},
    }
    with pytest.raises(SqlRejected):
        validate_sql(result["sql"].replace("s.c1 = c.c1", "s.c2 = c.c1"), registry, [JoinKey(**key)])
