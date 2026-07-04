"""LLM provider interface.

The pipeline talks to the LLM only through :class:`LLMProvider`. Two
implementations are shipped:

* :class:`MockLLM`   -- deterministic, offline, no API key. Used for tests and
  for the mandatory ``LLM_PROVIDER=mock`` end-to-end run.
* :class:`OpenAILLM` -- thin wrapper around the OpenAI Chat Completions API.

Core parsing/scoring is deterministic (see :mod:`hr_screening.skills`); the LLM
is used to write the natural-language rationale and to perform a secondary
fairness review. This keeps the product fully functional without any keys while
still benefiting from a real model when one is configured.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), good enough for cost estimates."""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMProvider(ABC):
    """Abstract LLM provider."""

    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 400) -> LLMResponse:
        """Return a completion for ``prompt``."""

    def write_rationale(
        self,
        name: str,
        matched: list[str],
        gaps: list[str],
        score: float,
        years: float,
    ) -> LLMResponse:
        """Produce a short hiring rationale."""
        prompt = (
            f"Candidate: {name}\n"
            f"Match score: {score:.0f}/100\n"
            f"Years experience: {years:g}\n"
            f"Matched skills: {', '.join(matched) or 'none'}\n"
            f"Missing skills: {', '.join(gaps) or 'none'}\n\n"
            "Write a concise (2-3 sentence) neutral hiring rationale focused only "
            "on job-relevant skills and experience. Do not reference age, gender, "
            "race, nationality, or other protected attributes."
        )
        system = "You are a fair, evidence-based technical recruiter."
        return self.complete(prompt, system=system, max_tokens=160)

    def fairness_review(self, resume_text: str, rationale: str) -> LLMResponse:
        """Secondary textual fairness check. Returns 'OK' or a flag string."""
        prompt = (
            "Review the following hiring rationale for bias against protected "
            "attributes (age, gender, race, religion, nationality, disability, "
            "marital/family status). Reply with 'OK' if clean, otherwise reply "
            "'FLAG: <reason>'.\n\n"
            f"Rationale:\n{rationale}\n"
        )
        system = "You are an AI fairness and compliance auditor."
        return self.complete(prompt, system=system, max_tokens=80)


class MockLLM(LLMProvider):
    """Deterministic, offline provider.

    Generates plausible, stable text from the structured prompt without any
    network access. Perfect for tests and no-key operation.
    """

    name = "mock"

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 400) -> LLMResponse:
        text = self._render(prompt, system)
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens(system + prompt),
            completion_tokens=estimate_tokens(text),
        )

    @staticmethod
    def _render(prompt: str, system: str) -> str:
        low = prompt.lower()
        if "fairness" in system.lower() or "reply with 'ok'" in low:
            # Deterministic clean review; real bias detection is done
            # deterministically in the QA agent.
            return "OK"

        # Rationale generation: parse the structured fields back out.
        fields = _parse_kv(prompt)
        name = fields.get("candidate", "The candidate")
        score = fields.get("match score", "")
        matched = fields.get("matched skills", "none")
        gaps = fields.get("missing skills", "none")
        years = fields.get("years experience", "0")

        matched_part = (
            f"brings relevant experience in {matched}" if matched != "none"
            else "shows limited overlap with the required skill set"
        )
        gap_part = (
            f" Key gaps to probe in interview: {gaps}." if gaps != "none"
            else " No major skill gaps were detected against the requirements."
        )
        return (
            f"{name} scores {score} and {matched_part} with {years} years of "
            f"experience.{gap_part} Recommendation is based solely on "
            f"job-relevant qualifications."
        )


def _parse_kv(prompt: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in prompt.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip().lower()] = value.strip()
    return out


class OpenAILLM(LLMProvider):
    """OpenAI Chat Completions backed provider."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover - only when lib missing
            raise RuntimeError(
                "openai package is not installed. Install it or use LLM_PROVIDER=mock."
            ) from exc
        self._client = OpenAI(api_key=api_key)
        self.model = model

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 400) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        if usage is not None:
            return LLMResponse(
                text=text,
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
            )
        return LLMResponse(
            text=text,
            prompt_tokens=estimate_tokens(system + prompt),
            completion_tokens=estimate_tokens(text),
        )


def get_llm(provider: str | None = None, *, api_key: str | None = None, model: str | None = None) -> LLMProvider:
    """Factory returning an :class:`LLMProvider`.

    Falls back to :class:`MockLLM` whenever OpenAI cannot be initialized so the
    product keeps working offline.
    """
    provider = (provider or os.environ.get("LLM_PROVIDER", "mock")).strip().lower()
    if provider == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Set the key or use LLM_PROVIDER=mock."
            )
        mdl = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return OpenAILLM(api_key=key, model=mdl)
    return MockLLM()
