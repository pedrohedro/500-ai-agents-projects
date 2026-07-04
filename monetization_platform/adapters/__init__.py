"""Thin adapters that wrap the four in-repo AI agents behind a uniform API.

Each adapter tries to import and drive the *real* agent package. If that import
fails for any reason (missing optional dependency, refactor, etc.) it transparently
falls back to a deterministic mock so the platform always runs and always returns
a well-shaped response.
"""

from __future__ import annotations

from .base import AgentResult
from .hr import HRAdapter
from .legal import LegalAdapter
from .marketing import MarketingAdapter
from .support import SupportAdapter

ADAPTERS = {
    "marketing": MarketingAdapter,
    "legal": LegalAdapter,
    "support": SupportAdapter,
    "hr": HRAdapter,
}

__all__ = [
    "AgentResult",
    "MarketingAdapter",
    "LegalAdapter",
    "SupportAdapter",
    "HRAdapter",
    "ADAPTERS",
    "get_adapter",
]


def get_adapter(name: str):
    """Return a constructed adapter instance for the given agent name."""
    try:
        return ADAPTERS[name]()
    except KeyError as exc:
        raise KeyError(f"Unknown agent '{name}'.") from exc
