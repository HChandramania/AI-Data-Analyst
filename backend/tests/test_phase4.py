"""Dashboard/export behavior against real authenticated evidence and bounded SQL execution."""

import asyncio
import json
import re
from html.parser import HTMLParser
from uuid import UUID, uuid4

import pytest
from test_phase2 import headers, setup
from test_phase2 import phase2_client as client_fixture
from test_phase3 import conversation, upload

from app.models import Analysis, Dashboard, Dataset, User
from app.planner import DashboardPlan, ProviderFailure

phase2_client = client_fixture


class DashboardProvider:
    def __init__(self, count=2, bad=False):
        self.calls = 0
        self.count = count
        self.bad = bad

    async def dashboard(self, question, datasets):
        self.calls += 1
        d = datasets[0]
        cards = [
            {
                "title": "Revenue",
                "plan": {
                    "action": "query",
                    "dataset_ids": [d["id"]],
                    "sql": f"SELECT SUM(c8) AS revenue FROM {d['table']}",
                },
            },
            {
                "title": "Revenue by region",
                "plan": {
                    "action": "query",
                    "dataset_ids": [d["id"]],
                    "sql": f"SELECT c5 AS region, SUM(c8) AS revenue FROM {d['table']} GROUP BY c5 ORDER BY c5",
                    "chart": {
                        "type": "bar",
                        "x": "region",
                        "y": "revenue",
                        "title": "Revenue",
                        "x_label": "Region",
                        "y_label": "USD",
                    },
                },
            },
        ]
        if self.bad:
            cards[1]["plan"]["sql"] = "SELECT * FROM read_csv_auto('/etc/passwd')"
        return {"cards": [cards[i % 2] for i in range(self.count)]}


def generate(client, cid, **extra):
    return client.post(
        "/api/v1/dashboards", headers=headers(client), json={"title": "Overview", "conversation_id": cid, **extra}
    )


def report(client, ids=None, **extra):
    return client.post("/api/v1/reports/export", headers=headers(client), json={"analysis_ids": ids or [], **extra})


def test_generation_reopen_export_and_reuse(phase2_client):
    c = phase2_client
    _, conv = setup(c)
    provider = DashboardProvider()
    c.app.state.provider = provider
    response = generate(c, conv["id"])
    assert response.status_code == 201, response.text
    d = response.json()["data"]
    assert d["status"] == "complete" and d["complete_cards"] == 2 and provider.calls == 1
    assert d["cards"][0]["evidence"]["table"]["rows"] == [{"revenue": "3760.00"}]
    assert c.get(f"/api/v1/dashboards/{d['id']}").json()["data"] == d
    assert c.get("/api/v1/dashboards").json()["data"][0]["id"] == d["id"]
    ids = [card["analysis_id"] for card in d["cards"]]
    reuse = generate(c, conv["id"], generate=False, analysis_ids=ids).json()["data"]
    assert [card["analysis_id"] for card in reuse["cards"]] == ids and provider.calls == 1
    exported = report(c, dashboard_ids=[d["id"]])
    assert exported.status_code == 200 and "3760.00" in exported.text
    assert exported.headers["content-type"] == "text/html; charset=utf-8"
    assert exported.headers["content-disposition"] == 'attachment; filename="Analysis-report.html"'
    assert exported.headers["cache-control"] == "no-store"
    data = json.loads(
        re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', exported.text).group(1)
    )
    assert data == d["cards"][1]["evidence"]["charts"]
    assert all(word in exported.text for word in ["Dataset versions", "Method, assumptions", "SQL", "Report generated"])
    assert provider.calls == 1


@pytest.mark.parametrize("count,expected", [(6, "complete"), (7, "failed")])
def test_card_limit(phase2_client, count, expected):
    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider(count)
    d = generate(c, conv["id"]).json()["data"]
    assert d["status"] == expected and len(d["cards"]) <= 6
    assert generate(c, conv["id"], analysis_ids=[str(uuid4()) for _ in range(7)]).status_code == 422


def test_partial_sql_failure_and_deleted_sources(phase2_client):
    c = phase2_client
    source, conv = setup(c)
    c.app.state.provider = DashboardProvider(bad=True)
    d = generate(c, conv["id"]).json()["data"]
    assert [card["status"] for card in d["cards"]] == ["complete", "failed"]
    assert d["status"] == "partial" and "/etc/passwd" not in d["cards"][1]["error"]
    assert report(c, dashboard_ids=[d["id"]]).status_code == 409
    aid = d["cards"][0]["analysis_id"]
    assert report(c, [aid]).status_code == 200
    c.delete(f"/api/v1/datasets/{source['id']}", headers=headers(c))
    reopened = c.get(f"/api/v1/dashboards/{d['id']}").json()["data"]
    assert all(card["status"] == "unavailable" and "evidence" not in card for card in reopened["cards"])
    assert report(c, [aid]).status_code == 404


def test_owner_and_anonymous_denial(phase2_client):
    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider(1)
    d = generate(c, conv["id"]).json()["data"]
    aid = d["cards"][0]["analysis_id"]
    c.post("/api/v1/auth/logout", headers=headers(c))
    assert c.get("/api/v1/dashboards").status_code == 401
    assert c.get(f"/api/v1/dashboards/{d['id']}").status_code == 401
    assert generate(c, conv["id"]).status_code == 401
    assert report(c, [aid]).status_code == 401
    c.post("/api/v1/auth/register", headers=headers(c), json={"email": "other@test.dev", "password": "strong-password"})
    assert c.get(f"/api/v1/dashboards/{d['id']}").status_code == 404
    assert c.get("/api/v1/dashboards").json()["data"] == []
    assert generate(c, conv["id"]).status_code == 404
    assert report(c, [aid]).status_code == 404
    assert report(c, dashboard_ids=[d["id"]]).status_code == 404


def test_deadline_preserves_success_and_releases_capacity(phase2_client, monkeypatch):
    import app.analysis as analysis
    import app.dashboards as dashboards

    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider(3)
    original = analysis.execute
    calls, cancelled = [], []

    async def slow_second(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            monkeypatch.setattr(dashboards, "DASHBOARD_DEADLINE", 1)
            try:
                await asyncio.sleep(20)
            finally:
                cancelled.append(True)
        return await original(*args, **kwargs)

    monkeypatch.setattr(analysis, "execute", slow_second)
    monkeypatch.setattr(dashboards, "DASHBOARD_DEADLINE", 5)
    d = generate(c, conv["id"]).json()["data"]
    assert [card["status"] for card in d["cards"]] == ["complete", "failed", "failed"]
    assert len(calls) == 2 and cancelled and not c.app.state.dashboard_capacity.locked()


def test_capacity_rejects_without_provider_call(phase2_client):
    c = phase2_client
    _, conv = setup(c)
    provider = DashboardProvider()
    c.app.state.provider = provider
    c.app.state.dashboard_capacity = asyncio.Semaphore(0)
    assert generate(c, conv["id"]).status_code == 429 and provider.calls == 0


def test_provider_failure_is_saved_safely(phase2_client):
    class Failed:
        async def dashboard(self, *args):
            raise ProviderFailure("sensitive secret")

    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = Failed()
    response = generate(c, conv["id"])
    assert response.json()["data"]["status"] == "failed" and "sensitive secret" not in response.text


def test_join_confirmation_enforced(phase2_client):
    c = phase2_client
    setup(c)
    left = upload(c, "left.csv", b"key,value\n1,10\n2,20\n")
    right = upload(c, "right.csv", b"key,label\n1,A\n2,B\n2,C\n")
    cid = conversation(c, [left, right])

    class Joined:
        async def dashboard(self, question, datasets):
            a, b = datasets
            return {
                "cards": [
                    {
                        "title": "Joined revenue",
                        "plan": {
                            "action": "query",
                            "dataset_ids": [a["id"], b["id"]],
                            "sql": f"SELECT SUM(a.c2) AS total FROM {a['table']} a "
                            f"INNER JOIN {b['table']} b ON a.c1=b.c1",
                        },
                    }
                ]
            }

    c.app.state.provider = Joined()
    d = generate(c, cid).json()["data"]
    assert d["cards"][0]["status"] == "clarification"
    assert d["cards"][0]["evidence"]["table"] is None
    keys = {"left": left["id"], "right": right["id"], "left_key": "c1", "right_key": "c1", "type": "inner"}
    proposal = c.post(f"/api/v1/conversations/{cid}/joins", headers=headers(c), json={"joins": [keys]})
    assert proposal.status_code == 200, proposal.text
    assert generate(c, cid, join_confirmation=proposal.json()["data"]["id"]).status_code == 409
    confirmed = generate(c, cid, join_confirmation=proposal.json()["data"]["id"], accept_multiplication=True).json()[
        "data"
    ]
    assert confirmed["cards"][0]["evidence"]["table"]["rows"] == [{"total": 50}]
    assert confirmed["cards"][0]["evidence"]["method"]["joins"]
    assert generate(c, cid, join_confirmation=str(uuid4())).status_code == 404


def test_report_limits_filename_and_reauthorization(phase2_client, monkeypatch):
    import app.reports as reports

    c = phase2_client
    source, conv = setup(c)
    c.app.state.provider = DashboardProvider(1)
    d = generate(c, conv["id"]).json()["data"]
    aid = d["cards"][0]["analysis_id"]
    assert report(c, []).status_code == 422
    assert report(c, [str(uuid4()) for _ in range(13)]).status_code == 422
    assert report(c, [aid, aid]).status_code == 422
    r = report(c, [aid], title='../../bad\r\n"<script>')
    assert r.headers["content-disposition"] == 'attachment; filename="bad-script.html"'
    monkeypatch.setattr(reports, "MAX_REPORT_BYTES", 100)
    assert report(c, [aid]).status_code == 413
    monkeypatch.setattr(reports, "MAX_REPORT_BYTES", 8 * 1024 * 1024)
    original = reports.render_report

    def changed(*args):
        result = original(*args)
        with c.app.state.sessions() as db:
            db.get(Dataset, UUID(source["id"])).version += 1
            db.commit()
        return result

    monkeypatch.setattr(reports, "render_report", changed)
    assert report(c, [aid]).status_code == 409


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.tables = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        assert "src" not in attrs and "href" not in attrs
        assert not any(a.lower().startswith("on") for a in attrs)
        if tag == "script":
            self.scripts.append(attrs)
        if tag == "table":
            self.tables += 1


def test_malicious_text_serialization_and_self_containment(phase2_client):
    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider()
    d = generate(c, conv["id"]).json()["data"]
    aid = d["cards"][1]["analysis_id"]
    attack = '</script><script>alert(1)</script><img src="https://evil.test" onerror="alert(1)">\u2028&'
    with c.app.state.sessions() as db:
        item = db.get(Analysis, UUID(aid))
        result = json.loads(item.result_json)
        result["charts"][0]["points"][0]["x"] = attack
        result["table"]["rows"][0]["region"] = attack
        item.result_json = json.dumps(result)
        item.question = attack
        db.commit()
    r = report(c, [aid], title=attack)
    assert r.status_code == 200 and attack not in r.text
    parser = ReportParser()
    parser.feed(r.text)
    assert len(parser.scripts) == 3 and parser.tables == 1
    assert "plotly.js" in r.text and "connect-src 'none'" in r.text
    embedded = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', r.text).group(1)
    assert "<" not in embedded and json.loads(embedded)[0]["points"][0]["x"] == attack
    assert "&lt;/script&gt;" in r.text


def test_dashboard_plan_rejects_invented_fields():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DashboardPlan.model_validate({"cards": [], "html": "<script>bad</script>"})


def test_expanded_dashboard_selection_limit(phase2_client):
    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider(1)
    d = generate(c, conv["id"]).json()["data"]
    dashboard_ids = []
    with c.app.state.sessions() as db:
        original = db.get(Analysis, UUID(d["cards"][0]["analysis_id"]))
        for count in [6, 6, 1]:
            cards = []
            for _ in range(count):
                clone = Analysis(
                    **{
                        column.name: getattr(original, column.name)
                        for column in Analysis.__table__.columns
                        if column.name not in {"id", "created_at"}
                    }
                )
                db.add(clone)
                db.flush()
                cards.append({"title": "Saved metric", "analysis_id": str(clone.id), "status": "complete"})
            saved = Dashboard(
                owner_id=original.owner_id,
                title="Overview",
                cards_json=json.dumps(cards),
                dataset_versions_json=original.dataset_versions_json,
            )
            db.add(saved)
            db.flush()
            dashboard_ids.append(str(saved.id))
        db.commit()
    assert report(c, dashboard_ids=dashboard_ids[:2]).status_code == 200
    assert report(c, dashboard_ids=dashboard_ids).status_code == 422


def test_nested_card_read_reauthorizes(phase2_client):
    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider(1)
    d = generate(c, conv["id"]).json()["data"]
    # Simulate a bad stored reference: even trusted dashboard persistence is not an auth boundary.
    with c.app.state.sessions() as db:
        saved = db.get(Dashboard, UUID(d["id"]))
        cards = json.loads(saved.cards_json)
        foreign = User(email="nested@example.test", password_hash="test-only-unusable-hash")
        db.add(foreign)
        db.flush()
        db.get(Analysis, UUID(cards[0]["analysis_id"])).owner_id = foreign.id
        db.commit()
    reopened = c.get(f"/api/v1/dashboards/{d['id']}").json()["data"]
    assert reopened["cards"][0]["status"] == "unavailable"
    assert "evidence" not in reopened["cards"][0]
    assert report(c, dashboard_ids=[d["id"]]).status_code == 409


def test_source_change_records_every_unfinished_card(phase2_client, monkeypatch):
    from fastapi import HTTPException

    import app.dashboards as dashboards

    c = phase2_client
    _, conv = setup(c)
    c.app.state.provider = DashboardProvider(3)
    original = dashboards.run_analysis
    calls = []

    async def changed(*args, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            raise HTTPException(409)
        return await original(*args, **kwargs)

    monkeypatch.setattr(dashboards, "run_analysis", changed)
    d = generate(c, conv["id"]).json()["data"]
    assert d["total_cards"] == 3 and d["complete_cards"] == 1
    assert [card["status"] for card in d["cards"]] == ["complete", "unavailable", "unavailable"]
    assert [card["title"] for card in d["cards"]] == ["Revenue", "Revenue by region", "Revenue"]
