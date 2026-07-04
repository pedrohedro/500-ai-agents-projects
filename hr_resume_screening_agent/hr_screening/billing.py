"""Credit-based billing for screening jobs.

Model
-----
* Customers buy *credits* (1 credit == 1 USD by default).
* Each resume screened deducts a price computed from estimated token cost plus
  a configurable margin, OR a flat ``price_per_resume`` -- whichever pricing
  strategy the operator chooses.
* When credits run out the pipeline raises :class:`OutOfCreditsError` and stops.

Stripe checkout is stubbed and cleanly disabled unless ``STRIPE_API_KEY`` is
present, so nothing here requires real keys to run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .llm import estimate_tokens


class OutOfCreditsError(RuntimeError):
    """Raised when an account has insufficient credits to continue."""


@dataclass
class PricingConfig:
    """Pricing knobs. All configurable via env / constructor."""

    price_per_1k_tokens_usd: float = 0.01  # your blended API cost per 1k tokens
    margin_multiplier: float = 3.0          # markup applied on top of API cost
    price_per_resume_usd: float = 0.50      # flat per-resume price
    strategy: str = "token"                 # 'token' or 'flat'

    @classmethod
    def from_env(cls) -> "PricingConfig":
        def _f(name: str, default: float) -> float:
            try:
                return float(os.environ.get(name, default))
            except (TypeError, ValueError):
                return default

        return cls(
            price_per_1k_tokens_usd=_f("PRICE_PER_1K_TOKENS_USD", 0.01),
            margin_multiplier=_f("MARGIN_MULTIPLIER", 3.0),
            price_per_resume_usd=_f("PRICE_PER_RESUME_USD", 0.50),
            strategy=os.environ.get("PRICING_STRATEGY", "token").strip().lower(),
        )

    def api_cost(self, tokens: int) -> float:
        return (tokens / 1000.0) * self.price_per_1k_tokens_usd

    def price_for_tokens(self, tokens: int) -> float:
        """Customer-facing price for a token count (API cost * margin)."""
        return self.api_cost(tokens) * self.margin_multiplier

    def price_for_resume(self, tokens: int) -> float:
        """Price to charge for screening a single resume."""
        if self.strategy == "flat":
            return self.price_per_resume_usd
        return self.price_for_tokens(tokens)


@dataclass
class BillingAccount:
    """A prepaid credit wallet."""

    account_id: str = "default"
    credits: float = 100.0
    pricing: PricingConfig = field(default_factory=PricingConfig)
    total_tokens: int = 0
    total_charged_usd: float = 0.0
    resumes_billed: int = 0

    # ---- credit management -------------------------------------------------
    def add_credits(self, amount: float) -> float:
        if amount < 0:
            raise ValueError("Cannot add negative credits.")
        self.credits += amount
        return self.credits

    def estimate_job_cost(self, resume_texts: list[str], jd_text: str = "") -> float:
        """Estimate the total price to screen a batch, before running it."""
        total = 0.0
        jd_tokens = estimate_tokens(jd_text)
        for text in resume_texts:
            tokens = estimate_tokens(text) + jd_tokens + 220  # +completion overhead
            total += self.pricing.price_for_resume(tokens)
        return round(total, 4)

    def can_afford(self, price: float) -> bool:
        return self.credits >= price

    def charge_for_resume(self, tokens: int) -> float:
        """Deduct the price for one screened resume. Raises if unaffordable."""
        price = round(self.pricing.price_for_resume(tokens), 6)
        if not self.can_afford(price):
            raise OutOfCreditsError(
                f"Insufficient credits: need {price:.4f}, have {self.credits:.4f}."
            )
        self.credits = round(self.credits - price, 6)
        self.total_tokens += tokens
        self.total_charged_usd = round(self.total_charged_usd + price, 6)
        self.resumes_billed += 1
        return price

    def summary(self) -> dict:
        return {
            "account_id": self.account_id,
            "credits_remaining": round(self.credits, 4),
            "resumes_billed": self.resumes_billed,
            "total_tokens": self.total_tokens,
            "total_charged_usd": round(self.total_charged_usd, 4),
        }


# --------------------------------------------------------------------------- #
# Stripe checkout stub (disabled without STRIPE_API_KEY)
# --------------------------------------------------------------------------- #
def stripe_enabled() -> bool:
    return bool(os.environ.get("STRIPE_API_KEY"))


def create_checkout_session(credits: float, *, success_url: str = "", cancel_url: str = "") -> dict:
    """Create a Stripe checkout session for buying credits.

    Returns a stub payload when ``STRIPE_API_KEY`` is not configured so the
    product runs fully offline. Wire real Stripe by adding the key.
    """
    if not stripe_enabled():
        return {
            "enabled": False,
            "message": "Stripe disabled (set STRIPE_API_KEY to enable real checkout).",
            "credits": credits,
            "amount_usd": round(credits, 2),
            "checkout_url": None,
        }

    try:  # pragma: no cover - requires stripe + network
        import stripe  # type: ignore

        stripe.api_key = os.environ["STRIPE_API_KEY"]
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"{credits:g} screening credits"},
                        "unit_amount": int(round(credits * 100)),
                    },
                    "quantity": 1,
                }
            ],
            success_url=success_url or "https://example.com/success",
            cancel_url=cancel_url or "https://example.com/cancel",
        )
        return {
            "enabled": True,
            "credits": credits,
            "amount_usd": round(credits, 2),
            "checkout_url": session.url,
            "session_id": session.id,
        }
    except Exception as exc:  # pragma: no cover
        return {
            "enabled": False,
            "error": str(exc),
            "message": "Stripe checkout failed; falling back to disabled stub.",
            "credits": credits,
            "checkout_url": None,
        }
