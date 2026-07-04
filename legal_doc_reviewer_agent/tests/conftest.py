"""Test configuration: put the package root on sys.path and force mock mode."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure the whole suite runs offline in deterministic mock mode.
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ["LLM_PROVIDER"] = "mock"
