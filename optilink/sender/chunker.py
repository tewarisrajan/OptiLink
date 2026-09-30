"""
OptiLink Sender - Stream Chunker & Generation Segmenter.

Partitions encrypted streams into uniform payloads suitable for optical packetization
and block-wise Cross-Frame Erasure Coding.
"""

from typing import List, Tuple
import math


class StreamChunker:
    """Chunks data streams and arranges them into FEC block generations."""

    def __init__(self, chunk_size: int = 256, block_size: int = 64):
        """
        chunk_size: payload bytes per optical packet
        block_size: number of source packets per FEC generation (max 128 for GF(2^8))
        """
        self.chunk_size = chunk_size
        self.block_size = block_size

    def chunk(self, data: bytes) -> List[bytes]:
        """
        Splits data into uniform chunks of chunk_size.
        The last chunk is padded with b'\\x00' to chunk_size if needed.
        """
        if not data:
            return [b"\x00" * self.chunk_size]

        chunks = []
        for i in range(0, len(data), self.chunk_size):
            chunk = data[i : i + self.chunk_size]
            if len(chunk) < self.chunk_size:
                chunk = chunk.ljust(self.chunk_size, b"\x00")
            chunks.append(chunk)
        return chunks

    def create_generations(self, chunks: List[bytes]) -> List[List[bytes]]:
        """
        Splits chunks into FEC generations/blocks of at most `block_size` chunks.
        """
        generations = []
        for i in range(0, len(chunks), self.block_size):
            generations.append(chunks[i : i + self.block_size])
        return generations
