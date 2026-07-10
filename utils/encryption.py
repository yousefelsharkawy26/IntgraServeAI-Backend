# utils/encryption.py
"""Application-level encryption utilities using Fernet (AES-128-CBC + HMAC)."""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from core.config import settings

logger = logging.getLogger(__name__)


def _derive_fernet_key(key_material: str) -> bytes:
    """Derive a 32-byte Fernet key from arbitrary key material."""
    raw = hashlib.sha256(key_material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def _get_encryption_key() -> bytes:
    """Return the Fernet key, preferring ENCRYPTION_KEY, falling back to SECRET_KEY."""
    env_key: Optional[str] = getattr(settings, "ENCRYPTION_KEY", None)
    if env_key:
        return _derive_fernet_key(env_key)

    # Fallback: derive from SECRET_KEY so things work out of the box,
    # but log a warning that a dedicated key is recommended.
    logger.warning(
        "ENCRYPTION_KEY is not set; falling back to SECRET_KEY for encryption. "
        "Set a dedicated ENCRYPTION_KEY environment variable for stronger isolation."
    )
    return _derive_fernet_key(settings.SECRET_KEY)


class SecretEncryptor:
    """Singleton-like Fernet encryptor for transparent at-rest encryption."""

    _instance: Optional["SecretEncryptor"] = None
    _fernet: Optional[Fernet] = None

    def __new__(cls) -> "SecretEncryptor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._fernet = Fernet(_get_encryption_key())
        return cls._instance

    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        if plaintext is None:
            return None
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: Optional[str]) -> Optional[str]:
        if ciphertext is None:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # If decryption fails (legacy plaintext), return as-is to avoid data loss
            logger.warning("Failed to decrypt value; returning plaintext fallback")
            return ciphertext
        except Exception as e:
            logger.error(f"Unexpected decryption error: {e}")
            raise
