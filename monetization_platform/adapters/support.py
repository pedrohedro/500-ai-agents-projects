"""Adapter for the support_chatbot_agent (RAG chatbot).

Real integration imports the ``chatbot`` package and builds the agent (which
loads/builds the local vector index). Falls back to a deterministic mock if the
import fails.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from .base import (
    REPO_ROOT,
    AgentResult,
    BaseAdapter,
    ensure_dir_on_path,
    prepare_llm_env,
)

_SUPPORT_DIR = os.path.join(REPO_ROOT, "support_chatbot_agent")

# Cache the built agent across calls (index building is relatively expensive).
_AGENT = None


class SupportAdapter(BaseAdapter):
    name = "support"

    def _run_real(self, payload: Dict[str, Any]) -> AgentResult:
        global _AGENT
        provider = prepare_llm_env()
        # The chatbot package resolves default KB/index paths relative to its own
        # location, so adding its dir to sys.path is enough (no cwd change needed).
        ensure_dir_on_path(_SUPPORT_DIR)

        from chatbot.agent import build_agent  # type: ignore
        from chatbot.config import get_config  # type: ignore

        question = (payload.get("question") or payload.get("message") or "").strip()
        if not question:
            raise ValueError("Field 'question' is required.")

        if _AGENT is None:
            _AGENT = build_agent(get_config())

        result = _AGENT.answer(question)
        data = result.to_dict()
        return AgentResult(
            output=data,
            tokens=int(data.get("tokens_used", 0)),
            usd_cost=0.0,
            provider=provider,
        )

    def _run_mock(self, payload: Dict[str, Any]) -> AgentResult:
        question = (payload.get("question") or payload.get("message") or "").strip()
        output = {
            "question": question,
            "answer": (
                "This is a deterministic mock answer. The support agent package "
                "was unavailable, so the platform served a fallback response."
            ),
            "confidence": 0.5,
            "escalate": False,
            "sources": [],
            "tokens_used": 60,
        }
        return AgentResult(output=output, tokens=60, usd_cost=0.0, used_mock_adapter=True)
