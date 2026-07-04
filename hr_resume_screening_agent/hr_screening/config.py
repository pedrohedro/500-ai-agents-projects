"""Runtime configuration loaded from environment variables.

Everything has a safe default so the pipeline runs in mock mode with zero
configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Settings:
    """Central settings object."""

    llm_provider: str = "mock"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # OpenRouter (open-source models via an OpenAI-compatible endpoint).
    openrouter_api_key: str | None = None
    openrouter_model: str = "deepseek/deepseek-v4-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Billing / pricing
    price_per_1k_tokens_usd: float = 0.01
    margin_multiplier: float = 3.0
    price_per_resume_usd: float = 0.50

    # Stripe (stub)
    stripe_api_key: str | None = None

    # QA gate
    min_confidence: float = 0.35

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "mock").strip().lower(),
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            openrouter_model=os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash"),
            openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            price_per_1k_tokens_usd=_get_float("PRICE_PER_1K_TOKENS_USD", 0.01),
            margin_multiplier=_get_float("MARGIN_MULTIPLIER", 3.0),
            price_per_resume_usd=_get_float("PRICE_PER_RESUME_USD", 0.50),
            stripe_api_key=os.environ.get("STRIPE_API_KEY") or None,
            min_confidence=_get_float("MIN_CONFIDENCE", 0.35),
        )
