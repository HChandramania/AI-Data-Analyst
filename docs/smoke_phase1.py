"""HTTP smoke through the live Next.js proxy and FastAPI server."""

from pathlib import Path
from argparse import ArgumentParser
from uuid import uuid4

import httpx

root = Path(__file__).resolve().parents[1]
parser = ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:3000")
args = parser.parse_args()
with httpx.Client(base_url=args.base_url, timeout=60, follow_redirects=False) as client:
    assert client.get("/datasets").status_code in (302, 307)
    token = client.get("/api/v1/auth/csrf").json()["data"]["csrf_token"]
    headers = {"Origin": args.base_url, "X-CSRF-Token": token}
    email = f"smoke-{uuid4()}@example.test"
    registered = client.post("/api/v1/auth/register", headers=headers,
                             json={"email": email, "password": "synthetic-smoke-password"})
    assert registered.status_code == 201, registered.text
    assert client.get("/api/v1/auth/me").json()["data"]["email"] == email
    assert client.get("/datasets").status_code == 200
    assert client.get("/analyze").status_code == 200
    with (root / "sample_data/sales.csv").open("rb") as sales, \
         (root / "sample_data/customers.csv").open("rb") as customers, \
         (root / "sample_data/products.csv").open("rb") as products:
        response = client.post("/api/v1/datasets", headers=headers, files=[
            ("files", ("sales.csv", sales, "text/csv")),
            ("files", ("customers.csv", customers, "text/csv")),
            ("files", ("products.csv", products, "text/csv")),
        ])
    assert response.status_code == 200, response.text
    datasets = response.json()["data"]
    assert [item["status"] for item in datasets] == ["accepted"] * 3, response.text
    assert [item["dataset"]["profile"]["row_count"] for item in datasets] == [24, 6, 3]
    assert len(client.get("/api/v1/datasets").json()["data"]) == 3
    for item in datasets:
        dataset_id = item["dataset"]["id"]
        assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 200
        assert client.get(f"/api/v1/datasets/{dataset_id}/preview").json()["data"]["returned_rows"] > 0
    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert len(logout.headers.get_list("set-cookie")) == 2
    assert client.get("/api/v1/datasets").status_code == 401
    assert client.get("/datasets").status_code in (302, 307)
print("Phase 1 proxy flow passed: register, upload 3, inspect, logout, denied")
