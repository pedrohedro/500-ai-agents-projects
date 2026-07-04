import json
import os

import pytest

from hr_screening.extract import extract_text, load_resume_folder
from hr_screening.llm import MockLLM
from hr_screening.models import ResumeDocument
from hr_screening.pipeline import ScreeningPipeline
from hr_screening.report import to_json, to_markdown

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(os.path.dirname(HERE), "samples")


def test_extract_text_file(tmp_path):
    p = tmp_path / "r.txt"
    p.write_text("Jane Doe\nPython engineer", encoding="utf-8")
    assert "Python engineer" in extract_text(str(p))


def test_load_resume_folder_reads_samples():
    loaded = load_resume_folder(os.path.join(SAMPLES, "resumes"))
    assert len(loaded) >= 4
    assert all(text.strip() for _, text in loaded)


def test_report_renders_markdown_and_json():
    with open(os.path.join(SAMPLES, "job_description.txt"), encoding="utf-8") as fh:
        jd_text = fh.read()
    docs = [
        ResumeDocument(candidate_id="a", raw_text="Alice\n8 years Python, Docker, AWS, SQL, REST APIs, CI/CD."),
        ResumeDocument(candidate_id="b", raw_text="Bob\n2 years JavaScript, React."),
    ]
    report = ScreeningPipeline(llm=MockLLM()).screen(jd_text, docs)

    md = to_markdown(report)
    assert "# Candidate Screening Report" in md
    assert "Ranking" in md

    payload = json.loads(to_json(report))
    assert payload["job_title"]
    assert len(payload["candidates"]) == 2
    assert payload["candidates"][0]["rank"] == 1


def test_webhook_screen_endpoint():
    fastapi = pytest.importorskip("fastapi")  # noqa: F841
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from hr_screening.scheduler import build_app

    client = TestClient(build_app())
    resp = client.post(
        "/screen",
        json={
            "job_description": "Requirements:\n- Python\n- SQL\n",
            "resumes": [
                {"candidate_id": "a", "text": "Ann\n5 years Python, SQL."},
                {"candidate_id": "b", "text": "Ben\n1 year HTML."},
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["candidates"][0]["rank"] == 1
    assert data["candidates"][0]["name"] == "Ann"
