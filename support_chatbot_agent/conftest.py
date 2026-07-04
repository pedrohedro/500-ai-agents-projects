"""Pytest configuration.

Ensures the ``support_chatbot_agent`` directory is importable so tests can do
``from chatbot.xxx import ...``, and forces mock mode so tests never touch the
network.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "mock")

# Make the package importable regardless of where pytest is invoked from.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
