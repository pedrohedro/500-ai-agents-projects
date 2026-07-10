"""Billing endpoints: checkout, webhook, and mock-mode helpers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..billing import (
    BillingError,
    build_mock_completed_event,
    create_checkout_session,
    parse_webhook_event,
)
from ..config import get_settings
from ..database import get_session
from ..models import User
from ..schemas import (
    BalanceResponse,
    CheckoutRequest,
    CheckoutResponse,
    SimulatePaymentRequest,
    UsageEventOut,
)
from ..security import get_current_user
from ..wallet import credit_wallet, recent_events

router = APIRouter(tags=["billing"])


@router.get("/billing/balance", response_model=BalanceResponse)
def balance(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> BalanceResponse:
    """Return the current balance plus recent ledger events (API-key gated)."""
    events = recent_events(session, user, limit=25)
    return BalanceResponse(
        user_id=user.id,
        email=user.email,
        credits=user.credits,
        recent_events=[UsageEventOut(**e.to_dict()) for e in events],
    )


@router.get("/billing/packs")
def list_packs() -> dict:
    """Public list of purchasable credit packs."""
    settings = get_settings()
    return {"packs": [p.to_dict() for p in settings.pack_list()]}


@router.post("/billing/checkout", response_model=CheckoutResponse)
def checkout(
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Create a Stripe Checkout Session (or a mock one) for a credit pack."""
    try:
        session = create_checkout_session(user.id, payload.pack_key)
    except BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CheckoutResponse(
        checkout_url=session.url,
        session_id=session.id,
        pack_key=session.pack_key,
        credits=session.credits,
        amount_usd=session.amount_usd,
        mock=session.mock,
    )


def _credit_from_payment(session: Session, payment) -> dict:
    user = session.get(User, payment.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User for payment not found.")
    event = credit_wallet(
        session,
        user,
        payment.credits,
        description=f"Credit pack purchase: {payment.pack_key}",
        reference=payment.reference,
    )
    return {
        "status": "credited",
        "user_id": user.id,
        "credits_added": payment.credits,
        "balance": user.credits,
        "event_id": event.id,
    }


@router.post("/billing/webhook")
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: Session = Depends(get_session),
) -> dict:
    """Stripe webhook. On ``checkout.session.completed`` the wallet is credited.

    In mock mode (no ``STRIPE_API_KEY``) the raw JSON body is trusted so tests
    and local runs can simulate a completed payment.
    """
    payload = await request.body()
    try:
        payment = parse_webhook_event(payload, stripe_signature)
    except BillingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if payment is None:
        return {"status": "ignored"}

    return _credit_from_payment(session, payment)


@router.post("/billing/simulate-payment")
def simulate_payment(
    payload: SimulatePaymentRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Mock-only: simulate a completed Stripe payment for the current user.

    Disabled once real Stripe is configured so it cannot be abused in production.
    """
    settings = get_settings()
    if settings.stripe_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="simulate-payment is disabled when real Stripe is configured. "
            "Use the real Stripe webhook instead.",
        )
    pack = settings.credit_packs.get(payload.pack_key)
    if pack is None:
        raise HTTPException(status_code=400, detail=f"Unknown pack '{payload.pack_key}'.")

    event = build_mock_completed_event(user.id, pack)

    from ..billing import CompletedPayment

    payment = CompletedPayment(
        user_id=user.id,
        pack_key=pack.key,
        credits=pack.credits,
        reference=event["data"]["object"]["id"],
    )
    return _credit_from_payment(session, payment)


@router.get("/billing/mock-checkout", response_class=HTMLResponse)
def mock_checkout(session_id: str, user_id: int, pack_key: str) -> HTMLResponse:
    """A fake hosted-checkout page shown by mock mode's checkout URL."""
    html = f"""
    <!doctype html><html><head><meta charset="utf-8">
    <title>Mock Checkout</title>
    <style>body{{font-family:system-ui;max-width:640px;margin:80px auto;padding:0 20px;color:#0f172a}}
    .card{{border:1px solid #e2e8f0;border-radius:16px;padding:32px;box-shadow:0 10px 30px rgba(2,6,23,.06)}}
    code{{background:#f1f5f9;padding:2px 6px;border-radius:6px}}</style></head>
    <body><div class="card">
    <h1>Mock Stripe Checkout</h1>
    <p>Real Stripe is not configured, so this is a simulated checkout page.</p>
    <p>Session: <code>{session_id}</code><br>Pack: <code>{pack_key}</code><br>
    User: <code>{user_id}</code></p>
    <p>To actually credit the wallet in mock mode, POST to
    <code>/billing/simulate-payment</code> with your API key, or send a mock
    <code>checkout.session.completed</code> event to <code>/billing/webhook</code>.</p>
    </div></body></html>
    """
    return HTMLResponse(content=html)
