"""HTML pages: landing page and dashboard (rendered via Jinja2)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import get_settings

router = APIRouter(tags=["pages"])

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    settings = get_settings()
    packs = [p.to_dict() for p in settings.pack_list()]
    agents = [
        {
            "name": "Marketing Content",
            "endpoint": "/v1/marketing/generate",
            "cost": settings.agent_costs["marketing"],
            "desc": "SEO blog posts, social copy, and hashtags from a single brief.",
        },
        {
            "name": "Legal Doc Reviewer",
            "endpoint": "/v1/legal/review",
            "cost": settings.agent_costs["legal"],
            "desc": "Extract clauses, flag risks, and score contracts automatically.",
        },
        {
            "name": "Support Chatbot",
            "endpoint": "/v1/support/chat",
            "cost": settings.agent_costs["support"],
            "desc": "RAG answers grounded in your knowledge base, with escalation.",
        },
        {
            "name": "HR Resume Screening",
            "endpoint": "/v1/hr/screen",
            "cost": settings.agent_costs["hr"],
            "desc": "Rank candidates against a job description with a fairness gate.",
        },
    ]
    return templates.TemplateResponse(
        "landing.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "packs": packs,
            "agents": agents,
            "signup_bonus": settings.signup_bonus_credits,
            "stripe_enabled": settings.stripe_enabled,
        },
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    settings = get_settings()
    packs = [p.to_dict() for p in settings.pack_list()]
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "packs": packs,
            "stripe_enabled": settings.stripe_enabled,
        },
    )
