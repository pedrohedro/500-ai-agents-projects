from hr_screening.agents import ResumeParserAgent, parse_job_description
from hr_screening.models import ResumeDocument
from hr_screening.skills import extract_skills, extract_years_experience, guess_name


def test_extract_skills_canonicalizes_aliases():
    skills = extract_skills("Expert in Py, node.js, k8s and PostgreSQL.")
    assert "python" in skills
    assert "javascript" in skills
    assert "kubernetes" in skills
    assert "sql" in skills


def test_extract_years_experience():
    assert extract_years_experience("8 years of experience") == 8.0
    assert extract_years_experience("5+ yrs building APIs") == 5.0
    assert extract_years_experience("no numbers here") == 0.0


def test_guess_name_from_header():
    assert guess_name("Alice Nguyen\nSenior Engineer", "fallback") == "Alice Nguyen"
    assert guess_name("\n\nName: Bob Martinez\n", "fallback") == "Bob Martinez"


def test_resume_parser_agent_extracts_structured_facts():
    doc = ResumeDocument(
        candidate_id="c1",
        raw_text="Alice Nguyen\n8 years of experience with Python, Docker and AWS.",
    )
    parsed = ResumeParserAgent().run(doc)
    assert parsed.name == "Alice Nguyen"
    assert parsed.years_experience == 8.0
    assert set(parsed.skills) >= {"python", "docker", "aws"}


def test_parse_job_description_splits_required_and_preferred():
    jd_text = (
        "Title: Backend Engineer\n"
        "Requirements (must have):\n"
        "- 5+ years experience\n- Strong Python\n- REST APIs\n- SQL\n- Docker\n- AWS\n- CI/CD\n"
        "Nice to have (preferred):\n- Kubernetes\n- Terraform\n- FastAPI\n"
    )
    jd = parse_job_description(jd_text)
    assert jd.title == "Backend Engineer"
    assert jd.min_years_experience == 5
    assert set(jd.required_skills) >= {"python", "rest api", "sql", "docker", "aws", "ci/cd"}
    assert set(jd.preferred_skills) >= {"kubernetes", "terraform", "fastapi"}
    # Preferred skills must not double-count as required.
    assert not (set(jd.required_skills) & set(jd.preferred_skills))
