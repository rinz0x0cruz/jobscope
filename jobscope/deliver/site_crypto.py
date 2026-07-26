"""Browser-compatible encryption for the published private dashboard payload."""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 210_000


def encrypt_dashboard(
    data: dict[str, Any],
    passphrase: str,
    *,
    salt: bytes | None = None,
    iv: bytes | None = None,
) -> dict[str, Any]:
    if len(passphrase) < 8:
        raise ValueError("dashboard passphrase must contain at least 8 characters")
    salt = salt or os.urandom(16)
    iv = iv or os.urandom(12)
    if len(salt) != 16 or len(iv) != 12:
        raise ValueError("invalid dashboard encryption salt or IV")
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS,
    ).derive(passphrase.encode("utf-8"))
    plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(iv, plaintext, None)
    return {
        "v": 1,
        "kdf": "PBKDF2-SHA256",
        "iter": ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "ct": base64.b64encode(ciphertext).decode("ascii"),
    }
