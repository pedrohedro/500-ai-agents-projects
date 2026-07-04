"""Render a Deliverable as human-friendly Markdown."""

from __future__ import annotations

from .schemas import Deliverable


def to_markdown(d: Deliverable) -> str:
    lines = []
    lines.append(f"# {d.seo_title or d.brief.topic}")
    lines.append("")
    lines.append(f"> **Meta description:** {d.meta_description}")
    lines.append("")
    lines.append(
        f"*Topic:* {d.brief.topic} · *Audience:* {d.brief.target_audience} · "
        f"*Platform:* {d.brief.platform} · *Tone:* {d.brief.tone}"
    )
    lines.append("")
    status = "PASSED" if d.qa.passed else "FAILED"
    lines.append(f"*QA:* **{status}** (score {d.qa.score})")
    if d.qa.issues:
        lines.append("")
        lines.append("**QA issues:**")
        for issue in d.qa.issues:
            lines.append(f"- {issue}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Blog Post")
    lines.append("")
    lines.append(d.blog_post)
    lines.append("")
    lines.append("## Social Variations")
    lines.append("")
    lines.append("### Instagram")
    lines.append("")
    lines.append(d.social.instagram)
    lines.append("")
    lines.append("### LinkedIn")
    lines.append("")
    lines.append(d.social.linkedin)
    lines.append("")
    lines.append("### X / Twitter")
    lines.append("")
    lines.append(d.social.twitter)
    lines.append("")
    lines.append("## Hashtags")
    lines.append("")
    lines.append(" ".join(d.hashtags))
    lines.append("")
    lines.append("## Usage & Cost")
    lines.append("")
    lines.append(
        f"- Tokens: {d.usage.total_tokens} "
        f"(prompt {d.usage.prompt_tokens} / completion {d.usage.completion_tokens})"
    )
    lines.append(f"- Estimated API cost: ${d.usage.estimated_cost_usd:.6f}")
    lines.append(f"- Credits charged: {d.usage.credits_charged}")
    lines.append("")
    return "\n".join(lines)
