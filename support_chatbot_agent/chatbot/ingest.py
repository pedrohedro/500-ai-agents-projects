"""Knowledge-base ingestion: load -> chunk -> embed -> index.

Loads ``.md`` and ``.txt`` files from the knowledge base directory, splits them
into overlapping chunks, embeds each chunk and persists a :class:`VectorStore`.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List

from .config import Config
from .llm import Embedder, get_embedder
from .vectorstore import Chunk, VectorStore

_SUPPORTED_SUFFIXES = {".md", ".txt", ".markdown"}


def _clean(text: str) -> str:
    # Collapse excessive whitespace but keep paragraph boundaries.
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into ~``chunk_size`` character chunks with overlap.

    Splitting happens on paragraph boundaries first, then packs paragraphs into
    chunks so we never cut mid-sentence when we can avoid it.
    """
    text = _clean(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # If a single paragraph is larger than chunk_size, hard-split it.
            if len(para) > chunk_size:
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i : i + chunk_size])
                current = ""
            else:
                current = para
    if current:
        chunks.append(current)

    # Apply overlap between adjacent chunks for retrieval robustness.
    if overlap > 0 and len(chunks) > 1:
        overlapped: List[str] = []
        for i, ch in enumerate(chunks):
            if i == 0:
                overlapped.append(ch)
            else:
                tail = chunks[i - 1][-overlap:]
                overlapped.append(f"{tail} {ch}".strip())
        chunks = overlapped

    return chunks


def load_documents(kb_dir: Path) -> List[tuple[str, str]]:
    """Return a list of ``(source_name, text)`` tuples from the KB directory."""
    kb_dir = Path(kb_dir)
    if not kb_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    docs: List[tuple[str, str]] = []
    for path in sorted(kb_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            docs.append((path.name, text))
    return docs


def build_index(config: Config, embedder: Embedder | None = None, persist: bool = True) -> VectorStore:
    """Ingest the knowledge base and build (and optionally persist) the index."""
    embedder = embedder or get_embedder(config)
    docs = load_documents(config.knowledge_base_dir)

    all_chunks: List[Chunk] = []
    for source, text in docs:
        for i, piece in enumerate(chunk_text(text, config.chunk_size, config.chunk_overlap)):
            chunk_id = hashlib.sha1(f"{source}:{i}:{piece[:32]}".encode()).hexdigest()[:16]
            all_chunks.append(Chunk(id=chunk_id, text=piece, source=source, embedding=[]))

    if not all_chunks:
        raise ValueError(
            f"No chunks produced from {config.knowledge_base_dir}. "
            "Add .md/.txt files to the knowledge base."
        )

    embeddings = embedder.embed([c.text for c in all_chunks])
    for chunk, emb in zip(all_chunks, embeddings):
        chunk.embedding = list(emb)

    store = VectorStore(all_chunks)
    if persist:
        store.save(config.index_path)
    return store


def load_or_build_index(config: Config, embedder: Embedder | None = None) -> VectorStore:
    """Load a persisted index if present, otherwise build it."""
    if VectorStore.exists(config.index_path):
        return VectorStore.load(config.index_path)
    return build_index(config, embedder=embedder)
