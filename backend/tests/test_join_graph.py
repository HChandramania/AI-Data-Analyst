"""Graph validation and five-source execution; provider doubles never run in production."""

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture
from test_phase3 import ask, conversation, preview, upload

from app.joins import JoinKey, validate_keys
from app.models import Analysis
from app.planner import AnalysisPlan, DashboardPlan
from app.sql_policy import SqlRejected, validate_sql

phase2_client = client_fixture


def source():
    return SimpleNamespace(
        id=uuid4(), schema_json=json.dumps([{"id": "c1", "type": "text"}, {"id": "c2", "type": "integer"}])
    )


def edge(a, b, **extra):
    return JoinKey(left=a.id, right=b.id, left_key="c1", right_key="c1", type="inner", **extra)


def test_unordered_chain_and_branch_order_preserves_left_semantics():
    a, b, c, d, e = [source() for _ in range(5)]
    joins = [edge(c, d), edge(a, b), edge(a, c), edge(a, e)]
    joins[0].type = "left"
    result = validate_keys(joins, [d, b, e, c, a])
    assert result == [joins[1], joins[2], joins[0], joins[3]]
    assert result[2].left == c.id and result[2].type == "left"
    assert validate_keys([edge(b, c), edge(a, b)], [c, b, a])[0].left == a.id


@pytest.mark.parametrize(
    "kind", ["self", "duplicate", "disconnected", "cycle", "parallel", "column", "type", "foreign"]
)
def test_invalid_graphs(kind):
    a, b, c, d, outsider = [source() for _ in range(5)]
    edges = [edge(a, b), edge(b, c), edge(c, d)]
    if kind == "self":
        edges[0] = edge(a, a)
    if kind == "duplicate":
        edges[1] = edge(a, b)
    if kind == "disconnected":
        edges = [edge(a, b), edge(c, d)]
    if kind == "cycle":
        edges = [edge(a, b), edge(b, c), edge(c, a)]
    if kind == "parallel":
        edges = [edge(a, b), edge(c, b), edge(b, d)]
    if kind == "column":
        edges[0].left_key = "c9"
    if kind == "type":
        edges[0].left_key = "c2"
    if kind == "foreign":
        edges[0] = edge(outsider, b)
    with pytest.raises(SqlRejected):
        validate_keys(edges, [a, b, c, d])


def test_edge_api_aliases_and_legacy_saved_shape():
    a, b = source(), source()
    legacy = edge(a, b)
    new = JoinKey.model_validate(
        {
            "left_dataset_id": str(a.id),
            "left_column": "c1",
            "right_dataset_id": str(b.id),
            "right_column": "c1",
            "join_type": "INNER",
        }
    )
    assert new == legacy
    assert JoinKey.model_validate(new.model_dump(mode="json")) == legacy
    with pytest.raises(ValidationError):
        JoinKey.model_validate({**legacy.model_dump(), "type": "cross"})


def test_five_source_olist_graph_fanout_enforcement_and_dashboard_compatibility(phase2_client):
    client = phase2_client
    setup(client)
    orders = upload(client, "orders.csv", b"order_id,customer_id\nO1,C1\n")
    customers = upload(client, "customers.csv", b"customer_id,region\nC1,North\n")
    items = upload(client, "items.csv", b"order_id,product_id,price\nO1,P1,10\nO1,P2,20\n")
    products = upload(client, "products.csv", b"product_id,category\nP1,A\nP2,B\n")
    payments = upload(client, "payments.csv", b"order_id,payment\nO1,15\nO1,15\n")
    sources = [products, payments, customers, items, orders]  # Root is deliberately last selected.
    cid = conversation(client, sources)

    def relation(left, lk, right, rk):
        return {
            "left_dataset_id": left["id"],
            "left_column": lk,
            "right_dataset_id": right["id"],
            "right_column": rk,
            "join_type": "LEFT",
        }

    edges = [
        relation(items, "c2", products, "c1"),
        relation(orders, "c2", customers, "c1"),
        relation(orders, "c1", items, "c1"),
        relation(orders, "c1", payments, "c1"),
    ]
    proposed = preview(client, cid, edges)
    graph = proposed["join_proposal"]
    assert graph["joins"][0]["left"] == orders["id"]
    assert graph["fanout_warning"] and "does not make aggregates correct" in graph["fanout_warning"]
    assert graph["requires_multiplication"]
    aliases = {s["id"]: a for s, a in zip(sources, "pcuio", strict=True)}
    sql = f"SELECT COUNT(*) AS joined_rows, SUM(i.c3) AS repeated_item_total FROM dataset_{UUID(orders['id']).hex} o "
    for j in graph["joins"]:
        sql += (
            f"LEFT JOIN dataset_{UUID(j['right']).hex} {aliases[j['right']]} "
            f"ON {aliases[j['left']]}.{j['left_key']}={aliases[j['right']]}.{j['right_key']} "
        )
    registry = {f"dataset_{UUID(s['id']).hex}": {c["id"] for c in s["profile"]["columns"]} for s in sources}
    confirmed = [JoinKey.model_validate(j) for j in graph["joins"]]
    validate_sql(sql, registry, confirmed)
    # A direct orders-to-products join must never replace the configured items-to-products edge.
    with pytest.raises(SqlRejected):
        validate_sql(sql.replace("i.c2=p.c1", "o.c1=p.c1"), registry, confirmed)

    class Provider:
        async def plan(self, question, datasets):
            assert datasets[0]["confirmed_joins"] == graph["joins"]
            return AnalysisPlan(action="query", dataset_ids=[s["id"] for s in sources], sql=sql)

        async def dashboard(self, question, datasets):
            assert datasets[0]["confirmed_joins"] == graph["joins"]
            return DashboardPlan(
                cards=[
                    {
                        "title": "Joined rows with disclosed fanout",
                        "plan": {"action": "query", "dataset_ids": [s["id"] for s in sources], "sql": sql},
                    }
                ]
            )

    client.app.state.provider = Provider()
    assert ask(client, cid, join_confirmation=proposed["id"]).status_code == 409
    response = ask(client, cid, join_confirmation=proposed["id"], accept_multiplication=True)
    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    assert saved["table"]["rows"] == [{"joined_rows": 4, "repeated_item_total": 60}]
    assert any("does not make aggregates correct" in a for a in saved["method"]["assumptions"])
    # Legacy saved proposal names and saved dashboards still work without data migration.
    with client.app.state.sessions() as db:
        old = db.get(Analysis, UUID(proposed["id"]))
        data = json.loads(old.result_json)
        data["join_proposal"].pop("fanout_warning")
        old.result_json = json.dumps(data)
        db.commit()
    dashboard = client.post(
        "/api/v1/dashboards",
        headers=headers(client),
        json={
            "title": "Legacy join confirmation",
            "conversation_id": cid,
            "join_confirmation": proposed["id"],
            "accept_multiplication": True,
        },
    )
    assert dashboard.status_code == 201, dashboard.text
    did = dashboard.json()["data"]["id"]
    assert client.get(f"/api/v1/dashboards/{did}").json()["data"]["complete_cards"] == 1
    assert client.get(f"/api/v1/analyses/{saved['id']}").status_code == 200
    # An owner cannot add another owner's dataset to a selected graph.
    foreign = uuid4()
    bad = client.post(
        f"/api/v1/conversations/{cid}/joins",
        headers=headers(client),
        json={"joins": [{**edges[0], "right_dataset_id": str(foreign)}] + edges[1:]},
    )
    assert bad.status_code == 422
