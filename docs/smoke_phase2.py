"""Disposable Phase 2 proxy smoke without pretending a provider is configured."""

from argparse import ArgumentParser
from pathlib import Path
from uuid import uuid4

import httpx

parser = ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:3102")
args = parser.parse_args()
fixture = Path(__file__).resolve().parents[1] / "sample_data" / "analysis_flat.csv"

with httpx.Client(base_url=args.base_url, timeout=60) as client:
    csrf = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    headers = {"Origin": args.base_url, "X-CSRF-Token": csrf}
    account = client.post("/api/v1/auth/register", headers=headers, json={
        "email": f"phase2-{uuid4()}@example.test", "password": "synthetic-smoke-password",
    })
    assert account.status_code == 201, account.text
    with fixture.open("rb") as csv:
        upload = client.post("/api/v1/datasets", headers=headers,
                             files=[("files", ("analysis_flat.csv", csv, "text/csv"))])
    assert upload.status_code == 200, upload.text
    dataset = upload.json()["data"][0]["dataset"]
    conversation = client.post("/api/v1/conversations", headers=headers,
                               json={"dataset_ids": [dataset["id"]]})
    assert conversation.status_code == 201, conversation.text
    conversation_id = conversation.json()["data"]["id"]
    failed = client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers,
                         json={"question": "Highest revenue region?"})
    assert failed.status_code == 503, failed.text
    assert failed.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    detail = client.get(f"/api/v1/conversations/{conversation_id}").json()["data"]
    assert detail["analyses"][0]["status"] == "failed"
    assert detail["analyses"][0]["table"] is None
    assert len(detail["messages"]) == 2
    print("Phase 2 proxy flow passed: account, upload, conversation, honest provider failure, persisted state")
