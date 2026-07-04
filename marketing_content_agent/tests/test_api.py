"""Webhook API tests. Skipped automatically if FastAPI/httpx aren't installed
(the core product does not require them)."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from marketing_content_agent.scheduler import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_generate_endpoint(client):
    resp = client.post(
        "/generate",
        json={"topic": "Autonomous marketing", "target_audience": "founders"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blog_post"]
    assert body["qa"]["passed"] is True


def test_generate_deducts_credits(client):
    resp = client.post("/generate", json={"topic": "Billing", "credits": 10})
    assert resp.status_code == 200
    assert resp.json()["credits_remaining"] == 5


def test_generate_out_of_credits_returns_402(client):
    resp = client.post("/generate", json={"topic": "Broke", "credits": 0})
    assert resp.status_code == 402


def test_generate_rejects_empty_topic(client):
    resp = client.post("/generate", json={"topic": ""})
    assert resp.status_code == 422
