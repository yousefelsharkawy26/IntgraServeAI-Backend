# utils/encrypted_type.py
"""SQLAlchemy TypeDecorator for transparent Fernet encryption."""

from sqlalchemy import TypeDecorator, Text
from utils.encryption import SecretEncryptor


class EncryptedText(TypeDecorator):
    """
    Transparently encrypt/decrypt text at the application layer.

    - Values bound to the DB are encrypted via Fernet.
    - Values loaded from the DB are decrypted automatically.
    - None is passed through unchanged.
    - If decryption fails (legacy plaintext), the raw value is returned
      to prevent data loss during migration.
    """

    impl = Text
    cache_ok = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._encryptor = SecretEncryptor()

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return self._encryptor.encrypt(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._encryptor.decrypt(value)
