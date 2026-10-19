"""Encryption at rest for users' LLM API keys (MultiFernet: first key encrypts, all keys decrypt)."""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from doctune.core.config import get_settings


class KeyDecryptError(Exception):
    pass


@lru_cache
def _fernet() -> MultiFernet:
    keys = [k.strip() for k in get_settings().key_encryption_keys.get_secret_value().split(",") if k.strip()]
    if not keys:
        raise RuntimeError("KEY_ENCRYPTION_KEYS is not set")
    return MultiFernet([Fernet(k.encode()) for k in keys])


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise KeyDecryptError("stored key can't be decrypted with the configured keys") from exc


def rotate(ciphertext: bytes) -> bytes:
    """Re-encrypt with the current (first) key."""
    return _fernet().rotate(ciphertext)


def mask(key: str) -> str:
    """Show enough to recognise a key, never enough to use it."""
    return key[-4:] if len(key) >= 8 else "****"
