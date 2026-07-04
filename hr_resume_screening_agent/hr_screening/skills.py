"""Deterministic skill / keyword extraction.

This module intentionally avoids any LLM call so that parsing and scoring are
reproducible and testable in mock mode. The LLM layer is used on top of this
for natural-language rationale and secondary fairness review.
"""

from __future__ import annotations

import re

# Canonical skill vocabulary. Keys are the normalized skill name; values are
# alternate surface forms / aliases that map back to the canonical name.
SKILL_ALIASES: dict[str, list[str]] = {
    "python": ["python", "py"],
    "java": ["java"],
    "javascript": ["javascript", "js", "node.js", "nodejs", "node"],
    "typescript": ["typescript", "ts"],
    "go": ["golang", "go lang"],
    "c++": ["c++", "cpp"],
    "sql": ["sql", "postgresql", "postgres", "mysql", "sqlite"],
    "nosql": ["nosql", "mongodb", "dynamodb", "cassandra"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "gcp": ["gcp", "google cloud"],
    "azure": ["azure", "microsoft azure"],
    "docker": ["docker", "containers", "containerization"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform", "iac"],
    "react": ["react", "reactjs", "react.js"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "machine learning": ["machine learning", "ml", "scikit-learn", "sklearn"],
    "deep learning": ["deep learning", "pytorch", "tensorflow", "keras"],
    "nlp": ["nlp", "natural language processing", "llm", "llms"],
    "data engineering": ["data engineering", "etl", "airflow", "spark"],
    "data analysis": ["data analysis", "pandas", "numpy", "analytics"],
    "rest api": ["rest api", "rest apis", "restful", "api design"],
    "graphql": ["graphql"],
    "ci/cd": ["ci/cd", "cicd", "continuous integration", "jenkins", "github actions"],
    "microservices": ["microservices", "micro-services"],
    "linux": ["linux", "unix", "bash", "shell scripting"],
    "git": ["git", "github", "gitlab", "version control"],
    "agile": ["agile", "scrum", "kanban"],
    "leadership": ["leadership", "team lead", "mentoring", "managed a team"],
    "communication": ["communication", "stakeholder", "presentation"],
    "project management": ["project management", "pmp", "jira"],
    "security": ["security", "cybersecurity", "oauth", "encryption"],
    "product management": ["product management", "roadmap", "product owner"],
}

# Build reverse lookup (alias -> canonical), longest aliases first so that
# multi-word aliases win over single-word ones.
_ALIAS_TO_CANONICAL: list[tuple[str, str]] = sorted(
    ((alias.lower(), canonical) for canonical, aliases in SKILL_ALIASES.items() for alias in aliases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

_YEARS_PATTERNS = [
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*yrs?", re.IGNORECASE),
]


def extract_skills(text: str) -> list[str]:
    """Return the sorted list of canonical skills mentioned in ``text``."""
    lowered = f" {text.lower()} "
    found: set[str] = set()
    for alias, canonical in _ALIAS_TO_CANONICAL:
        # word-boundary-ish match; keep it simple and robust for punctuation.
        pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            found.add(canonical)
    return sorted(found)


def extract_years_experience(text: str) -> float:
    """Best-effort extraction of the max years of experience mentioned."""
    years: list[float] = []
    for pat in _YEARS_PATTERNS:
        for m in pat.finditer(text):
            try:
                years.append(float(m.group(1)))
            except ValueError:
                continue
    # Ignore implausible values (e.g. "2024 years").
    years = [y for y in years if 0 < y <= 50]
    return max(years) if years else 0.0


def guess_name(text: str, fallback: str) -> str:
    """Heuristically pull a candidate name from the top of a resume."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip common header labels.
        cleaned = re.sub(r"^(name|candidate)\s*[:\-]\s*", "", line, flags=re.IGNORECASE)
        # A name line is short, mostly alphabetic, and has 1-4 words.
        words = cleaned.split()
        if 1 <= len(words) <= 4 and all(re.match(r"^[A-Za-z.'\-]+$", w) for w in words):
            if len(cleaned) <= 40:
                return cleaned.title()
        break
    return fallback
