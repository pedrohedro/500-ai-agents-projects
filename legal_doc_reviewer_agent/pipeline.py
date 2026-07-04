"""The multi-agent review pipeline.

Three cooperating agents, each a thin wrapper over the LLM provider with a
focused prompt and JSON contract:

1. :class:`ClauseExtractorAgent` - finds key clauses and excerpts.
2. :class:`RiskAnalyzerAgent`    - flags risks / red flags with severity.
3. :class:`ReviewerQAAgent`      - validates completeness, checks for missing
   standard clauses, and flags low-confidence findings before release.

:class:`ReviewPipeline` orchestrates the three and computes the overall risk
score.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from config import STANDARD_CLAUSES, Settings, get_settings
from llm import LLMProvider, get_provider
from pdf_extractor import load_document
from schemas import (
    Clause,
    QAResult,
    ReviewResult,
    Risk,
    Severity,
    SEVERITY_WEIGHT,
)


def _safe_json(content: str) -> Dict[str, Any]:
    """Parse JSON defensively; tolerate models that wrap output in prose/fences."""
    if not content:
        return {}
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        # drop a leading language hint like "json\n"
        nl = content.find("\n")
        if nl != -1:
            content = content[nl + 1 :]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start : end + 1])
            except json.JSONDecodeError:
                return {}
        return {}


def _wrap_document(text: str) -> str:
    return f"Analyse the following contract.\n<document>\n{text}\n</document>"


class ClauseExtractorAgent:
    ROLE = (
        "You are a meticulous legal analyst. Extract the key clauses from the "
        "contract. Respond ONLY with JSON of the form "
        '{"clauses": [{"type": str, "excerpt": str, "confidence": float}]}.'
    )

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.tokens = 0

    def run(self, text: str) -> List[Clause]:
        resp = self.provider.complete(self.ROLE, _wrap_document(text), task="extract_clauses")
        self.tokens += resp.get("tokens", 0)
        data = _safe_json(resp.get("content", ""))
        clauses = []
        for item in data.get("clauses", []):
            if not item.get("type") or not item.get("excerpt"):
                continue
            clauses.append(
                Clause(
                    type=str(item["type"]),
                    excerpt=str(item["excerpt"]),
                    confidence=float(item.get("confidence", 1.0)),
                )
            )
        return clauses


class RiskAnalyzerAgent:
    ROLE = (
        "You are a contract risk specialist. Identify risks and red flags. For "
        "each, give a severity of low, medium or high, an explanation and a "
        "suggested change. Respond ONLY with JSON of the form "
        '{"risks": [{"title": str, "severity": str, "explanation": str, '
        '"suggested_change": str, "related_clause": str, "confidence": float}]}.'
    )

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.tokens = 0

    def run(self, text: str) -> List[Risk]:
        resp = self.provider.complete(self.ROLE, _wrap_document(text), task="analyze_risks")
        self.tokens += resp.get("tokens", 0)
        data = _safe_json(resp.get("content", ""))
        risks = []
        for item in data.get("risks", []):
            severity = str(item.get("severity", "medium")).lower()
            if severity not in SEVERITY_WEIGHT:
                severity = Severity.MEDIUM.value
            title = item.get("title") or "Unspecified risk"
            risks.append(
                Risk(
                    title=str(title),
                    severity=severity,
                    explanation=str(item.get("explanation", "")),
                    suggested_change=str(item.get("suggested_change", "")),
                    related_clause=item.get("related_clause"),
                    confidence=float(item.get("confidence", 1.0)),
                )
            )
        return risks


class SummarizerAgent:
    ROLE = (
        "You summarise contracts concisely for a business audience. Respond ONLY "
        'with JSON of the form {"summary": str}.'
    )

    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.tokens = 0

    def run(self, text: str) -> str:
        resp = self.provider.complete(self.ROLE, _wrap_document(text), task="summarize")
        self.tokens += resp.get("tokens", 0)
        data = _safe_json(resp.get("content", ""))
        return str(data.get("summary", "")).strip() or "No summary available."


class ReviewerQAAgent:
    """Validates completeness and flags low-confidence findings before release.

    This agent is deterministic and does not require the LLM: it audits the
    output of the previous agents, which is exactly what a QA reviewer does.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(
        self,
        clauses: List[Clause],
        risks: List[Risk],
        missing_clauses: List[str],
    ) -> QAResult:
        threshold = self.settings.qa_confidence_threshold
        flagged: List[str] = []
        notes: List[str] = []

        for c in clauses:
            if c.confidence < threshold:
                flagged.append(f"Low-confidence clause extraction: {c.type} ({c.confidence:.2f})")
        for r in risks:
            if r.confidence < threshold:
                flagged.append(f"Low-confidence risk finding: {r.title} ({r.confidence:.2f})")

        # Completeness: fraction of standard clauses that are present.
        present = len(STANDARD_CLAUSES) - len(
            [m for m in missing_clauses if m in STANDARD_CLAUSES]
        )
        completeness_score = round(present / len(STANDARD_CLAUSES), 2) if STANDARD_CLAUSES else 1.0

        if not clauses:
            notes.append("No clauses were extracted; document may be empty or unreadable.")
        if missing_clauses:
            notes.append(
                f"{len(missing_clauses)} standard clause(s) appear to be missing: "
                f"{', '.join(missing_clauses)}."
            )
        if not risks:
            notes.append("No risks detected. Manual spot-check recommended.")

        # The QA gate: pass only if we extracted something and completeness is
        # acceptable. Human review is required whenever findings were flagged or
        # completeness is poor.
        needs_human_review = bool(flagged) or completeness_score < 0.5 or not clauses
        passed = bool(clauses) and completeness_score >= 0.3

        if needs_human_review:
            notes.append("QA flagged this review for human verification before release.")

        return QAResult(
            passed=passed,
            completeness_score=completeness_score,
            flagged_findings=flagged,
            notes=notes,
            needs_human_review=needs_human_review,
        )


def compute_risk_score(risks: List[Risk], missing_clauses: List[str]) -> float:
    """Compute an overall 0-100 risk score.

    Combines weighted severity of detected risks with a penalty for missing
    standard protections, then normalises to 0-100.
    """
    raw = sum(SEVERITY_WEIGHT.get(r.severity, 3) for r in risks)
    raw += 2 * len(missing_clauses)  # missing protections add risk
    # Normalise: assume a "very risky" contract tops out around 40 raw points.
    score = min(100.0, (raw / 40.0) * 100.0)
    return round(score, 1)


def score_to_level(score: float) -> str:
    if score >= 66:
        return Severity.HIGH.value
    if score >= 33:
        return Severity.MEDIUM.value
    return Severity.LOW.value


class ReviewPipeline:
    """Orchestrates the three agents end-to-end."""

    def __init__(self, settings: Optional[Settings] = None, provider: Optional[LLMProvider] = None):
        self.settings = settings or get_settings()
        self.provider = provider or get_provider(self.settings)
        self.extractor = ClauseExtractorAgent(self.provider)
        self.risk_analyzer = RiskAnalyzerAgent(self.provider)
        self.summarizer = SummarizerAgent(self.provider)
        self.qa = ReviewerQAAgent(self.settings)

    def _missing_clauses(self, clauses: List[Clause]) -> List[str]:
        found_types = {c.type for c in clauses}
        return [name for name in STANDARD_CLAUSES if name not in found_types]

    def review(self, source: str, document_name: Optional[str] = None) -> ReviewResult:
        """Run the full pipeline on a file path or raw contract text."""
        text = load_document(source)
        name = document_name or (source if len(source) < 120 and "\n" not in source else "contract")

        summary = self.summarizer.run(text)
        clauses = self.extractor.run(text)
        risks = self.risk_analyzer.run(text)
        missing = self._missing_clauses(clauses)

        qa_result = self.qa.run(clauses, risks, missing)
        score = compute_risk_score(risks, missing)
        level = score_to_level(score)

        total_tokens = (
            self.summarizer.tokens + self.extractor.tokens + self.risk_analyzer.tokens
        )

        return ReviewResult(
            document_summary=summary,
            key_clauses=clauses,
            risks=risks,
            missing_clauses=missing,
            overall_risk_score=score,
            risk_level=level,
            qa=qa_result,
            token_usage=total_tokens,
            provider=self.provider.name,
            document_name=name,
        )
