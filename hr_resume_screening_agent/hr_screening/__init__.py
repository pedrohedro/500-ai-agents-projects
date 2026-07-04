"""HR Resume Screening / Candidate Ranking agent.

A multi-agent pipeline (Parser -> JD Matcher -> Scorer/Ranker -> QA reviewer)
that screens a batch of resumes against a job description, produces a ranked
list of candidates, and runs a fairness/bias QA gate before release.

The whole pipeline runs end-to-end with NO API keys in ``LLM_PROVIDER=mock``.
"""

from .models import (
    JobDescription,
    ResumeDocument,
    CandidateResult,
    ScreeningReport,
)
from .pipeline import ScreeningPipeline
from .llm import get_llm, LLMProvider, MockLLM

__all__ = [
    "JobDescription",
    "ResumeDocument",
    "CandidateResult",
    "ScreeningReport",
    "ScreeningPipeline",
    "get_llm",
    "LLMProvider",
    "MockLLM",
]

__version__ = "0.1.0"
