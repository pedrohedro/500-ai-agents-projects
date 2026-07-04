"""A tiny local vector store backed by numpy cosine similarity.

No external services required. The index is a plain JSON file so it is easy to
inspect and ship. If numpy is unavailable we transparently fall back to a pure
Python cosine implementation so the product still runs.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Sequence

try:  # numpy makes search fast, but is optional.
    import numpy as _np

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - exercised only when numpy missing
    _np = None
    _HAS_NUMPY = False


@dataclass
class Chunk:
    """A single retrievable unit of the knowledge base."""

    id: str
    text: str
    source: str
    embedding: List[float]


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


def _cosine_py(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class VectorStore:
    """In-memory vector store with JSON persistence."""

    def __init__(self, chunks: List[Chunk] | None = None) -> None:
        self.chunks: List[Chunk] = chunks or []
        self._matrix = None
        if self.chunks:
            self._build_matrix()

    # -- construction ----------------------------------------------------
    def _build_matrix(self) -> None:
        if _HAS_NUMPY and self.chunks:
            mat = _np.array([c.embedding for c in self.chunks], dtype="float32")
            norms = _np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._matrix = mat / norms
        else:
            self._matrix = None

    def add(self, chunks: Sequence[Chunk]) -> None:
        self.chunks.extend(chunks)
        self._build_matrix()

    def __len__(self) -> int:
        return len(self.chunks)

    # -- search ----------------------------------------------------------
    def search(self, query_embedding: Sequence[float], top_k: int = 4) -> List[SearchResult]:
        if not self.chunks:
            return []

        if _HAS_NUMPY and self._matrix is not None:
            q = _np.array(query_embedding, dtype="float32")
            qn = _np.linalg.norm(q)
            if qn == 0:
                qn = 1.0
            q = q / qn
            scores = self._matrix @ q
            order = _np.argsort(-scores)[:top_k]
            return [SearchResult(chunk=self.chunks[i], score=float(scores[i])) for i in order]

        scored = [
            SearchResult(chunk=c, score=_cosine_py(query_embedding, c.embedding))
            for c in self.chunks
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    # -- persistence -----------------------------------------------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"chunks": [asdict(c) for c in self.chunks]}
        path.write_text(json.dumps(payload), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        chunks = [Chunk(**c) for c in data["chunks"]]
        return cls(chunks)

    @staticmethod
    def exists(path: str | Path) -> bool:
        return Path(path).exists()
