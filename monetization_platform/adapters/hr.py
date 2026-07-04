"""Adapter for the hr_resume_screening_agent.

Real integration adds the agent folder to ``sys.path`` and imports the
``hr_screening`` package. Falls back to a deterministic mock if the import fails.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from .base import (
    REPO_ROOT,
    AgentResult,
    BaseAdapter,
    ensure_dir_on_path,
    prepare_llm_env,
)

_HR_DIR = os.path.join(REPO_ROOT, "hr_resume_screening_agent")


def _coerce_resumes(raw: Any) -> List[Dict[str, str]]:
    """Normalize the incoming resumes into a list of {id, text} dicts."""
    resumes: List[Dict[str, str]] = []
    if not raw:
        return resumes
    for idx, item in enumerate(raw, start=1):
        if isinstance(item, str):
            resumes.append({"id": f"candidate_{idx}", "text": item})
        elif isinstance(item, dict):
            resumes.append(
                {
                    "id": str(item.get("id") or item.get("candidate_id") or f"candidate_{idx}"),
                    "text": str(item.get("text") or item.get("raw_text") or ""),
                }
            )
    return resumes


class HRAdapter(BaseAdapter):
    name = "hr"

    def _run_real(self, payload: Dict[str, Any]) -> AgentResult:
        provider = prepare_llm_env()
        ensure_dir_on_path(_HR_DIR)

        from hr_screening.models import ResumeDocument  # type: ignore
        from hr_screening.pipeline import ScreeningPipeline  # type: ignore

        jd = (payload.get("job_description") or payload.get("jd") or "").strip()
        if not jd:
            raise ValueError("Field 'job_description' is required.")
        resumes = _coerce_resumes(payload.get("resumes"))
        if not resumes:
            raise ValueError("Field 'resumes' must be a non-empty list.")

        docs = [
            ResumeDocument(candidate_id=r["id"], raw_text=r["text"]) for r in resumes
        ]
        pipeline = ScreeningPipeline()
        report = pipeline.screen(jd, docs, job_title=payload.get("job_title"))
        data = report.to_dict()
        return AgentResult(
            output=data,
            tokens=int(data.get("tokens_used", 0)),
            usd_cost=float(data.get("cost_usd", 0.0)),
            provider=data.get("provider", provider),
        )

    def _run_mock(self, payload: Dict[str, Any]) -> AgentResult:
        resumes = _coerce_resumes(payload.get("resumes"))
        candidates = []
        for rank, r in enumerate(resumes, start=1):
            candidates.append(
                {
                    "candidate_id": r["id"],
                    "name": r["id"].replace("_", " ").title(),
                    "score": round(max(0.0, 90 - (rank - 1) * 12), 1),
                    "matched_skills": ["python", "communication"],
                    "gaps": ["leadership"],
                    "years_experience": 4.0,
                    "rationale": "Deterministic mock ranking (fallback adapter).",
                    "confidence": 0.7,
                    "qa_passed": True,
                    "qa_flags": [],
                    "needs_human_review": False,
                    "rank": rank,
                }
            )
        output = {
            "job_title": payload.get("job_title") or "Open Role",
            "provider": "mock",
            "tokens_used": 90 * max(1, len(resumes)),
            "cost_usd": 0.0,
            "credits_remaining": None,
            "candidates": candidates,
        }
        return AgentResult(
            output=output,
            tokens=90 * max(1, len(resumes)),
            usd_cost=0.0,
            used_mock_adapter=True,
        )
