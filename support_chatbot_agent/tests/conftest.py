"""Shared fixtures for the test suite (all run in mock mode)."""
import os
from pathlib import Path

import pytest

os.environ["LLM_PROVIDER"] = "mock"

from chatbot.config import Config, get_config  # noqa: E402
from chatbot.ingest import build_index  # noqa: E402


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """A mock-mode config pointing the index at a temp dir."""
    cfg = get_config()
    cfg.llm_provider = "mock"
    cfg.index_path = tmp_path / "index.json"
    return cfg


@pytest.fixture
def store(config: Config):
    """A freshly built vector store over the sample knowledge base."""
    return build_index(config, persist=False)
