"""Tests for the credit / billing system."""
import pytest

from billing import (
    BillingManager,
    CreditAccount,
    OutOfCreditsError,
    create_checkout_session,
    estimate_cost,
)
from config import get_settings


def test_cost_estimate_has_positive_margin():
    est = estimate_cost(10_000, get_settings())
    assert est.price > est.api_cost
    assert est.margin > 0
    assert est.margin_pct > 0


def test_charge_deducts_balance():
    settings = get_settings()
    account = CreditAccount(balance=100.0)
    mgr = BillingManager(account, settings)
    est = mgr.estimate(5000)
    receipt = mgr.charge_for_review(5000, "doc.txt")
    assert receipt["charged"] == pytest.approx(est.price)
    assert account.balance == pytest.approx(100.0 - est.price)


def test_multiple_charges_accumulate():
    account = CreditAccount(balance=10.0)
    mgr = BillingManager(account, get_settings())
    start = account.balance
    mgr.charge_for_review(1000, "a")
    mgr.charge_for_review(1000, "b")
    assert account.balance < start


def test_out_of_credits_blocks_review():
    account = CreditAccount(balance=0.10)
    mgr = BillingManager(account, get_settings())
    with pytest.raises(OutOfCreditsError):
        mgr.charge_for_review(50_000, "expensive.txt")
    # Balance is unchanged after a blocked charge.
    assert account.balance == pytest.approx(0.10)


def test_preauthorize():
    account = CreditAccount(balance=0.55)
    mgr = BillingManager(account, get_settings())
    assert mgr.preauthorize(100) is True  # small doc affordable
    assert mgr.preauthorize(1_000_000) is False  # huge doc not affordable


def test_add_credits():
    account = CreditAccount(balance=1.0)
    account.add_credits(9.0)
    assert account.balance == pytest.approx(10.0)
    with pytest.raises(Exception):
        account.add_credits(-1.0)


def test_credit_persistence(tmp_path):
    path = str(tmp_path / "credits.json")
    account = CreditAccount(balance=5.0, path=path)
    account.charge(2.0)
    reopened = CreditAccount(path=path)
    assert reopened.balance == pytest.approx(3.0)


def test_stripe_disabled_without_key(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    session = create_checkout_session(20.0, get_settings())
    assert session["enabled"] is False
    assert session["checkout_url"] is None
