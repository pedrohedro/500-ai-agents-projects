"""End-to-end screening pipeline orchestration.

Wires the agents together, enforces billing, ranks candidates, and applies the
QA/fairness gate.
"""

from __future__ import annotations

from .agents import (
    JDMatcherAgent,
    QAReviewAgent,
    ResumeParserAgent,
    ScorerAgent,
    parse_job_description,
)
from .billing import BillingAccount, OutOfCreditsError
from .config import Settings
from .llm import LLMProvider, estimate_tokens, get_llm
from .models import CandidateResult, JobDescription, ResumeDocument, ScreeningReport


class ScreeningPipeline:
    """Coordinates Parser -> Matcher -> Scorer -> QA over a batch of resumes."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        settings: Settings | None = None,
        billing: BillingAccount | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.llm = llm or get_llm(self.settings.llm_provider)
        self.billing = billing
        self.parser = ResumeParserAgent()
        self.matcher = JDMatcherAgent()
        self.scorer = ScorerAgent(self.llm)
        self.qa = QAReviewAgent(self.llm, min_confidence=self.settings.min_confidence)

    # ------------------------------------------------------------------ #
    def screen(
        self,
        jd: JobDescription | str,
        resumes: list[ResumeDocument],
        job_title: str | None = None,
    ) -> ScreeningReport:
        if isinstance(jd, str):
            jd = parse_job_description(jd, title=job_title)

        results: list[CandidateResult] = []
        total_tokens = 0
        total_cost = 0.0

        jd_tokens = estimate_tokens(jd.raw_text)

        for doc in resumes:
            # ---- billing gate (before doing paid work) -----------------
            if self.billing is not None:
                est_tokens = estimate_tokens(doc.raw_text) + jd_tokens + 220
                try:
                    total_cost += self.billing.charge_for_resume(est_tokens)
                except OutOfCreditsError:
                    # Stop cleanly; return what we have so far.
                    break

            parsed = self.parser.run(doc)
            match = self.matcher.run(jd, parsed)
            result, score_tokens = self.scorer.run(jd, parsed, match)
            result, qa_tokens = self.qa.run(result)
            total_tokens += score_tokens + qa_tokens
            results.append(result)

        ranked = self._rank(results)

        credits_remaining = self.billing.credits if self.billing is not None else None
        return ScreeningReport(
            job_title=jd.title,
            candidates=ranked,
            tokens_used=total_tokens,
            cost_usd=round(total_cost, 6),
            credits_remaining=credits_remaining,
            provider=self.llm.name,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _rank(results: list[CandidateResult]) -> list[CandidateResult]:
        """Sort by score desc, then confidence desc, then name for stability."""
        ranked = sorted(
            results,
            key=lambda c: (-c.score, -c.confidence, c.name.lower()),
        )
        for i, c in enumerate(ranked, start=1):
            c.rank = i
        return ranked
