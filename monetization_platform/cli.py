"""Command-line helpers for local development and deployment.

Usage::

    python -m monetization_platform.cli init          # create tables
    python -m monetization_platform.cli seed           # create a demo user + credits
    python -m monetization_platform.cli seed --email you@example.com --credits 500
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal, init_db
from .models import ApiKey, User
from .security import generate_api_key
from .wallet import credit_wallet


def cmd_init(_: argparse.Namespace) -> int:
    init_db()
    print("Database tables created / verified.")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    init_db()
    session = SessionLocal()
    try:
        user = session.scalar(select(User).where(User.email == args.email))
        if user is None:
            user = User(email=args.email, credits=0)
            session.add(user)
            session.flush()
            issued = generate_api_key()
            session.add(
                ApiKey(
                    user_id=user.id,
                    key_hash=issued.key_hash,
                    prefix=issued.prefix,
                    label="seed",
                )
            )
            session.commit()
            credit_wallet(session, user, args.credits, description="Seed credits")
            print("Created demo user:")
            print(f"  email:   {user.email}")
            print(f"  user_id: {user.id}")
            print(f"  credits: {user.credits}")
            print(f"  API KEY (save it): {issued.raw}")
        else:
            credit_wallet(session, user, args.credits, description="Seed top-up")
            print(f"User {user.email} already existed; topped up to {user.credits} credits.")
            print("(API keys are only shown at creation time.)")
        return 0
    finally:
        session.close()


def main(argv=None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=f"{settings.app_name} admin CLI")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Create database tables.")
    p_init.set_defaults(func=cmd_init)

    p_seed = sub.add_parser("seed", help="Create a demo user with credits.")
    p_seed.add_argument("--email", default="demo@example.com")
    p_seed.add_argument("--credits", type=int, default=500)
    p_seed.set_defaults(func=cmd_seed)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
