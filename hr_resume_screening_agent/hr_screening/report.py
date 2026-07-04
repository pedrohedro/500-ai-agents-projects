"""Render screening results as Markdown and JSON."""

from __future__ import annotations

import json

from .models import ScreeningReport


def to_json(report: ScreeningReport, *, indent: int = 2) -> str:
    return json.dumps(report.to_dict(), indent=indent, ensure_ascii=False)


def to_markdown(report: ScreeningReport) -> str:
    lines: list[str] = []
    lines.append(f"# Candidate Screening Report - {report.job_title}")
    lines.append("")
    lines.append(f"- **Provider:** `{report.provider}`")
    lines.append(f"- **Candidates screened:** {len(report.candidates)}")
    lines.append(f"- **Tokens used (est.):** {report.tokens_used}")
    lines.append(f"- **Cost (USD):** ${report.cost_usd:.4f}")
    if report.credits_remaining is not None:
        lines.append(f"- **Credits remaining:** {report.credits_remaining:.4f}")
    lines.append("")

    lines.append("## Ranking")
    lines.append("")
    lines.append("| Rank | Candidate | Score | Confidence | QA | Matched skills | Gaps |")
    lines.append("|------|-----------|-------|------------|----|----------------|------|")
    for c in report.candidates:
        qa = "PASS" if c.qa_passed else "REVIEW"
        if c.needs_human_review and c.qa_passed:
            qa = "REVIEW*"
        matched = ", ".join(c.matched_skills) or "-"
        gaps = ", ".join(c.gaps) or "-"
        lines.append(
            f"| {c.rank} | {c.name} | {c.score:.1f} | {c.confidence:.2f} | {qa} "
            f"| {matched} | {gaps} |"
        )
    lines.append("")
    lines.append("_QA legend: PASS = released, REVIEW = fairness/bias flag, "
                 "REVIEW* = low-confidence, human review recommended._")
    lines.append("")

    lines.append("## Details")
    lines.append("")
    for c in report.candidates:
        lines.append(f"### {c.rank}. {c.name}  -  score {c.score:.1f}")
        lines.append("")
        lines.append(f"- **Years experience:** {c.years_experience:g}")
        lines.append(f"- **Matched skills:** {', '.join(c.matched_skills) or 'none'}")
        lines.append(f"- **Gaps:** {', '.join(c.gaps) or 'none'}")
        lines.append(f"- **Confidence:** {c.confidence:.2f}")
        lines.append(f"- **Rationale:** {c.rationale}")
        if c.qa_flags:
            lines.append(f"- **QA flags:** {'; '.join(c.qa_flags)}")
        lines.append("")
    return "\n".join(lines)
