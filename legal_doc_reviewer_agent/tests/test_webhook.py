"""Tests for the FastAPI webhook. Skipped cleanly if FastAPI isn't installed."""
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scheduler import build_app  # noqa: E402

CONTRACT = (
    "1. CONFIDENTIALITY. Keep confidential in perpetuity. "
    "2. PAYMENT. Net 90, non-refundable. "
    "3. LIABILITY. Provider shall have unlimited liability."
)


@pytest.fixture
def client():
    return TestClient(build_app())


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_review_endpoint(client):
    resp = client.post("/review", json={"text": CONTRACT})
    assert resp.status_code == 200
    body = resp.json()
    assert "json" in body and "markdown" in body
    assert body["json"]["overall_risk_score"] >= 0
    assert body["json"]["risks"]


def test_review_requires_input(client):
    resp = client.post("/review", json={})
    assert resp.status_code == 400
