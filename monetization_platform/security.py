"""API-key generation, hashing, and the Bearer-token auth dependency."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_session
from .models import ApiKey, User

_KEY_PREFIX = "sk_live_"
_KEY_BYTES = 24


@dataclass
class IssuedKey:
    """The raw key (shown to the user exactly once) plus its stored hash."""

    raw: str
    key_hash: str
    prefix: str


def hash_key(raw_key: str) -> str:
    """Deterministic SHA-256 hash used for lookup and storage."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> IssuedKey:
    """Create a new random API key. The raw value is never persisted."""
    token = secrets.token_urlsafe(_KEY_BYTES)
    raw = f"{_KEY_PREFIX}{token}"
    return IssuedKey(raw=raw, key_hash=hash_key(raw), prefix=raw[: len(_KEY_PREFIX) + 6])


def _extract_bearer(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use 'Authorization: Bearer <api_key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header. Expected 'Bearer <api_key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1].strip()


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the authenticated user from the ``Authorization: Bearer`` header."""
    raw_key = _extract_bearer(authorization)
    key_hash = hash_key(raw_key)
    api_key = session.scalar(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.active.is_(True))
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = session.get(User, api_key.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found."
        )
    return user
