"""FastAPI service exposing the support chatbot as a webhook.

Run: ``uvicorn app:app --reload`` (from the support_chatbot_agent/ directory).

Endpoints:
    GET  /health          -> liveness + provider info
    POST /chat            -> answer a question (RAG + billing)
    POST /billing/checkout-> create a Stripe checkout session (or stub)
    GET  /account/{id}    -> account usage/credits

A website widget, WhatsApp, or Slack integration can call ``POST /chat``
unattended. The service auto-builds the index on startup.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from chatbot.agent import SupportAgent, build_agent
from chatbot.billing import BillingEngine, OutOfCreditsError, create_checkout_session
from chatbot.config import get_config

config = get_config()

# Shared singletons -- built once, reused across requests.
_agent: Optional[SupportAgent] = None
_billing: Optional[BillingEngine] = None


def get_agent() -> SupportAgent:
    global _agent
    if _agent is None:
        _agent = build_agent(config)
    return _agent


def get_billing() -> BillingEngine:
    global _billing
    if _billing is None:
        _billing = BillingEngine(config)
    return _billing


@asynccontextmanager
async def lifespan(app: FastAPI):  # pragma: no cover - server runtime
    # Warm the index + billing engine on startup so the first request is fast.
    get_agent()
    get_billing()
    yield


app = FastAPI(title="24/7 Support Chatbot", version="0.1.0", lifespan=lifespan)


# --- Schemas -----------------------------------------------------------
class SourceOut(BaseModel):
    id: str
    source: str
    score: float
    snippet: str


class ChatRequest(BaseModel):
    question: str = Field(..., description="The end-user question.")
    account_id: str = Field("demo", description="Billable account / workspace id.")


class ChatResponse(BaseModel):
    answer: str
    confidence: float
    escalate: bool
    sources: List[SourceOut]
    tokens_used: int
    charged: bool
    amount_charged: float
    remaining_credits: float


class CheckoutRequest(BaseModel):
    plan_key: str = "starter"
    seats: int = 1


# --- Routes ------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "provider": config.llm_provider,
        "mock_mode": config.is_mock,
        "stripe_enabled": config.stripe_enabled,
        "indexed_chunks": len(get_agent().store),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    agent = get_agent()
    billing = get_billing()

    result = agent.answer(req.question)

    try:
        charge = billing.charge_message(
            req.account_id, result.tokens_used, answered=not result.escalate
        )
    except OutOfCreditsError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    return ChatResponse(
        answer=result.answer,
        confidence=round(result.confidence, 4),
        escalate=result.escalate,
        sources=[SourceOut(**s.__dict__) for s in result.sources],
        tokens_used=result.tokens_used,
        charged=charge.charged,
        amount_charged=charge.amount,
        remaining_credits=charge.remaining_credits,
    )


@app.post("/billing/checkout")
def checkout(req: CheckoutRequest) -> dict:
    session = create_checkout_session(config, req.plan_key, req.seats)
    return session.__dict__


@app.get("/account/{account_id}")
def account(account_id: str) -> dict:
    billing = get_billing()
    acc = billing.get_account(account_id)
    return {
        "account_id": acc.account_id,
        "plan": acc.plan.name,
        "seats": acc.seats,
        "credits": round(acc.credits, 4),
        "messages_answered": acc.messages_answered,
        "messages_escalated": acc.messages_escalated,
        "total_tokens": acc.total_tokens,
        "total_charged": round(acc.total_charged, 4),
    }
