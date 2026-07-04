"""Stripe checkout + webhook tests (mock mode)."""

from __future__ import annotations

import json


def test_list_packs_public(client):
    resp = client.get("/billing/packs")
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()["packs"]}
    assert keys == {"starter", "pro", "business"}


def test_checkout_creates_mock_session(client, account):
    resp = client.post(
        "/billing/checkout", json={"pack_key": "pro"}, headers=account["headers"]
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mock"] is True
    assert data["checkout_url"].startswith("http")
    assert data["pack_key"] == "pro"
    assert data["credits"] == 5000


def test_checkout_unknown_pack_rejected(client, account):
    resp = client.post(
        "/billing/checkout", json={"pack_key": "nope"}, headers=account["headers"]
    )
    assert resp.status_code == 400


def test_checkout_requires_auth(client):
    assert client.post("/billing/checkout", json={"pack_key": "pro"}).status_code == 401


def test_simulate_payment_credits_wallet(client, account):
    before = client.get("/auth/me", headers=account["headers"]).json()["credits"]
    resp = client.post(
        "/billing/simulate-payment",
        json={"pack_key": "starter"},
        headers=account["headers"],
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "credited"
    assert body["credits_added"] == 1000
    after = client.get("/auth/me", headers=account["headers"]).json()["credits"]
    assert after == before + 1000


def test_webhook_credits_wallet(client, account):
    user_id = account["signup"]["user_id"]
    before = account["signup"]["credits"]
    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "client_reference_id": str(user_id),
                "metadata": {
                    "user_id": str(user_id),
                    "pack_key": "business",
                    "credits": "25000",
                },
            }
        },
    }
    resp = client.post(
        "/billing/webhook",
        content=json.dumps(event),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "credited"
    after = client.get("/auth/me", headers=account["headers"]).json()["credits"]
    assert after == before + 25000


def test_webhook_ignores_other_events(client):
    event = {"id": "evt_x", "type": "payment_intent.created", "data": {"object": {}}}
    resp = client.post(
        "/billing/webhook",
        content=json.dumps(event),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
