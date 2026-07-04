"""Vercel serverless entrypoint (ASGI).

Vercel's Python runtime detects the module-level ``app`` (an ASGI app) and serves
it. We add the repository root to ``sys.path`` so the platform and the four sibling
agent packages (marketing_content_agent, legal_doc_reviewer_agent,
support_chatbot_agent, hr_resume_screening_agent) import correctly.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from monetization_platform.app import app  # noqa: E402

# Vercel looks for a module-level `app` (ASGI) or `handler`.
handler = app
