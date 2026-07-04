"""The multi-agent pipeline stages.

Each stage is a small, single-responsibility class:

* :class:`ResumeParserAgent` -- raw text -> structured :class:`ParsedResume`.
* :class:`JDMatcherAgent`     -- compare a parsed resume to the JD.
* :class:`ScorerAgent`        -- compute a 0-100 score + LLM rationale.
* :class:`QAReviewAgent`      -- fairness/bias gate + low-confidence flagging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .llm import LLMProvider
from .models import CandidateResult, JobDescription, ParsedResume, ResumeDocument
from .skills import extract_skills, extract_years_experience, guess_name

# Terms that must never drive a hiring decision. Used by the QA agent to detect
# when a rationale leaks protected-attribute reasoning.
PROTECTED_ATTRIBUTE_TERMS: list[str] = [
    "age", "aged", "years old", "young", "younger", "old", "older", "elderly",
    "male", "female", "man", "woman", "gender", "he ", "she ",
    "race", "ethnic", "ethnicity", "black", "white", "asian", "hispanic", "latino",
    "religion", "religious", "muslim", "christian", "jewish", "hindu",
    "nationality", "immigrant", "foreign", "visa status", "citizen",
    "married", "single", "pregnant", "children", "family status", "maternity",
    "disability", "disabled", "handicap",
    "gay", "lesbian", "lgbt", "sexual orientation",
]


# --------------------------------------------------------------------------- #
# Job description parsing
# --------------------------------------------------------------------------- #
def parse_job_description(raw_text: str, title: str | None = None) -> JobDescription:
    """Parse a raw JD into required/preferred skills and minimum experience."""
    lines = raw_text.splitlines()
    detected_title = title
    if not detected_title:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(?:title|role|position)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
            if m:
                detected_title = m.group(1).strip()
            else:
                detected_title = line
            break
    detected_title = detected_title or "Untitled Role"

    required_block, preferred_block = _split_requirement_blocks(raw_text)
    required_skills = extract_skills(required_block) if required_block else []
    preferred_skills = [s for s in extract_skills(preferred_block) if s not in required_skills]

    # Fall back: if no explicit required block, treat all detected skills as required.
    if not required_skills:
        required_skills = extract_skills(raw_text)

    min_years = _extract_min_years(raw_text)

    return JobDescription(
        title=detected_title,
        raw_text=raw_text,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        min_years_experience=min_years,
    )


def _split_requirement_blocks(text: str) -> tuple[str, str]:
    """Split JD text into (required, preferred) sections when headings exist."""
    lowered = text.lower()
    required, preferred = text, ""

    pref_markers = ["nice to have", "preferred", "bonus", "plus:", "desirable"]
    req_markers = ["required", "requirements", "must have", "qualifications", "responsibilities"]

    pref_idx = min(
        (lowered.find(m) for m in pref_markers if lowered.find(m) != -1),
        default=-1,
    )
    if pref_idx != -1:
        required = text[:pref_idx]
        preferred = text[pref_idx:]
        req_idx = min(
            (required.lower().find(m) for m in req_markers if required.lower().find(m) != -1),
            default=-1,
        )
        if req_idx != -1:
            required = required[req_idx:]
    return required, preferred


def _extract_min_years(text: str) -> int:
    m = re.search(r"(\d+)\s*\+?\s*years?", text, re.IGNORECASE)
    if m:
        try:
            val = int(m.group(1))
            return val if 0 < val <= 50 else 0
        except ValueError:
            return 0
    return 0


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
class ResumeParserAgent:
    """Extract structured facts from raw resume text."""

    def run(self, doc: ResumeDocument) -> ParsedResume:
        text = doc.raw_text
        name = guess_name(text, fallback=doc.candidate_id)
        return ParsedResume(
            candidate_id=doc.candidate_id,
            name=name,
            skills=extract_skills(text),
            years_experience=extract_years_experience(text),
            source_path=doc.source_path,
        )


@dataclass
class MatchResult:
    matched_required: list[str]
    matched_preferred: list[str]
    gaps: list[str]


class JDMatcherAgent:
    """Compare a parsed resume against the job description."""

    def run(self, jd: JobDescription, resume: ParsedResume) -> MatchResult:
        resume_skills = set(resume.skills)
        req = set(jd.required_skills)
        pref = set(jd.preferred_skills)
        matched_required = sorted(req & resume_skills)
        matched_preferred = sorted(pref & resume_skills)
        gaps = sorted(req - resume_skills)
        return MatchResult(matched_required, matched_preferred, gaps)


class ScorerAgent:
    """Compute the weighted 0-100 score, confidence, and LLM rationale."""

    W_REQUIRED = 0.70
    W_PREFERRED = 0.15
    W_EXPERIENCE = 0.15

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def run(
        self,
        jd: JobDescription,
        resume: ParsedResume,
        match: MatchResult,
    ) -> tuple[CandidateResult, int]:
        req_total = len(jd.required_skills)
        pref_total = len(jd.preferred_skills)

        req_score = (len(match.matched_required) / req_total) if req_total else 0.0
        pref_score = (len(match.matched_preferred) / pref_total) if pref_total else 0.0

        if jd.min_years_experience > 0:
            exp_score = min(resume.years_experience / jd.min_years_experience, 1.0)
        else:
            exp_score = 1.0 if resume.years_experience > 0 else 0.5

        raw = (
            self.W_REQUIRED * req_score
            + self.W_PREFERRED * pref_score
            + self.W_EXPERIENCE * exp_score
        )
        score = round(raw * 100, 1)

        confidence = self._confidence(resume, match, req_total)

        matched_all = sorted(set(match.matched_required) | set(match.matched_preferred))
        rationale_resp = self.llm.write_rationale(
            name=resume.name,
            matched=matched_all,
            gaps=match.gaps,
            score=score,
            years=resume.years_experience,
        )

        result = CandidateResult(
            candidate_id=resume.candidate_id,
            name=resume.name,
            score=score,
            matched_skills=matched_all,
            gaps=match.gaps,
            years_experience=resume.years_experience,
            rationale=rationale_resp.text.strip(),
            confidence=confidence,
        )
        return result, rationale_resp.total_tokens

    @staticmethod
    def _confidence(resume: ParsedResume, match: MatchResult, req_total: int) -> float:
        # More evidence (skills, resume length, experience signal) -> higher confidence.
        evidence = len(resume.skills)
        conf = 0.2 + 0.12 * evidence
        if resume.years_experience > 0:
            conf += 0.1
        if req_total and not match.matched_required:
            conf -= 0.15  # no required-skill overlap at all: uncertain match
        return round(max(0.05, min(conf, 0.95)), 2)


class QAReviewAgent:
    """Fairness/bias gate run before results are released.

    Responsibilities:
      * Detect protected-attribute reasoning leaking into the rationale.
      * Flag low-confidence matches for human review.
      * Run a secondary LLM fairness review.
    """

    def __init__(self, llm: LLMProvider, min_confidence: float = 0.35) -> None:
        self.llm = llm
        self.min_confidence = min_confidence

    def run(self, result: CandidateResult) -> tuple[CandidateResult, int]:
        flags: list[str] = []
        tokens = 0

        leaked = self._protected_terms_in(result.rationale)
        if leaked:
            flags.append(
                "possible bias: rationale references protected attribute(s): "
                + ", ".join(sorted(leaked))
            )

        if result.confidence < self.min_confidence:
            flags.append(
                f"low-confidence match ({result.confidence:.2f} < "
                f"{self.min_confidence:.2f}); recommend human review"
            )

        # Secondary LLM fairness review (deterministic 'OK' in mock mode).
        review = self.llm.fairness_review(resume_text="", rationale=result.rationale)
        tokens += review.total_tokens
        review_text = review.text.strip()
        if review_text.upper().startswith("FLAG"):
            flags.append(f"llm fairness review: {review_text}")

        bias_flagged = any(f.startswith("possible bias") or "fairness review" in f for f in flags)
        result.qa_flags = flags
        result.qa_passed = not bias_flagged
        result.needs_human_review = bool(flags)
        return result, tokens

    @staticmethod
    def _protected_terms_in(text: str) -> set[str]:
        lowered = f" {text.lower()} "
        hits: set[str] = set()
        for term in PROTECTED_ATTRIBUTE_TERMS:
            needle = term.strip()
            pattern = r"(?<![a-z])" + re.escape(needle) + r"(?![a-z])"
            if re.search(pattern, lowered):
                hits.add(needle)
        return hits
