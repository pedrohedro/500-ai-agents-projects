"""Orchestrates the Researcher -> Copywriter -> Editor/QA pipeline.

Mirrors CrewAI's sequential process: each agent runs in order, passing context
forward. The QA gate validates output before it is released. Billing is applied
before generation (credits are reserved/charged up-front) so out-of-credits is
enforced deterministically.
"""

from __future__ import annotations

from typing import Optional

from .agents import CopywriterAgent, EditorQAAgent, ResearcherAgent
from .billing import BillingEngine, Wallet
from .config import Settings, get_settings
from .llm import LLMProvider, get_llm
from .schemas import ContentBrief, Deliverable, SocialVariations, UsageStats


class ContentPipeline:
    """A configurable, multi-agent content generation pipeline."""

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        settings: Optional[Settings] = None,
        billing: Optional[BillingEngine] = None,
        max_qa_retries: int = 1,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm or get_llm(self.settings)
        self.billing = billing or BillingEngine(self.settings)
        self.researcher = ResearcherAgent(self.llm)
        self.copywriter = CopywriterAgent(self.llm)
        self.editor = EditorQAAgent(self.llm)
        self.max_qa_retries = max_qa_retries

    def run(self, brief: ContentBrief, wallet: Optional[Wallet] = None) -> Deliverable:
        """Run the full pipeline. If ``wallet`` is given, credits are charged
        up-front and OutOfCreditsError propagates if the wallet is empty."""
        if wallet is not None:
            # Charge before doing any (potentially costly) LLM work.
            self.billing.charge_for_generation(wallet, reason=f"generate:{brief.topic}")

        prompt_tokens = 0
        completion_tokens = 0

        # 1) Research
        research = self.researcher.run(brief)
        prompt_tokens += research.prompt_tokens
        completion_tokens += research.completion_tokens

        # 2) Copywriting
        copy = self.copywriter.run(brief, research.data["research_notes"])
        prompt_tokens += copy.prompt_tokens
        completion_tokens += copy.completion_tokens

        content = dict(copy.data)
        content.setdefault("social", SocialVariations())

        # 3) Editor / QA — review, and retry copy once if it fails the gate.
        qa = self.editor.review(brief, content)
        attempts = 0
        while not qa.passed and attempts < self.max_qa_retries:
            attempts += 1
            copy = self.copywriter.run(brief, research.data["research_notes"])
            prompt_tokens += copy.prompt_tokens
            completion_tokens += copy.completion_tokens
            content = dict(copy.data)
            content.setdefault("social", SocialVariations())
            qa = self.editor.review(brief, content)

        estimate = self.billing.estimate_cost(prompt_tokens, completion_tokens)
        usage = UsageStats(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=estimate.api_cost_usd,
            credits_charged=(self.billing.credits_for_generation() if wallet is not None else 0),
        )

        return Deliverable(
            brief=brief,
            seo_title=content.get("seo_title", ""),
            meta_description=content.get("meta_description", ""),
            blog_post=content.get("blog_post", ""),
            social=content.get("social", SocialVariations()),
            hashtags=content.get("hashtags", []),
            research_notes=research.data["research_notes"],
            qa=qa,
            usage=usage,
        )


def run_pipeline(
    brief: ContentBrief,
    *,
    wallet: Optional[Wallet] = None,
    settings: Optional[Settings] = None,
) -> Deliverable:
    """Convenience one-shot runner."""
    settings = settings or get_settings()
    pipeline = ContentPipeline(settings=settings)
    return pipeline.run(brief, wallet=wallet)
