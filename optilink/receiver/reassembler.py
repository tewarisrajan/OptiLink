"""
OptiLink Receiver - Session Packet Reassembly & Cryptographic Validation.

Assembles received data & parity frames, applies Cross-Frame Erasure Decoding,
authenticates AES-256-GCM ciphertexts, decompresses streams, and verifies SHA-256 checksums.
"""

from typing import Dict, List, Optional, Tuple
import time
import hashlib

from ..protocol.header import FrameType, FrameHeader
from ..protocol.packet import OpticalPacket
from ..protocol.session import SessionMetadata, calculate_sha256
from ..protocol.fec import CrossFrameErasureCodec
from ..sender.encryptor import StreamEncryptor
from ..sender.compressor import StreamCompressor


class SessionReassembler:
    """Manages the full state machine and cryptographic reassembly of an optical transfer."""

    def __init__(self, metadata: Optional[SessionMetadata] = None):
        self.metadata = metadata
        self.is_complete = False
        self.integrity_verified = False
        self.error_message: Optional[str] = None

        # Tracking maps: seq_num -> payload bytes
        self.received_packets: Dict[int, bytes] = {}
        self.seen_seq_nums = set()

        # Telemetry metrics
        self.total_frames_received = 0
        self.duplicate_frames = 0
        self.in_frame_errors_corrected = 0
        self.fec_recovered_frames = 0
        self.estimated_lost_frames = 0

        self.start_time: Optional[float] = None
        self.last_frame_time: Optional[float] = None
        self.completion_time: Optional[float] = None

        self.reconstructed_file_bytes: Optional[bytes] = None

    def process_packet(self, packet: OpticalPacket) -> Tuple[bool, str]:
        """
        Ingests a decoded optical packet.
        Returns: (is_new_packet, status_message)
        """
        now = time.time()
        if self.start_time is None:
            self.start_time = now
        self.last_frame_time = now

        self.total_frames_received += 1
        if packet.in_frame_errors_corrected > 0:
            self.in_frame_errors_corrected += packet.in_frame_errors_corrected

        header = packet.header

        # 1. Announce Packet (Session Handshake)
        if header.frame_type == FrameType.ANNOUNCE:
            try:
                self.metadata = SessionMetadata.from_bytes(packet.payload)
                return True, f"SESSION INITIALIZED: {self.metadata.filename} ({self.metadata.file_size} B)"
            except Exception as e:
                return False, f"Invalid announce payload: {e}"

        # 2. Data or Parity Packet
        seq = header.seq_num

        if seq in self.seen_seq_nums:
            self.duplicate_frames += 1
            return False, f"DUPLICATE frame seq #{seq}"

        self.seen_seq_nums.add(seq)
        self.received_packets[seq] = packet.payload

        # Check if we have enough packets to attempt reassembly
        if self.metadata is not None:
            k = self.metadata.total_source_chunks
            total_n = self.metadata.total_frames or (k + int(k * self.metadata.fec_ratio))

            # Missing packets estimation
            max_seen = max(self.seen_seq_nums) if self.seen_seq_nums else 0
            expected_up_to_max = min(max_seen + 1, total_n)
            self.estimated_lost_frames = max(0, expected_up_to_max - len(self.seen_seq_nums))

            # Attempt full reconstruction when we have >= K packets
            if len(self.received_packets) >= k and not self.is_complete:
                success, msg = self._attempt_assembly()
                if success:
                    return True, msg

        return True, f"ACCEPTED frame seq #{seq}"

    def _attempt_assembly(self) -> Tuple[bool, str]:
        """Attempts Cross-Frame FEC recovery and end-to-end decryption/integrity verification."""
        if not self.metadata:
            return False, "No session metadata"

        k = self.metadata.total_source_chunks
        m = self.metadata.total_parity_chunks
        chunk_size = self.metadata.chunk_size

        # Check if all K source packets (seq 0 to k-1) are already received
        all_sources_present = all(i in self.received_packets for i in range(k))

        if not all_sources_present:
            # Need Cross-Frame FEC recovery
            if m > 0 and len(self.received_packets) >= k:
                try:
                    fec_codec = CrossFrameErasureCodec(k=k, m=m, packet_len=chunk_size)
                    recovered_chunks, count = fec_codec.decode(self.received_packets)
                    self.fec_recovered_frames += count
                    source_chunks = recovered_chunks
                except Exception as e:
                    return False, f"FEC recovery pending: {e}"
            else:
                return False, f"Waiting for more frames ({len(self.received_packets)}/{k})"
        else:
            source_chunks = [self.received_packets[i] for i in range(k)]

        # Assemble ciphertext stream
        combined_payload = b"".join(source_chunks)

        # Slice to expected ciphertext length if recorded
        target_len = self.metadata.compressed_size if self.metadata.compression_enabled else self.metadata.file_size
        ciphertext = combined_payload[:target_len]

        # Decrypt if encryption enabled
        if self.metadata.encryption_enabled and self.metadata.encryption_key:
            try:
                key = bytes.fromhex(self.metadata.encryption_key)
                nonce = bytes.fromhex(self.metadata.encryption_nonce)
                tag = bytes.fromhex(self.metadata.encryption_tag)
                plaintext = StreamEncryptor.decrypt(key, ciphertext, nonce, tag)
            except Exception as e:
                self.error_message = f"Decryption/Auth failed: {e}"
                return False, self.error_message
        else:
            plaintext = ciphertext

        # Decompress if compression enabled
        if self.metadata.compression_enabled:
            try:
                plaintext = StreamCompressor.decompress(plaintext)
            except Exception as e:
                self.error_message = f"Decompression failed: {e}"
                return False, self.error_message

        # Verify SHA-256
        actual_sha256 = calculate_sha256(plaintext)
        if actual_sha256.lower() != self.metadata.file_sha256.lower():
            self.error_message = f"SHA-256 mismatch: {actual_sha256} != {self.metadata.file_sha256}"
            return False, self.error_message

        # Transfer complete!
        self.is_complete = True
        self.integrity_verified = True
        self.completion_time = time.time()
        self.reconstructed_file_bytes = plaintext
        return True, "TRANSFER COMPLETE! File integrity verified by SHA-256."

    def get_telemetry(self) -> Dict:
        """Returns comprehensive real-time transfer telemetry for UI display."""
        now = time.time()
        elapsed = (now - self.start_time) if self.start_time else 0.0

        if self.is_complete and self.completion_time and self.start_time:
            total_duration = max(0.001, self.completion_time - self.start_time)
        else:
            total_duration = max(0.001, elapsed)

        file_size = self.metadata.file_size if self.metadata else 0
        filename = self.metadata.filename if self.metadata else "Unknown"
        k = self.metadata.total_source_chunks if self.metadata else 1

        received_count = len(self.received_packets)
        progress_pct = min(100.0, (received_count / k) * 100.0) if k > 0 else 0.0

        bytes_reconstructed = int((progress_pct / 100.0) * file_size)
        avg_kbps = (bytes_reconstructed / 1024.0) / total_duration if total_duration > 0 else 0.0

        # Estimate remaining time
        if progress_pct > 0 and progress_pct < 100.0 and avg_kbps > 0:
            remaining_bytes = file_size - bytes_reconstructed
            remaining_sec = remaining_bytes / (avg_kbps * 1024.0)
        else:
            remaining_sec = 0.0

        return {
            "filename": filename,
            "file_size": file_size,
            "bytes_transferred": bytes_reconstructed,
            "progress_percent": round(progress_pct, 1),
            "is_complete": self.is_complete,
            "integrity_verified": self.integrity_verified,
            "frames_received": self.total_frames_received,
            "unique_frames": len(self.seen_seq_nums),
            "duplicate_frames": self.duplicate_frames,
            "frames_recovered_fec": self.fec_recovered_frames,
            "in_frame_errors_corrected": self.in_frame_errors_corrected,
            "estimated_lost_frames": self.estimated_lost_frames,
            "speed_kbps": round(avg_kbps, 1),
            "elapsed_seconds": round(total_duration, 1),
            "remaining_seconds": round(remaining_sec, 1),
            "sha256": self.metadata.file_sha256 if self.metadata else "",
        }
