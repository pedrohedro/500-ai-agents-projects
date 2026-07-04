"""Core data models for the screening pipeline.

Uses plain dataclasses so the package has no hard third-party dependency for
its data layer (keeps mock mode runnable even when heavy deps fail to install).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class JobDescription:
    """A parsed job description."""

    title: str
    raw_text: str
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    min_years_experience: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResumeDocument:
    """Raw resume content plus its source identifier."""

    candidate_id: str
    raw_text: str
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedResume:
    """Structured facts extracted from a resume by the Parser agent."""

    candidate_id: str
    name: str
    skills: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    source_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateResult:
    """The final per-candidate screening outcome."""

    candidate_id: str
    name: str
    score: float
    matched_skills: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    rationale: str = ""
    confidence: float = 0.0
    # QA / fairness signals
    qa_passed: bool = True
    qa_flags: list[str] = field(default_factory=list)
    needs_human_review: bool = False
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScreeningReport:
    """Aggregate result of a screening job."""

    job_title: str
    candidates: list[CandidateResult] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    credits_remaining: float | None = None
    provider: str = "mock"

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_title": self.job_title,
            "provider": self.provider,
            "tokens_used": self.tokens_used,
            "cost_usd": round(self.cost_usd, 6),
            "credits_remaining": self.credits_remaining,
            "candidates": [c.to_dict() for c in self.candidates],
        }
