"""CLI for the 24/7 Support Chatbot.

Examples (run from the support_chatbot_agent/ directory):

    # Ingest the knowledge base into the local vector index
    python main.py ingest

    # Ask a single question (mock mode needs no API keys)
    LLM_PROVIDER=mock python main.py ask "How do I reset my password?"

    # Interactive chat loop
    python main.py chat

    # Show billing / pricing preview
    python main.py billing
"""
from __future__ import annotations

import argparse
import json
import sys

from chatbot.agent import build_agent
from chatbot.billing import BillingEngine, OutOfCreditsError
from chatbot.config import get_config
from chatbot.ingest import build_index


def _print_result(result) -> None:
    print("\n" + "=" * 68)
    print(f"Q: {result.question}")
    print("-" * 68)
    print(f"A: {result.answer}")
    print("-" * 68)
    print(f"confidence = {result.confidence:.3f}   escalate = {result.escalate}   "
          f"tokens = {result.tokens_used}")
    if result.sources:
        print("sources:")
        for s in result.sources:
            print(f"  - [{s.source}] (score={s.score:.3f}) {s.snippet[:80]}...")
    print("=" * 68 + "\n")


def cmd_ingest(args: argparse.Namespace) -> int:
    config = get_config()
    store = build_index(config)
    print(f"Ingested {len(store)} chunks from {config.knowledge_base_dir}")
    print(f"Index saved to {config.index_path}")
    print(f"Provider: {config.llm_provider}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    config = get_config()
    agent = build_agent(config)
    billing = BillingEngine(config)

    result = agent.answer(args.question)
    _print_result(result)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))

    try:
        charge = billing.charge_message(
            args.account, result.tokens_used, answered=not result.escalate
        )
        if charge.charged:
            print(f"[billing] charged ${charge.amount:.4f} "
                  f"(margin ${charge.margin:.4f}), remaining ${charge.remaining_credits:.4f}")
        else:
            print(f"[billing] not charged ({charge.reason}), "
                  f"remaining ${charge.remaining_credits:.4f}")
    except OutOfCreditsError as exc:
        print(f"[billing] {exc}")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    config = get_config()
    agent = build_agent(config)
    print(f"Support chatbot ready (provider={config.llm_provider}). Type 'exit' to quit.")
    while True:
        try:
            question = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        result = agent.answer(question)
        _print_result(result)
    return 0


def cmd_billing(args: argparse.Namespace) -> int:
    config = get_config()
    billing = BillingEngine(config)
    from chatbot.billing import PLANS

    print("Plans:")
    for plan in PLANS.values():
        print(f"  {plan.name:8s} ${plan.price_per_seat_month:6.0f}/seat/mo  "
              f"{plan.monthly_credits_per_seat:.0f} USD credits/seat  "
              f"{plan.seats_included} seats")

    preview = billing.preview(tokens=500)
    print(f"\nCost model: ${config.price_per_1k_tokens}/1k tokens billed, "
          f"${config.api_cost_per_1k_tokens}/1k tokens API cost")
    print(f"Example 500-token message: charge ${preview.amount:.4f}, "
          f"API cost ${preview.api_cost:.4f}, margin ${preview.margin:.4f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="24/7 Support Chatbot CLI")
    sub = parser.add_subparsers(dest="command")

    p_ingest = sub.add_parser("ingest", help="Build the vector index from the KB")
    p_ingest.set_defaults(func=cmd_ingest)

    p_ask = sub.add_parser("ask", help="Ask a single question")
    p_ask.add_argument("question", help="The question to ask")
    p_ask.add_argument("--account", default="demo", help="Billable account id")
    p_ask.add_argument("--json", action="store_true", help="Also print JSON output")
    p_ask.set_defaults(func=cmd_ask)

    p_chat = sub.add_parser("chat", help="Interactive chat loop")
    p_chat.set_defaults(func=cmd_chat)

    p_bill = sub.add_parser("billing", help="Show pricing / cost model")
    p_bill.set_defaults(func=cmd_billing)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # Default: ask a friendly demo question so `python main.py` just works.
        args = parser.parse_args(["ask", "How do I reset my password?"])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
