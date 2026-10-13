"""Verify an already-running local server and optionally save actual evidence."""

import argparse
import json
from pathlib import Path

import httpx


def verify(base_url):
    with httpx.Client(
        base_url=base_url, follow_redirects=False, timeout=10, trust_env=False
    ) as client:
        health = client.get("/health")
        assert health.status_code == 200
        schema = client.get("/openapi.json")
        assert schema.status_code == 200 and "/api/urls" in schema.json()["paths"]
        created = client.post("/api/urls", json={"url": "https://example.com/smoke"})
        assert created.status_code == 201
        code = created.json()["shortCode"]
        redirect = client.get("/" + code)
        assert redirect.status_code == 307
        analytics = client.get(f"/api/urls/{code}/analytics")
        assert analytics.json()["totalClicks"] == 1
        report = {
            "health_status": health.status_code,
            "openapi_status": schema.status_code,
            "create_status": created.status_code,
            "redirect_status": redirect.status_code,
            "analytics_status": analytics.status_code,
            "analytics": analytics.json(),
            "live_llm_verified": False,
        }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = verify(args.base_url)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
