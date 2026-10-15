"""Small authenticated live Gemini smoke with independent synthetic expectations.

Run from backend/: python live_gemini_smoke.py
Uses a disposable metadata directory and the repository root .env; never prints credentials.
"""

import csv
import json
import os
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Analysis

ROOT = Path(__file__).resolve().parents[1]


def main():
    env_file = ROOT / ".env"
    if not env_file.is_file():
        raise RuntimeError("Root .env is missing")
    with (ROOT / "sample_data" / "analysis_flat.csv").open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    south = [row for row in rows if row["region"] == "South"]
    monthly = defaultdict(Decimal)
    for row in south:
        monthly[row["sale_date"][:7]] += Decimal(row["quantity"]) * Decimal(row["unit_price_usd"])
    expected_south = sum(monthly.values())
    expected_all = sum(Decimal(row["quantity"]) * Decimal(row["unit_price_usd"]) for row in rows)

    def numbers(row):
        found = []
        for value in row.values():
            try:
                found.append(Decimal(str(value)))
            except (ValueError, ArithmeticError):
                continue
        return found

    with TemporaryDirectory() as temp:
        data_dir = Path(temp) / "data"
        previous_data_dir = os.environ.get("DBO_DATA_DIR")
        os.environ["DBO_DATA_DIR"] = str(data_dir)
        try:
            command.upgrade(Config("alembic.ini"), "head")
        finally:
            if previous_data_dir is None:
                os.environ.pop("DBO_DATA_DIR", None)
            else:
                os.environ["DBO_DATA_DIR"] = previous_data_dir
        settings = Settings(
            _env_file=None,
            data_dir=data_dir,
            allow_insecure_cookies=True,
            gemini_api_key=None,
            runtime_env_file=env_file,
        )
        with TestClient(create_app(settings)) as client:
            csrf = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
            headers = {"Origin": settings.public_origin, "X-CSRF-Token": csrf}
            response = client.post(
                "/api/v1/auth/register",
                headers=headers,
                json={"email": f"live-smoke-{uuid4()}@example.test", "password": "synthetic-smoke-password"},
            )
            assert response.status_code == 201, response.json().get("error")

            def upload(filename):
                response = client.post(
                    "/api/v1/datasets",
                    headers=headers,
                    files=[("files", (filename, (ROOT / "sample_data" / filename).read_bytes(), "text/csv"))],
                )
                assert response.status_code == 200, response.json().get("error")
                return response.json()["data"][0]["dataset"]

            flat = upload("analysis_flat.csv")
            response = client.post("/api/v1/conversations", headers=headers, json={"dataset_ids": [flat["id"]]})
            assert response.status_code == 201, response.json().get("error")
            cid = response.json()["data"]["id"]

            def ask(conversation_id, question, **extra):
                response = client.post(
                    f"/api/v1/conversations/{conversation_id}/messages",
                    headers=headers,
                    json={"question": question, **extra},
                )
                if response.status_code != 200:
                    code = response.json().get("error", {}).get("code")
                    if code == "SQL_REJECTED":
                        with client.app.state.sessions() as db:
                            latest = db.query(Analysis).order_by(Analysis.created_at.desc()).first()
                            planned_sql = json.loads(latest.plan_json).get("sql") if latest else None
                            print("Rejected synthetic SQL: " + str(planned_sql)[:800], file=sys.stderr)
                    raise RuntimeError(f"Analysis HTTP {response.status_code}: {code}")
                data = response.json()["data"]
                if data["status"] != "complete":
                    raise RuntimeError(f"Analysis status: {data['status']}")
                return data

            first = ask(
                cid, "What is the total revenue in USD for the South region? Use quantity times unit_price_usd."
            )
            assert len(first["table"]["rows"]) == 1
            assert expected_south in numbers(first["table"]["rows"][0])
            print("Live Gemini single-source South revenue: matched independent expectation")

            follow = ask(cid, "Now break that down by month, ordered chronologically.")
            assert len(follow["table"]["rows"]) == len(monthly)
            for row, expected in zip(follow["table"]["rows"], monthly.values(), strict=True):
                assert expected in numbers(row)
            print("Live Gemini contextual monthly follow-up: matched independent expectation")

            sales = upload("sales.csv")
            customers = upload("customers.csv")
            response = client.post(
                "/api/v1/conversations", headers=headers, json={"dataset_ids": [sales["id"], customers["id"]]}
            )
            assert response.status_code == 201, response.json().get("error")
            join_cid = response.json()["data"]["id"]
            response = client.post(
                f"/api/v1/conversations/{join_cid}/joins",
                headers=headers,
                json={
                    "joins": [
                        {
                            "left": sales["id"],
                            "right": customers["id"],
                            "left_key": "c3",
                            "right_key": "c1",
                            "type": "inner",
                        }
                    ]
                },
            )
            assert response.status_code == 200, response.json().get("error")
            proposal = response.json()["data"]
            joined = ask(
                join_cid,
                "Using the confirmed sales-to-customers join, what is total revenue in USD across all sales? "
                "Calculate SUM(sales quantity times sales unit_price_usd).",
                join_confirmation=proposal["id"],
                accept_multiplication=True,
            )
            assert len(joined["table"]["rows"]) == 1
            assert expected_all in numbers(joined["table"]["rows"][0])
            print("Live Gemini confirmed cross-file revenue: matched independent expectation")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Live smoke stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
