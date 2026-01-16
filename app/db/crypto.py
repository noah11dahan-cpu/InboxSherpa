from __future__ import annotations

import base64
import os
from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not set")
    # Fernet expects urlsafe base64-encoded 32-byte key
    return Fernet(key.encode("utf-8"))


def encrypt_token(token: str) -> str:
    f = _fernet()
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(token_enc: str) -> str:
    f = _fernet()
    return f.decrypt(token_enc.encode("utf-8")).decode("utf-8")
