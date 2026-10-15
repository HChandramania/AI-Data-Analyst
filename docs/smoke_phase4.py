"""Authenticated dashboard/export smoke through Next.js, with restart mode.

Explicit fixture provider lives only in the disposable Compose override.
Run from backend with ../docs/smoke_phase4.py --base-url http://localhost:3104.
Then restart backend and rerun with --reopen. State/reports are ignored verification files.
"""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

import httpx


class OfflineParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = 0
        self.tables = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        assert "src" not in attrs and "href" not in attrs, "External asset reference"
        assert not any(key.startswith("on") for key in attrs), "Executable attribute"
        self.scripts += tag == "script"
        self.tables += tag == "table"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:3104")
    parser.add_argument("--reopen", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    storage = root / ".verification" / "phase4"
    storage.mkdir(parents=True, exist_ok=True)
    state_file = storage / "state.json"
    with httpx.Client(base_url=args.base_url, timeout=110) as c:
        token = c.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
        headers = {"Origin": args.base_url, "X-CSRF-Token": token}
        if args.reopen:
            state = json.loads(state_file.read_text())
            auth = c.post(
                "/api/v1/auth/login",
                headers=headers,
                json={"email": state["email"], "password": "phase4-smoke-password"},
            )
        else:
            state = {"email": f"phase4-{uuid4().hex}@example.test"}
            assert c.get("/dashboards").status_code == 307
            auth = c.post(
                "/api/v1/auth/register",
                headers=headers,
                json={"email": state["email"], "password": "phase4-smoke-password"},
            )
        assert auth.is_success, auth.text
        if not args.reopen:
            uploaded = c.post(
                "/api/v1/datasets",
                headers=headers,
                files=[
                    ("files", ("analysis_flat.csv", (root / "sample_data/analysis_flat.csv").read_bytes(), "text/csv"))
                ],
            )
            source = uploaded.json()["data"][0]["dataset"]["id"]
            conv = c.post("/api/v1/conversations", headers=headers, json={"dataset_ids": [source]}).json()["data"]
            generated = c.post(
                "/api/v1/dashboards",
                headers=headers,
                json={"title": "TEST FIXTURE overview", "conversation_id": conv["id"]},
            )
            assert generated.status_code == 201, generated.text
            state["dashboard"] = generated.json()["data"]["id"]
            state_file.write_text(json.dumps(state))
        d = c.get(f"/api/v1/dashboards/{state['dashboard']}").json()["data"]
        assert d["status"] == "complete" and d["complete_cards"] == 2
        assert d["cards"][0]["evidence"]["table"]["rows"] == [{"revenue": "3760.00"}]
        assert c.get(f"/dashboards/{d['id']}").status_code == 200
        r = c.post(
            "/api/v1/reports/export",
            headers=headers,
            json={"dashboard_ids": [d["id"]], "title": "Phase 4 offline report"},
        )
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"] == "text/html; charset=utf-8"
        assert r.headers["content-disposition"] == 'attachment; filename="Phase-4-offline-report.html"'
        assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
        report_file = storage / "offline-report.html"
        report_file.write_bytes(r.content)
        parsed = OfflineParser()
        parsed.feed(r.text)
        assert parsed.scripts == 3 and parsed.tables == 2
        assert "connect-src 'none'" in r.text and "plotly.js" in r.text
        charts = json.loads(
            re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', r.text).group(1)
        )
        assert charts == d["cards"][1]["evidence"]["charts"]
        # Save executable blocks for node --check, without running them outside a browser.
        for index, script in enumerate(re.findall(r"<script>(.*?)</script>", r.text, re.S)):
            (storage / f"script-{index}.js").write_text(script, encoding="utf-8")
        assert "3760.00" in r.text
        c.post("/api/v1/auth/logout", headers=headers)
        headers["X-CSRF-Token"] = c.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
        assert c.post("/api/v1/reports/export", headers=headers, json={"dashboard_ids": [d["id"]]}).status_code == 401
        print(
            json.dumps(
                {
                    "mode": "reopen" if args.reopen else "create",
                    "cards": 2,
                    "revenue": "3760.00",
                    "report_bytes": len(r.content),
                    "self_contained": True,
                    "offline_rendering": "unverified",
                    "proxy_attachment": "passed",
                }
            )
        )


if __name__ == "__main__":
    main()
