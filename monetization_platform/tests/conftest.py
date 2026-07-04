"""Pytest fixtures.

Configures a fully offline environment (mock Stripe + mock LLM + a throwaway
SQLite database) BEFORE the application modules are imported, so the whole suite
passes with no real keys.
"""

from __future__ import annotations

import os
import tempfile

# --- Configure the environment before importing the app --------------------
_TMP_DB = os.path.join(tempfile.gettempdir(), "mp_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ.pop("STRIPE_API_KEY", None)  # ensure mock Stripe mode
os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
os.environ["SIGNUP_BONUS_CREDITS"] = "25"
os.environ["BASE_URL"] = "http://testserver"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from monetization_platform.app import app  # noqa: E402
from monetization_platform.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    """Reset the schema before every test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def account(client):
    """Create a user and return (api_key, auth headers, signup payload)."""
    resp = client.post("/auth/signup", json={"email": "user@example.com"})
    assert resp.status_code == 201, resp.text
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['api_key']}"}
    return {"api_key": data["api_key"], "headers": headers, "signup": data}
