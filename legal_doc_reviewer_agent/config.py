"""Central configuration for the Legal Document Reviewer.

All settings are read from environment variables with sensible defaults so the
product runs out-of-the-box in ``mock`` mode with no configuration at all.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Standard clauses we expect to find in a well-formed commercial contract.
# Used by the QA agent to detect *missing* protections.
STANDARD_CLAUSES: List[str] = [
    "Confidentiality",
    "Limitation of Liability",
    "Indemnification",
    "Termination",
    "Governing Law",
    "Dispute Resolution",
    "Intellectual Property",
    "Payment Terms",
    "Warranty",
    "Force Majeure",
]


@dataclass
class Settings:
    """Runtime settings resolved from the environment."""

    # LLM provider: "mock" (default, no keys), "openrouter" (open-source) or "openai".
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock").strip().lower())
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # OpenRouter (open-source models via an OpenAI-compatible endpoint).
    # DeepSeek V4 Flash: strong structured-output/JSON support, 1M-token context
    # (handles very long contracts) and the best cost/accuracy for extraction.
    openrouter_api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    openrouter_model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
    )
    openrouter_base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )

    # Billing / pricing.
    price_per_1k_tokens: float = field(default_factory=lambda: _get_float("PRICE_PER_1K_TOKENS", 0.03))
    api_cost_per_1k_tokens: float = field(default_factory=lambda: _get_float("API_COST_PER_1K_TOKENS", 0.005))
    flat_fee_per_document: float = field(default_factory=lambda: _get_float("FLAT_FEE_PER_DOCUMENT", 0.50))
    credits_file: str = field(default_factory=lambda: os.getenv("CREDITS_FILE", ".credits.json"))

    # Stripe (stub, disabled unless a key is present).
    stripe_api_key: str = field(default_factory=lambda: os.getenv("STRIPE_API_KEY", ""))
    stripe_price_id: str = field(default_factory=lambda: os.getenv("STRIPE_PRICE_ID", ""))

    # Automation.
    inbox_dir: str = field(default_factory=lambda: os.getenv("INBOX_DIR", "inbox"))
    outbox_dir: str = field(default_factory=lambda: os.getenv("OUTBOX_DIR", "outbox"))
    poll_interval_seconds: int = field(default_factory=lambda: _get_int("POLL_INTERVAL_SECONDS", 10))

    # QA gate: findings below this confidence are flagged for human review.
    qa_confidence_threshold: float = field(default_factory=lambda: _get_float("QA_CONFIDENCE_THRESHOLD", 0.6))

    @property
    def is_mock(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.stripe_api_key)


def get_settings() -> Settings:
    """Return a freshly-resolved Settings instance.

    Constructed on each call so tests can mutate the environment between runs.
    """
    return Settings()
