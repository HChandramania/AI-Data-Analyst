"""Check a running frontend with stdlib HTTP; this is not visual browser testing."""
import argparse
import json
import re
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:3000")
parser.add_argument("--expect-unavailable", action="store_true")
args = parser.parse_args()
base = args.url.rstrip("/")


def get(path):
    try:
        response = urllib.request.urlopen(base + path, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


status, _, raw = get("/analyze")
assert status == 200
html = raw.decode()
assert "Not available yet" in html
assert "Checking service availability" in html
assets = set(re.findall(r'(?:href|src)="(/_next/static/[^\"]+)"', html))
assert assets
for asset in assets:
    assert get(asset)[0] == 200, asset

status, headers, raw = get("/api/v1/health/ready")
body = json.loads(raw)
assert headers["X-Request-ID"] == body["request_id"]
assert headers["Cache-Control"] == "no-store"
if args.expect_unavailable:
    assert status == 503
    assert body["error"]["code"] == "BACKEND_UNAVAILABLE"
    assert body["error"]["details"] == {}
    assert "127.0.0.1" not in raw.decode()
else:
    assert status == 200
    assert body["data"] == {"status": "ready", "phase": 0}

status, _, raw = get("/api/v1/health/not-implemented")
assert status == 404
assert json.loads(raw)["error"]["code"] == "HTTP_404"
print(f"PASS: Analyze, {len(assets)} unique assets, proxy "
      f"{'unavailable' if args.expect_unavailable else 'ready'}, and unknown-probe rejection.")
