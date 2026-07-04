"""LLM provider interface with an OpenAI-backed implementation and a
deterministic MOCK implementation.

The whole product is designed so that ``LLM_PROVIDER=mock`` requires no API
keys and no network — this is the path used for verification and testing.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from .config import Settings, get_settings


@dataclass
class LLMResponse:
    """A single completion plus token accounting."""

    text: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) used for cost accounting.

    Deterministic and dependency-free; good enough for billing estimates and
    identical across mock/real so tests are stable.
    """
    if not text:
        return 0
    # Count word-ish chunks then apply a chars-per-token heuristic.
    char_estimate = max(1, len(text) // 4)
    word_estimate = len(re.findall(r"\S+", text))
    return max(char_estimate, word_estimate)


class LLMProvider(ABC):
    """Abstract provider. Implementations must be safe to construct cheaply."""

    name: str = "abstract"

    @abstractmethod
    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        """Return a completion for ``prompt`` with an optional system message."""
        raise NotImplementedError


class MockLLM(LLMProvider):
    """Deterministic, offline provider.

    Produces plausible, structured marketing copy purely from the prompt content
    so the pipeline output is realistic and fully reproducible in CI. It keys off
    ``role`` markers embedded in prompts by the agents.
    """

    name = "mock"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    def _seed(self, text: str) -> int:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:
        full_prompt = f"{system or ''}\n{prompt}"
        text = self._render(prompt)
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens(full_prompt),
            completion_tokens=estimate_tokens(text),
        )

    # -- deterministic content generators keyed on role marker ----------------

    def _render(self, prompt: str) -> str:
        role = self._extract(prompt, "ROLE") or "generic"
        topic = self._extract(prompt, "TOPIC") or "the topic"
        audience = self._extract(prompt, "AUDIENCE") or "your audience"
        tone = self._extract(prompt, "TONE") or "professional"
        platform = self._extract(prompt, "PLATFORM") or "blog"
        cta = self._extract(prompt, "CTA") or "Learn more"
        keywords = self._extract(prompt, "KEYWORDS") or ""

        if role == "researcher":
            return self._research(topic, audience, keywords)
        if role == "copywriter":
            return self._copy(topic, audience, tone, platform, cta, keywords)
        if role == "editor":
            # The editor mock lightly "polishes" by trimming double spaces.
            body = self._extract(prompt, "DRAFT") or ""
            return re.sub(r"[ \t]{2,}", " ", body).strip()
        return f"[mock:{role}] Content about {topic} for {audience}."

    @staticmethod
    def _extract(prompt: str, marker: str) -> str:
        # Markers are written as <<MARKER: value>> by the agents.
        match = re.search(rf"<<{marker}:(.*?)>>", prompt, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _research(self, topic: str, audience: str, keywords: str) -> str:
        kw = keywords or topic
        return (
            f"Research summary on {topic}:\n"
            f"- Audience insight: {audience} increasingly care about {topic} and value clarity.\n"
            f"- Trend: demand for {topic} solutions is rising year over year.\n"
            f"- Pain point: {audience} struggle to find trustworthy guidance on {topic}.\n"
            f"- Opportunity: educational, benefit-led content converts best.\n"
            f"- Suggested angles: how-to, myth-busting, and ROI-focused framing.\n"
            f"- Primary keywords to target: {kw}."
        )

    def _copy(self, topic, audience, tone, platform, cta, keywords) -> str:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] or [topic]
        primary_kw = kw_list[0]
        blog = (
            f"# {self._title(topic)}\n\n"
            f"If you're part of {audience}, {topic} probably feels both important and "
            f"overwhelming. This guide breaks it down in a {tone} way so you can act with "
            f"confidence.\n\n"
            f"## Why {topic} matters now\n\n"
            f"Interest in {topic} is at an all-time high, and for good reason: it directly "
            f"affects results that {audience} care about. Getting it right saves time, money, "
            f"and stress.\n\n"
            f"## Three practical takeaways\n\n"
            f"1. Start with a clear goal for {primary_kw} before choosing tools.\n"
            f"2. Measure what matters instead of chasing vanity metrics.\n"
            f"3. Iterate quickly — small, consistent improvements compound.\n\n"
            f"## Putting it into practice\n\n"
            f"You don't need a huge budget to make progress on {topic}. Focus on fundamentals, "
            f"stay consistent, and let data guide your next move.\n\n"
            f"{cta} — {cta.lower()} today and take the next step with {topic}."
        )
        insta = (
            f"✨ {self._title(topic)} ✨\n\n"
            f"Made for {audience} who want real results, not hype. Swipe for 3 quick wins on "
            f"{primary_kw}. {cta} 👉 link in bio."
        )
        linkedin = (
            f"{self._title(topic)}\n\n"
            f"For {audience}: {topic} is no longer optional. Here are three takeaways we keep "
            f"coming back to:\n\n"
            f"1) Set a clear goal.\n2) Measure what matters.\n3) Iterate fast.\n\n"
            f"{cta}. What would you add to this list?"
        )
        twitter = (
            f"{topic} in one thread 🧵\n\n"
            f"For {audience}: 3 things that actually move the needle on {primary_kw}. "
            f"{cta} 👇"
        )
        # Encode sub-sections so the copywriter agent can parse them back.
        return (
            f"<<BLOG>>{blog}<<END>>\n"
            f"<<INSTAGRAM>>{insta}<<END>>\n"
            f"<<LINKEDIN>>{linkedin}<<END>>\n"
            f"<<TWITTER>>{twitter}<<END>>\n"
            f"<<SEO_TITLE>>{self._title(topic)} | A Practical Guide<<END>>\n"
            f"<<META>>Discover how {audience} can master {topic}. Actionable tips, real "
            f"takeaways, and a clear next step. {cta}.<<END>>\n"
            f"<<HASHTAGS>>{self._hashtags(kw_list, topic)}<<END>>"
        )

    @staticmethod
    def _title(topic: str) -> str:
        return topic.strip().title()

    @staticmethod
    def _hashtags(kw_list: List[str], topic: str) -> str:
        tags = []
        for kw in kw_list + [topic, "marketing", "growth"]:
            tag = "#" + re.sub(r"[^A-Za-z0-9]", "", kw.title())
            if tag != "#" and tag not in tags:
                tags.append(tag)
        return ", ".join(tags[:8])


class OpenAILLM(LLMProvider):
    """OpenAI-backed provider. Imports the SDK lazily so it is never required
    for mock runs. Raises a clear error if used without an API key or SDK."""

    name = "openai"

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Use LLM_PROVIDER=mock for offline runs."
            )
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional dep
            raise RuntimeError(
                "The 'openai' package is not installed. Install it or use "
                "LLM_PROVIDER=mock."
            ) from exc
        self._client = OpenAI(api_key=self.settings.openai_api_key)

    def complete(self, prompt: str, *, system: Optional[str] = None) -> LLMResponse:  # pragma: no cover - network
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self.settings.model,
            temperature=self.settings.temperature,
            messages=messages,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        if usage is not None:
            return LLMResponse(
                text=text,
                prompt_tokens=getattr(usage, "prompt_tokens", estimate_tokens(prompt)),
                completion_tokens=getattr(usage, "completion_tokens", estimate_tokens(text)),
            )
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens((system or "") + prompt),
            completion_tokens=estimate_tokens(text),
        )


def get_llm(settings: Optional[Settings] = None) -> LLMProvider:
    """Factory that returns the configured provider.

    Falls back to MockLLM for any unknown provider string so the product never
    hard-crashes on misconfiguration in a demo environment.
    """
    settings = settings or get_settings()
    provider = settings.llm_provider
    if provider == "openai":
        return OpenAILLM(settings)
    if provider == "mock":
        return MockLLM(settings)
    # Unknown provider -> safe default.
    return MockLLM(settings)
