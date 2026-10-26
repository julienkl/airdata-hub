"""Hachage des mots de passe et jetons JWT (utilisé par l'API C5)."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

SECRET_KEY = os.getenv("JWT_SECRET", "change-me-in-.env")
ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("JWT_MINUTES", "60"))
_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_token(username: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": username, "role": role, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
