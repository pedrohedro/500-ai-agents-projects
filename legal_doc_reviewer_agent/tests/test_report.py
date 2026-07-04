"""Tests for JSON and Markdown report rendering."""
import json
import os

from config import get_settings
from pipeline import ReviewPipeline
from report import to_json, to_markdown

SAMPLE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples",
    "sample_contract.txt",
)


def _result():
    return ReviewPipeline(get_settings()).review(SAMPLE_PATH, document_name="sample.txt")


def test_json_is_valid_and_complete():
    payload = json.loads(to_json(_result()))
    for key in [
        "document_summary",
        "key_clauses",
        "risks",
        "missing_clauses",
        "overall_risk_score",
        "risk_level",
        "qa",
    ]:
        assert key in payload


def test_markdown_contains_sections_and_disclaimer():
    md = to_markdown(_result())
    assert "# Legal Document Review" in md
    assert "## Identified Risks" in md
    assert "## Missing Standard Clauses" in md
    assert "not legal advice" in md.lower()
