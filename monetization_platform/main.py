"""Uvicorn entry point.

Run locally with::

    uvicorn monetization_platform.main:app --reload

or directly::

    python -m monetization_platform.main
"""

from __future__ import annotations

import os

from .app import app  # re-exported for `uvicorn monetization_platform.main:app`


def run() -> None:  # pragma: no cover - convenience runner
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("monetization_platform.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    run()
