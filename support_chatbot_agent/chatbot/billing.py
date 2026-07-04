"""Monetization primitives: credits, per-seat plans and cost estimation.

The design bills per *answered message* using estimated token usage and a
configurable price-per-1k-tokens. Escalated (unanswered) messages are billed at
a lower/optional rate. A Stripe checkout stub is included but cleanly disabled
unless ``STRIPE_API_KEY`` is set.

Nothing here talks to a real database -- accounts live in memory so the MVP runs
end-to-end offline. Swapping :class:`InMemoryBillingStore` for a real store is
the production upgrade path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .config import Config


class OutOfCreditsError(Exception):
    """Raised when an account has insufficient credits for a charge."""


@dataclass(frozen=True)
class Plan:
    """A subscription plan. Price is per seat / month; credits are per seat."""

    key: str
    name: str
    price_per_seat_month: float
    monthly_credits_per_seat: float  # USD of answer spend included per seat
    seats_included: int


# Reference pricing. Margin comes from the spread between ``price_per_1k_tokens``
# billed to customers and ``api_cost_per_1k_tokens`` we pay the LLM provider.
PLANS: Dict[str, Plan] = {
    "free": Plan("free", "Free", 0.0, 1.0, 1),
    "starter": Plan("starter", "Starter", 49.0, 25.0, 3),
    "growth": Plan("growth", "Growth", 199.0, 120.0, 10),
    "scale": Plan("scale", "Scale", 599.0, 400.0, 30),
}


@dataclass
class Account:
    """A billable customer account (a workspace / team)."""

    account_id: str
    plan_key: str = "free"
    seats: int = 1
    credits: float = 0.0  # remaining answer-spend budget, in USD
    messages_answered: int = 0
    messages_escalated: int = 0
    total_tokens: int = 0
    total_charged: float = 0.0

    @property
    def plan(self) -> Plan:
        return PLANS.get(self.plan_key, PLANS["free"])


@dataclass
class ChargeResult:
    charged: bool
    amount: float
    tokens: int
    api_cost: float
    margin: float
    remaining_credits: float
    reason: str = ""


class BillingEngine:
    """Estimates cost per message and manages credit deduction."""

    def __init__(self, config: Config, store: Optional["InMemoryBillingStore"] = None) -> None:
        self.config = config
        self.store = store or InMemoryBillingStore()

    # -- account lifecycle ----------------------------------------------
    def create_account(self, account_id: str, plan_key: str = "free", seats: int = 1) -> Account:
        plan = PLANS.get(plan_key, PLANS["free"])
        seats = max(seats, 1)
        account = Account(
            account_id=account_id,
            plan_key=plan.key,
            seats=seats,
            credits=plan.monthly_credits_per_seat * seats,
        )
        self.store.put(account)
        return account

    def get_account(self, account_id: str) -> Account:
        account = self.store.get(account_id)
        if account is None:
            account = self.create_account(account_id, "free", 1)
        return account

    # -- cost model ------------------------------------------------------
    def estimate_cost(self, tokens: int) -> float:
        """Customer-facing price for a given token count."""
        return (tokens / 1000.0) * self.config.price_per_1k_tokens

    def estimate_api_cost(self, tokens: int) -> float:
        """What we pay the LLM provider for a given token count."""
        return (tokens / 1000.0) * self.config.api_cost_per_1k_tokens

    def preview(self, tokens: int) -> ChargeResult:
        amount = self.estimate_cost(tokens)
        api_cost = self.estimate_api_cost(tokens)
        return ChargeResult(
            charged=False,
            amount=round(amount, 6),
            tokens=tokens,
            api_cost=round(api_cost, 6),
            margin=round(amount - api_cost, 6),
            remaining_credits=0.0,
        )

    # -- charging --------------------------------------------------------
    def charge_message(self, account_id: str, tokens: int, answered: bool = True) -> ChargeResult:
        """Deduct the cost of one message. Raises if out of credits.

        Escalated messages (``answered=False``) are not charged -- customers only
        pay for value delivered, which is a strong selling point.
        """
        account = self.get_account(account_id)
        amount = self.estimate_cost(tokens)
        api_cost = self.estimate_api_cost(tokens)

        if not answered:
            account.messages_escalated += 1
            self.store.put(account)
            return ChargeResult(
                charged=False,
                amount=0.0,
                tokens=tokens,
                api_cost=round(api_cost, 6),
                margin=0.0,
                remaining_credits=round(account.credits, 6),
                reason="escalated_not_charged",
            )

        if account.credits < amount:
            raise OutOfCreditsError(
                f"Account '{account_id}' is out of credits "
                f"(needs {amount:.4f}, has {account.credits:.4f})."
            )

        account.credits -= amount
        account.messages_answered += 1
        account.total_tokens += tokens
        account.total_charged += amount
        self.store.put(account)

        return ChargeResult(
            charged=True,
            amount=round(amount, 6),
            tokens=tokens,
            api_cost=round(api_cost, 6),
            margin=round(amount - api_cost, 6),
            remaining_credits=round(account.credits, 6),
            reason="answered",
        )

    def add_credits(self, account_id: str, amount: float) -> Account:
        account = self.get_account(account_id)
        account.credits += amount
        self.store.put(account)
        return account


class InMemoryBillingStore:
    """A trivial in-memory account store. Swap for Postgres in production."""

    def __init__(self) -> None:
        self._accounts: Dict[str, Account] = {}

    def get(self, account_id: str) -> Optional[Account]:
        return self._accounts.get(account_id)

    def put(self, account: Account) -> None:
        self._accounts[account.account_id] = account


# ---------------------------------------------------------------------------
# Stripe checkout stub -- disabled unless STRIPE_API_KEY is configured.
# ---------------------------------------------------------------------------
@dataclass
class CheckoutSession:
    enabled: bool
    url: Optional[str] = None
    message: str = ""


def create_checkout_session(config: Config, plan_key: str, seats: int = 1) -> CheckoutSession:
    """Create a Stripe checkout session, or a disabled stub without a key."""
    plan = PLANS.get(plan_key)
    if plan is None:
        return CheckoutSession(enabled=False, message=f"Unknown plan '{plan_key}'.")

    if not config.stripe_enabled:
        return CheckoutSession(
            enabled=False,
            message=(
                "Stripe is not configured (set STRIPE_API_KEY to enable checkout). "
                f"Would subscribe to '{plan.name}' at "
                f"${plan.price_per_seat_month:.0f}/seat/mo x {seats} seats."
            ),
        )

    # Real integration path (only runs when a key is present).
    try:  # pragma: no cover - requires network + real key
        import stripe

        stripe.api_key = config.stripe_api_key
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": config.stripe_price_id, "quantity": seats}],
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )
        return CheckoutSession(enabled=True, url=session.url, message="Checkout session created.")
    except Exception as exc:  # pragma: no cover
        return CheckoutSession(enabled=False, message=f"Stripe error: {exc}")
