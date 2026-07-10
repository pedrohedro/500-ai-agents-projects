"""Adapter for the marketing_content_agent package.

Real integration: imports the ``ContentPipeline`` and ``ContentBrief`` from the
package (a proper Python package with relative imports) and runs it. Falls back
to a deterministic mock if the import fails.
"""

from __future__ import annotations

from typing import Any, Dict

from .base import AgentResult, BaseAdapter, ensure_repo_on_path, prepare_llm_env


class MarketingAdapter(BaseAdapter):
    name = "marketing"

    def _run_real(self, payload: Dict[str, Any]) -> AgentResult:
        ensure_repo_on_path()
        provider = prepare_llm_env()

        from marketing_content_agent.pipeline import ContentPipeline
        from marketing_content_agent.schemas import ContentBrief

        topic = (payload.get("topic") or "").strip()
        if not topic:
            raise ValueError("Field 'topic' is required.")

        keywords = payload.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        brief = ContentBrief(
            topic=topic,
            target_audience=payload.get("audience", "general audience"),
            platform=payload.get("platform", "blog"),
            tone=payload.get("tone", "professional"),
            keywords=keywords,
            call_to_action=payload.get("call_to_action", "Learn more"),
            word_count=int(payload.get("word_count", 600)),
        )

        pipeline = ContentPipeline()
        deliverable = pipeline.run(brief)
        data = deliverable.to_dict()
        usage = data.get("usage", {})
        return AgentResult(
            output=data,
            tokens=int(usage.get("total_tokens", 0)),
            usd_cost=float(usage.get("estimated_cost_usd", 0.0)),
            provider=getattr(pipeline.llm, "name", provider),
        )

    def _run_mock(self, payload: Dict[str, Any]) -> AgentResult:
        topic = (payload.get("topic") or "your product").strip()
        audience = payload.get("audience", "general audience")
        output = {
            "seo_title": f"The Complete Guide to {topic}",
            "meta_description": f"Everything {audience} need to know about {topic}.",
            "blog_post": (
                f"# {topic}\n\n{topic} matters to {audience}. "
                "This deterministic mock output proves the platform works even "
                "when the real agent package is unavailable."
            ),
            "social": {
                "linkedin": f"Why {topic} matters for {audience}.",
                "twitter": f"{topic}: a quick take.",
                "instagram": f"Let's talk {topic}.",
            },
            "hashtags": [f"#{topic.replace(' ', '')}", "#marketing"],
        }
        return AgentResult(output=output, tokens=120, usd_cost=0.0, used_mock_adapter=True)
