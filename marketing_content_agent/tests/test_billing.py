"""Tests for credit deduction, out-of-credits, and cost estimation."""

import pytest

from marketing_content_agent.billing import (
    BillingEngine,
    OutOfCreditsError,
    StripeCheckout,
    Wallet,
)
from marketing_content_agent.config import get_settings
from marketing_content_agent.pipeline import ContentPipeline
from marketing_content_agent.schemas import ContentBrief


def _brief():
    return ContentBrief(topic="Credit test", call_to_action="Get started")


def test_wallet_charge_deducts():
    w = Wallet(balance=10)
    engine = BillingEngine()
    tx = engine.charge_for_generation(w)
    assert tx.kind == "debit"
    assert w.balance == 10 - engine.credits_for_generation()


def test_wallet_out_of_credits_raises():
    w = Wallet(balance=1)
    engine = BillingEngine()
    with pytest.raises(OutOfCreditsError):
        engine.charge_for_generation(w)
    # Balance untouched on failure.
    assert w.balance == 1


def test_top_up_and_history():
    w = Wallet(balance=0)
    w.top_up(20)
    assert w.balance == 20
    assert w.history[-1].kind == "credit"


def test_pipeline_deducts_credits():
    settings = get_settings()
    per_gen = settings.credits_per_generation
    w = Wallet(balance=per_gen * 2)
    pipeline = ContentPipeline(settings=settings)
    d = pipeline.run(_brief(), wallet=w)
    assert w.balance == per_gen
    assert d.usage.credits_charged == per_gen


def test_pipeline_blocks_when_out_of_credits():
    w = Wallet(balance=0)
    pipeline = ContentPipeline()
    with pytest.raises(OutOfCreditsError):
        pipeline.run(_brief(), wallet=w)


def test_pipeline_runs_without_wallet():
    pipeline = ContentPipeline()
    d = pipeline.run(_brief())
    assert d.usage.credits_charged == 0


def test_cost_estimate_and_margin():
    engine = BillingEngine()
    est = engine.estimate_cost(prompt_tokens=1000, completion_tokens=500)
    assert est.total_tokens == 1500
    assert est.retail_price_usd > 0
    # Retail should exceed API cost -> positive margin (mock API cost is 0).
    assert est.margin_usd >= 0


def test_stripe_disabled_without_key():
    checkout = StripeCheckout()
    result = checkout.create_checkout_session(credits=25)
    assert checkout.enabled is False
    assert result["enabled"] is False
    assert result["status"] == "disabled"
