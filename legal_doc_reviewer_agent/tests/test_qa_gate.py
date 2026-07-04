"""Tests for the QA / reviewer gate."""
from config import get_settings, STANDARD_CLAUSES
from pipeline import ReviewerQAAgent
from schemas import Clause, Risk, Severity


def _settings():
    return get_settings()


def test_qa_flags_low_confidence_findings():
    settings = _settings()
    settings.qa_confidence_threshold = 0.6
    qa = ReviewerQAAgent(settings)
    clauses = [Clause("Confidentiality", "text", confidence=0.4)]
    risks = [Risk("risk", Severity.HIGH.value, "e", "s", confidence=0.3)]
    result = qa.run(clauses, risks, missing_clauses=[])
    assert result.flagged_findings
    assert result.needs_human_review is True


def test_qa_passes_clean_high_confidence_review():
    settings = _settings()
    settings.qa_confidence_threshold = 0.6
    qa = ReviewerQAAgent(settings)
    clauses = [Clause(name, "text", confidence=0.95) for name in STANDARD_CLAUSES]
    risks = [Risk("risk", Severity.LOW.value, "e", "s", confidence=0.9)]
    result = qa.run(clauses, risks, missing_clauses=[])
    assert result.passed is True
    assert result.needs_human_review is False
    assert not result.flagged_findings
    assert result.completeness_score == 1.0


def test_qa_completeness_reflects_missing_clauses():
    settings = _settings()
    qa = ReviewerQAAgent(settings)
    present = STANDARD_CLAUSES[:3]
    missing = STANDARD_CLAUSES[3:]
    clauses = [Clause(name, "text", confidence=0.9) for name in present]
    result = qa.run(clauses, [], missing_clauses=missing)
    assert 0.0 < result.completeness_score < 1.0
    assert result.needs_human_review  # majority missing -> review


def test_qa_fails_when_no_clauses():
    settings = _settings()
    qa = ReviewerQAAgent(settings)
    result = qa.run([], [], missing_clauses=list(STANDARD_CLAUSES))
    assert result.passed is False
    assert result.needs_human_review is True
