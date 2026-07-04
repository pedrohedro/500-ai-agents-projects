"""FastAPI application factory for the monetization platform."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .database import init_db
from .routes import auth, billing, gateway, pages

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app() -> FastAPI:
    settings = get_settings()
    # Translate LLM settings into the env the wrapped agents read.
    settings.apply_llm_env()
    # Auto-create tables on startup (idempotent).
    init_db()

    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description=(
            "Monetized gateway for four AI agents: marketing content, legal doc "
            "review, support chatbot, and HR resume screening. Buy credits, call "
            "the agents, pay per use."
        ),
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "llm_provider": settings.llm_provider,
            "stripe_enabled": settings.stripe_enabled,
            "agent_costs": settings.agent_costs,
        }

    app.include_router(pages.router)
    app.include_router(auth.router)
    app.include_router(billing.router)
    app.include_router(gateway.router)

    if os.path.isdir(_STATIC_DIR):
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


app = create_app()
