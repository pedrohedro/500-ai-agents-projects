"""ORM models: users, API keys, and the immutable usage/credit ledger.

The wallet balance lives on the ``User`` row; every credit or debit is recorded
as an immutable row in ``usage_events`` so the balance is always auditable.
"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    api_keys: Mapped[List["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    events: Mapped[List["UsageEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    # Only the SHA-256 hash of the key is stored; the raw key is shown once.
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(120), default="default", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="api_keys")


class UsageEvent(Base):
    """Immutable ledger row.

    ``kind`` is either ``credit`` (money in / grant) or ``debit`` (agent usage).
    ``credits_delta`` is positive for credits, negative for debits so a simple
    SUM reconstructs the balance.
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # credit | debit
    agent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    credits_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usd_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, index=True, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="events")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "agent": self.agent,
            "credits_delta": self.credits_delta,
            "balance_after": self.balance_after,
            "tokens": self.tokens,
            "usd_cost": round(self.usd_cost, 6),
            "description": self.description,
            "reference": self.reference,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
