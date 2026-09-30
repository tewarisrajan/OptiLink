"""
OptiLink Sender - Streaming File Reader.

Efficiently processes files of any size without loading entire multi-GB files into RAM.
Computes SHA-256 stream digests incrementally.
"""

import os
import hashlib
from typing import Generator, Tuple, Optional


class StreamingFileReader:
    """Streams data from disk or memory while computing checksums."""

    def __init__(self, file_path_or_data, filename: str = "transfer.bin"):
        if isinstance(file_path_or_data, (str, os.PathLike)):
            self.file_path = str(file_path_or_data)
            self.filename = os.path.basename(self.file_path)
            self.file_size = os.path.getsize(self.file_path)
            self._is_file = True
            self._data = None
        elif isinstance(file_path_or_data, bytes):
            self.file_path = None
            self.filename = filename
            self.file_size = len(file_path_or_data)
            self._is_file = False
            self._data = file_path_or_data
        else:
            raise TypeError("Expected file path string or bytes")

    def compute_sha256(self, buffer_size: int = 65536) -> str:
        """Computes SHA-256 without loading large files into memory."""
        hasher = hashlib.sha256()
        if self._is_file:
            with open(self.file_path, "rb") as f:
                while chunk := f.read(buffer_size):
                    hasher.update(chunk)
        else:
            hasher.update(self._data)
        return hasher.hexdigest()

    def stream_chunks(self, chunk_size: int = 1024) -> Generator[bytes, None, None]:
        """Yields chunks of specified size."""
        if self._is_file:
            with open(self.file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk
        else:
            for offset in range(0, self.file_size, chunk_size):
                yield self._data[offset : offset + chunk_size]

    def read_all(self) -> bytes:
        """Returns full content (used for smaller files or when encrypting full stream)."""
        if self._is_file:
            with open(self.file_path, "rb") as f:
                return f.read()
        return self._data
