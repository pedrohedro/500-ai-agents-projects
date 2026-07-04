import os
import sys

# Make the package importable when running `pytest` from anywhere.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Force deterministic mock mode for the whole test session.
os.environ.setdefault("LLM_PROVIDER", "mock")
