"""Lightweight multi-agent abstraction.

Each agent has a role, a system prompt, and a ``run`` method that takes a shared
context dict and returns its contribution. This mirrors the CrewAI mental model
(agents + tasks + sequential process) without requiring the dependency. If
CrewAI is installed it can be swapped in behind the same pipeline; the mock path
never needs it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List

from .llm import LLMProvider, LLMResponse
from .schemas import ContentBrief, QAReport, SocialVariations


@dataclass
class AgentResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    data: Dict = field(default_factory=dict)


class Agent:
    """Base agent: wraps an LLM provider with a role + system prompt."""

    role: str = "generic"
    system_prompt: str = "You are a helpful assistant."

    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def _call(self, prompt: str) -> LLMResponse:
        return self.llm.complete(prompt, system=self.system_prompt)

    @staticmethod
    def _markers(brief: ContentBrief) -> str:
        return (
            f"<<TOPIC:{brief.topic}>> "
            f"<<AUDIENCE:{brief.target_audience}>> "
            f"<<TONE:{brief.tone}>> "
            f"<<PLATFORM:{brief.platform}>> "
            f"<<CTA:{brief.call_to_action}>> "
            f"<<KEYWORDS:{', '.join(brief.keywords)}>> "
            f"<<WORDCOUNT:{brief.word_count}>>"
        )


class ResearcherAgent(Agent):
    role = "researcher"
    system_prompt = (
        "You are a senior market researcher. You produce concise, factual, "
        "insight-driven briefs that a copywriter can act on."
    )

    def run(self, brief: ContentBrief) -> AgentResult:
        prompt = (
            "<<ROLE:researcher>>\n"
            f"{self._markers(brief)}\n"
            f"Research the topic and summarize audience insights, trends, pain points, "
            f"and the best content angles."
        )
        resp = self._call(prompt)
        return AgentResult(
            text=resp.text,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            data={"research_notes": resp.text},
        )


class CopywriterAgent(Agent):
    role = "copywriter"
    system_prompt = (
        "You are an expert marketing copywriter. You turn research into a blog "
        "post plus platform-native social variations, SEO metadata, and hashtags."
    )

    def run(self, brief: ContentBrief, research_notes: str) -> AgentResult:
        prompt = (
            "<<ROLE:copywriter>>\n"
            f"{self._markers(brief)}\n"
            f"<<RESEARCH:{research_notes}>>\n"
            "Write a blog post, Instagram/LinkedIn/Twitter variations, an SEO title, "
            "a meta description, and hashtags. Delimit each section with the given tags."
        )
        resp = self._call(prompt)
        parsed = self._parse(resp.text)
        return AgentResult(
            text=resp.text,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            data=parsed,
        )

    @staticmethod
    def _section(text: str, tag: str) -> str:
        match = re.search(rf"<<{tag}>>(.*?)<<END>>", text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _parse(self, text: str) -> Dict:
        hashtags_raw = self._section(text, "HASHTAGS")
        hashtags = [h.strip() for h in hashtags_raw.split(",") if h.strip()]
        return {
            "blog_post": self._section(text, "BLOG"),
            "social": SocialVariations(
                instagram=self._section(text, "INSTAGRAM"),
                linkedin=self._section(text, "LINKEDIN"),
                twitter=self._section(text, "TWITTER"),
            ),
            "seo_title": self._section(text, "SEO_TITLE"),
            "meta_description": self._section(text, "META"),
            "hashtags": hashtags,
        }


# Words we never want to ship in marketing copy (spammy / non-compliant claims).
DEFAULT_BANNED_WORDS: List[str] = [
    "guaranteed",
    "miracle",
    "100% free",
    "risk-free",
    "clickbait",
    "get rich quick",
    "lorem ipsum",
]


class EditorQAAgent(Agent):
    """Editor + QA reviewer. Enforces objective quality gates before release."""

    role = "editor"
    system_prompt = (
        "You are a meticulous editor and QA reviewer. You verify tone, length, "
        "banned-word compliance, and presence of a call to action, then approve "
        "or reject the deliverable."
    )

    def __init__(
        self,
        llm: LLMProvider,
        banned_words: List[str] | None = None,
        min_blog_words: int = 120,
        max_meta_chars: int = 200,
        pass_threshold: float = 0.75,
    ) -> None:
        super().__init__(llm)
        self.banned_words = [w.lower() for w in (banned_words or DEFAULT_BANNED_WORDS)]
        self.min_blog_words = min_blog_words
        self.max_meta_chars = max_meta_chars
        self.pass_threshold = pass_threshold

    def review(self, brief: ContentBrief, content: Dict) -> QAReport:
        blog = content.get("blog_post", "") or ""
        social = content.get("social", SocialVariations())
        seo_title = content.get("seo_title", "") or ""
        meta = content.get("meta_description", "") or ""
        hashtags = content.get("hashtags", []) or []

        combined = " ".join(
            [blog, social.instagram, social.linkedin, social.twitter, seo_title, meta]
        )
        combined_lower = combined.lower()

        blog_words = len(re.findall(r"\S+", blog))
        cta_terms = {brief.call_to_action.lower(), "learn more", "sign up", "get started",
                     "today", "next step", "link in bio", "subscribe", "join"}
        has_cta = any(term and term in combined_lower for term in cta_terms)

        found_banned = [w for w in self.banned_words if w in combined_lower]

        checks = {
            "blog_present": bool(blog.strip()),
            "blog_min_length": blog_words >= self.min_blog_words,
            "seo_title_present": bool(seo_title.strip()),
            "meta_present": bool(meta.strip()),
            "meta_length_ok": 0 < len(meta) <= self.max_meta_chars,
            "social_complete": all(
                [social.instagram.strip(), social.linkedin.strip(), social.twitter.strip()]
            ),
            "hashtags_present": len(hashtags) >= 3,
            "has_cta": has_cta,
            "no_banned_words": len(found_banned) == 0,
        }

        issues: List[str] = []
        if not checks["blog_present"]:
            issues.append("Blog post is empty.")
        if not checks["blog_min_length"]:
            issues.append(
                f"Blog post too short: {blog_words} words (min {self.min_blog_words})."
            )
        if not checks["seo_title_present"]:
            issues.append("SEO title missing.")
        if not checks["meta_present"]:
            issues.append("Meta description missing.")
        if not checks["meta_length_ok"]:
            issues.append(
                f"Meta description length {len(meta)} out of range (1..{self.max_meta_chars})."
            )
        if not checks["social_complete"]:
            issues.append("One or more social variations are missing.")
        if not checks["hashtags_present"]:
            issues.append("Fewer than 3 hashtags provided.")
        if not checks["has_cta"]:
            issues.append("No clear call to action detected.")
        if not checks["no_banned_words"]:
            issues.append(f"Banned words present: {', '.join(found_banned)}.")

        score = sum(1 for v in checks.values() if v) / len(checks)
        # These checks are non-negotiable: failing any one blocks release
        # regardless of the aggregate score.
        critical = ["blog_present", "blog_min_length", "no_banned_words", "has_cta"]
        critical_ok = all(checks[c] for c in critical)
        passed = critical_ok and score >= self.pass_threshold
        return QAReport(passed=passed, score=round(score, 3), checks=checks, issues=issues)
