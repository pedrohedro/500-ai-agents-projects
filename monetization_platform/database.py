"""Database engine, session factory, and table bootstrap.

Defaults to a local SQLite file but transparently upgrades to Postgres (or any
SQLAlchemy-supported backend) via the ``DATABASE_URL`` environment variable.
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _normalize_url(url: str) -> str:
    """Normalize provider-specific Postgres URLs for SQLAlchemy 2.x.

    Managed Postgres providers (Vercel Postgres, Neon, Supabase, Heroku) hand out
    URLs starting with ``postgres://``, which SQLAlchemy 2.x no longer accepts.
    Rewrite them to the ``postgresql+psycopg2://`` driver form.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _make_engine():
    settings = get_settings()
    url = _normalize_url(settings.database_url)
    connect_args = {}
    engine_kwargs = {}
    if url.startswith("sqlite"):
        # Required for SQLite when used across FastAPI's threadpool.
        connect_args = {"check_same_thread": False}
    else:
        # Serverless (e.g. Vercel) reuses warm containers; pre_ping avoids
        # "server closed the connection" errors on recycled Postgres sockets.
        engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 300}
    return create_engine(url, connect_args=connect_args, future=True, **engine_kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables if they do not already exist (idempotent bootstrap)."""
    # Import models so they are registered on the metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a transactional session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
