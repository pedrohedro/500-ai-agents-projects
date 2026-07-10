"""Signup + account endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_session
from ..models import ApiKey, User
from ..schemas import MeResponse, SignupRequest, SignupResponse
from ..security import generate_api_key, get_current_user
from ..wallet import credit_wallet

router = APIRouter(tags=["auth"])


@router.post("/auth/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, session: Session = Depends(get_session)) -> SignupResponse:
    """Register an email, issue an API key (shown once), and grant trial credits."""
    settings = get_settings()
    existing = session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(email=payload.email, credits=0)
    session.add(user)
    session.flush()  # assign user.id

    issued = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        key_hash=issued.key_hash,
        prefix=issued.prefix,
        label="default",
    )
    session.add(api_key)
    session.commit()

    bonus = settings.signup_bonus_credits
    if bonus > 0:
        credit_wallet(session, user, bonus, description="Signup bonus credits")

    return SignupResponse(
        user_id=user.id,
        email=user.email,
        api_key=issued.raw,
        credits=user.credits,
        message="Save this API key now — it will not be shown again.",
    )


@router.get("/auth/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user_id=user.id, email=user.email, credits=user.credits)
