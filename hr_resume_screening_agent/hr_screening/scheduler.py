"""Automation: unattended batch screening + a FastAPI webhook.

* :func:`run_batch` screens every resume in a folder against a JD file and
  writes ``report.md`` / ``report.json`` -- no human in the loop.
* :func:`build_app` returns a FastAPI app exposing ``POST /screen``. FastAPI is
  imported lazily so the batch path works even when the web deps are missing.
"""

from __future__ import annotations

import os

from .billing import BillingAccount, PricingConfig
from .config import Settings
from .extract import load_resume_folder
from .models import ResumeDocument, ScreeningReport
from .pipeline import ScreeningPipeline
from .report import to_json, to_markdown


def _docs_from_folder(folder: str) -> list[ResumeDocument]:
    docs: list[ResumeDocument] = []
    for path, text in load_resume_folder(folder):
        cid = os.path.splitext(os.path.basename(path))[0]
        docs.append(ResumeDocument(candidate_id=cid, raw_text=text, source_path=path))
    return docs


def run_batch(
    jd_path: str,
    resumes_folder: str,
    *,
    output_dir: str | None = None,
    settings: Settings | None = None,
    billing: BillingAccount | None = None,
) -> ScreeningReport:
    """Screen a folder of resumes against a JD file, unattended."""
    settings = settings or Settings.from_env()
    with open(jd_path, "r", encoding="utf-8", errors="ignore") as fh:
        jd_text = fh.read()

    docs = _docs_from_folder(resumes_folder)
    pipeline = ScreeningPipeline(settings=settings, billing=billing)
    report = pipeline.screen(jd_text, docs)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "report.md"), "w", encoding="utf-8") as fh:
            fh.write(to_markdown(report))
        with open(os.path.join(output_dir, "report.json"), "w", encoding="utf-8") as fh:
            fh.write(to_json(report))
    return report


# --------------------------------------------------------------------------- #
# FastAPI webhook
# --------------------------------------------------------------------------- #
# Request/response models are defined at module scope (guarded) so FastAPI can
# resolve their type hints. When pydantic is missing they simply stay ``None``
# and only the web path is unavailable -- batch mode keeps working.
try:  # pragma: no cover - import guard
    from pydantic import BaseModel as _BaseModel
    from pydantic import Field as _Field

    class ResumeIn(_BaseModel):
        candidate_id: str
        text: str

    class ScreenRequest(_BaseModel):
        job_description: str
        job_title: str | None = None
        resumes: list[ResumeIn] = _Field(default_factory=list)
        credits: float | None = None

except Exception:  # pragma: no cover
    ResumeIn = None  # type: ignore
    ScreenRequest = None  # type: ignore


def build_app():  # pragma: no cover - exercised via TestClient when available
    """Build and return a FastAPI app exposing ``POST /screen``."""
    try:
        from fastapi import FastAPI, HTTPException
    except Exception as exc:
        raise RuntimeError(
            "FastAPI/pydantic not installed. Install web extras or use batch mode."
        ) from exc
    if ScreenRequest is None:
        raise RuntimeError("pydantic not installed. Install web extras or use batch mode.")

    app = FastAPI(title="HR Resume Screening Agent", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "provider": Settings.from_env().llm_provider}

    @app.post("/screen")
    def screen(req: ScreenRequest) -> dict:
        if not req.resumes:
            raise HTTPException(status_code=400, detail="No resumes provided.")
        settings = Settings.from_env()
        billing = None
        if req.credits is not None:
            billing = BillingAccount(credits=req.credits, pricing=PricingConfig.from_env())
        pipeline = ScreeningPipeline(settings=settings, billing=billing)
        docs = [
            ResumeDocument(candidate_id=r.candidate_id, raw_text=r.text)
            for r in req.resumes
        ]
        report = pipeline.screen(req.job_description, docs, job_title=req.job_title)
        return report.to_dict()

    return app
