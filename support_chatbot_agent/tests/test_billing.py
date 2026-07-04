"""Tests for the monetization / billing engine."""
import pytest

from chatbot.billing import (
    BillingEngine,
    OutOfCreditsError,
    create_checkout_session,
)


def test_create_account_grants_plan_credits(config):
    engine = BillingEngine(config)
    acc = engine.create_account("acme", plan_key="starter", seats=2)
    assert acc.plan.key == "starter"
    assert acc.seats == 2
    # starter = 25 USD credits/seat * 2 seats
    assert acc.credits == pytest.approx(50.0)


def test_charge_deducts_credits(config):
    engine = BillingEngine(config)
    engine.create_account("acme", plan_key="starter", seats=1)
    before = engine.get_account("acme").credits

    result = engine.charge_message("acme", tokens=1000, answered=True)
    assert result.charged
    assert result.amount == pytest.approx(config.price_per_1k_tokens)
    assert result.margin > 0  # customer price exceeds API cost
    after = engine.get_account("acme").credits
    assert after == pytest.approx(before - result.amount)


def test_escalated_message_not_charged(config):
    engine = BillingEngine(config)
    engine.create_account("acme", plan_key="starter", seats=1)
    before = engine.get_account("acme").credits

    result = engine.charge_message("acme", tokens=1000, answered=False)
    assert not result.charged
    assert result.amount == 0.0
    assert engine.get_account("acme").credits == pytest.approx(before)
    assert engine.get_account("acme").messages_escalated == 1


def test_out_of_credits_blocks(config):
    engine = BillingEngine(config)
    acc = engine.create_account("broke", plan_key="free", seats=1)
    acc.credits = 0.0
    engine.store.put(acc)

    with pytest.raises(OutOfCreditsError):
        engine.charge_message("broke", tokens=1000, answered=True)


def test_add_credits_tops_up(config):
    engine = BillingEngine(config)
    engine.create_account("acme", plan_key="free", seats=1)
    engine.add_credits("acme", 10.0)
    assert engine.get_account("acme").credits >= 10.0


def test_cost_model_has_margin(config):
    engine = BillingEngine(config)
    preview = engine.preview(tokens=1000)
    assert preview.amount == pytest.approx(config.price_per_1k_tokens)
    assert preview.api_cost == pytest.approx(config.api_cost_per_1k_tokens)
    assert preview.margin == pytest.approx(preview.amount - preview.api_cost)
    assert preview.margin > 0


def test_stripe_disabled_without_key(config):
    config.stripe_api_key = None
    session = create_checkout_session(config, "starter", seats=3)
    assert session.enabled is False
    assert "Stripe is not configured" in session.message
