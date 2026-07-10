"""Shared adapter plumbing: result type, repo path, and LLM env setup."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict

from ..config import get_settings

# Repository root = parent of the monetization_platform package. The agent
# packages live as sibling top-level folders, so this must be importable.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ensure_repo_on_path() -> None:
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)


def ensure_dir_on_path(path: str) -> None:
    """Add an agent's own folder to sys.path (needed for flat-import agents)."""
    if path not in sys.path:
        sys.path.insert(0, path)


def prepare_llm_env() -> str:
    """Apply the platform's LLM provider settings to the environment and return
    the effective provider string the agents will see."""
    settings = get_settings()
    settings.apply_llm_env()
    return os.environ.get("LLM_PROVIDER", "mock")


@dataclass
class AgentResult:
    """Uniform result returned by every adapter."""

    output: Dict[str, Any]
    tokens: int = 0
    usd_cost: float = 0.0
    provider: str = "mock"
    used_mock_adapter: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output": self.output,
            "usage": {
                "tokens": self.tokens,
                "usd_cost": round(self.usd_cost, 6),
                "provider": self.provider,
                "mock_adapter": self.used_mock_adapter,
            },
        }


class BaseAdapter:
    """Common base with real/mock dispatch."""

    name: str = "base"

    def run(self, payload: Dict[str, Any]) -> AgentResult:
        try:
            return self._run_real(payload)
        except ImportError:
            # The real agent package could not be imported -> deterministic mock.
            return self._run_mock(payload)

    def _run_real(self, payload: Dict[str, Any]) -> AgentResult:  # pragma: no cover
        raise NotImplementedError

    def _run_mock(self, payload: Dict[str, Any]) -> AgentResult:  # pragma: no cover
        raise NotImplementedError
