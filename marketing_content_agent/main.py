"""CLI entry point for the Marketing Content Agent.

Runs the full multi-agent pipeline against a brief and prints the deliverable as
Markdown and/or JSON. Works fully offline with LLM_PROVIDER=mock (the default).

Examples
--------
    python -m marketing_content_agent.main --topic "AI for small business"
    python main.py --topic "Zero-waste kitchens" --audience "eco-conscious millennials" \
        --platform blog --tone friendly --keywords "sustainability,zero waste" --json
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

# Support both `python main.py` (script) and `python -m marketing_content_agent.main`.
try:
    from .billing import BillingEngine, OutOfCreditsError, Wallet
    from .config import get_settings
    from .pipeline import ContentPipeline
    from .render import to_markdown
    from .schemas import ContentBrief
except ImportError:  # pragma: no cover - executed only when run as a loose script
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from marketing_content_agent.billing import BillingEngine, OutOfCreditsError, Wallet
    from marketing_content_agent.config import get_settings
    from marketing_content_agent.pipeline import ContentPipeline
    from marketing_content_agent.render import to_markdown
    from marketing_content_agent.schemas import ContentBrief


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="marketing_content_agent",
        description="Autonomous multi-agent marketing content generator.",
    )
    parser.add_argument("--topic", required=True, help="Content topic (required).")
    parser.add_argument("--audience", default="general audience", help="Target audience.")
    parser.add_argument("--platform", default="blog", help="Primary platform.")
    parser.add_argument("--tone", default="professional", help="Desired tone of voice.")
    parser.add_argument(
        "--keywords", default="", help="Comma-separated SEO keywords."
    )
    parser.add_argument("--cta", default="Learn more", help="Call to action.")
    parser.add_argument("--word-count", type=int, default=600, help="Target blog word count.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--both", action="store_true", help="Print both Markdown and JSON.")
    parser.add_argument(
        "--credits",
        type=int,
        default=None,
        help="Starting wallet credits (enables billing). Omit to skip billing.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    brief = ContentBrief(
        topic=args.topic,
        target_audience=args.audience,
        platform=args.platform,
        tone=args.tone,
        keywords=keywords,
        call_to_action=args.cta,
        word_count=args.word_count,
    )

    wallet = None
    if args.credits is not None:
        wallet = Wallet(balance=args.credits)

    pipeline = ContentPipeline(settings=settings)

    print(f"[provider: {pipeline.llm.name}] Generating content for: {brief.topic!r}\n",
          file=sys.stderr)

    try:
        deliverable = pipeline.run(brief, wallet=wallet)
    except OutOfCreditsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json and not args.both:
        print(deliverable.to_json())
    elif args.both:
        print(to_markdown(deliverable))
        print("\n\n<!-- JSON -->\n")
        print(deliverable.to_json())
    else:
        print(to_markdown(deliverable))

    if wallet is not None:
        print(
            f"\n[billing] Credits remaining: {wallet.balance}",
            file=sys.stderr,
        )

    return 0 if deliverable.qa.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
