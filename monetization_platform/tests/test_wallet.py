"""Direct wallet + ledger unit tests."""

from __future__ import annotations

import pytest

from monetization_platform.database import SessionLocal
from monetization_platform.models import User
from monetization_platform.wallet import (
    OutOfCreditsError,
    credit_wallet,
    debit_wallet,
    recent_events,
)


def _make_user(session) -> User:
    user = User(email="wallet@example.com", credits=0)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_credit_and_debit_updates_balance_and_ledger():
    session = SessionLocal()
    try:
        user = _make_user(session)
        credit_wallet(session, user, 100, description="topup")
        assert user.credits == 100

        debit_wallet(session, user, 30, agent="marketing", tokens=50, usd_cost=0.01)
        assert user.credits == 70

        events = recent_events(session, user)
        assert len(events) == 2
        # newest first: the debit
        assert events[0].kind == "debit"
        assert events[0].credits_delta == -30
        assert events[0].balance_after == 70
        assert events[0].agent == "marketing"
        assert events[0].tokens == 50

        # Ledger sum must reconstruct the balance exactly.
        assert sum(e.credits_delta for e in events) == user.credits
    finally:
        session.close()


def test_debit_beyond_balance_raises():
    session = SessionLocal()
    try:
        user = _make_user(session)
        credit_wallet(session, user, 5, description="topup")
        with pytest.raises(OutOfCreditsError):
            debit_wallet(session, user, 10, agent="legal")
        # Balance unchanged after failed debit.
        assert user.credits == 5
    finally:
        session.close()
