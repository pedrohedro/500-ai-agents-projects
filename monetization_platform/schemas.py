"""Pydantic request/response models for the public API."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Auth --------------------------------------------------------------
class SignupRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("A valid email address is required.")
        return v


class SignupResponse(BaseModel):
    user_id: int
    email: str
    api_key: str = Field(..., description="Shown ONCE. Store it securely.")
    credits: int
    message: str


class MeResponse(BaseModel):
    user_id: int
    email: str
    credits: int


# --- Billing -----------------------------------------------------------
class CheckoutRequest(BaseModel):
    pack_key: str = Field("starter", description="One of: starter, pro, business.")


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    pack_key: str
    credits: int
    amount_usd: float
    mock: bool


class SimulatePaymentRequest(BaseModel):
    """Mock-mode helper to prove the wallet gets credited without real Stripe."""

    pack_key: str = "starter"


# --- Wallet / usage ----------------------------------------------------
class UsageEventOut(BaseModel):
    id: int
    kind: str
    agent: Optional[str] = None
    credits_delta: int
    balance_after: int
    tokens: int
    usd_cost: float
    description: str
    created_at: Optional[str] = None


class BalanceResponse(BaseModel):
    user_id: int
    email: str
    credits: int
    recent_events: List[UsageEventOut]


# --- Gateway (metered agent calls) -------------------------------------
class MarketingRequest(BaseModel):
    topic: str
    audience: str = "general audience"
    platform: str = "blog"
    tone: str = "professional"
    keywords: List[str] = Field(default_factory=list)
    call_to_action: str = "Learn more"
    word_count: int = 600


class LegalRequest(BaseModel):
    document_text: str
    document_name: str = "contract"


class SupportRequest(BaseModel):
    question: str


class HRResume(BaseModel):
    id: Optional[str] = None
    text: str


class HRRequest(BaseModel):
    job_description: str
    resumes: List[HRResume]
    job_title: Optional[str] = None


class AgentResponse(BaseModel):
    agent: str
    credits_charged: int
    credits_remaining: int
    output: Dict[str, Any]
    usage: Dict[str, Any]
