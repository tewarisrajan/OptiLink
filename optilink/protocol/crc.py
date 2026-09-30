"""
OptiLink Protocol - Checksum and CRC utilities.
Provides CRC-32 and CRC-16 implementations for packet and header integrity.
"""

import zlib
import struct


def compute_crc32(data: bytes) -> int:
    """Computes standard IEEE 802.3 CRC-32 checksum (unsigned 32-bit integer)."""
    return zlib.crc32(data) & 0xFFFFFFFF


def verify_crc32(data: bytes, expected_crc: int) -> bool:
    """Verifies data matches expected 32-bit CRC."""
    return compute_crc32(data) == (expected_crc & 0xFFFFFFFF)


def compute_crc16(data: bytes) -> int:
    """
    Computes CRC-16-CCITT (poly 0x1021, init 0xFFFF).
    Used for compact 2-byte header verification.
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def verify_crc16(data: bytes, expected_crc: int) -> bool:
    """Verifies data matches expected 16-bit CRC."""
    return compute_crc16(data) == (expected_crc & 0xFFFF)
