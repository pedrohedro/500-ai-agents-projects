import pytest

from hr_screening.billing import (
    BillingAccount,
    OutOfCreditsError,
    PricingConfig,
    create_checkout_session,
    stripe_enabled,
)
from hr_screening.llm import MockLLM
from hr_screening.models import ResumeDocument
from hr_screening.pipeline import ScreeningPipeline


def test_pricing_applies_margin():
    pricing = PricingConfig(price_per_1k_tokens_usd=0.01, margin_multiplier=3.0)
    assert pricing.api_cost(1000) == pytest.approx(0.01)
    assert pricing.price_for_tokens(1000) == pytest.approx(0.03)


def test_charge_deducts_credits():
    acct = BillingAccount(credits=1.0, pricing=PricingConfig(strategy="flat", price_per_resume_usd=0.25))
    price = acct.charge_for_resume(tokens=500)
    assert price == pytest.approx(0.25)
    assert acct.credits == pytest.approx(0.75)
    assert acct.resumes_billed == 1


def test_out_of_credits_raises():
    acct = BillingAccount(credits=0.10, pricing=PricingConfig(strategy="flat", price_per_resume_usd=0.25))
    with pytest.raises(OutOfCreditsError):
        acct.charge_for_resume(tokens=500)


def test_pipeline_stops_when_out_of_credits():
    # Enough credits for only 2 of 4 resumes at a flat $1 each.
    acct = BillingAccount(credits=2.0, pricing=PricingConfig(strategy="flat", price_per_resume_usd=1.0))
    docs = [
        ResumeDocument(candidate_id=f"c{i}", raw_text=f"Cand {i}\n3 years Python.")
        for i in range(4)
    ]
    pipeline = ScreeningPipeline(llm=MockLLM(), billing=acct)
    report = pipeline.screen("Requirements:\n- Python\n", docs)
    assert len(report.candidates) == 2
    assert acct.credits == pytest.approx(0.0)
    assert report.credits_remaining == pytest.approx(0.0)


def test_estimate_job_cost_positive():
    acct = BillingAccount(credits=100, pricing=PricingConfig())
    est = acct.estimate_job_cost(["some resume text", "another resume"], "the jd")
    assert est > 0


def test_stripe_disabled_without_key(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert stripe_enabled() is False
    session = create_checkout_session(25.0)
    assert session["enabled"] is False
    assert session["checkout_url"] is None
