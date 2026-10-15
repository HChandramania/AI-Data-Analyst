"""One live authenticated dashboard request; synthetic known answers, no test provider."""

import csv
import json
import os
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings, load_runtime_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def main():
    env_file = ROOT / ".env"
    base = Settings(_env_file=None, allow_insecure_cookies=True)
    current = load_runtime_settings(base, env_file) if env_file.is_file() else base
    if not current.gemini_api_key or not current.gemini_api_key.get_secret_value():
        print("SKIPPED: Gemini credentials unavailable")
        return
    with (ROOT / "sample_data/analysis_flat.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    expected = [
        sum(Decimal(row["revenue_usd"]) for row in rows),
        sum(Decimal(row["revenue_usd"]) for row in rows if row["region"] == "South"),
    ]
    with TemporaryDirectory(prefix="phase4-live-", dir=Path(".verification")) as temp:
        previous = os.environ.get("DBO_DATA_DIR")
        os.environ["DBO_DATA_DIR"] = str(Path(temp) / "data")
        try:
            command.upgrade(Config("alembic.ini"), "head")
            settings = current.model_copy(update={"data_dir": Path(temp) / "data"})
            with TestClient(create_app(settings)) as c:
                token = c.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
                headers = {"Origin": settings.public_origin, "X-CSRF-Token": token}
                assert (
                    c.post(
                        "/api/v1/auth/register",
                        headers=headers,
                        json={"email": f"dashboard-{uuid4().hex}@example.test", "password": "live-smoke-password"},
                    ).status_code
                    == 201
                )
                uploaded = c.post(
                    "/api/v1/datasets",
                    headers=headers,
                    files=[
                        (
                            "files",
                            ("analysis_flat.csv", (ROOT / "sample_data/analysis_flat.csv").read_bytes(), "text/csv"),
                        )
                    ],
                )
                did = uploaded.json()["data"][0]["dataset"]["id"]
                cid = c.post("/api/v1/conversations", headers=headers, json={"dataset_ids": [did]}).json()["data"]["id"]
                response = c.post(
                    "/api/v1/dashboards",
                    headers=headers,
                    json={
                        "title": "Live synthetic dashboard smoke",
                        "conversation_id": cid,
                        "prompt": "Exactly two cards in this order: total revenue_usd across all records; "
                        "total revenue_usd where region is South. One numeric scalar SUM per card. No other cards.",
                    },
                )
                assert response.status_code == 201, response.json().get("error")
                d = response.json()["data"]
                actual = []
                for card in d["cards"]:
                    table = card.get("evidence", {}).get("table")
                    if (
                        card["status"] == "complete"
                        and table
                        and len(table["rows"]) == 1
                        and len(table["columns"]) == 1
                    ):
                        actual.append(Decimal(str(table["rows"][0][table["columns"][0]])))
                passed = d["status"] == "complete" and actual == expected
                print(
                    json.dumps(
                        {
                            "provider": "Gemini",
                            "model": current.gemini_model,
                            "status": d["status"],
                            "actual": [str(x) for x in actual],
                            "expected": [str(x) for x in expected],
                            "passed": passed,
                            "cards": [{"status": card["status"], "error": card.get("error")} for card in d["cards"]],
                        }
                    )
                )
        finally:
            if previous is None:
                os.environ.pop("DBO_DATA_DIR", None)
            else:
                os.environ["DBO_DATA_DIR"] = previous


if __name__ == "__main__":
    main()
