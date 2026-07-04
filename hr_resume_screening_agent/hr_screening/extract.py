"""Resume text extraction.

Supports ``.txt``/``.md`` directly and ``.pdf`` via :mod:`pypdf` when it is
installed. If pypdf is unavailable (heavy dep failed to install / offline) the
extractor degrades gracefully: it attempts a naive text read and, failing that,
skips the file with a warning rather than crashing the pipeline.
"""

from __future__ import annotations

import os
import warnings

TEXT_EXTENSIONS = {".txt", ".md", ".text"}
PDF_EXTENSIONS = {".pdf"}


def pdf_support_available() -> bool:
    try:
        import pypdf  # noqa: F401  # type: ignore

        return True
    except Exception:
        return False


def extract_pdf_text(path: str) -> str:
    """Extract text from a PDF. Returns '' if pypdf is not available."""
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        warnings.warn(
            f"pypdf not installed; cannot parse PDF {path!r}. "
            "Install pypdf or supply .txt resumes.",
            RuntimeWarning,
            stacklevel=2,
        )
        return ""

    try:
        reader = PdfReader(path)
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(parts).strip()
    except Exception as exc:  # pragma: no cover - malformed PDFs
        warnings.warn(f"Failed to parse PDF {path!r}: {exc}", RuntimeWarning, stacklevel=2)
        return ""


def extract_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read().strip()


def extract_text(path: str) -> str:
    """Extract text from a single resume file based on its extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in PDF_EXTENSIONS:
        text = extract_pdf_text(path)
        if text:
            return text
        # Graceful fallback: try to read raw bytes as text.
        try:
            return extract_text_file(path)
        except Exception:
            return ""
    if ext in TEXT_EXTENSIONS or ext == "":
        return extract_text_file(path)
    # Unknown extension: attempt a plain-text read.
    try:
        return extract_text_file(path)
    except Exception:
        warnings.warn(f"Unsupported file type skipped: {path!r}", RuntimeWarning, stacklevel=2)
        return ""


def load_resume_folder(folder: str) -> list[tuple[str, str]]:
    """Return ``[(source_path, text), ...]`` for every readable resume file."""
    results: list[tuple[str, str]] = []
    if not os.path.isdir(folder):
        raise NotADirectoryError(f"Resume folder not found: {folder!r}")
    for entry in sorted(os.listdir(folder)):
        path = os.path.join(folder, entry)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext not in TEXT_EXTENSIONS | PDF_EXTENSIONS and ext != "":
            continue
        text = extract_text(path)
        if text.strip():
            results.append((path, text))
        else:
            warnings.warn(f"No text extracted from {path!r}; skipping.", RuntimeWarning, stacklevel=2)
    return results
