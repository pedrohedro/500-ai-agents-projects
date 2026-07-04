"""Landing page + health tests."""

from __future__ import annotations


def test_landing_renders_with_pricing(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "text/html" in resp.headers["content-type"]
    # All three pricing tiers present.
    assert "Starter" in html
    assert "Pro" in html
    assert "Business" in html
    # Signup form + agents present.
    assert 'id="signup-form"' in html
    assert "/v1/marketing/generate" in html


def test_dashboard_renders(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Your dashboard" in resp.text


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["llm_provider"] == "mock"
    assert data["stripe_enabled"] is False
