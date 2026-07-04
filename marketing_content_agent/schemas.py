"""Typed data structures for the content pipeline.

Implemented with stdlib dataclasses (no pydantic dependency) so the core runs
with zero third-party packages. Includes JSON (de)serialization helpers.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContentBrief:
    """The input to the pipeline: what to write and for whom."""

    topic: str
    target_audience: str = "general audience"
    platform: str = "blog"
    tone: str = "professional"
    keywords: List[str] = field(default_factory=list)
    call_to_action: str = "Learn more"
    word_count: int = 600

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContentBrief":
        allowed = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        clean = {k: v for k, v in data.items() if k in allowed}
        if "topic" not in clean or not clean["topic"]:
            raise ValueError("ContentBrief requires a non-empty 'topic'.")
        return cls(**clean)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SocialVariations:
    """Platform-specific social copy."""

    instagram: str = ""
    linkedin: str = ""
    twitter: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QAReport:
    """Output of the Editor/QA reviewer agent."""

    passed: bool = False
    score: float = 0.0
    checks: Dict[str, bool] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UsageStats:
    """Token accounting and cost for a single run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    credits_charged: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Deliverable:
    """The structured product returned to the customer."""

    brief: ContentBrief
    seo_title: str = ""
    meta_description: str = ""
    blog_post: str = ""
    social: SocialVariations = field(default_factory=SocialVariations)
    hashtags: List[str] = field(default_factory=list)
    research_notes: str = ""
    qa: QAReport = field(default_factory=QAReport)
    usage: UsageStats = field(default_factory=UsageStats)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brief": self.brief.to_dict(),
            "seo_title": self.seo_title,
            "meta_description": self.meta_description,
            "blog_post": self.blog_post,
            "social": self.social.to_dict(),
            "hashtags": self.hashtags,
            "research_notes": self.research_notes,
            "qa": self.qa.to_dict(),
            "usage": self.usage.to_dict(),
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
