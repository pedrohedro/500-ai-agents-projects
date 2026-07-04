"""Tests for the Editor/QA quality gate."""

from marketing_content_agent.agents import EditorQAAgent
from marketing_content_agent.llm import MockLLM
from marketing_content_agent.schemas import ContentBrief, SocialVariations


def _editor():
    return EditorQAAgent(MockLLM())


def _good_content():
    return {
        "blog_post": " ".join(["word"] * 200),
        "social": SocialVariations(
            instagram="Insta copy get started",
            linkedin="LinkedIn copy",
            twitter="Twitter copy",
        ),
        "seo_title": "A Great Title",
        "meta_description": "A concise, compelling meta description that fits nicely.",
        "hashtags": ["#ai", "#growth", "#marketing"],
    }


def _brief():
    return ContentBrief(topic="Testing", call_to_action="Get started")


def test_qa_passes_valid_content():
    report = _editor().review(_brief(), _good_content())
    assert report.passed is True
    assert report.checks["has_cta"] is True
    assert report.checks["no_banned_words"] is True


def test_qa_fails_short_blog():
    content = _good_content()
    content["blog_post"] = "too short"
    report = _editor().review(_brief(), content)
    assert report.passed is False
    assert report.checks["blog_min_length"] is False
    assert any("too short" in i.lower() for i in report.issues)


def test_qa_fails_banned_words():
    content = _good_content()
    content["blog_post"] = " ".join(["word"] * 200) + " this is guaranteed to work"
    report = _editor().review(_brief(), content)
    assert report.passed is False
    assert report.checks["no_banned_words"] is False


def test_qa_fails_missing_cta():
    content = _good_content()
    content["blog_post"] = " ".join(["neutral"] * 200)
    content["social"] = SocialVariations(
        instagram="plain", linkedin="plain", twitter="plain"
    )
    content["meta_description"] = "A plain description without any action phrasing here."
    report = _editor().review(
        ContentBrief(topic="Testing", call_to_action="zzznotpresentzzz"), content
    )
    assert report.checks["has_cta"] is False


def test_qa_fails_insufficient_hashtags():
    content = _good_content()
    content["hashtags"] = ["#one", "#two"]
    report = _editor().review(_brief(), content)
    assert report.checks["hashtags_present"] is False
