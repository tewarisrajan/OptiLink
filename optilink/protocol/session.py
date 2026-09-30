"""
OptiLink Protocol - Session Management & Metadata.

Defines the session lifecycle, cryptographic authentication metadata,
file description, and initial handshake parameters.
"""

from dataclasses import dataclass, asdict
import json
import hashlib
from typing import Optional


@dataclass
class SessionMetadata:
    session_id: int
    filename: str
    file_size: int
    file_sha256: str
    chunk_size: int
    total_source_chunks: int
    fec_ratio: float = 0.20
    total_parity_chunks: int = 0
    total_frames: int = 0
    modulation_mode: int = 2
    grid_rows: int = 32
    grid_cols: int = 32
    fps: int = 30
    compression_enabled: bool = False
    compressed_size: int = 0
    encryption_enabled: bool = True
    encryption_algo: str = "AES-GCM-256"
    encryption_nonce: str = ""
    encryption_tag: str = ""
    encryption_key: str = ""  # Hex-encoded key for receiver display / automatic decrypt

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    @classmethod
    def from_json(cls, json_str: str) -> "SessionMetadata":
        data = json.loads(json_str)
        return cls(**data)

    @classmethod
    def from_bytes(cls, data: bytes) -> "SessionMetadata":
        return cls.from_json(data.decode("utf-8"))


def calculate_sha256(data: bytes) -> str:
    """Computes SHA-256 hex digest of data."""
    return hashlib.sha256(data).hexdigest()
