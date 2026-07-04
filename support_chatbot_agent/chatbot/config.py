"""Environment-driven configuration for the support chatbot.

Everything is read from environment variables so the same code runs in local
mock mode (no API keys) and in production (OpenAI + Stripe) without changes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Optional .env support. We deliberately do NOT hard-fail if python-dotenv is
# missing so the product keeps working in a minimal environment.
try:  # pragma: no cover - trivial import guard
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Resolve the package root so default paths work regardless of the CWD.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    """Runtime configuration resolved from environment variables."""

    # --- Provider selection ---------------------------------------------
    # ``mock`` runs fully offline with deterministic embeddings + answers.
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "mock").lower())

    # --- OpenAI settings (only used when llm_provider == "openai") ------
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_chat_model: str = field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    openai_embedding_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    )

    # --- Retrieval / RAG tuning -----------------------------------------
    knowledge_base_dir: Path = field(
        default_factory=lambda: Path(os.getenv("KNOWLEDGE_BASE_DIR", str(_PACKAGE_ROOT / "knowledge_base")))
    )
    index_path: Path = field(
        default_factory=lambda: Path(os.getenv("INDEX_PATH", str(_PACKAGE_ROOT / "data" / "index.json")))
    )
    chunk_size: int = field(default_factory=lambda: _get_int("CHUNK_SIZE", 250))
    chunk_overlap: int = field(default_factory=lambda: _get_int("CHUNK_OVERLAP", 40))
    top_k: int = field(default_factory=lambda: _get_int("TOP_K", 4))
    embedding_dim: int = field(default_factory=lambda: _get_int("EMBEDDING_DIM", 768))

    # --- Escalation / QA gate -------------------------------------------
    # If the best retrieval similarity is below this, we escalate to a human
    # instead of risking a hallucinated answer.
    confidence_threshold: float = field(default_factory=lambda: _get_float("CONFIDENCE_THRESHOLD", 0.18))

    # --- Billing / monetization -----------------------------------------
    price_per_1k_tokens: float = field(default_factory=lambda: _get_float("PRICE_PER_1K_TOKENS", 0.02))
    api_cost_per_1k_tokens: float = field(default_factory=lambda: _get_float("API_COST_PER_1K_TOKENS", 0.005))
    free_credits: float = field(default_factory=lambda: _get_float("FREE_CREDITS", 1.0))
    stripe_api_key: str | None = field(default_factory=lambda: os.getenv("STRIPE_API_KEY"))
    stripe_price_id: str | None = field(default_factory=lambda: os.getenv("STRIPE_PRICE_ID"))

    @property
    def is_mock(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def stripe_enabled(self) -> bool:
        return bool(self.stripe_api_key)


def get_config() -> Config:
    """Build a fresh :class:`Config` from the current environment."""
    return Config()
