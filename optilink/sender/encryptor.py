"""
OptiLink Sender - Authenticated Encryption Module.

Uses AES-256-GCM (Galois/Counter Mode) authenticated encryption.
Guarantees both confidentiality and tamper-proof message integrity.
"""

import os
from typing import Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class StreamEncryptor:
    """Authenticated encryption using AES-256-GCM."""

    def __init__(self, key: bytes = None):
        """
        Initializes with 256-bit (32 bytes) key.
        If key is None, a secure random key is generated.
        """
        self.key = key if key is not None else AESGCM.generate_key(bit_length=256)
        self._aesgcm = AESGCM(self.key)

    @property
    def key_hex(self) -> str:
        return self.key.hex()

    def encrypt(self, plaintext: bytes, associated_data: bytes = None) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypts plaintext with a random 96-bit (12 bytes) IV/nonce.
        Returns: (ciphertext, nonce, auth_tag)
        """
        nonce = os.urandom(12)
        # AESGCM in cryptography appends the 16-byte tag to the ciphertext
        ct_with_tag = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        ciphertext = ct_with_tag[:-16]
        tag = ct_with_tag[-16:]
        return ciphertext, nonce, tag

    @classmethod
    def decrypt(cls, key: bytes, ciphertext: bytes, nonce: bytes, tag: bytes, associated_data: bytes = None) -> bytes:
        """
        Decrypts and authenticates ciphertext.
        Raises InvalidTag if ciphertext or tag was tampered with.
        """
        aesgcm = AESGCM(key)
        ct_with_tag = ciphertext + tag
        return aesgcm.decrypt(nonce, ct_with_tag, associated_data)
