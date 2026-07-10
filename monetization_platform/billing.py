"""Stripe monetization: checkout sessions + webhook crediting.

Two modes, selected automatically:

* **Real Stripe** — when ``STRIPE_API_KEY`` is set. Creates real Checkout
  Sessions and verifies webhook signatures.
* **Mock Stripe** — when no key is set. Returns a deterministic fake checkout
  URL and lets a test-flagged webhook simulate ``checkout.session.completed`` so
  the whole money loop is exercisable with zero external dependencies.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .config import CreditPack, Settings, get_settings


class BillingError(Exception):
    """Raised for invalid billing requests (unknown pack, bad signature, ...)."""


@dataclass
class CheckoutSession:
    """Result of creating a checkout session."""

    id: str
    url: str
    pack_key: str
    credits: int
    amount_usd: float
    mock: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "pack_key": self.pack_key,
            "credits": self.credits,
            "amount_usd": self.amount_usd,
            "mock": self.mock,
        }


def _metadata_for(user_id: int, pack: CreditPack) -> Dict[str, str]:
    return {
        "user_id": str(user_id),
        "pack_key": pack.key,
        "credits": str(pack.credits),
    }


def create_checkout_session(
    user_id: int,
    pack_key: str,
    settings: Optional[Settings] = None,
) -> CheckoutSession:
    """Create a Stripe Checkout Session (or a mock one) for a credit pack."""
    settings = settings or get_settings()
    pack = settings.credit_packs.get(pack_key)
    if pack is None:
        raise BillingError(
            f"Unknown credit pack '{pack_key}'. Choose one of: "
            f"{', '.join(settings.credit_packs)}."
        )

    if not settings.stripe_enabled:
        # ---- MOCK MODE ---------------------------------------------------
        session_id = f"cs_mock_{user_id}_{pack.key}_{int(time.time())}"
        url = (
            f"{settings.base_url}/billing/mock-checkout"
            f"?session_id={session_id}&user_id={user_id}&pack_key={pack.key}"
        )
        return CheckoutSession(
            id=session_id,
            url=url,
            pack_key=pack.key,
            credits=pack.credits,
            amount_usd=pack.price_usd,
            mock=True,
        )

    # ---- REAL STRIPE -----------------------------------------------------
    import stripe  # imported lazily so mock mode needs no configured SDK

    stripe.api_key = settings.stripe_api_key
    session = stripe.checkout.Session.create(
        mode="payment",
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        client_reference_id=str(user_id),
        metadata=_metadata_for(user_id, pack),
        line_items=[
            {
                "quantity": 1,
                "price_data": {
                    "currency": settings.stripe_currency,
                    "unit_amount": pack.price_cents,
                    "product_data": {
                        "name": f"{settings.app_name} — {pack.name} ({pack.credits} credits)",
                    },
                },
            }
        ],
    )
    return CheckoutSession(
        id=session.id,
        url=session.url,
        pack_key=pack.key,
        credits=pack.credits,
        amount_usd=pack.price_usd,
        mock=False,
    )


@dataclass
class CompletedPayment:
    """Normalized result of a completed checkout, used to credit the wallet."""

    user_id: int
    pack_key: str
    credits: int
    reference: str


def parse_webhook_event(
    payload: bytes,
    signature: Optional[str],
    settings: Optional[Settings] = None,
) -> Optional[CompletedPayment]:
    """Verify + parse a Stripe webhook.

    Returns a :class:`CompletedPayment` for ``checkout.session.completed`` events,
    or ``None`` for events we do not act on. Raises :class:`BillingError` on an
    invalid signature (real mode) or malformed payload.
    """
    settings = settings or get_settings()

    if settings.stripe_enabled and settings.stripe_webhook_secret:
        import stripe

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.stripe_webhook_secret
            )
        except Exception as exc:  # signature/verification failure
            raise BillingError(f"Webhook signature verification failed: {exc}") from exc
        event = dict(event)
    else:
        # Mock mode: accept the raw JSON body as the event (no signature check).
        try:
            event = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise BillingError(f"Invalid webhook payload: {exc}") from exc

    if event.get("type") != "checkout.session.completed":
        return None

    obj = (event.get("data", {}) or {}).get("object", {}) or {}
    metadata = obj.get("metadata", {}) or {}

    user_id = metadata.get("user_id") or obj.get("client_reference_id")
    pack_key = metadata.get("pack_key")
    credits = metadata.get("credits")

    if user_id is None or credits is None:
        raise BillingError("Webhook missing user_id/credits metadata.")

    return CompletedPayment(
        user_id=int(user_id),
        pack_key=pack_key or "unknown",
        credits=int(credits),
        reference=obj.get("id") or event.get("id") or "stripe_event",
    )


def build_mock_completed_event(user_id: int, pack: CreditPack) -> Dict[str, Any]:
    """Construct a mock ``checkout.session.completed`` event body for testing."""
    return {
        "id": f"evt_mock_{user_id}_{pack.key}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_mock_{user_id}_{pack.key}",
                "client_reference_id": str(user_id),
                "metadata": _metadata_for(user_id, pack),
            }
        },
    }
