"""Password hashing, signed session tokens and encryption of stored provider keys.

Stdlib PBKDF2 for passwords, HMAC-signed tokens for sessions, Fernet (cryptography) for API keys at rest.
The signing secret comes from STUDIO_SECRET or a generated file in server/data (git-ignored).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = Path(os.environ.get("STUDIO_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
TOKEN_TTL = 12 * 3600


@lru_cache
def _secret() -> bytes:
    env = os.environ.get("STUDIO_SECRET")
    if env:
        return env.encode()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    f = DATA_DIR / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        cand = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
        return hmac.compare_digest(cand.hex(), dk)
    except ValueError:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_token(user_id: str, ttl: int = TOKEN_TTL) -> str:
    body = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl}).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> str | None:
    """Returns the user id, or None when the token is malformed, forged or expired."""
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return payload["sub"] if payload["exp"] > time.time() else None
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"provider-keys:" + _secret()).digest()))


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(blob: str) -> str | None:
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None


def mask(key: str) -> str:
    return f"{key[:4]}...{key[-4:]}" if len(key) > 10 else "****"
