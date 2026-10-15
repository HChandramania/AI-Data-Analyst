"""Phase 3 product/security fixtures. Providers below exist only in tests."""

from pathlib import Path
from statistics import quantiles
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture

from app.charts import ChartIntent, build_chart
from app.joins import JoinKey
from app.models import Dataset
from app.planner import AnalysisPlan, AnomalyIntent, ProviderFailure
from app.sql_policy import SqlRejected, validate_sql

phase2_client = client_fixture


def chart(kind, x="x", y="y", **kwargs):
    return ChartIntent(type=kind, x=x, y=y, title="Executed values", x_label=x, y_label=y, **kwargs)


def table(xs, ys, xt="VARCHAR", yt="DECIMAL(18,2)", truncated=False):
    return {
        "columns": ["x", "y"],
        "types": {"x": xt, "y": yt},
        "rows": [{"x": x, "y": y} for x, y in zip(xs, ys, strict=True)],
        "truncated": truncated,
    }


@pytest.mark.parametrize("kind", ["bar", "pie", "scatter", "line"])
def test_four_charts_use_only_evidence(kind):
    result = table([2, 1], ["20.00", "10.00"], "INTEGER")
    artifact = build_chart(chart(kind), result)
    assert {(p["x"], p["y"]) for p in artifact["points"]} == {(2, "20.00"), (1, "10.00")}
    if kind == "line":
        assert artifact["points"][0]["x"] == 1


@pytest.mark.parametrize(
    ("kind", "result"),
    [
        ("pie", table(["A", "B"], [-1, 2])),
        ("pie", table(["A"], [0])),
        ("pie", table(["A"], [None])),
        ("pie", table(["A"], [1], truncated=True)),
        ("pie", table(list(range(9)), list(range(9)))),
        ("bar", table(["A", "A"], [1, 2])),
        ("bar", table(list(range(51)), list(range(51)))),
        ("bar", table([None], [1])),
        ("bar", table(["A"], [None])),
        ("line", table([1], [None], "INTEGER")),
        ("bar", table(["A"], ["1"], yt="VARCHAR")),
        ("scatter", table(["A"], [1])),
        ("scatter", table([1], [None], "INTEGER")),
        ("line", table(["January"], [1])),
        ("line", table([1, 1], [1, 2], "INTEGER")),
        ("bar", table([1], [float("inf")])),
        ("bar", table([], [])),
    ],
)
def test_invalid_chart_combinations(kind, result):
    with pytest.raises(ValueError):
        build_chart(chart(kind), result)


def test_chart_schema_and_temporal_gaps():
    with pytest.raises(ValidationError):
        ChartIntent(**chart("bar").model_dump(), values=[999])
    with pytest.raises(ValueError):
        build_chart(chart("bar", x="invented"), table([1], [2]))
    result = table(["2025-03-01", "2025-01-01"], [30, 10], "DATE")
    artifact = build_chart(chart("line", period="month"), result)
    assert artifact["points"] == [
        {"x": "2025-01-01", "y": 10},
        {"x": "2025-03-01", "y": None},
        {"x": "2025-03-01", "y": 30},
    ]
    with pytest.raises(ValueError):
        build_chart(chart("line"), result)


def test_line_iso_month_labels_preserve_table_and_expose_gaps():
    result = table(["2026-03", "2026-01"], ["2400.00", "360.00"])
    artifact = build_chart(chart("line", period="month"), result)
    assert artifact["points"] == [
        {"x": "2026-01-01", "y": "360.00"},
        {"x": "2026-03-01", "y": None},
        {"x": "2026-03-01", "y": "2400.00"},
    ]
    assert result["rows"][0]["x"] == "2026-03"
    assert any("Supporting table values are unchanged" in caveat for caveat in artifact["caveats"])


@pytest.mark.parametrize(
    "label,period",
    [("January", "month"), ("2026-13", "month"), ("01/02/2026", "day"), ("2026-02-30", "day"), ("2026-01", None)],
)
def test_line_rejects_ambiguous_invalid_or_unconfirmed_text_dates(label, period):
    with pytest.raises(ValueError):
        build_chart(chart("line", period=period), table([label], [1]))


@pytest.mark.parametrize("label,period,expected", [("2026", "year", "2026-01-01"), ("2026-01-02", "day", "2026-01-02")])
def test_line_iso_year_day_labels(label, period, expected):
    assert build_chart(chart("line", period=period), table([label], [1]))["points"] == [{"x": expected, "y": 1}]


def test_formatted_month_line_end_to_end(phase2_client):
    client = phase2_client
    dataset, convo = setup(client)

    class Provider:
        async def plan(self, question, datasets):
            return AnalysisPlan(
                action="query",
                dataset_ids=[dataset["id"]],
                sql=(
                    "SELECT STRFTIME(CAST(c2 AS DATE), '%Y-%m') AS x, SUM(c8) AS y "
                    f"FROM {datasets[0]['table']} GROUP BY x ORDER BY x"
                ),
                chart=chart("line", period="month"),
            )

    client.app.state.provider = Provider()
    response = client.post(
        f"/api/v1/conversations/{convo['id']}/messages", headers=headers(client), json={"question": "Monthly line"}
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["data"]
    assert evidence["charts"][0]["points"] == [
        {"x": "2026-01-01", "y": "360.00"},
        {"x": "2026-02-01", "y": "1000.00"},
        {"x": "2026-03-01", "y": "2400.00"},
    ]
    assert evidence["table"]["rows"][0]["x"] == "2026-01"


def test_regional_bar_internal_columns_and_display_aliases(phase2_client):
    client = phase2_client
    dataset, convo = setup(client)

    class Provider:
        async def plan(self, question, datasets):
            return AnalysisPlan(
                action="query",
                dataset_ids=[dataset["id"]],
                sql=(
                    "SELECT c5 AS region, SUM(c8) AS total_revenue_usd "
                    f"FROM {datasets[0]['table']} GROUP BY c5 ORDER BY total_revenue_usd DESC"
                ),
                chart=chart("bar", x="region", y="total_revenue_usd"),
            )

    client.app.state.provider = Provider()
    response = client.post(
        f"/api/v1/conversations/{convo['id']}/messages",
        headers=headers(client),
        json={"question": "Show a bar chart of total revenue_usd by region, ordered by revenue descending."},
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["data"]
    expected = [("South", "1800.00"), ("North", "960.00"), ("West", "520.00"), ("East", "480.00")]
    assert [(r["region"], r["total_revenue_usd"]) for r in evidence["table"]["rows"]] == expected
    assert [(p["x"], p["y"]) for p in evidence["charts"][0]["points"]] == expected
    registry = {f"dataset_{UUID(dataset['id']).hex}": {"c5", "c8"}}
    for projection in ("region, SUM(c8)", "region AS region, SUM(revenue_usd)"):
        with pytest.raises(SqlRejected, match="Unknown column"):
            validate_sql(
                f"SELECT {projection} AS total_revenue FROM {next(iter(registry))} "
                "GROUP BY region ORDER BY total_revenue DESC",
                registry,
            )


def upload(client, name, content):
    response = client.post("/api/v1/datasets", headers=headers(client), files=[("files", (name, content, "text/csv"))])
    assert response.status_code == 200, response.text
    return response.json()["data"][0]["dataset"]


def conversation(client, datasets):
    response = client.post(
        "/api/v1/conversations", headers=headers(client), json={"dataset_ids": [d["id"] for d in datasets]}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def ask(client, cid, question="Compute", **kwargs):
    return client.post(
        f"/api/v1/conversations/{cid}/messages", headers=headers(client), json={"question": question, **kwargs}
    )


def test_context_inheritance_failure_and_selection_changes(phase2_client):
    client = phase2_client
    dataset, conv = setup(client)
    captured = []

    class ContextProvider:
        async def plan(self, question, datasets):
            captured.append(datasets)
            t = datasets[0]["table"]
            if "fail" in question:
                raise ProviderFailure()
            if "month" in question:
                prior = datasets[0]["prior_intent"]
                assert prior["filters"] == "c5 = 'South'"
                assert "SUM(c8)" in prior["metrics"]
                sql = (
                    "SELECT DATE_TRUNC('month', CAST(c2 AS DATE)) AS month, "
                    f"SUM(c8) AS revenue FROM {t} WHERE c5='South' GROUP BY month ORDER BY month"
                )
                chart_intent = chart("line", "month", "revenue", period="month")
            else:
                sql = f"SELECT SUM(c8) AS revenue FROM {t} WHERE c5='South'"
                chart_intent = None
            return AnalysisPlan(action="query", dataset_ids=[datasets[0]["id"]], sql=sql, chart=chart_intent)

    client.app.state.provider = ContextProvider()
    first = ask(client, conv["id"], "South revenue").json()["data"]
    assert first["table"]["rows"] == [{"revenue": "1800.00"}]
    follow = ask(client, conv["id"], "Now break that down by month")
    assert follow.status_code == 200, follow.text
    assert sum(float(r["revenue"]) for r in follow.json()["data"]["table"]["rows"]) == 1800
    assert follow.json()["data"]["charts"][0]["type"] == "line"
    assert ask(client, conv["id"], "fail").status_code == 502
    assert client.get(f"/api/v1/analyses/{first['id']}").json()["data"]["table"] == first["table"]
    second = upload(client, "other.csv", b"amount\n1\n2\n")
    client.patch(f"/api/v1/conversations/{conv['id']}", headers=headers(client), json={"dataset_ids": [second["id"]]})
    assert ask(client, conv["id"], "Now use that").json()["data"]["status"] == "clarification"
    # Deleting a historical source also invalidates a conversation whose selection changed.
    assert client.delete(f"/api/v1/datasets/{dataset['id']}", headers=headers(client)).status_code == 200
    assert client.get(f"/api/v1/analyses/{first['id']}").status_code == 404
    assert len(captured) == 3


def test_ambiguous_reference_and_version_change(phase2_client):
    client = phase2_client
    dataset, conv = setup(client)
    assert ask(client, conv["id"], "Now break that down by month").json()["data"]["status"] == "clarification"
    with client.app.state.sessions() as db:
        db.get(Dataset, UUID(dataset["id"])).version += 1
        db.commit()
    assert ask(client, conv["id"], "Revenue").status_code == 409


@pytest.mark.parametrize(
    ("values", "verdict", "flagged"),
    [
        (list(range(1, 25)) + [1000, None], "flagged", 1),
        (list(range(20)), "no_values_flagged", 0),
        ([5] * 20 + [None], "insufficient_evidence", 0),
        (list(range(19)), "insufficient_evidence", 0),
    ],
)
def test_anomaly_full_snapshot_rules(phase2_client, values, verdict, flagged):
    client = phase2_client
    setup(client)
    data = "value,record\n" + "\n".join(f"{'' if v is None else v},r{i}" for i, v in enumerate(values)) + "\n"
    raw = (
        (Path(__file__).resolve().parents[2] / "sample_data/phase3_anomalies.csv").read_bytes()
        if flagged
        else data.encode()
    )
    dataset = upload(client, "anomalies.csv", raw)
    cid = conversation(client, [dataset])

    class AnomalyProvider:
        async def plan(self, question, datasets):
            return AnalysisPlan(action="anomalies", dataset_ids=[dataset["id"]], anomaly=AnomalyIntent(measure="c1"))

    client.app.state.provider = AnomalyProvider()
    response = ask(client, cid)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    evidence = result["anomalies"]
    group = evidence["groups"][0]
    assert group["status"] == verdict
    assert group["flagged_count"] == flagged
    assert group["null_count"] == values.count(None)
    expected = quantiles([v for v in values if v is not None], n=4, method="inclusive")
    assert group["q1"] == expected[0] and group["q3"] == expected[2]
    if flagged:
        assert result["table"]["rows"][0]["row_reference"] == 25
        assert result["table"]["rows"][0]["value"] == 1000
    assert client.get(f"/api/v1/analyses/{result['id']}").json()["data"]["anomalies"] == evidence


def join_fixture(client, duplicate=False):
    setup(client)
    left = upload(client, "orders.csv", b"customer,amount\nA,10\nA,20\nB,30\nZ,40\n,50\n")
    right = upload(
        client, "customers.csv", b"customer,region\nA,North\nB,South\nC,East\n" + (b"A,West\n" if duplicate else b"")
    )
    cid = conversation(client, [left, right])
    key = {"left": left["id"], "right": right["id"], "left_key": "c1", "right_key": "c1", "type": "left"}

    class JoinedProvider:
        async def plan(self, question, datasets):
            left_table, right_table = [d["table"] for d in datasets]
            return AnalysisPlan(
                action="query",
                dataset_ids=[d["id"] for d in datasets],
                sql=f"SELECT SUM(a.c2) AS total FROM {left_table} a LEFT JOIN {right_table} b ON a.c1=b.c1",
            )

    client.app.state.provider = JoinedProvider()
    return cid, left, right, key


def preview(client, cid, joins):
    response = client.post(f"/api/v1/conversations/{cid}/joins", headers=headers(client), json={"joins": joins})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_confirmed_many_to_one_unmatched_and_owner_denial(phase2_client):
    client = phase2_client
    cid, left, right, key = join_fixture(client)
    assert ask(client, cid).json()["data"]["status"] == "clarification"
    proposal = preview(client, cid, [key])
    facts = proposal["join_proposal"]["diagnostics"][0]
    assert facts["left_duplicate_keys"] == 1 and facts["right_duplicate_keys"] == 0
    assert facts["left_unmatched_rows"] == 2 and facts["right_unmatched_rows"] == 1
    assert facts["left_nulls"] == 1 and facts["matched_rows"] == 3
    assert facts["cardinality"] == "many-to-one" and facts["multiplies_right_rows"] == 1
    answer = ask(client, cid, join_confirmation=proposal["id"], accept_multiplication=True)
    assert answer.status_code == 200, answer.text
    aid = answer.json()["data"]["id"]
    assert answer.json()["data"]["table"]["rows"] == [{"total": 150}]
    assert ask(client, cid, join_confirmation=str(uuid4())).status_code == 409
    foreign_cid = conversation(client, [left, right])
    assert ask(client, foreign_cid, join_confirmation=proposal["id"]).status_code == 409
    client.post("/api/v1/auth/logout", headers=headers(client))
    client.post(
        "/api/v1/auth/register",
        headers=headers(client),
        json={"email": "foreign@test.dev", "password": "strong-password"},
    )
    assert ask(client, cid, join_confirmation=proposal["id"]).status_code == 404
    assert client.get(f"/api/v1/analyses/{aid}").status_code == 404
    assert (
        client.post(f"/api/v1/conversations/{cid}/joins", headers=headers(client), json={"joins": [key]}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/conversations", headers=headers(client), json={"dataset_ids": [left["id"], right["id"]]}
        ).status_code
        == 404
    )


def test_confirmed_sales_region_join_qualifies_overlapping_column_ids(phase2_client):
    client = phase2_client
    setup(client)
    fixtures = Path(__file__).resolve().parents[2] / "sample_data"
    sales = upload(client, "sales.csv", (fixtures / "sales.csv").read_bytes())
    customers = upload(client, "customers.csv", (fixtures / "customers.csv").read_bytes())
    cid = conversation(client, [sales, customers])
    key = {"left": sales["id"], "right": customers["id"], "left_key": "c3", "right_key": "c1", "type": "inner"}
    proposal = preview(client, cid, [key])

    class Provider:
        async def plan(self, question, datasets):
            return AnalysisPlan(
                action="query",
                dataset_ids=[sales["id"], customers["id"]],
                sql=(
                    "SELECT c.c3 AS region, SUM(s.c5*s.c6) AS total_revenue_usd "
                    f"FROM dataset_{UUID(sales['id']).hex} s "
                    f"INNER JOIN dataset_{UUID(customers['id']).hex} c ON s.c3=c.c1 "
                    "GROUP BY c.c3 ORDER BY total_revenue_usd DESC"
                ),
                chart=chart("bar", x="region", y="total_revenue_usd"),
            )

    client.app.state.provider = Provider()
    response = ask(client, cid, join_confirmation=proposal["id"], accept_multiplication=True)
    assert response.status_code == 200, response.text
    evidence = response.json()["data"]
    expected = [("South", "1800.00"), ("North", "960.00"), ("West", "520.00"), ("East", "480.00")]
    assert [(r["region"], r["total_revenue_usd"]) for r in evidence["table"]["rows"]] == expected
    assert [(p["x"], p["y"]) for p in evidence["charts"][0]["points"]] == expected
    registry = {
        f"dataset_{UUID(sales['id']).hex}": {"c3", "c5", "c6"},
        f"dataset_{UUID(customers['id']).hex}": {"c1", "c3"},
    }
    with pytest.raises(SqlRejected, match="Unconfirmed join keys"):
        validate_sql(evidence["sql"].replace("s.c3 = c.c1", "c3 = c1"), registry, [JoinKey(**key)])


def test_multiplication_stale_confirmation_and_deletion(phase2_client):
    client = phase2_client
    cid, left, right, key = join_fixture(client, duplicate=True)
    proposal = preview(client, cid, [key])
    assert proposal["join_proposal"]["requires_multiplication"] is True
    assert ask(client, cid, join_confirmation=proposal["id"]).status_code == 409
    result = ask(client, cid, join_confirmation=proposal["id"], accept_multiplication=True).json()["data"]
    assert result["table"]["rows"] == [{"total": 180}]
    with client.app.state.sessions() as db:
        db.get(Dataset, UUID(right["id"])).version += 1
        db.commit()
    client.patch(
        f"/api/v1/conversations/{cid}", headers=headers(client), json={"dataset_ids": [left["id"], right["id"]]}
    )
    assert ask(client, cid, join_confirmation=proposal["id"], accept_multiplication=True).status_code == 409
    client.delete(f"/api/v1/datasets/{right['id']}", headers=headers(client))
    assert client.get(f"/api/v1/analyses/{result['id']}").status_code == 404


@pytest.mark.parametrize(
    "suffix",
    [
        "LEFT JOIN {r} b ON a.c2=b.c1",
        "INNER JOIN {r} b ON a.c1=b.c1",
        "CROSS JOIN {r} b",
        "LEFT JOIN {r} b ON a.c1=b.c1 OR 1=1",
        "LEFT JOIN secret b ON a.c1=b.c1",
        "LEFT JOIN {r} b USING(c1)",
        "LEFT JOIN {r} b ON a.c1=b.c1 LEFT JOIN {r} c ON a.c1=c.c1",
    ],
)
def test_tampered_join_sql(suffix):
    left, right = uuid4(), uuid4()
    left_table, right_table = f"dataset_{left.hex}", f"dataset_{right.hex}"
    confirmed = [JoinKey(left=left, right=right, left_key="c1", right_key="c1", type="left")]
    with pytest.raises(SqlRejected):
        validate_sql(
            f"SELECT SUM(a.c2) AS total FROM {left_table} a " + suffix.format(r=right_table),
            {left_table: {"c1", "c2"}, right_table: {"c1"}},
            confirmed,
        )


def test_invalid_join_keys_and_all_null_anomaly_group(phase2_client):
    client = phase2_client
    cid, _, _, key = join_fixture(client)
    for change in ({"right_key": "c99"}, {"left_key": "c2"}, {"left": str(uuid4())}):
        response = client.post(
            f"/api/v1/conversations/{cid}/joins", headers=headers(client), json={"joins": [{**key, **change}]}
        )
        assert response.status_code == 422
    # Numeric column overall, but one confirmed group has only null values.
    ds = upload(client, "groups.csv", ("value,group\n,A\n,A\n" + "\n".join(f"{i},B" for i in range(20))).encode())
    cid = conversation(client, [ds])

    class GroupProvider:
        async def plan(self, question, datasets):
            return AnalysisPlan(
                action="anomalies", dataset_ids=[ds["id"]], anomaly=AnomalyIntent(measure="c1", group="c2")
            )

    client.app.state.provider = GroupProvider()
    assert ask(client, cid).json()["data"]["status"] == "clarification"
    response = ask(client, cid, anomaly_group_confirmation="c2")
    assert response.status_code == 200, response.text
    groups = response.json()["data"]["anomalies"]["groups"]
    assert groups[0]["status"] == "insufficient_evidence" and groups[0]["null_count"] == 2
    assert groups[1]["status"] == "no_values_flagged"


def test_anomaly_count_exceeds_display_cap(phase2_client):
    client = phase2_client
    setup(client)
    values = list(range(3000)) + [100000] * 600
    ds = upload(client, "large.csv", ("value\n" + "\n".join(map(str, values))).encode())
    cid = conversation(client, [ds])

    class Provider:
        async def plan(self, question, datasets):
            return AnalysisPlan(action="anomalies", dataset_ids=[ds["id"]], anomaly=AnomalyIntent(measure="c1"))

    client.app.state.provider = Provider()
    response = ask(client, cid)
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["anomalies"]["flagged_count"] == 600
    assert result["table"]["returned_rows"] == 500 and result["table"]["truncated"]
    assert result["anomalies"]["groups"][0]["sample_size"] == 3600


@pytest.mark.parametrize("kind", ["bar", "line", "pie", "scatter"])
def test_chart_pipeline_and_partial_failure(phase2_client, kind):
    client = phase2_client
    setup(client)
    ds = upload(client, "chart.csv", b"x,y\n1,10\n2,20\n3,30\n")
    cid = conversation(client, [ds])

    class Provider:
        async def plan(self, question, datasets):
            intent = chart(kind, y="missing" if question == "invalid" else "y")
            return AnalysisPlan(
                action="query",
                dataset_ids=[ds["id"]],
                sql=f"SELECT c1 AS x, c2 AS y FROM {datasets[0]['table']} ORDER BY c1",
                chart=intent,
            )

    client.app.state.provider = Provider()
    result = ask(client, cid).json()["data"]
    assert result["charts"][0]["type"] == kind
    assert result["charts"][0]["points"] == [{"x": 1, "y": 10}, {"x": 2, "y": 20}, {"x": 3, "y": 30}]
    invalid = ask(client, cid, "invalid").json()["data"]
    assert invalid["status"] == "complete" and invalid["chart_error"] and not invalid["charts"]
    assert invalid["table"]["rows"] == result["table"]["rows"]


def test_entirely_null_measure(phase2_client):
    client = phase2_client
    setup(client)
    ds = upload(client, "null.csv", b"amount,id\n,A\n,B\n")
    cid = conversation(client, [ds])

    class Provider:
        async def plan(self, question, datasets):
            return AnalysisPlan(action="anomalies", dataset_ids=[ds["id"]], anomaly=AnomalyIntent(measure="c1"))

    client.app.state.provider = Provider()
    response = ask(client, cid)
    assert response.status_code == 200, response.text
    group = response.json()["data"]["anomalies"]["groups"][0]
    assert group["status"] == "insufficient_evidence" and group["sample_size"] == 0
    assert group["null_count"] == 2


@pytest.mark.parametrize("source_count", [5])
def test_multi_source_analysis_and_disconnected_join_denial(phase2_client, source_count):
    client = phase2_client
    setup(client)
    sources = [
        upload(client, f"source{i}.csv", f"key,value\nA,{i}\nB,{i * 10}\n".encode()) for i in range(1, source_count + 1)
    ]
    cid = conversation(client, sources)
    joins = [
        {"left": sources[0]["id"], "right": s["id"], "left_key": "c1", "right_key": "c1", "type": "inner"}
        for s in sources[1:]
    ]
    invalid = client.post(f"/api/v1/conversations/{cid}/joins", headers=headers(client), json={"joins": joins[:1]})
    assert invalid.status_code == 422
    proposed = preview(client, cid, joins)
    assert not proposed["join_proposal"]["requires_multiplication"]

    class Provider:
        async def embed(self, content, *, task_type):
            return [1.0] + [0.0] * 767

        async def plan(self, question, datasets):
            last = "abcdefghij"[source_count - 1]
            sql = f"SELECT SUM(a.c2+{last}.c2) AS total FROM {datasets[0]['table']} a "
            sql += " ".join(
                f"INNER JOIN {d['table']} {alias} ON a.c1={alias}.c1"
                for alias, d in zip("bcdefghij"[: source_count - 1], datasets[1:], strict=True)
            )
            return AnalysisPlan(action="query", dataset_ids=[d["id"] for d in datasets], sql=sql)

    client.app.state.provider = Provider()
    response = ask(client, cid, join_confirmation=proposed["id"])
    assert response.status_code == 200, response.text
    artifact = response.json()["data"]
    assert artifact["table"]["rows"] == [{"total": (source_count + 1) * 11}]
    found = client.post("/api/v1/search", headers=headers(client), json={"query": "Combined totals"})
    assert found.status_code == 200 and found.json()["data"][0]["analysis_id"] == artifact["id"]
    if source_count == 10:
        extra = upload(client, "extra.csv", b"key,value\nA,99\n")
        invalid = client.post(
            "/api/v1/conversations",
            headers=headers(client),
            json={"dataset_ids": [s["id"] for s in sources] + [extra["id"]]},
        )
        assert invalid.status_code == 422


def test_nested_intent_retains_inner_filters(phase2_client):
    client = phase2_client
    ds, conv = setup(client)

    class Provider:
        async def plan(self, question, datasets):
            if question == "Now summarize that":
                stages = datasets[0]["prior_intent"]["stages"]
                assert any("South" in s["filters"] for s in stages)
                assert len(datasets[0]["recent_messages"]) <= 4
            sql = (
                f"WITH south AS (SELECT c8 FROM {datasets[0]['table']} WHERE c5='South') "
                "SELECT SUM(c8) AS total FROM south"
            )
            return AnalysisPlan(action="query", dataset_ids=[ds["id"]], sql=sql)

    client.app.state.provider = Provider()
    assert ask(client, conv["id"]).json()["data"]["table"]["rows"] == [{"total": "1800.00"}]
    response = ask(client, conv["id"], "Now summarize that")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["table"]["rows"] == [{"total": "1800.00"}]

    class AnomalyProvider:
        async def plan(self, question, datasets):
            return AnalysisPlan(action="anomalies", dataset_ids=[ds["id"]], anomaly=AnomalyIntent(measure="c8"))

    client.app.state.provider = AnomalyProvider()
    assert ask(client, conv["id"], "Now find anomalies in that").json()["data"]["status"] == "clarification"
