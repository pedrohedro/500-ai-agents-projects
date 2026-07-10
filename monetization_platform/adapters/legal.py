"""Adapter for the legal_doc_reviewer_agent.

This agent uses *flat* module imports (``from config import ...``) and is not a
Python package, so we must add its own directory to ``sys.path`` before importing
``ReviewPipeline``. Falls back to a deterministic mock if the import fails.
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

_LEGAL_DIR = os.path.join(REPO_ROOT, "legal_doc_reviewer_agent")


class LegalAdapter(BaseAdapter):
    name = "legal"

    def _run_real(self, payload: Dict[str, Any]) -> AgentResult:
        provider = prepare_llm_env()
        ensure_dir_on_path(_LEGAL_DIR)

        # Flat import resolved from the agent's own directory on sys.path.
        from pipeline import ReviewPipeline  # type: ignore

        text = (payload.get("document_text") or payload.get("text") or "").strip()
        if not text:
            raise ValueError("Field 'document_text' is required.")
        name = payload.get("document_name", "contract")

        pipeline = ReviewPipeline()
        result = pipeline.review(text, document_name=name)
        data = result.to_dict()
        return AgentResult(
            output=data,
            tokens=int(data.get("token_usage", 0)),
            usd_cost=0.0,
            provider=data.get("provider", provider),
        )

    def _run_mock(self, payload: Dict[str, Any]) -> AgentResult:
        text = (payload.get("document_text") or payload.get("text") or "").strip()
        name = payload.get("document_name", "contract")
        output = {
            "document_name": name,
            "provider": "mock",
            "document_summary": (
                "Deterministic mock review: the agreement was analysed for key "
                "clauses and risks (mock adapter)."
            ),
            "key_clauses": [
                {"type": "Termination", "excerpt": text[:80], "confidence": 0.9}
            ],
            "risks": [
                {
                    "title": "Unlimited liability",
                    "severity": "high",
                    "explanation": "No liability cap detected.",
                    "suggested_change": "Add a mutual liability cap.",
                    "related_clause": "Liability",
                    "confidence": 0.8,
                }
            ],
            "missing_clauses": ["Confidentiality"],
            "overall_risk_score": 42.0,
            "risk_level": "medium",
            "qa": {
                "passed": True,
                "completeness_score": 0.6,
                "flagged_findings": [],
                "notes": ["Mock adapter output."],
                "needs_human_review": False,
            },
            "token_usage": 200,
        }
        return AgentResult(output=output, tokens=200, usd_cost=0.0, used_mock_adapter=True)
