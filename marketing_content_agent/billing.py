"""Credit-based billing with cost estimation and a Stripe checkout stub.

Design goals:
- Estimate token usage -> API cost using a configurable price-per-1k table.
- Charge a fixed number of credits per generation and block when out.
- Provide a Stripe checkout that cleanly disables itself without STRIPE_API_KEY.

No third-party dependency is required for the credit ledger; Stripe is imported
lazily and only used when a key is present.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import Settings, get_settings


class OutOfCreditsError(RuntimeError):
    """Raised when a wallet lacks the credits required for a generation."""


@dataclass
class Transaction:
    kind: str  # "debit" | "credit"
    amount: int
    reason: str
    balance_after: int


@dataclass
class Wallet:
    """A simple in-memory credit ledger.

    In production this would be backed by a database row per customer; the API
    (charge/top_up/balance) is intentionally storage-agnostic.
    """

    balance: int = 0
    history: List[Transaction] = field(default_factory=list)

    def top_up(self, amount: int, reason: str = "top_up") -> Transaction:
        if amount <= 0:
            raise ValueError("Top-up amount must be positive.")
        self.balance += amount
        tx = Transaction("credit", amount, reason, self.balance)
        self.history.append(tx)
        return tx

    def can_afford(self, amount: int) -> bool:
        return self.balance >= amount

    def charge(self, amount: int, reason: str = "generation") -> Transaction:
        if amount < 0:
            raise ValueError("Charge amount cannot be negative.")
        if not self.can_afford(amount):
            raise OutOfCreditsError(
                f"Insufficient credits: need {amount}, have {self.balance}."
            )
        self.balance -= amount
        tx = Transaction("debit", amount, reason, self.balance)
        self.history.append(tx)
        return tx


@dataclass
class CostEstimate:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    api_cost_usd: float
    credits: int
    retail_price_usd: float
    margin_usd: float


class BillingEngine:
    """Computes cost estimates and applies the per-generation credit policy."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> CostEstimate:
        price = self.settings.model_price()
        input_cost = (prompt_tokens / 1000.0) * price.get("input", 0.0)
        output_cost = (completion_tokens / 1000.0) * price.get("output", 0.0)
        api_cost = input_cost + output_cost
        credits = self.settings.credits_per_generation
        retail_price = credits * self.settings.credit_price_usd
        return CostEstimate(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            input_cost_usd=round(input_cost, 8),
            output_cost_usd=round(output_cost, 8),
            api_cost_usd=round(api_cost, 8),
            credits=credits,
            retail_price_usd=round(retail_price, 4),
            margin_usd=round(retail_price - api_cost, 4),
        )

    def credits_for_generation(self) -> int:
        return self.settings.credits_per_generation

    def charge_for_generation(
        self, wallet: Wallet, reason: str = "content_generation"
    ) -> Transaction:
        """Deduct credits for one generation; raises OutOfCreditsError if broke."""
        return wallet.charge(self.credits_for_generation(), reason=reason)


class StripeCheckout:
    """Stripe checkout stub that is disabled without STRIPE_API_KEY.

    When enabled and the ``stripe`` SDK is installed, ``create_checkout_session``
    creates a real session. Otherwise it returns a clearly-marked disabled
    response so the rest of the app keeps working offline.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.stripe_api_key)

    def create_checkout_session(
        self,
        *,
        credits: int,
        success_url: str = "https://example.com/success",
        cancel_url: str = "https://example.com/cancel",
    ) -> Dict:
        if not self.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": (
                    "Stripe is disabled: set STRIPE_API_KEY (and STRIPE_PRICE_ID) to "
                    "enable real checkout."
                ),
                "credits": credits,
                "amount_usd": round(credits * self.settings.credit_price_usd, 2),
            }

        try:  # pragma: no cover - requires stripe SDK + network
            import stripe  # type: ignore

            stripe.api_key = self.settings.stripe_api_key
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[
                    {
                        "price": self.settings.stripe_price_id,
                        "quantity": credits,
                    }
                ],
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return {
                "enabled": True,
                "status": "created",
                "id": session.get("id"),
                "url": session.get("url"),
                "credits": credits,
            }
        except Exception as exc:  # pragma: no cover - network/SDK dependent
            return {
                "enabled": True,
                "status": "error",
                "message": f"Stripe error: {exc}",
                "credits": credits,
            }
