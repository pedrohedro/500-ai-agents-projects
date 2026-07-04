"""Command-line entry point for the Legal Document Reviewer.

Usage::

    python main.py samples/sample_contract.txt
    python main.py samples/sample_contract.txt --format json
    LLM_PROVIDER=mock python main.py "raw contract text..."

Runs fully in mock mode with no API keys.
"""
from __future__ import annotations

import argparse
import os
import sys

# Allow running both as ``python main.py`` (cwd = this folder) and as a module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from billing import BillingManager, CreditAccount, OutOfCreditsError  # noqa: E402
from config import get_settings  # noqa: E402
from pipeline import ReviewPipeline  # noqa: E402
from report import to_json, to_markdown  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review a contract and produce a structured risk report.",
    )
    parser.add_argument(
        "source",
        help="Path to a .txt/.pdf contract file, or raw contract text.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "both"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--credits",
        type=float,
        default=None,
        help="Optional starting credit balance to exercise billing/deduction.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write the report to instead of stdout.",
    )
    return parser


def run(argv=None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    pipeline = ReviewPipeline(settings)

    billing = None
    if args.credits is not None:
        billing = BillingManager(CreditAccount(balance=args.credits), settings)

    try:
        result = pipeline.review(args.source)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    billing_line = ""
    if billing is not None:
        try:
            charge = billing.charge_for_review(result.token_usage, result.document_name)
            billing_line = (
                f"\n[billing] charged ${charge['charged']:.4f}, "
                f"remaining balance ${charge['remaining_balance']:.4f} "
                f"(margin {charge['estimate']['margin_pct']:.1f}%)"
            )
        except OutOfCreditsError as exc:
            print(f"[billing] BLOCKED: {exc}", file=sys.stderr)
            return 3

    if args.format == "json":
        output = to_json(result)
    elif args.format == "both":
        output = to_markdown(result) + "\n\n---\n\n```json\n" + to_json(result) + "\n```"
    else:
        output = to_markdown(result)

    output += billing_line

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(output)
        print(f"Report written to {args.out}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
