"""Encryption for stored connection secrets (Fernet: AES-128-CBC + HMAC-SHA256)."""

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def _fernet() -> Fernet:
    # Accept any string; derive a valid 32-byte Fernet key from it.
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.credentials_key.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode("utf-8")).decode("ascii")


def decrypt_json(token: str) -> dict:
    try:
        return json.loads(_fernet().decrypt(token.encode("ascii")))
    except InvalidToken as exc:
        raise ValueError("Stored connection could not be decrypted (was CREDENTIALS_KEY changed?)") from exc
