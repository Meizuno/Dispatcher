"""Service authentication tokens.

A service is issued an opaque bearer token once at registration; only the
SHA-256 hash is stored. Authentication hashes the presented token and looks
the service up by that hash, so the plaintext is never persisted.
"""

from __future__ import annotations

import hashlib
import secrets


def generate_token() -> str:
    """Return a fresh, URL-safe opaque token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored/compared for a token."""
    return hashlib.sha256(token.encode()).hexdigest()
