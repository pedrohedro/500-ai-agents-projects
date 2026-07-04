"""Pytest configuration: force MOCK mode and make the package importable.

Ensures tests never require network access or API keys.
"""

import os
import sys

# Force offline, deterministic provider for the whole test session.
os.environ.setdefault("LLM_PROVIDER", "mock")

# Make the repo root importable so `import marketing_content_agent` works when
# pytest is invoked from inside the package directory.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
