"""Render a :class:`ReviewResult` as JSON or a human-readable Markdown report."""
from __future__ import annotations

import json
from typing import Any, Dict

from schemas import ReviewResult

_SEVERITY_EMOJI = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def to_json(result: ReviewResult, indent: int = 2) -> str:
    return json.dumps(result.to_dict(), indent=indent)


def to_markdown(result: ReviewResult) -> str:
    r = result
    lines = []
    lines.append(f"# Legal Document Review: {r.document_name}")
    lines.append("")
    lines.append(
        f"**Overall risk score:** {r.overall_risk_score}/100 "
        f"(**{r.risk_level.upper()}**)  |  "
        f"**Provider:** `{r.provider}`  |  "
        f"**Est. tokens:** {r.token_usage}"
    )
    lines.append("")
    lines.append("> DISCLAIMER: This automated review is **not legal advice**. "
                 "Consult a qualified attorney before acting on it.")
    lines.append("")

    lines.append("## Summary")
    lines.append(r.document_summary)
    lines.append("")

    lines.append("## QA / Reviewer Assessment")
    lines.append(f"- **Passed QA gate:** {'yes' if r.qa.passed else 'no'}")
    lines.append(f"- **Completeness score:** {r.qa.completeness_score:.2f}")
    lines.append(f"- **Needs human review:** {'yes' if r.qa.needs_human_review else 'no'}")
    if r.qa.flagged_findings:
        lines.append("- **Flagged (low-confidence) findings:**")
        for f in r.qa.flagged_findings:
            lines.append(f"  - {f}")
    if r.qa.notes:
        lines.append("- **Notes:**")
        for n in r.qa.notes:
            lines.append(f"  - {n}")
    lines.append("")

    lines.append("## Key Clauses")
    if r.key_clauses:
        lines.append("| Type | Confidence | Excerpt |")
        lines.append("| --- | --- | --- |")
        for c in r.key_clauses:
            excerpt = c.excerpt.replace("\n", " ").replace("|", "\\|")
            if len(excerpt) > 160:
                excerpt = excerpt[:157] + "..."
            lines.append(f"| {c.type} | {c.confidence:.2f} | {excerpt} |")
    else:
        lines.append("_No key clauses were extracted._")
    lines.append("")

    lines.append("## Identified Risks / Red Flags")
    if r.risks:
        for i, risk in enumerate(r.risks, 1):
            tag = _SEVERITY_EMOJI.get(risk.severity, risk.severity.upper())
            lines.append(f"### {i}. {risk.title} [{tag}]")
            lines.append(f"- **Explanation:** {risk.explanation}")
            lines.append(f"- **Suggested change:** {risk.suggested_change}")
            if risk.related_clause:
                rc = risk.related_clause.replace("\n", " ")
                lines.append(f"- **Related text:** _{rc[:200]}_")
            lines.append(f"- **Confidence:** {risk.confidence:.2f}")
            lines.append("")
    else:
        lines.append("_No risks were identified._")
        lines.append("")

    lines.append("## Missing Standard Clauses")
    if r.missing_clauses:
        for m in r.missing_clauses:
            lines.append(f"- {m}")
    else:
        lines.append("_All standard clauses appear to be present._")
    lines.append("")

    return "\n".join(lines)


def to_bundle(result: ReviewResult) -> Dict[str, Any]:
    """Return both representations for API responses."""
    return {"json": result.to_dict(), "markdown": to_markdown(result)}
