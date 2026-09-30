"""
OptiLink Sender - Optical Transmitter Engine.

Orchestrates the entire transmission pipeline:
File -> Compression -> Encryption -> Chunking -> 2D FEC -> Optical Packetization -> Frame Rendering.
"""

from typing import List, Generator, Tuple, Optional, Dict
import os
import time
import math
import cv2
import numpy as np

from .file_reader import StreamingFileReader
from .compressor import StreamCompressor
from .encryptor import StreamEncryptor
from .chunker import StreamChunker
from ..protocol.header import FrameHeader, FrameType, ModulationMode, FECScheme
from ..protocol.session import SessionMetadata, calculate_sha256
from ..protocol.fec import CrossFrameErasureCodec
from ..protocol.packet import OpticalPacket
from ..optical.frame_layout import FrameLayout
from ..optical.frame_generator import FrameGenerator
from ..optical.colors import get_bits_per_cell


class OpticalTransmitter:
    """High-speed optical frame generator and transmission engine."""

    def __init__(
        self,
        file_path_or_data,
        filename: str = "transfer.bin",
        modulation_mode: int = 2,
        grid_rows: int = 32,
        grid_cols: int = 32,
        fps: int = 30,
        fec_ratio: float = 0.20,
        in_frame_fec_bytes: int = 8,
        enable_encryption: bool = True,
        enable_compression: bool = True,
        session_id: int = None,
    ):
        self.reader = StreamingFileReader(file_path_or_data, filename)
        self.filename = self.reader.filename
        self.file_size = self.reader.file_size
        self.modulation_mode = modulation_mode
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.fps = fps
        self.fec_ratio = fec_ratio
        self.in_frame_fec_bytes = in_frame_fec_bytes
        self.enable_encryption = enable_encryption
        self.enable_compression = enable_compression
        self.session_id = session_id or int(time.time()) & 0xFFFFFFFF

        self.layout = FrameLayout(rows=grid_rows, cols=grid_cols, corner_size=8)
        self.generator = FrameGenerator(self.layout)

        # Computed during prepare()
        self.metadata: Optional[SessionMetadata] = None
        self.packets: List[OpticalPacket] = []
        self.total_frames = 0
        self.is_prepared = False

        # Live telemetry
        self.frames_sent = 0
        self.start_time: Optional[float] = None

    def prepare(self):
        """Prepares entire transmission dataset: compression, encryption, FEC, and packetization."""
        raw_data = self.reader.read_all()
        sha256_hash = self.reader.compute_sha256()

        # 1. Optional Compression
        compressed_size = len(raw_data)
        if self.enable_compression:
            compressed_data, effective = StreamCompressor.compress(raw_data)
            if effective:
                data_to_encrypt = compressed_data
                compressed_size = len(compressed_data)
                self.is_compressed = True
            else:
                data_to_encrypt = raw_data
                self.is_compressed = False
        else:
            data_to_encrypt = raw_data
            self.is_compressed = False

        # 2. Authenticated Encryption (AES-256-GCM)
        if self.enable_encryption:
            encryptor = StreamEncryptor()
            ciphertext, nonce, tag = encryptor.encrypt(data_to_encrypt)
            key_hex = encryptor.key_hex
            nonce_hex = nonce.hex()
            tag_hex = tag.hex()
        else:
            ciphertext = data_to_encrypt
            key_hex, nonce_hex, tag_hex = "", "", ""

        # 3. Calculate payload capacity per optical frame
        bpc = get_bits_per_cell(self.modulation_mode)
        chunk_size = self.layout.get_max_payload_bytes(
            bits_per_cell=bpc,
            header_size=25,
            fec_parity_len=self.in_frame_fec_bytes,
            crc_len=4,
        )

        # 4. Chunk ciphertext
        chunker = StreamChunker(chunk_size=chunk_size)
        source_chunks = chunker.chunk(ciphertext)
        k = len(source_chunks)

        # 5. Cross-Frame Erasure Coding
        m = max(1, int(math.ceil(k * self.fec_ratio))) if self.fec_ratio > 0 else 0
        if m > 0:
            # Handle block limit (GF(2^8) max block K+M <= 255)
            # If K + M > 250, split into generations
            if k + m <= 250:
                fec_codec = CrossFrameErasureCodec(k=k, m=m, packet_len=chunk_size)
                parity_chunks = fec_codec.encode(source_chunks)
            else:
                # Fallback to no parity or simple chunking for massive single files
                m = 0
                parity_chunks = []
        else:
            parity_chunks = []

        total_frames = 1 + k + m + 1  # 1 Announce + K Data + M Parity + 1 EOT
        self.total_frames = total_frames

        # 6. Session Metadata
        self.metadata = SessionMetadata(
            session_id=self.session_id,
            filename=self.filename,
            file_size=self.file_size,
            file_sha256=sha256_hash,
            chunk_size=chunk_size,
            total_source_chunks=k,
            fec_ratio=self.fec_ratio,
            total_parity_chunks=m,
            total_frames=total_frames,
            modulation_mode=self.modulation_mode,
            grid_rows=self.grid_rows,
            grid_cols=self.grid_cols,
            fps=self.fps,
            compression_enabled=self.is_compressed,
            compressed_size=compressed_size,
            encryption_enabled=self.enable_encryption,
            encryption_algo="AES-GCM-256",
            encryption_nonce=nonce_hex,
            encryption_tag=tag_hex,
            encryption_key=key_hex,
        )

        # 7. Assemble Optical Packets
        self.packets = []

        # Frame 0: Announce Frame (Repeated 2-3 times at start for instant discovery)
        announce_payload = self.metadata.to_bytes()
        announce_hdr = FrameHeader(
            session_id=self.session_id,
            seq_num=0,
            total_frames=total_frames,
            payload_len=len(announce_payload),
            frame_type=FrameType.ANNOUNCE,
            modulation_mode=ModulationMode(self.modulation_mode),
            grid_rows=self.grid_rows,
            grid_cols=self.grid_cols,
            fec_scheme=FECScheme.IN_FRAME_RS,
            fec_parity_len=self.in_frame_fec_bytes,
        )
        self.packets.append(OpticalPacket(header=announce_hdr, payload=announce_payload))

        # Frames 1 to K: Source Data Frames
        for seq, chunk in enumerate(source_chunks):
            data_hdr = FrameHeader(
                session_id=self.session_id,
                seq_num=seq,
                total_frames=total_frames,
                payload_len=len(chunk),
                frame_type=FrameType.DATA,
                modulation_mode=ModulationMode(self.modulation_mode),
                grid_rows=self.grid_rows,
                grid_cols=self.grid_cols,
                fec_scheme=FECScheme.HYBRID,
                fec_parity_len=self.in_frame_fec_bytes,
            )
            self.packets.append(OpticalPacket(header=data_hdr, payload=chunk))

        # Frames K to K+M-1: Cross-Frame FEC Parity Frames
        for p_idx, p_chunk in enumerate(parity_chunks):
            parity_hdr = FrameHeader(
                session_id=self.session_id,
                seq_num=k + p_idx,
                total_frames=total_frames,
                payload_len=len(p_chunk),
                frame_type=FrameType.FEC_PARITY,
                modulation_mode=ModulationMode(self.modulation_mode),
                grid_rows=self.grid_rows,
                grid_cols=self.grid_cols,
                fec_scheme=FECScheme.HYBRID,
                fec_parity_len=self.in_frame_fec_bytes,
            )
            self.packets.append(OpticalPacket(header=parity_hdr, payload=p_chunk))

        # Final Frame: End of Transmission (EOT)
        eot_hdr = FrameHeader(
            session_id=self.session_id,
            seq_num=total_frames - 1,
            total_frames=total_frames,
            payload_len=0,
            frame_type=FrameType.EOT,
            modulation_mode=ModulationMode(self.modulation_mode),
            grid_rows=self.grid_rows,
            grid_cols=self.grid_cols,
            fec_scheme=FECScheme.NONE,
            fec_parity_len=0,
        )
        self.packets.append(OpticalPacket(header=eot_hdr, payload=b""))

        self.is_prepared = True

    def get_transmission_stream(
        self,
        target_size: int = 768,
        loop: bool = True,
    ) -> Generator[Tuple[int, np.ndarray, OpticalPacket, Dict], None, None]:
        """
        Yields sequential optical frames ready for screen display.
        In loop=True mode, cycles continuously through data and parity packets so receivers
        can lock on asynchronously.
        """
        if not self.is_prepared:
            self.prepare()

        self.start_time = time.time()
        self.frames_sent = 0

        # Cycle announce packet twice initially to ensure quick discovery
        initial_packets = [self.packets[0], self.packets[0]] + self.packets

        while True:
            for idx, pkt in enumerate(initial_packets):
                frame_img = self.generator.generate_grid_image(pkt, target_size=target_size)
                self.frames_sent += 1

                elapsed = max(0.001, time.time() - self.start_time)
                instant_fps = self.frames_sent / elapsed

                bpc = get_bits_per_cell(self.modulation_mode)
                symbols_per_frame = self.layout.usable_cell_count
                raw_bitrate_bps = symbols_per_frame * bpc * instant_fps
                effective_bps = (self.file_size * 8.0) / max(0.001, (self.total_frames / max(1, self.fps)))

                telemetry = {
                    "filename": self.filename,
                    "file_size": self.file_size,
                    "frame_index": self.frames_sent,
                    "seq_num": pkt.header.seq_num,
                    "frame_type": pkt.header.frame_type.name,
                    "total_frames": self.total_frames,
                    "progress_percent": round(min(100.0, (pkt.header.seq_num / max(1, self.total_frames)) * 100.0), 1),
                    "fps": round(instant_fps, 1),
                    "raw_bitrate_kbps": round(raw_bitrate_bps / 1000.0, 1),
                    "effective_bitrate_kbps": round(effective_bps / 1000.0, 1),
                    "modulation_mode": self.modulation_mode,
                    "grid_size": f"{self.grid_rows}x{self.grid_cols}",
                    "encryption": self.enable_encryption,
                }

                yield self.frames_sent, frame_img, pkt, telemetry

            if not loop:
                break
