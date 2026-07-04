"""Automation layer for unattended operation.

Two triggers are provided:

1. **Folder watch / batch mode** - process every contract dropped into an
   ``inbox/`` directory, writing JSON + Markdown results to ``outbox/`` and
   moving processed files aside. Works with only the standard library.

2. **FastAPI webhook** - ``POST /review`` accepts contract text (or a file path)
   and returns the structured review. Exposed only when ``fastapi`` is
   installed; ``build_app`` raises a clear error otherwise so the rest of the
   product still runs.

Both paths reuse :class:`ReviewPipeline` and optional billing.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from billing import BillingManager, CreditAccount, OutOfCreditsError
from config import Settings, get_settings
from pipeline import ReviewPipeline
from report import to_json, to_markdown

_SUPPORTED_EXT = {".txt", ".pdf", ".md"}

# Define the request model at module scope so FastAPI/pydantic can resolve the
# (stringified, due to `from __future__ import annotations`) type hint. Guarded
# so the module still imports when pydantic is not installed.
try:  # pragma: no cover - trivial import guard
    from pydantic import BaseModel as _BaseModel

    class ReviewRequest(_BaseModel):
        text: Optional[str] = None
        file_path: Optional[str] = None
        document_name: Optional[str] = None

except Exception:  # pragma: no cover
    ReviewRequest = None  # type: ignore[assignment]


def _ensure_dirs(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def process_inbox(
    settings: Optional[Settings] = None,
    billing: Optional[BillingManager] = None,
    move_processed: bool = True,
) -> List[Dict[str, Any]]:
    """Process every supported file currently in the inbox. Returns summaries."""
    settings = settings or get_settings()
    inbox = settings.inbox_dir
    outbox = settings.outbox_dir
    processed_dir = os.path.join(inbox, "_processed")
    failed_dir = os.path.join(inbox, "_failed")
    _ensure_dirs(inbox, outbox)

    pipeline = ReviewPipeline(settings)
    results: List[Dict[str, Any]] = []

    for entry in sorted(os.listdir(inbox)):
        path = os.path.join(inbox, entry)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(entry)[1].lower() not in _SUPPORTED_EXT:
            continue

        record: Dict[str, Any] = {"file": entry}
        try:
            result = pipeline.review(path, document_name=entry)

            if billing is not None:
                charge = billing.charge_for_review(result.token_usage, entry)
                record["billing"] = charge

            base = os.path.splitext(entry)[0]
            json_path = os.path.join(outbox, f"{base}.review.json")
            md_path = os.path.join(outbox, f"{base}.review.md")
            with open(json_path, "w", encoding="utf-8") as fh:
                fh.write(to_json(result))
            with open(md_path, "w", encoding="utf-8") as fh:
                fh.write(to_markdown(result))

            record.update(
                {
                    "status": "ok",
                    "risk_score": result.overall_risk_score,
                    "risk_level": result.risk_level,
                    "needs_human_review": result.qa.needs_human_review,
                    "json_output": json_path,
                    "markdown_output": md_path,
                }
            )
            if move_processed:
                _ensure_dirs(processed_dir)
                shutil.move(path, os.path.join(processed_dir, entry))
        except OutOfCreditsError as exc:
            record.update({"status": "blocked", "error": str(exc)})
            # Leave the file in the inbox so it can be retried after top-up.
        except Exception as exc:  # noqa: BLE001 - report and continue batch
            record.update({"status": "error", "error": str(exc)})
            if move_processed:
                _ensure_dirs(failed_dir)
                try:
                    shutil.move(path, os.path.join(failed_dir, entry))
                except Exception:
                    pass
        results.append(record)

    return results


def watch_inbox(
    settings: Optional[Settings] = None,
    billing: Optional[BillingManager] = None,
    iterations: Optional[int] = None,
) -> None:  # pragma: no cover - long-running loop
    """Continuously poll the inbox. ``iterations`` bounds the loop for testing."""
    settings = settings or get_settings()
    count = 0
    print(f"[scheduler] watching '{settings.inbox_dir}' every "
          f"{settings.poll_interval_seconds}s (Ctrl+C to stop)")
    while iterations is None or count < iterations:
        results = process_inbox(settings, billing)
        for r in results:
            print(f"[scheduler] {r['file']}: {r.get('status')}")
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(settings.poll_interval_seconds)


# ---------------------------------------------------------------------------
# FastAPI webhook
# ---------------------------------------------------------------------------


def build_app(settings: Optional[Settings] = None):
    """Build and return a FastAPI app exposing ``POST /review``.

    Raises RuntimeError with a helpful message if FastAPI is not installed.
    """
    settings = settings or get_settings()
    try:
        from fastapi import FastAPI, HTTPException
    except Exception as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(
            "FastAPI is not installed. Install 'fastapi' and 'uvicorn' to use "
            "the webhook, or use the folder-watch/batch mode instead."
        ) from exc

    if ReviewRequest is None:  # pragma: no cover
        raise RuntimeError("pydantic is required for the webhook.")

    app = FastAPI(title="Legal Document Reviewer", version="0.1.0")
    pipeline = ReviewPipeline(settings)

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "provider": pipeline.provider.name}

    @app.post("/review")
    def review(req: ReviewRequest) -> Dict[str, Any]:
        source = req.file_path or req.text
        if not source:
            raise HTTPException(status_code=400, detail="Provide 'text' or 'file_path'.")
        try:
            result = pipeline.review(source, document_name=req.document_name)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail=str(exc))
        return {
            "json": result.to_dict(),
            "markdown": to_markdown(result),
        }

    return app


def main() -> None:  # pragma: no cover - CLI entry
    import argparse

    parser = argparse.ArgumentParser(description="Legal Reviewer automation layer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_batch = sub.add_parser("batch", help="Process the inbox once and exit")
    p_batch.add_argument("--credits", type=float, default=None, help="Optional starting credit balance")

    p_watch = sub.add_parser("watch", help="Continuously watch the inbox")
    p_watch.add_argument("--iterations", type=int, default=None)

    p_serve = sub.add_parser("serve", help="Run the FastAPI webhook server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    settings = get_settings()

    if args.cmd == "batch":
        billing = None
        if args.credits is not None:
            billing = BillingManager(CreditAccount(balance=args.credits), settings)
        results = process_inbox(settings, billing)
        print(json.dumps(results, indent=2))
    elif args.cmd == "watch":
        watch_inbox(settings, iterations=args.iterations)
    elif args.cmd == "serve":
        try:
            import uvicorn  # type: ignore
        except Exception:
            raise SystemExit("uvicorn is required to serve. pip install uvicorn fastapi")
        uvicorn.run(build_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
