"""Wallet operations backed by the immutable usage-event ledger.

Every mutation of a user's balance goes through here so that the ledger and the
cached ``users.credits`` column can never drift apart.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import UsageEvent, User


class OutOfCreditsError(Exception):
    """Raised when a debit would take the balance below zero."""

    def __init__(self, required: int, available: int) -> None:
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient credits: need {required}, have {available}."
        )


def credit_wallet(
    session: Session,
    user: User,
    amount: int,
    *,
    description: str = "",
    reference: Optional[str] = None,
    agent: Optional[str] = None,
) -> UsageEvent:
    """Add credits to a wallet and record a ``credit`` ledger event."""
    if amount <= 0:
        raise ValueError("Credit amount must be positive.")
    user.credits += amount
    event = UsageEvent(
        user_id=user.id,
        kind="credit",
        agent=agent,
        credits_delta=amount,
        balance_after=user.credits,
        description=description,
        reference=reference,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def debit_wallet(
    session: Session,
    user: User,
    amount: int,
    *,
    agent: str,
    tokens: int = 0,
    usd_cost: float = 0.0,
    description: str = "",
    reference: Optional[str] = None,
) -> UsageEvent:
    """Deduct credits for agent usage, recording a ``debit`` ledger event.

    Raises :class:`OutOfCreditsError` if the balance is insufficient.
    """
    if amount < 0:
        raise ValueError("Debit amount must be non-negative.")
    if user.credits < amount:
        raise OutOfCreditsError(required=amount, available=user.credits)
    user.credits -= amount
    event = UsageEvent(
        user_id=user.id,
        kind="debit",
        agent=agent,
        credits_delta=-amount,
        balance_after=user.credits,
        tokens=tokens,
        usd_cost=usd_cost,
        description=description,
        reference=reference,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def recent_events(session: Session, user: User, limit: int = 20) -> List[UsageEvent]:
    """Return the most recent ledger events for a user (newest first)."""
    stmt = (
        select(UsageEvent)
        .where(UsageEvent.user_id == user.id)
        .order_by(UsageEvent.created_at.desc(), UsageEvent.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())
