#!/usr/bin/env python3
"""CLI for the HR Resume Screening / Candidate Ranking agent.

Examples
--------
Run against the bundled samples in mock mode (no API key needed)::

    LLM_PROVIDER=mock python main.py

Screen a custom JD + resume folder and write reports::

    python main.py --jd path/to/jd.txt --resumes path/to/resumes --out out/

Estimate cost only (no screening)::

    python main.py --estimate
"""

from __future__ import annotations

import argparse
import os
import sys

# Allow running as a script from the package folder.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hr_screening.billing import BillingAccount, PricingConfig  # noqa: E402
from hr_screening.config import Settings  # noqa: E402
from hr_screening.extract import load_resume_folder  # noqa: E402
from hr_screening.models import ResumeDocument  # noqa: E402
from hr_screening.pipeline import ScreeningPipeline  # noqa: E402
from hr_screening.report import to_json, to_markdown  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JD = os.path.join(HERE, "samples", "job_description.txt")
DEFAULT_RESUMES = os.path.join(HERE, "samples", "resumes")


def _load_docs(folder: str) -> list[ResumeDocument]:
    docs: list[ResumeDocument] = []
    for path, text in load_resume_folder(folder):
        cid = os.path.splitext(os.path.basename(path))[0]
        docs.append(ResumeDocument(candidate_id=cid, raw_text=text, source_path=path))
    return docs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HR Resume Screening / Candidate Ranking agent")
    parser.add_argument("--jd", default=DEFAULT_JD, help="Path to the job description text file.")
    parser.add_argument("--resumes", default=DEFAULT_RESUMES, help="Folder of resume files (.txt/.pdf).")
    parser.add_argument("--out", default=None, help="Optional output dir for report.md/report.json.")
    parser.add_argument("--credits", type=float, default=None, help="Enable billing with this many credits.")
    parser.add_argument("--provider", default=None, help="Override LLM_PROVIDER (mock|openai).")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    parser.add_argument("--estimate", action="store_true", help="Only estimate the job cost, do not screen.")
    args = parser.parse_args(argv)

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    settings = Settings.from_env()

    if not os.path.exists(args.jd):
        print(f"error: JD file not found: {args.jd}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.resumes):
        print(f"error: resumes folder not found: {args.resumes}", file=sys.stderr)
        return 2

    with open(args.jd, "r", encoding="utf-8", errors="ignore") as fh:
        jd_text = fh.read()
    docs = _load_docs(args.resumes)
    if not docs:
        print(f"error: no readable resumes in {args.resumes}", file=sys.stderr)
        return 2

    billing = None
    if args.credits is not None or args.estimate:
        billing = BillingAccount(
            credits=args.credits if args.credits is not None else 1e9,
            pricing=PricingConfig.from_env(),
        )

    if args.estimate:
        est = billing.estimate_job_cost([d.raw_text for d in docs], jd_text)
        print(f"Estimated cost to screen {len(docs)} resume(s): ${est:.4f}")
        print(f"Pricing strategy: {billing.pricing.strategy} | "
              f"per-1k-tokens ${billing.pricing.price_per_1k_tokens_usd} x "
              f"margin {billing.pricing.margin_multiplier}")
        return 0

    pipeline = ScreeningPipeline(settings=settings, billing=billing)
    report = pipeline.screen(jd_text, docs)

    if args.json:
        print(to_json(report))
    else:
        print(to_markdown(report))

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as fh:
            fh.write(to_markdown(report))
        with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as fh:
            fh.write(to_json(report))
        print(f"\nReports written to {args.out}/report.md and report.json", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
