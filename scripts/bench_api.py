import time
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

endpoints = [
    ('GET', '/dashboard'),
    ('GET', '/ledger?page=1&page_size=10'),
    ('GET', '/ledger?department=West%20Bengal&status=UNVERIFIED&page=1&page_size=5'),
    ('GET', '/calendar?month=2023-10'),
    ('GET', '/export.csv?status=COMPLIED'),
    ('GET', '/judgments?limit=5'),
    ('GET', '/judgments/160'),
    ('GET', '/judgments/160/directions'),
    ('GET', '/directions/1'),
    ('GET', '/directions/1/timeline'),
    ('GET', '/cases/MAT%2F408%2F2022/timeline'),
    ('GET', '/stats/links'),
    ('GET', '/agent/runs'),
]

header = f"{'METHOD':<6} {'ENDPOINT':<50} {'STATUS':<8} {'LATENCY':<10} {'CONTENT SUMMARY'}"
print(header)
print('-' * len(header))

for method, ep in endpoints:
    t0 = time.perf_counter()
    r = client.get(ep)
    t1 = time.perf_counter()
    lat_ms = (t1 - t0) * 1000.0
    status = r.status_code
    if ep.endswith('.csv') or '.csv?' in ep:
        summary = f"{len(r.text.splitlines())} CSV lines ({len(r.content)} bytes)"
    else:
        try:
            data = r.json()
            if isinstance(data, dict):
                keys = list(data.keys())[:4]
                summary = f"dict with keys {keys}"
            elif isinstance(data, list):
                summary = f"list with {len(data)} items"
            else:
                summary = str(data)[:40]
        except Exception:
            summary = f"{len(r.content)} bytes"
    print(f"{method:<6} {ep:<50} {status:<8} {lat_ms:6.2f}ms   {summary}")

