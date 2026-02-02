"""AES-256-GCM encryption for sensitive data."""

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


class EncryptionService:
    """AES-256-GCM encryption service for sensitive data like CNIC, bank accounts."""

    def __init__(self, key: bytes) -> None:
        """Initialize with 32-byte key for AES-256."""
        if len(key) != 32:
            raise ValueError("Encryption key must be 32 bytes for AES-256")
        self._key = key
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string and return bytes (nonce + ciphertext).

        Args:
            plaintext: The string to encrypt

        Returns:
            bytes: 12-byte nonce prepended to the ciphertext
        """
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt bytes and return the original string.

        Args:
            ciphertext: Bytes containing nonce + encrypted data

        Returns:
            str: The decrypted plaintext
        """
        if len(ciphertext) < 12:
            raise ValueError("Ciphertext too short")
        nonce = ciphertext[:12]
        encrypted_data = ciphertext[12:]
        plaintext = self._aesgcm.decrypt(nonce, encrypted_data, None)
        return plaintext.decode("utf-8")

    def encrypt_to_base64(self, plaintext: str) -> str:
        """Encrypt and return as base64 string for JSON storage."""
        encrypted = self.encrypt(plaintext)
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt_from_base64(self, ciphertext_b64: str) -> str:
        """Decrypt from base64 string."""
        ciphertext = base64.b64decode(ciphertext_b64.encode("ascii"))
        return self.decrypt(ciphertext)


@lru_cache
def get_encryption_service() -> EncryptionService:
    """Get cached encryption service instance."""
    # Derive 32-byte key from settings
    key = settings.encryption_key.encode("utf-8")
    if len(key) < 32:
        key = key.ljust(32, b"\0")
    elif len(key) > 32:
        key = key[:32]
    return EncryptionService(key)


# Convenience functions
def encrypt_sensitive(plaintext: str) -> bytes:
    """Encrypt sensitive data."""
    return get_encryption_service().encrypt(plaintext)


def decrypt_sensitive(ciphertext: bytes) -> str:
    """Decrypt sensitive data."""
    return get_encryption_service().decrypt(ciphertext)
