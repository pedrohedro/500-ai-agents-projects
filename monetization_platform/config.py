"""Central, environment-driven configuration for the monetization platform.

Every value has a sane default so the platform boots and runs end-to-end with no
configuration at all (local SQLite + mock Stripe + mock LLM). To go live the
owner only needs to set a handful of variables (see ``.env.example``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List

try:  # best-effort .env loading; never hard-fail if missing.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


@dataclass(frozen=True)
class CreditPack:
    """A purchasable bundle of credits."""

    key: str
    name: str
    price_usd: float
    credits: int

    @property
    def price_cents(self) -> int:
        return int(round(self.price_usd * 100))

    def to_dict(self) -> Dict[str, object]:
        return {
            "key": self.key,
            "name": self.name,
            "price_usd": self.price_usd,
            "credits": self.credits,
            "price_per_credit_usd": round(self.price_usd / self.credits, 4)
            if self.credits
            else 0.0,
        }


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    """Runtime settings resolved from environment variables on construction."""

    def __init__(self) -> None:
        # --- Core / database ------------------------------------------------
        self.app_name: str = os.getenv("APP_NAME", "Agent API Cloud")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./monetization.db")
        self.base_url: str = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

        # --- LLM provider pass-through -------------------------------------
        # mock | openai | openrouter. Passed through to the agent adapters.
        self.llm_provider: str = os.getenv("LLM_PROVIDER", "mock").lower()
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_base_url: str = os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
        self.llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

        # --- Stripe --------------------------------------------------------
        self.stripe_api_key: str = os.getenv("STRIPE_API_KEY", "")
        self.stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.stripe_success_url: str = os.getenv(
            "STRIPE_SUCCESS_URL", f"{self.base_url}/dashboard?checkout=success"
        )
        self.stripe_cancel_url: str = os.getenv(
            "STRIPE_CANCEL_URL", f"{self.base_url}/?checkout=cancelled"
        )
        self.stripe_currency: str = os.getenv("STRIPE_CURRENCY", "usd")

        # --- Pricing / economics -------------------------------------------
        # Credits granted to a brand-new account (free trial credits).
        self.signup_bonus_credits: int = _get_int("SIGNUP_BONUS_CREDITS", 25)
        # Retail price of a single credit (used for margin documentation).
        self.credit_price_usd: float = _get_float("CREDIT_PRICE_USD", 0.02)

        # Per-agent credit cost per successful call.
        self.cost_marketing: int = _get_int("COST_MARKETING", 5)
        self.cost_legal: int = _get_int("COST_LEGAL", 8)
        self.cost_support: int = _get_int("COST_SUPPORT", 1)
        self.cost_hr: int = _get_int("COST_HR", 3)

        # --- Credit packs (env-tunable) ------------------------------------
        self.pack_starter_price: float = _get_float("PACK_STARTER_PRICE", 19.0)
        self.pack_starter_credits: int = _get_int("PACK_STARTER_CREDITS", 1000)
        self.pack_pro_price: float = _get_float("PACK_PRO_PRICE", 79.0)
        self.pack_pro_credits: int = _get_int("PACK_PRO_CREDITS", 5000)
        self.pack_business_price: float = _get_float("PACK_BUSINESS_PRICE", 299.0)
        self.pack_business_credits: int = _get_int("PACK_BUSINESS_CREDITS", 25000)

    # ---------------------------------------------------------------------
    @property
    def stripe_enabled(self) -> bool:
        """Real Stripe is used only when an API key is configured."""
        return bool(self.stripe_api_key)

    @property
    def agent_costs(self) -> Dict[str, int]:
        return {
            "marketing": self.cost_marketing,
            "legal": self.cost_legal,
            "support": self.cost_support,
            "hr": self.cost_hr,
        }

    @property
    def credit_packs(self) -> Dict[str, CreditPack]:
        packs = [
            CreditPack("starter", "Starter", self.pack_starter_price, self.pack_starter_credits),
            CreditPack("pro", "Pro", self.pack_pro_price, self.pack_pro_credits),
            CreditPack(
                "business", "Business", self.pack_business_price, self.pack_business_credits
            ),
        ]
        return {p.key: p for p in packs}

    def pack_list(self) -> List[CreditPack]:
        return list(self.credit_packs.values())

    def apply_llm_env(self) -> None:
        """Translate the platform's LLM settings into the environment variables
        the wrapped agents understand.

        The agents only speak ``mock`` and ``openai`` natively, but OpenRouter is
        OpenAI-API compatible. When ``LLM_PROVIDER=openrouter`` we therefore point
        the OpenAI SDK (which the agents use) at OpenRouter via ``OPENAI_BASE_URL``
        and feed it the OpenRouter key — no changes to the agent code required.
        """
        if self.llm_provider == "openrouter":
            os.environ["LLM_PROVIDER"] = "openai"
            if self.openrouter_api_key:
                os.environ["OPENAI_API_KEY"] = self.openrouter_api_key
            os.environ["OPENAI_BASE_URL"] = self.openrouter_base_url
            os.environ.setdefault("LLM_MODEL", self.llm_model)
        else:
            os.environ["LLM_PROVIDER"] = self.llm_provider
            if self.openai_api_key:
                os.environ.setdefault("OPENAI_API_KEY", self.openai_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests that mutate the environment)."""
    get_settings.cache_clear()
