"""Central configuration, loaded from environment variables.

Everything here has a sane default so the product runs with no configuration at
all in MOCK mode. Optional .env loading is best-effort: if python-dotenv is
installed we use it, otherwise we do a tiny manual parse so no dependency is
strictly required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict


def _load_dotenv() -> None:
    """Best-effort .env loader that never hard-fails."""
    # Prefer python-dotenv when available.
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
        return
    except Exception:
        pass

    # Fallback: minimal manual parser for a local .env file.
    env_path = Path(os.getcwd()) / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        # Configuration is best-effort; never crash the pipeline on parse errors.
        pass


_load_dotenv()


# Default price table: USD cost charged by the upstream LLM API per 1k tokens.
# Values mirror published list prices and are fully configurable. Open-source
# models are served through OpenRouter (https://openrouter.ai) and are ~20-50x
# cheaper than proprietary models, which is what makes the unit economics work.
DEFAULT_PRICE_PER_1K: Dict[str, Dict[str, float]] = {
    # Proprietary (OpenAI) references.
    "gpt-4o-mini": {"input": 0.00015, "output": 0.00060},
    "gpt-4o": {"input": 0.0025, "output": 0.010},
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    # Open-source models via OpenRouter (per 1k tokens).
    "meta-llama/llama-4-maverick": {"input": 0.00020, "output": 0.00060},
    "deepseek/deepseek-v4-flash": {"input": 0.00009, "output": 0.00018},
    "deepseek/deepseek-r2": {"input": 0.00030, "output": 0.00120},
    "qwen/qwen-3-235b": {"input": 0.00020, "output": 0.00060},
    "z-ai/glm-4.7": {"input": 0.00040, "output": 0.00160},
    "mock": {"input": 0.0, "output": 0.0},
}


@dataclass
class Settings:
    """Runtime settings resolved from the environment."""

    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock").lower())
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    temperature: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.7")))

    # OpenRouter (open-source models via an OpenAI-compatible endpoint).
    # Default model chosen for strong, multilingual, creative copy at low cost.
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "meta-llama/llama-4-maverick")
    )
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )

    # Billing
    starting_credits: int = field(default_factory=lambda: int(os.getenv("STARTING_CREDITS", "100")))
    credits_per_generation: int = field(
        default_factory=lambda: int(os.getenv("CREDITS_PER_GENERATION", "5"))
    )
    credit_price_usd: float = field(
        default_factory=lambda: float(os.getenv("CREDIT_PRICE_USD", "0.20"))
    )
    markup_multiplier: float = field(
        default_factory=lambda: float(os.getenv("MARKUP_MULTIPLIER", "5.0"))
    )
    stripe_api_key: str = field(default_factory=lambda: os.getenv("STRIPE_API_KEY", ""))
    stripe_price_id: str = field(default_factory=lambda: os.getenv("STRIPE_PRICE_ID", ""))

    # Scheduler
    schedule_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("SCHEDULE_INTERVAL_SECONDS", "3600"))
    )

    @property
    def price_per_1k(self) -> Dict[str, Dict[str, float]]:
        return DEFAULT_PRICE_PER_1K

    @property
    def active_model(self) -> str:
        """The model actually used for generation, given the provider."""
        if self.llm_provider == "mock":
            return "mock"
        if self.llm_provider == "openrouter":
            return self.openrouter_model
        return self.model

    def model_price(self) -> Dict[str, float]:
        return self.price_per_1k.get(self.active_model, self.price_per_1k["gpt-4o-mini"])


def get_settings() -> Settings:
    """Return a freshly-resolved Settings object (re-reads env each call)."""
    return Settings()
