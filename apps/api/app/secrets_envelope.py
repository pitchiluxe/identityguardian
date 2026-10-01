"""Envelope encryption for connector secrets (SECURITY.md "Secrets").

A random data key encrypts the secret (AES-256-GCM); the master key encrypts the data key. Only
the envelope is stored. The master key comes from server configuration and is never stored with
the data. Plaintext is used in memory only (e.g. webhook verification) and never returned by APIs.
"""

import base64
import os

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


def seal(plaintext: str, encoded_master: str, context: str) -> dict:
    kek = master_key(encoded_master)
    data_key = AESGCM.generate_key(bit_length=256)
    nonce, dk_nonce = os.urandom(12), os.urandom(12)
    ciphertext = AESGCM(data_key).encrypt(nonce, plaintext.encode(), context.encode())
    wrapped = AESGCM(kek).encrypt(dk_nonce, data_key, context.encode())
    return dict(
        v=VERSION,
        alg="AES-256-GCM",
        dk_nonce=_b64(dk_nonce),
        dk=_b64(wrapped),
        nonce=_b64(nonce),
        ct=_b64(ciphertext),
    )


def open_envelope(envelope: dict, encoded_master: str, context: str) -> str:
    kek = master_key(encoded_master)
    data_key = AESGCM(kek).decrypt(
        base64.b64decode(envelope["dk_nonce"]), base64.b64decode(envelope["dk"]), context.encode()
    )
    return (
        AESGCM(data_key)
        .decrypt(
            base64.b64decode(envelope["nonce"]), base64.b64decode(envelope["ct"]), context.encode()
        )
        .decode()
    )
