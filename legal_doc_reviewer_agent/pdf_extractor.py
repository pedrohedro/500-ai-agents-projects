"""Document loading with a lightweight PDF extractor.

Uses ``pypdf`` when available and gracefully falls back to plain-text reading
for ``.txt`` files (and for ``.pdf`` files when ``pypdf`` is missing, so the
product never hard-fails on a missing optional dependency).
"""
from __future__ import annotations

import os
from typing import Optional


class ExtractionError(Exception):
    """Raised when a document cannot be read at all."""


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _extract_pdf(path: str) -> Optional[str]:
    """Return extracted PDF text, or ``None`` if pypdf is unavailable."""
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None
    try:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    except Exception as exc:  # corrupt / unreadable PDF
        raise ExtractionError(f"Failed to parse PDF {path!r}: {exc}") from exc


def load_document(source: str) -> str:
    """Load contract text from a file path or return the string as-is.

    * If ``source`` is a path to a ``.pdf`` file, extract text via pypdf
      (falling back to a note if pypdf is not installed).
    * If ``source`` is a path to a ``.txt``/other text file, read it.
    * Otherwise treat ``source`` as raw contract text.
    """
    if not isinstance(source, str):
        raise ExtractionError("Document source must be a string.")

    # Heuristic: treat as a path only if it looks like one and exists.
    looks_like_path = (
        os.path.sep in source or source.lower().endswith((".txt", ".pdf", ".md"))
    ) and len(source) < 4096

    if looks_like_path and os.path.isfile(source):
        ext = os.path.splitext(source)[1].lower()
        if ext == ".pdf":
            text = _extract_pdf(source)
            if text is None:
                raise ExtractionError(
                    "pypdf is not installed; cannot extract PDF text. Install "
                    "pypdf or pass a .txt file / raw text instead."
                )
            return text
        return _read_text_file(source)

    if looks_like_path and not os.path.isfile(source):
        # A path was clearly intended but the file is missing.
        raise ExtractionError(f"File not found: {source!r}")

    # Fall back to treating the input as raw contract text.
    return source
