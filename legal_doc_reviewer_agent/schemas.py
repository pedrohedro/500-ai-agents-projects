"""Structured data models for the review pipeline.

Plain dataclasses (no third-party dependency) with ``to_dict`` helpers so the
result can be serialised to JSON regardless of which optional libraries are
installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Weight used to convert individual risk severities into an overall score.
SEVERITY_WEIGHT: Dict[str, int] = {
    Severity.LOW.value: 1,
    Severity.MEDIUM.value: 3,
    Severity.HIGH.value: 6,
}


@dataclass
class Clause:
    """A key clause extracted from the contract."""

    type: str
    excerpt: str
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Risk:
    """An identified risk or red flag."""

    title: str
    severity: str  # one of Severity values
    explanation: str
    suggested_change: str
    related_clause: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QAResult:
    """Output of the QA / reviewer agent."""

    passed: bool
    completeness_score: float
    flagged_findings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    needs_human_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    """The full structured review output."""

    document_summary: str
    key_clauses: List[Clause]
    risks: List[Risk]
    missing_clauses: List[str]
    overall_risk_score: float
    risk_level: str
    qa: QAResult
    token_usage: int = 0
    provider: str = "mock"
    document_name: str = "contract"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_name": self.document_name,
            "provider": self.provider,
            "document_summary": self.document_summary,
            "key_clauses": [c.to_dict() for c in self.key_clauses],
            "risks": [r.to_dict() for r in self.risks],
            "missing_clauses": list(self.missing_clauses),
            "overall_risk_score": self.overall_risk_score,
            "risk_level": self.risk_level,
            "qa": self.qa.to_dict(),
            "token_usage": self.token_usage,
        }
