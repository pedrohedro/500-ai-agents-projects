"""End-to-end pipeline tests in MOCK mode."""

from marketing_content_agent.config import get_settings
from marketing_content_agent.llm import MockLLM, get_llm
from marketing_content_agent.pipeline import ContentPipeline, run_pipeline
from marketing_content_agent.schemas import ContentBrief


def _brief(**kw):
    base = dict(
        topic="AI for small business",
        target_audience="small business owners",
        platform="blog",
        tone="friendly",
        keywords=["ai", "automation", "small business"],
        call_to_action="Get started",
    )
    base.update(kw)
    return ContentBrief(**base)


def test_provider_is_mock_by_default():
    settings = get_settings()
    assert settings.llm_provider == "mock"
    assert isinstance(get_llm(settings), MockLLM)


def test_pipeline_produces_full_deliverable():
    d = run_pipeline(_brief())
    assert d.blog_post.strip()
    assert d.seo_title.strip()
    assert d.meta_description.strip()
    assert d.social.instagram.strip()
    assert d.social.linkedin.strip()
    assert d.social.twitter.strip()
    assert len(d.hashtags) >= 3
    assert d.research_notes.strip()


def test_pipeline_qa_passes_for_good_content():
    d = run_pipeline(_brief())
    assert d.qa.passed is True
    assert d.qa.score >= 0.75
    assert d.qa.issues == []


def test_deliverable_json_roundtrip():
    d = run_pipeline(_brief())
    data = d.to_dict()
    assert data["brief"]["topic"] == "AI for small business"
    assert "blog_post" in data
    assert isinstance(d.to_json(), str)


def test_deterministic_output():
    d1 = run_pipeline(_brief())
    d2 = run_pipeline(_brief())
    assert d1.blog_post == d2.blog_post
    assert d1.usage.total_tokens == d2.usage.total_tokens


def test_usage_tokens_tracked():
    pipeline = ContentPipeline()
    d = pipeline.run(_brief())
    assert d.usage.total_tokens > 0
    assert d.usage.prompt_tokens > 0
    assert d.usage.completion_tokens > 0
