"""Metered agent gateway tests: deduction, 402, ledger, and all four agents."""

from __future__ import annotations


MARKETING_PAYLOAD = {"topic": "AI for small business", "audience": "founders"}
LEGAL_PAYLOAD = {
    "document_text": "This Agreement is between Acme and Beta. Term: 12 months. "
    "Either party may terminate with 30 days notice.",
    "document_name": "msa.txt",
}
SUPPORT_PAYLOAD = {"question": "How do I reset my password?"}
HR_PAYLOAD = {
    "job_description": "Senior Python engineer with 5 years experience in APIs.",
    "resumes": [
        {"id": "alice", "text": "Alice. Python, FastAPI, 6 years experience."},
        {"id": "bob", "text": "Bob. Java developer, 2 years experience."},
    ],
}


def test_gateway_requires_auth(client):
    assert client.post("/v1/marketing/generate", json=MARKETING_PAYLOAD).status_code == 401


def test_marketing_call_deducts_credits_and_logs(client, account):
    headers = account["headers"]
    before = client.get("/auth/me", headers=headers).json()["credits"]

    resp = client.post("/v1/marketing/generate", json=MARKETING_PAYLOAD, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent"] == "marketing"
    assert body["credits_charged"] == 5
    assert body["credits_remaining"] == before - 5
    assert "output" in body and body["output"]

    # Ledger recorded a debit event for the marketing agent.
    balance = client.get("/billing/balance", headers=headers).json()
    assert balance["credits"] == before - 5
    debit = balance["recent_events"][0]
    assert debit["kind"] == "debit"
    assert debit["agent"] == "marketing"
    assert debit["credits_delta"] == -5


def test_all_four_agents_callable(client, account):
    headers = account["headers"]
    # Top up so every agent call succeeds.
    client.post("/billing/simulate-payment", json={"pack_key": "starter"}, headers=headers)

    cases = [
        ("/v1/marketing/generate", MARKETING_PAYLOAD, "marketing", 5),
        ("/v1/legal/review", LEGAL_PAYLOAD, "legal", 8),
        ("/v1/support/chat", SUPPORT_PAYLOAD, "support", 1),
        ("/v1/hr/screen", HR_PAYLOAD, "hr", 3),
    ]
    for endpoint, payload, agent, cost in cases:
        resp = client.post(endpoint, json=payload, headers=headers)
        assert resp.status_code == 200, f"{endpoint}: {resp.text}"
        body = resp.json()
        assert body["agent"] == agent
        assert body["credits_charged"] == cost
        assert body["output"]
        assert "usage" in body


def test_out_of_credits_returns_402(client, account):
    headers = account["headers"]
    # Signup grants 25 credits; marketing costs 5 -> 5 calls succeed, 6th fails.
    for i in range(5):
        r = client.post("/v1/marketing/generate", json=MARKETING_PAYLOAD, headers=headers)
        assert r.status_code == 200, f"call {i}: {r.text}"

    assert client.get("/auth/me", headers=headers).json()["credits"] == 0

    r = client.post("/v1/marketing/generate", json=MARKETING_PAYLOAD, headers=headers)
    assert r.status_code == 402, r.text
    assert "Insufficient credits" in r.json()["detail"]

    # A failed (402) call must NOT create a debit ledger event.
    events = client.get("/billing/balance", headers=headers).json()["recent_events"]
    debits = [e for e in events if e["kind"] == "debit"]
    assert len(debits) == 5


def test_full_money_loop(client, account):
    """signup -> pay -> balance up -> spend -> balance down -> ledger."""
    headers = account["headers"]
    start = client.get("/auth/me", headers=headers).json()["credits"]
    assert start == 25

    pay = client.post(
        "/billing/simulate-payment", json={"pack_key": "starter"}, headers=headers
    ).json()
    assert pay["balance"] == start + 1000

    call = client.post("/v1/legal/review", json=LEGAL_PAYLOAD, headers=headers).json()
    assert call["credits_remaining"] == start + 1000 - 8

    balance = client.get("/billing/balance", headers=headers).json()
    kinds = [e["kind"] for e in balance["recent_events"]]
    assert "credit" in kinds and "debit" in kinds
