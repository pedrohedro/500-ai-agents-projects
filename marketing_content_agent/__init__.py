"""Marketing Content Agent — an autonomous, monetizable multi-agent content pipeline.

Public API surface kept intentionally small and dependency-light so the core
pipeline runs end-to-end in MOCK mode with zero third-party packages installed.
"""

from .schemas import ContentBrief, Deliverable
from .pipeline import ContentPipeline, run_pipeline
from .llm import get_llm, LLMProvider, MockLLM, OpenAILLM

__all__ = [
    "ContentBrief",
    "Deliverable",
    "ContentPipeline",
    "run_pipeline",
    "get_llm",
    "LLMProvider",
    "MockLLM",
    "OpenAILLM",
]

__version__ = "0.1.0"
