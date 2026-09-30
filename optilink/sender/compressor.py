"""
OptiLink Sender - Data Compression Module.

Supports zlib compression with fallback if compressed size is larger than raw data.
"""

import zlib
from typing import Tuple


class StreamCompressor:
    """Handles optional streaming / in-memory data compression."""

    @staticmethod
    def compress(data: bytes, level: int = 6) -> Tuple[bytes, bool]:
        """
        Compresses data using zlib.
        Returns: (compressed_data, was_effective)
        If compressed data is larger than raw data (e.g. already compressed files like zip/mp4/jpg),
        returns raw data and was_effective=False.
        """
        if not data:
            return data, False

        compressed = zlib.compress(data, level=level)
        if len(compressed) < len(data):
            return compressed, True
        return data, False

    @staticmethod
    def decompress(data: bytes) -> bytes:
        """Decompresses zlib-compressed data."""
        return zlib.decompress(data)
