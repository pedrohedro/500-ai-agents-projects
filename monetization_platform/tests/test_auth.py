"""Signup + authentication tests."""

from __future__ import annotations


def test_signup_issues_api_key_and_bonus(client):
    resp = client.post("/auth/signup", json={"email": "New@Example.com"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["api_key"].startswith("sk_live_")
    assert data["email"] == "new@example.com"  # normalized lower-case
    assert data["credits"] == 25  # signup bonus


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "dup@example.com"})
    resp = client.post("/auth/signup", json={"email": "dup@example.com"})
    assert resp.status_code == 409


def test_signup_invalid_email_rejected(client):
    resp = client.post("/auth/signup", json={"email": "not-an-email"})
    assert resp.status_code == 422


def test_me_requires_valid_key(client, account):
    # No auth header -> 401
    assert client.get("/auth/me").status_code == 401
    # Bad key -> 401
    assert client.get(
        "/auth/me", headers={"Authorization": "Bearer sk_live_bogus"}
    ).status_code == 401
    # Good key -> 200
    resp = client.get("/auth/me", headers=account["headers"])
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@example.com"


def test_api_key_is_hashed_not_stored_raw(client, account):
    """The raw key must never be retrievable from the database."""
    from monetization_platform.database import SessionLocal
    from monetization_platform.models import ApiKey

    session = SessionLocal()
    try:
        keys = session.query(ApiKey).all()
        assert keys, "expected at least one api key"
        raw = account["api_key"]
        for k in keys:
            assert k.key_hash != raw
            assert len(k.key_hash) == 64  # sha-256 hex digest
    finally:
        session.close()
