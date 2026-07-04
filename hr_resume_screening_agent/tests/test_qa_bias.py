from hr_screening.agents import QAReviewAgent
from hr_screening.llm import MockLLM
from hr_screening.models import CandidateResult


def _candidate(**kw):
    base = dict(
        candidate_id="c1",
        name="Test Candidate",
        score=80.0,
        matched_skills=["python"],
        gaps=[],
        years_experience=5,
        rationale="Strong Python engineer with relevant API experience.",
        confidence=0.8,
    )
    base.update(kw)
    return CandidateResult(**base)


def test_qa_passes_clean_candidate():
    qa = QAReviewAgent(MockLLM(), min_confidence=0.35)
    result, _ = qa.run(_candidate())
    assert result.qa_passed is True
    assert result.needs_human_review is False
    assert result.qa_flags == []


def test_qa_flags_protected_attribute_in_rationale():
    qa = QAReviewAgent(MockLLM(), min_confidence=0.35)
    biased = _candidate(
        rationale="Great candidate but she is likely too old for this fast-paced team."
    )
    result, _ = qa.run(biased)
    assert result.qa_passed is False
    assert result.needs_human_review is True
    assert any("bias" in f for f in result.qa_flags)


def test_qa_flags_low_confidence_for_human_review():
    qa = QAReviewAgent(MockLLM(), min_confidence=0.5)
    low = _candidate(confidence=0.2)
    result, _ = qa.run(low)
    assert result.needs_human_review is True
    assert any("low-confidence" in f for f in result.qa_flags)
    # Low confidence alone is not a bias failure.
    assert result.qa_passed is True


def test_scoring_ignores_protected_attributes():
    # Two identical skill profiles; one resume also mentions protected info.
    # Scores must be equal -> protected attributes do not affect scoring.
    from hr_screening.models import ResumeDocument
    from hr_screening.pipeline import ScreeningPipeline

    jd = "Requirements:\n- 3 years\n- Python\n- SQL\n- Docker\n"
    neutral = ResumeDocument(candidate_id="n", raw_text="Pat\n3 years Python, SQL, Docker.")
    with_attrs = ResumeDocument(
        candidate_id="a",
        raw_text="Sam\n3 years Python, SQL, Docker. 55 year old disabled veteran, married.",
    )
    pipeline = ScreeningPipeline(llm=MockLLM())
    report = pipeline.screen(jd, [neutral, with_attrs])
    scores = {c.candidate_id: c.score for c in report.candidates}
    assert scores["n"] == scores["a"]
