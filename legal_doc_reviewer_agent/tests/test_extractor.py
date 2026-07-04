"""Tests for document loading and PDF fallback."""
import os

import pytest

from pdf_extractor import ExtractionError, load_document


def test_load_txt_file(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("hello contract")
    assert load_document(str(p)) == "hello contract"


def test_load_raw_text_passthrough():
    text = "This is raw contract text with a CONFIDENTIALITY clause."
    assert load_document(text) == text


def test_missing_file_raises():
    with pytest.raises(ExtractionError):
        load_document("/nonexistent/path/to/file.txt")


def test_pdf_without_pypdf_or_extract(tmp_path):
    # Create a fake .pdf that is actually text; either pypdf parses/raises or,
    # if pypdf is missing, we get a clear ExtractionError. Both are acceptable.
    p = tmp_path / "c.pdf"
    p.write_bytes(b"%PDF-1.4 not a real pdf")
    with pytest.raises(ExtractionError):
        load_document(str(p))
