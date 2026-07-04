"""Automation layer: unattended triggers for the content pipeline.

Two mechanisms are provided:

1. A cron-style loop (``run_cron_loop``) that periodically pulls briefs from a
   queue callable and runs the pipeline autonomously.
2. A FastAPI app exposing ``POST /generate`` that runs the pipeline on request.

FastAPI is imported lazily so the rest of the package (and the mock pipeline)
never requires it. Run the API with:

    uvicorn marketing_content_agent.scheduler:app --reload
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Iterable, List, Optional

from .billing import BillingEngine, OutOfCreditsError, Wallet
from .config import get_settings
from .pipeline import ContentPipeline
from .schemas import ContentBrief, Deliverable


def run_once(brief: ContentBrief, wallet: Optional[Wallet] = None) -> Deliverable:
    """Run the pipeline a single time for a brief."""
    pipeline = ContentPipeline(settings=get_settings())
    return pipeline.run(brief, wallet=wallet)


def run_cron_loop(
    brief_source: Callable[[], Iterable[Dict]],
    *,
    interval_seconds: Optional[int] = None,
    max_iterations: Optional[int] = None,
    wallet: Optional[Wallet] = None,
    on_result: Optional[Callable[[Deliverable], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> List[Deliverable]:
    """Poll ``brief_source`` every ``interval_seconds`` and process briefs.

    ``max_iterations`` bounds the loop (use ``None`` for truly unattended runs;
    tests pass a small integer). ``sleep`` is injectable so tests run instantly.
    """
    settings = get_settings()
    interval = interval_seconds if interval_seconds is not None else settings.schedule_interval_seconds
    pipeline = ContentPipeline(settings=settings)
    results: List[Deliverable] = []

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        for raw in brief_source():
            try:
                brief = ContentBrief.from_dict(raw)
                deliverable = pipeline.run(brief, wallet=wallet)
            except OutOfCreditsError:
                # Autonomous operation: stop cleanly when the budget is exhausted.
                return results
            except Exception:
                # A malformed brief should not kill the whole loop.
                continue
            results.append(deliverable)
            if on_result is not None:
                on_result(deliverable)
        if max_iterations is None or iteration < max_iterations:
            sleep(interval)
    return results


# --------------------------------------------------------------------------- #
# FastAPI app (lazily constructed).
# --------------------------------------------------------------------------- #
def create_app():
    """Build and return a FastAPI app exposing POST /generate and GET /health.

    Imported lazily; raises a clear error if FastAPI is not installed.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel, Field
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "FastAPI/pydantic are not installed. Install them (see requirements.txt) "
            "to use the webhook API."
        ) from exc

    app = FastAPI(title="Marketing Content Agent", version="0.1.0")

    class BriefRequest(BaseModel):
        topic: str = Field(..., min_length=1)
        target_audience: str = "general audience"
        platform: str = "blog"
        tone: str = "professional"
        keywords: List[str] = Field(default_factory=list)
        call_to_action: str = "Learn more"
        word_count: int = 600
        credits: Optional[int] = None

    # This module uses ``from __future__ import annotations``, so route handler
    # annotations are stored as strings. Expose the request model in module
    # globals so FastAPI/pydantic can resolve the "BriefRequest" forward ref.
    globals()["BriefRequest"] = BriefRequest

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "provider": get_settings().llm_provider}

    @app.post("/generate")
    def generate(req: BriefRequest) -> Dict:
        brief = ContentBrief.from_dict(req.model_dump())
        wallet = Wallet(balance=req.credits) if req.credits is not None else None
        pipeline = ContentPipeline(settings=get_settings())
        try:
            deliverable = pipeline.run(brief, wallet=wallet)
        except OutOfCreditsError as exc:
            raise HTTPException(status_code=402, detail=str(exc))
        payload = deliverable.to_dict()
        if wallet is not None:
            payload["credits_remaining"] = wallet.balance
        return payload

    return app


# Module-level app for `uvicorn marketing_content_agent.scheduler:app`.
# Falls back to None if FastAPI is unavailable so importing this module never fails.
try:  # pragma: no cover - depends on optional dependency availability
    app = create_app()
except Exception:  # pragma: no cover
    app = None


if __name__ == "__main__":  # pragma: no cover
    # Demo the cron loop with a tiny static source in mock mode.
    def _source() -> Iterable[Dict]:
        return [{"topic": "Autonomous marketing agents", "target_audience": "founders"}]

    out = run_cron_loop(_source, interval_seconds=0, max_iterations=1)
    print(f"Generated {len(out)} deliverable(s). QA passed: {out[0].qa.passed if out else 'n/a'}")
