import os

from hr_screening.agents import JDMatcherAgent, ResumeParserAgent, parse_job_description
from hr_screening.llm import MockLLM
from hr_screening.models import ResumeDocument
from hr_screening.pipeline import ScreeningPipeline

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), "samples")


def _load_samples():
    with open(os.path.join(SAMPLES, "job_description.txt"), encoding="utf-8") as fh:
        jd_text = fh.read()
    docs = []
    rdir = os.path.join(SAMPLES, "resumes")
    for name in sorted(os.listdir(rdir)):
        path = os.path.join(rdir, name)
        with open(path, encoding="utf-8") as fh:
            docs.append(ResumeDocument(candidate_id=os.path.splitext(name)[0], raw_text=fh.read()))
    return jd_text, docs


def test_matcher_finds_matches_and_gaps():
    jd = parse_job_description(
        "Requirements:\n- Python\n- SQL\n- Docker\n- AWS\n"
    )
    doc = ResumeDocument(candidate_id="c", raw_text="Bob\nPython and SQL developer.")
    parsed = ResumeParserAgent().run(doc)
    match = JDMatcherAgent().run(jd, parsed)
    assert set(match.matched_required) == {"python", "sql"}
    assert set(match.gaps) == {"docker", "aws"}


def test_pipeline_ranks_candidates_in_expected_order():
    jd_text, docs = _load_samples()
    pipeline = ScreeningPipeline(llm=MockLLM())
    report = pipeline.screen(jd_text, docs)

    names_in_rank_order = [c.name for c in report.candidates]
    # Alice (full match + 8y) and Erin (full match + 7y) are strongest.
    assert names_in_rank_order[0] == "Alice Nguyen"
    assert names_in_rank_order[1] == "Erin Kelly"
    # Weakest is the frontend-only candidate.
    assert names_in_rank_order[-1] == "David Okoro"

    # Scores must be monotonically non-increasing along the ranking.
    scores = [c.score for c in report.candidates]
    assert scores == sorted(scores, reverse=True)

    # Ranks are assigned 1..N.
    assert [c.rank for c in report.candidates] == list(range(1, len(report.candidates) + 1))


def test_top_candidate_has_matched_skills_and_rationale():
    jd_text, docs = _load_samples()
    report = ScreeningPipeline(llm=MockLLM()).screen(jd_text, docs)
    top = report.candidates[0]
    assert {"python", "docker", "aws"} <= set(top.matched_skills)
    assert top.rationale  # non-empty rationale generated
    assert top.score > report.candidates[-1].score
