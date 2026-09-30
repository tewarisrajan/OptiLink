"""
OptiLink Protocol - Forward Error Correction (FEC).

Implements dual-tier error correction:
1. In-Frame FEC: Reed-Solomon per frame to correct burst/random bit & byte flips.
2. Cross-Frame Erasure Coding: 2D Block Reed-Solomon erasure coding across packet batches.
   Allows complete recovery of missing/dropped frames (e.g. shutter blink, camera motion blur)
   without requiring retransmission.
"""

from typing import Dict, List, Optional, Tuple
import reedsolo


class InFrameRSCodec:
    """Reed-Solomon error correction for a single frame payload."""

    def __init__(self, parity_len: int = 8):
        self.parity_len = parity_len
        self._codec = reedsolo.RSCodec(parity_len) if parity_len > 0 else None

    def encode(self, data: bytes) -> bytes:
        """Appends RS parity bytes to data."""
        if not self._codec or self.parity_len == 0:
            return data
        encoded = self._codec.encode(data)
        return bytes(encoded)

    def decode(self, data_with_parity: bytes) -> Tuple[bytes, int]:
        """
        Decodes and repairs corrupted data.
        Returns: (repaired_data, error_count)
        Raises: reedsolo.ReedSolomonError if errors exceed correction capacity.
        """
        if not self._codec or self.parity_len == 0:
            return data_with_parity, 0
        decoded, decoded_full, errata = self._codec.decode(data_with_parity)
        err_count = len(errata) if errata is not None else 0
        return bytes(decoded), err_count


class CrossFrameErasureCodec:
    """
    Cross-frame systematic erasure coding using vertical Reed-Solomon across packet streams.
    
    Given K source packets of uniform length L:
    Generates M parity packets of length L.
    Any K packets out of the total K + M packets are sufficient to reconstruct
    all K original source packets.
    """

    def __init__(self, k: int, m: int, packet_len: int):
        if k < 1:
            raise ValueError("Source packet count K must be >= 1")
        if m < 0:
            raise ValueError("Parity packet count M must be >= 0")
        if k + m > 255:
            raise ValueError(f"K + M ({k + m}) exceeds Galois field GF(2^8) maximum block length 255")

        self.k = k
        self.m = m
        self.packet_len = packet_len
        self._codec = reedsolo.RSCodec(m) if m > 0 else None

    def encode(self, source_packets: List[bytes]) -> List[bytes]:
        """
        Encodes K source packets into M parity packets.
        All packets must have length == packet_len (pad if necessary).
        Returns: List of M parity packet bytes.
        """
        if len(source_packets) != self.k:
            raise ValueError(f"Expected {self.k} source packets, got {len(source_packets)}")

        for i, p in enumerate(source_packets):
            if len(p) != self.packet_len:
                raise ValueError(f"Packet {i} length {len(p)} != expected {self.packet_len}")

        if self.m == 0:
            return []

        # Create M parity packet buffers of length packet_len
        parity_buffers = [bytearray(self.packet_len) for _ in range(self.m)]

        # Vertical Reed-Solomon encoding column-by-column
        for col in range(self.packet_len):
            col_bytes = bytes(source_packets[row][col] for row in range(self.k))
            encoded_col = self._codec.encode(col_bytes)
            # Parity symbols are in encoded_col[self.k : self.k + self.m]
            for p_idx in range(self.m):
                parity_buffers[p_idx][col] = encoded_col[self.k + p_idx]

        return [bytes(buf) for buf in parity_buffers]

    def decode(self, received_packets: Dict[int, bytes]) -> Tuple[List[bytes], int]:
        """
        Reconstructs all K source packets given any >= K received packets (source or parity).
        received_packets is a dict mapping index (0 <= index < K + M) to packet bytes.
        Returns: (list_of_k_source_packets, recovered_count)
        """
        if len(received_packets) < self.k:
            raise ValueError(
                f"Insufficient packets: have {len(received_packets)}, need at least {self.k}"
            )

        # Check if all K source packets are already present (no loss)
        all_sources_present = all(i in received_packets for i in range(self.k))
        if all_sources_present:
            source_packets = [received_packets[i] for i in range(self.k)]
            return source_packets, 0

        if self.m == 0:
            raise ValueError("Cannot recover lost packets when M=0 parity packets")

        total_n = self.k + self.m
        missing_indices = [i for i in range(total_n) if i not in received_packets]

        if len(missing_indices) > self.m:
            raise ValueError(
                f"Too many missing packets: {len(missing_indices)} > parity capacity {self.m}"
            )

        # Build column templates with zeros at missing positions
        col_template = bytearray(total_n)
        for idx, pkt in received_packets.items():
            if idx < total_n:
                pass  # filled per column

        reconstructed_sources = [bytearray(self.packet_len) for _ in range(self.k)]
        erase_pos = missing_indices

        # Reconstruct vertical columns
        for col in range(self.packet_len):
            for idx, pkt in received_packets.items():
                if idx < total_n:
                    col_template[idx] = pkt[col]
            for idx in missing_indices:
                col_template[idx] = 0

            # Decode using erasure positions
            try:
                decoded_col, _, _ = self._codec.decode(col_template, erase_pos=erase_pos)
                for row in range(self.k):
                    reconstructed_sources[row][col] = decoded_col[row]
            except Exception as e:
                raise ValueError(f"FEC column reconstruction failed at byte {col}: {e}")

        recovered_count = sum(1 for i in range(self.k) if i not in received_packets)
        return [bytes(buf) for buf in reconstructed_sources], recovered_count
