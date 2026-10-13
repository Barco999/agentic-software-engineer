from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import update

from app.main import create_app
from app.models import ShortURL
from app.security import URLSafetyPolicy


def test_create_redirect_and_analytics(client):
    response = client.post("/api/urls", json={"url": "https://example.com/article"})
    assert response.status_code == 201
    code = response.json()["shortCode"]
    assert response.json()["createdAt"].endswith("Z")
    redirect = client.get("/" + code, follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.com/article"
    stats = client.get(f"/api/urls/{code}/analytics").json()
    assert stats["totalClicks"] == 1
    assert stats["lastAccessedAt"] is not None


def test_missing_codes(client):
    assert client.get("/missing", follow_redirects=False).status_code == 404
    assert client.get("/api/urls/missing/analytics").status_code == 404


def test_route_order_health_swagger_and_agent_writes(client):
    assert client.get("/health").json()["database"] == "ready"
    assert client.get("/docs").status_code == 200
    assert "post" in client.get("/openapi.json").json()["paths"]["/api/urls"]
    assert client.post("/api/agent/runs", json={}).status_code == 405


def test_custom_collision_and_reserved_code(client):
    body = {"url": "https://example.com", "customCode": "reusable"}
    assert client.post("/api/urls", json=body).status_code == 201
    assert client.post("/api/urls", json=body).status_code == 409
    assert client.post("/api/urls", json={**body, "customCode": "docs"}).status_code == 422


def test_random_collisions_are_bounded(client, monkeypatch):
    calls = []

    def fixed():
        calls.append(1)
        return "fixed77"

    monkeypatch.setattr("app.shortener.generate_code", fixed)
    assert client.post("/api/urls", json={"url": "https://example.com"}).status_code == 201
    assert client.post("/api/urls", json={"url": "https://example.org"}).status_code == 503
    assert len(calls) == 6


def test_expiration_prevents_redirect_and_click(application, client):
    response = client.post(
        "/api/urls",
        json={
            "url": "https://example.com",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201
    code = response.json()["shortCode"]
    with application.state.session_factory() as db:
        db.execute(
            update(ShortURL)
            .where(ShortURL.short_code == code)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        )
        db.commit()
    assert client.get("/" + code, follow_redirects=False).status_code == 410
    assert client.get(f"/api/urls/{code}/analytics").json()["totalClicks"] == 0


def test_past_and_naive_expiration_rejected(client):
    for expiry in ["2000-01-01T00:00:00Z", "2099-01-01T00:00:00"]:
        assert (
            client.post(
                "/api/urls", json={"url": "https://example.com", "expiresAt": expiry}
            ).status_code
            == 422
        )


def test_database_persists_across_app_instances(settings):
    with TestClient(create_app(settings, URLSafetyPolicy(False))) as first:
        code = first.post("/api/urls", json={"url": "https://example.com"}).json()["shortCode"]
    with TestClient(create_app(settings, URLSafetyPolicy(False))) as second:
        assert second.get(f"/api/urls/{code}/analytics").status_code == 200


def test_creation_rate_limit(settings):
    settings.creation_rate_limit = 2
    with TestClient(create_app(settings, URLSafetyPolicy(False))) as client:
        for _ in range(2):
            assert client.post("/api/urls", json={"url": "https://example.com"}).status_code == 201
        assert client.post("/api/urls", json={"url": "https://example.com"}).status_code == 429
