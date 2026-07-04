"""Monetization: credit-based, per-document billing.

Pricing model
-------------
Each document review is charged as::

    price = flat_fee_per_document + (estimated_tokens / 1000) * price_per_1k_tokens

Our underlying API cost is estimated with ``api_cost_per_1k_tokens`` so we can
report the margin. Customers pre-purchase *credits* (a stored balance in the
account currency). Each review deducts its price from the balance; when the
balance is insufficient the review is blocked with :class:`OutOfCreditsError`.

A Stripe checkout stub is included and cleanly disabled unless ``STRIPE_API_KEY``
is set.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from config import Settings, get_settings


class BillingError(Exception):
    pass


class OutOfCreditsError(BillingError):
    """Raised when an account does not have enough credits for a review."""


@dataclass
class CostEstimate:
    tokens: int
    price: float
    api_cost: float
    margin: float
    margin_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens": self.tokens,
            "price": round(self.price, 4),
            "api_cost": round(self.api_cost, 4),
            "margin": round(self.margin, 4),
            "margin_pct": round(self.margin_pct, 2),
        }


def estimate_cost(tokens: int, settings: Optional[Settings] = None) -> CostEstimate:
    """Estimate the customer price, our API cost and the resulting margin."""
    settings = settings or get_settings()
    tokens = max(0, int(tokens))
    variable = (tokens / 1000.0) * settings.price_per_1k_tokens
    price = settings.flat_fee_per_document + variable
    api_cost = (tokens / 1000.0) * settings.api_cost_per_1k_tokens
    margin = price - api_cost
    margin_pct = (margin / price * 100.0) if price > 0 else 0.0
    return CostEstimate(
        tokens=tokens,
        price=round(price, 4),
        api_cost=round(api_cost, 4),
        margin=round(margin, 4),
        margin_pct=round(margin_pct, 2),
    )


class CreditAccount:
    """A simple file-backed credit balance.

    Persistence is optional: pass ``path=None`` for an in-memory account (used by
    tests). The balance is stored as a float in the account currency.
    """

    def __init__(self, balance: float = 0.0, path: Optional[str] = None):
        self._path = path
        if path and os.path.isfile(path):
            self._balance = self._load()
        else:
            self._balance = float(balance)
            if path:
                self._save()

    # -- persistence ------------------------------------------------------
    def _load(self) -> float:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                return float(json.load(fh).get("balance", 0.0))
        except Exception:
            return 0.0

    def _save(self) -> None:
        if not self._path:
            return
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump({"balance": round(self._balance, 6)}, fh)

    # -- operations -------------------------------------------------------
    @property
    def balance(self) -> float:
        return round(self._balance, 6)

    def add_credits(self, amount: float) -> float:
        if amount < 0:
            raise BillingError("Cannot add a negative amount of credits.")
        self._balance += float(amount)
        self._save()
        return self.balance

    def can_afford(self, price: float) -> bool:
        return self._balance + 1e-9 >= price

    def charge(self, price: float, description: str = "document review") -> float:
        """Deduct ``price`` from the balance or raise :class:`OutOfCreditsError`."""
        if price < 0:
            raise BillingError("Charge amount cannot be negative.")
        if not self.can_afford(price):
            raise OutOfCreditsError(
                f"Insufficient credits for {description}: need {price:.4f}, "
                f"have {self._balance:.4f}. Top up to continue."
            )
        self._balance -= price
        self._save()
        return self.balance


class BillingManager:
    """High-level façade tying cost estimation to a credit account."""

    def __init__(self, account: CreditAccount, settings: Optional[Settings] = None):
        self.account = account
        self.settings = settings or get_settings()

    def estimate(self, tokens: int) -> CostEstimate:
        return estimate_cost(tokens, self.settings)

    def charge_for_review(self, tokens: int, document_name: str = "document") -> Dict[str, Any]:
        """Charge for a completed review; raises OutOfCreditsError when broke."""
        estimate = self.estimate(tokens)
        remaining = self.account.charge(estimate.price, f"review of {document_name}")
        return {
            "charged": estimate.price,
            "remaining_balance": remaining,
            "estimate": estimate.to_dict(),
        }

    def preauthorize(self, tokens: int) -> bool:
        """Check affordability *before* running an expensive review."""
        return self.account.can_afford(self.estimate(tokens).price)


# ---------------------------------------------------------------------------
# Stripe checkout stub (disabled without STRIPE_API_KEY)
# ---------------------------------------------------------------------------


def create_checkout_session(
    amount_usd: float,
    settings: Optional[Settings] = None,
    success_url: str = "https://example.com/success",
    cancel_url: str = "https://example.com/cancel",
) -> Dict[str, Any]:
    """Create a Stripe checkout session for buying credits.

    Cleanly disabled when ``STRIPE_API_KEY`` is not configured: returns a stub
    payload marked ``enabled=False`` instead of raising, so the rest of the
    product keeps working with no keys.
    """
    settings = settings or get_settings()
    if not settings.stripe_enabled:
        return {
            "enabled": False,
            "reason": "STRIPE_API_KEY not set; billing checkout is disabled.",
            "amount_usd": round(amount_usd, 2),
            "checkout_url": None,
        }

    try:  # pragma: no cover - requires the stripe package + a real key
        import stripe  # type: ignore

        stripe.api_key = settings.stripe_api_key
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "Legal Reviewer credits"},
                        "unit_amount": int(round(amount_usd * 100)),
                    },
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {
            "enabled": True,
            "amount_usd": round(amount_usd, 2),
            "checkout_url": session.url,
            "session_id": session.id,
        }
    except Exception as exc:  # pragma: no cover
        return {
            "enabled": False,
            "reason": f"Stripe error: {exc}",
            "amount_usd": round(amount_usd, 2),
            "checkout_url": None,
        }
