"""Metered agent gateway.

Each endpoint: authenticate → check credits → run the agent → deduct credits →
log a usage event → return the result. Returns HTTP 402 when out of credits.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..adapters import get_adapter
from ..config import get_settings
from ..database import get_session
from ..models import User
from ..schemas import (
    AgentResponse,
    HRRequest,
    LegalRequest,
    MarketingRequest,
    SupportRequest,
)
from ..security import get_current_user
from ..wallet import OutOfCreditsError, debit_wallet

router = APIRouter(prefix="/v1", tags=["agents"])


def _meter_and_run(
    agent: str,
    payload: Dict[str, Any],
    user: User,
    session: Session,
) -> AgentResponse:
    """Shared metering flow used by every agent endpoint."""
    settings = get_settings()
    cost = settings.agent_costs[agent]

    # Fail fast (402) before doing any paid work if credits are insufficient.
    if user.credits < cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Insufficient credits: '{agent}' costs {cost} credits, "
                f"you have {user.credits}. Buy more at /billing/checkout."
            ),
        )

    adapter = get_adapter(agent)
    try:
        result = adapter.run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive; never charge on failure
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Agent '{agent}' failed: {exc}",
        )

    try:
        event = debit_wallet(
            session,
            user,
            cost,
            agent=agent,
            tokens=result.tokens,
            usd_cost=result.usd_cost,
            description=f"{agent} agent call",
            reference=str(result.meta.get("reference")) if result.meta.get("reference") else None,
        )
    except OutOfCreditsError as exc:
        # Race: balance drained concurrently between the pre-check and debit.
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc))

    return AgentResponse(
        agent=agent,
        credits_charged=cost,
        credits_remaining=event.balance_after,
        output=result.output,
        usage=result.to_dict()["usage"],
    )


@router.post("/marketing/generate", response_model=AgentResponse)
def marketing_generate(
    body: MarketingRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AgentResponse:
    return _meter_and_run("marketing", body.model_dump(), user, session)


@router.post("/legal/review", response_model=AgentResponse)
def legal_review(
    body: LegalRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AgentResponse:
    return _meter_and_run("legal", body.model_dump(), user, session)


@router.post("/support/chat", response_model=AgentResponse)
def support_chat(
    body: SupportRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AgentResponse:
    return _meter_and_run("support", body.model_dump(), user, session)


@router.post("/hr/screen", response_model=AgentResponse)
def hr_screen(
    body: HRRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AgentResponse:
    return _meter_and_run("hr", body.model_dump(), user, session)
