"""LLM provider interface.

The rest of the codebase only talks to the abstract :class:`LLMProvider`.
Two concrete implementations are shipped:

* :class:`MockLLMProvider` - deterministic, no network, no API key. This is the
  default and is what the test-suite and ``LLM_PROVIDER=mock`` use.
* :class:`OpenAILLMProvider` - backed by the OpenAI Chat Completions API. Only
  imported/instantiated when explicitly selected, so the ``openai`` package is
  an optional dependency.

Both providers speak a tiny JSON contract: given a ``system`` prompt, a ``user``
prompt and a ``task`` hint, return a dict ``{"content": <str>, "tokens": <int>}``.
The pipeline is responsible for parsing ``content`` as JSON.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from config import Settings, get_settings


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token), good enough for cost estimation."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


class LLMProvider(ABC):
    """Abstract provider. Implementations must be deterministic in mock mode."""

    name: str = "abstract"

    @abstractmethod
    def complete(self, system: str, user: str, task: str = "") -> Dict[str, Any]:
        """Return ``{"content": str, "tokens": int}``."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

# Heuristic clause detection keyed on section headings / keywords. Fully offline.
_CLAUSE_PATTERNS = {
    "Confidentiality": r"confidential|non-disclosure|nda",
    "Limitation of Liability": r"limitation of liability|liab(le|ility)|not be liable",
    "Indemnification": r"indemnif|hold harmless",
    "Termination": r"terminat",
    "Governing Law": r"governing law|governed by the laws",
    "Dispute Resolution": r"arbitrat|dispute resolution|jurisdiction|venue",
    "Intellectual Property": r"intellectual property|\bip\b|copyright|patent|work product",
    "Payment Terms": r"payment|invoice|fees?\b|net \d+",
    "Warranty": r"warrant",
    "Force Majeure": r"force majeure|acts of god",
    "Assignment": r"assign",
    "Non-Compete": r"non-?compete|not compete",
    "Auto-Renewal": r"auto-?renew|automatically renew|renewal term",
}

# Risky language -> (severity, explanation, suggested change).
_RISK_RULES = [
    (
        "Unlimited liability exposure",
        r"unlimited liability|without limitation of liability|no limit on liability",
        "high",
        "The contract exposes a party to unlimited liability, which can be financially catastrophic.",
        "Add a mutual limitation of liability capped at fees paid in the prior 12 months.",
    ),
    (
        "Uncapped indemnification",
        r"indemnif[a-z ]*for any and all|unlimited indemnif",
        "high",
        "Indemnification obligations are broad and uncapped.",
        "Cap indemnification and limit it to third-party claims arising from breach or negligence.",
    ),
    (
        "Automatic renewal without notice",
        r"automatically renew|auto-?renew",
        "medium",
        "The agreement auto-renews, which can lock a party into unwanted terms.",
        "Require at least 30 days' written notice before any automatic renewal and allow opt-out.",
    ),
    (
        "One-sided termination rights",
        r"terminate .*for any reason|sole discretion|at any time without cause",
        "medium",
        "Termination or discretion appears one-sided, favouring the counterparty.",
        "Make termination rights mutual and require reasonable written notice for convenience.",
    ),
    (
        "Perpetual or overly broad IP assignment",
        r"assign[s]? all .*intellectual property|perpetual.*license|irrevocable.*license",
        "high",
        "Broad IP assignment or a perpetual/irrevocable licence may transfer more rights than intended.",
        "Limit the licence in scope, duration and field of use; retain ownership of pre-existing IP.",
    ),
    (
        "Unfavourable payment terms",
        r"net 60|net 90|non-refundable|penalt(y|ies)|late fee",
        "low",
        "Payment terms include long payment windows, penalties or non-refundable amounts.",
        "Negotiate Net 30 terms and cap or remove punitive late fees.",
    ),
    (
        "Broad confidentiality with no time limit",
        r"confidential.*in perpetuity|perpetual.*confidential",
        "medium",
        "Confidentiality obligations appear perpetual, which is difficult to comply with indefinitely.",
        "Limit confidentiality obligations to a defined term (e.g. 3-5 years post-termination).",
    ),
    (
        "Non-compete restriction",
        r"non-?compete|shall not.*compete",
        "medium",
        "A non-compete clause may be overly restrictive or unenforceable in some jurisdictions.",
        "Narrow the non-compete by geography, duration and scope, or replace with non-solicitation.",
    ),
]


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.;:\n])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _excerpt_for(pattern: str, sentences: List[str]) -> str:
    rx = re.compile(pattern, re.IGNORECASE)
    for s in sentences:
        if rx.search(s):
            return s[:400]
    return ""


class MockLLMProvider(LLMProvider):
    """Deterministic offline analyzer.

    It performs genuine keyword/heuristic analysis of the contract text so that
    the pipeline produces meaningful, reproducible output with zero dependencies
    and no network access.
    """

    name = "mock"

    def complete(self, system: str, user: str, task: str = "") -> Dict[str, Any]:
        text = _extract_document(user)
        sentences = _split_sentences(text)
        tokens = estimate_tokens(system) + estimate_tokens(user)

        if task == "extract_clauses":
            content = self._extract_clauses(text, sentences)
        elif task == "analyze_risks":
            content = self._analyze_risks(text, sentences)
        elif task == "summarize":
            content = self._summarize(text, sentences)
        else:
            content = json.dumps({"result": ""})

        # Add a small deterministic token count for the "completion".
        tokens += estimate_tokens(content)
        return {"content": content, "tokens": tokens}

    def _summarize(self, text: str, sentences: List[str]) -> str:
        word_count = len(text.split())
        detected = [
            name for name, pat in _CLAUSE_PATTERNS.items()
            if re.search(pat, text, re.IGNORECASE)
        ]
        head = sentences[0] if sentences else "Contract document."
        summary = (
            f"This document is an approximately {word_count}-word agreement. "
            f"It appears to address {len(detected)} recognised clause categories "
            f"({', '.join(detected[:6]) or 'none detected'}). "
            f"Opening statement: {head[:200]}"
        )
        return json.dumps({"summary": summary})

    def _extract_clauses(self, text: str, sentences: List[str]) -> str:
        clauses = []
        for name, pat in _CLAUSE_PATTERNS.items():
            excerpt = _excerpt_for(pat, sentences)
            if excerpt:
                # Confidence is a deterministic function of match strength.
                match_count = len(re.findall(pat, text, re.IGNORECASE))
                confidence = round(min(1.0, 0.55 + 0.1 * match_count), 2)
                clauses.append(
                    {"type": name, "excerpt": excerpt, "confidence": confidence}
                )
        return json.dumps({"clauses": clauses})

    def _analyze_risks(self, text: str, sentences: List[str]) -> str:
        risks = []
        for title, pat, severity, explanation, suggestion in _RISK_RULES:
            rx = re.compile(pat, re.IGNORECASE)
            hit = None
            for s in sentences:
                if rx.search(s):
                    hit = s[:300]
                    break
            if hit:
                # Deterministic pseudo-confidence derived from a hash so some
                # findings fall below the QA threshold and exercise the gate.
                h = int(hashlib.sha256((title + hit).encode()).hexdigest(), 16)
                confidence = round(0.45 + (h % 55) / 100.0, 2)
                risks.append(
                    {
                        "title": title,
                        "severity": severity,
                        "explanation": explanation,
                        "suggested_change": suggestion,
                        "related_clause": hit,
                        "confidence": confidence,
                    }
                )
        return json.dumps({"risks": risks})


def _extract_document(user_prompt: str) -> str:
    """Pull the raw contract text back out of a user prompt.

    The pipeline embeds the document between explicit markers so the mock
    provider can recover it deterministically.
    """
    m = re.search(r"<document>(.*?)</document>", user_prompt, re.DOTALL)
    if m:
        return m.group(1).strip()
    return user_prompt.strip()


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAILLMProvider(LLMProvider):
    """OpenAI-backed provider. Requires the ``openai`` package and an API key."""

    name = "openai"

    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for the OpenAI provider. "
                "Set LLM_PROVIDER=mock to run without any keys."
            )
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # pragma: no cover - exercised only with dep
            raise RuntimeError(
                "The 'openai' package is not installed. Install it or use "
                "LLM_PROVIDER=mock."
            ) from exc
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def complete(self, system: str, user: str, task: str = "") -> Dict[str, Any]:  # pragma: no cover - needs network
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content or "{}"
        tokens = 0
        if getattr(resp, "usage", None) is not None:
            tokens = getattr(resp.usage, "total_tokens", 0) or 0
        if not tokens:
            tokens = estimate_tokens(system) + estimate_tokens(user) + estimate_tokens(content)
        return {"content": content, "tokens": tokens}


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Factory that returns the configured provider.

    Falls back to the mock provider for any unknown value so the product always
    runs.
    """
    settings = settings or get_settings()
    provider = (settings.llm_provider or "mock").lower()
    if provider == "openai":
        return OpenAILLMProvider(settings)
    return MockLLMProvider()
