"""End-to-end pipeline tests in mock mode (no API keys, no network)."""
import os

import pytest

from config import get_settings, STANDARD_CLAUSES
from pipeline import ReviewPipeline, compute_risk_score, score_to_level
from schemas import Risk, Severity

SAMPLE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples",
    "sample_contract.txt",
)


@pytest.fixture
def result():
    pipeline = ReviewPipeline(get_settings())
    return pipeline.review(SAMPLE_PATH, document_name="sample_contract.txt")


def test_pipeline_runs_in_mock_mode(result):
    assert result.provider == "mock"
    assert result.document_summary
    assert result.token_usage > 0


def test_extracts_key_clauses(result):
    assert len(result.key_clauses) >= 3
    types = {c.type for c in result.key_clauses}
    # The sample clearly contains these.
    assert "Confidentiality" in types
    assert "Payment Terms" in types


def test_identifies_risks_with_valid_severities(result):
    assert len(result.risks) >= 3
    for risk in result.risks:
        assert risk.severity in {s.value for s in Severity}
        assert risk.explanation
        assert risk.suggested_change


def test_detects_high_severity_risk(result):
    severities = {r.severity for r in result.risks}
    # The sample has unlimited liability / uncapped indemnification -> high.
    assert Severity.HIGH.value in severities


def test_missing_clauses_are_subset_of_standard(result):
    for m in result.missing_clauses:
        assert m in STANDARD_CLAUSES


def test_overall_risk_score_range(result):
    assert 0.0 <= result.overall_risk_score <= 100.0
    assert result.risk_level in {s.value for s in Severity}


def test_deterministic_output():
    p1 = ReviewPipeline(get_settings())
    p2 = ReviewPipeline(get_settings())
    r1 = p1.review(SAMPLE_PATH)
    r2 = p2.review(SAMPLE_PATH)
    assert r1.overall_risk_score == r2.overall_risk_score
    assert len(r1.risks) == len(r2.risks)
    assert r1.document_summary == r2.document_summary


def test_review_from_raw_text():
    text = (
        "1. CONFIDENTIALITY. The parties shall keep information confidential. "
        "2. PAYMENT. Client shall pay Net 90. All fees are non-refundable."
    )
    r = ReviewPipeline(get_settings()).review(text)
    assert r.key_clauses
    assert r.token_usage > 0


def test_risk_score_monotonic():
    low = [Risk("a", Severity.LOW.value, "x", "y")]
    high = [Risk("a", Severity.HIGH.value, "x", "y")]
    assert compute_risk_score(high, []) > compute_risk_score(low, [])
    # Missing clauses increase the score.
    assert compute_risk_score(low, ["Termination"]) > compute_risk_score(low, [])


def test_score_to_level_thresholds():
    assert score_to_level(10) == Severity.LOW.value
    assert score_to_level(50) == Severity.MEDIUM.value
    assert score_to_level(80) == Severity.HIGH.value
