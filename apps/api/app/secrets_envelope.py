"""Envelope encryption for connector secrets (SECURITY.md "Secrets").

A random data key encrypts the secret (AES-256-GCM); the master key encrypts the data key. Only
the envelope is stored. The master key comes from server configuration and is never stored with
the data. Plaintext is used in memory only (e.g. webhook verification) and never returned by APIs.
"""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 1


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def master_key(encoded: str) -> bytes:
    if not encoded:
        raise ValueError("Secret storage is disabled: no master key is configured")
    key = base64.b64decode(encoded)
    if len(key) != 32:
        raise ValueError("Master key must be 32 bytes (base64)")
    return key


def key_id(encoded: str) -> str:
    """Non-secret identifier recorded on each envelope so rotation knows which key wrapped it."""
    return hashlib.sha256(b"identityguardian-kek|" + master_key(encoded)).hexdigest()[:16]


def _wrap(kek: bytes, data_key: bytes, context: str) -> tuple[bytes, bytes]:
    dk_nonce = os.urandom(12)
    return dk_nonce, AESGCM(kek).encrypt(dk_nonce, data_key, context.encode())


def _data_key(envelope: dict, current: str, previous, context: str) -> bytes:
    candidates = [current, *previous]
    if "kid" in envelope:
        candidates = [k for k in candidates if k and key_id(k) == envelope["kid"]]
        if not candidates:
            raise ValueError("The master key that sealed this secret is not configured")
    wrapped = base64.b64decode(envelope["dk"])
    nonce = base64.b64decode(envelope["dk_nonce"])
    for index, encoded in enumerate(candidates):
        try:
            return AESGCM(master_key(encoded)).decrypt(nonce, wrapped, context.encode())
        except InvalidTag:
            if index == len(candidates) - 1:
                raise
    raise ValueError("Secret storage is disabled: no master key is configured")


def seal(plaintext: str, encoded_master: str, context: str) -> dict:
    kek = master_key(encoded_master)
    data_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext.encode(), context.encode())
    dk_nonce, wrapped = _wrap(kek, data_key, context)
    return dict(
        v=VERSION,
        alg="AES-256-GCM",
        kid=key_id(encoded_master),
        dk_nonce=_b64(dk_nonce),
        dk=_b64(wrapped),
        nonce=_b64(nonce),
        ct=_b64(ciphertext),
    )


def open_envelope(envelope: dict, encoded_master: str, context: str, previous=()) -> str:
    data_key = _data_key(envelope, encoded_master, previous, context)
    return (
        AESGCM(data_key)
        .decrypt(
            base64.b64decode(envelope["nonce"]), base64.b64decode(envelope["ct"]), context.encode()
        )
        .decode()
    )


def rewrap(envelope: dict, encoded_master: str, context: str, previous=()) -> dict | None:
    """Re-wrap the data key under the current master key; the ciphertext is untouched.

    Returns None when the envelope already uses the current key (rotation is idempotent).
    """
    if envelope.get("kid") == key_id(encoded_master):
        return None
    data_key = _data_key(envelope, encoded_master, previous, context)
    dk_nonce, wrapped = _wrap(master_key(encoded_master), data_key, context)
    return {
        **envelope,
        "kid": key_id(encoded_master),
        "dk_nonce": _b64(dk_nonce),
        "dk": _b64(wrapped),
    }
