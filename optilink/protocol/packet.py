"""
OptiLink Protocol - Packet Assembly and Disassembly.

Structure:
  [ Header (25B) | Payload (NB) | In-Frame RS Parity (PB) | CRC32 (4B) ]
"""

from dataclasses import dataclass
import struct
from typing import Optional, Tuple
from .header import FrameHeader, HEADER_SIZE
from .crc import compute_crc32, verify_crc32
from .fec import InFrameRSCodec
import reedsolo


@dataclass
class OpticalPacket:
    header: FrameHeader
    payload: bytes
    in_frame_errors_corrected: int = 0

    def serialize(self) -> bytes:
        """
        Serializes packet:
        1. Packs header (25 bytes) with synchronized payload_len
        2. Appends payload
        3. Appends In-Frame Reed-Solomon parity bytes if configured
        4. Appends 4-byte CRC32 over the entire block
        """
        self.header.payload_len = len(self.payload)
        header_bytes = self.header.pack()
        block = header_bytes + self.payload

        if self.header.fec_parity_len > 0:
            rs = InFrameRSCodec(self.header.fec_parity_len)
            block = rs.encode(block)

        crc = compute_crc32(block)
        return block + struct.pack("!I", crc)

    @classmethod
    def parse(cls, raw_bytes: bytes, fec_parity_len: int = 8) -> Tuple[Optional["OpticalPacket"], str]:
        """
        Parses and validates a raw optical packet from demodulated bytes.
        Handles trailing cell padding gracefully.
        Returns: (packet_obj, status_message)
        """
        if len(raw_bytes) < HEADER_SIZE + 4:
            return None, f"Packet too short ({len(raw_bytes)} bytes)"

        # Strategy 1: Try parsing header first to determine exact packet boundary
        try:
            header = FrameHeader.unpack(raw_bytes[:HEADER_SIZE])
            parity_len = header.fec_parity_len
            expected_pkt_len = HEADER_SIZE + header.payload_len + parity_len + 4

            if len(raw_bytes) >= expected_pkt_len:
                pkt_bytes = raw_bytes[:expected_pkt_len]
                block = pkt_bytes[:-4]
                expected_crc = struct.unpack("!I", pkt_bytes[-4:])[0]

                if verify_crc32(block, expected_crc):
                    # CRC valid without repair
                    payload = block[HEADER_SIZE : HEADER_SIZE + header.payload_len]
                    return cls(header=header, payload=payload, in_frame_errors_corrected=0), "OK"

                # CRC failed on block: attempt RS repair on block
                if parity_len > 0:
                    try:
                        rs = InFrameRSCodec(parity_len)
                        repaired, errors_corrected = rs.decode(block)
                        header_rep = FrameHeader.unpack(repaired[:HEADER_SIZE])
                        payload = repaired[HEADER_SIZE : HEADER_SIZE + header_rep.payload_len]
                        return cls(
                            header=header_rep,
                            payload=payload,
                            in_frame_errors_corrected=errors_corrected,
                        ), f"REPAIRED ({errors_corrected} errors)"
                    except Exception:
                        pass
        except Exception:
            pass

        # Strategy 2: If header itself had bit flips, try RS decode on initial window
        if fec_parity_len > 0:
            for window_len in (len(raw_bytes), min(len(raw_bytes), 256)):
                if window_len > HEADER_SIZE + fec_parity_len + 4:
                    block = raw_bytes[:window_len - 4]
                    try:
                        rs = InFrameRSCodec(fec_parity_len)
                        repaired, errors_corrected = rs.decode(block)
                        header = FrameHeader.unpack(repaired[:HEADER_SIZE])
                        payload = repaired[HEADER_SIZE : HEADER_SIZE + header.payload_len]
                        return cls(
                            header=header,
                            payload=payload,
                            in_frame_errors_corrected=errors_corrected,
                        ), f"REPAIRED ({errors_corrected} errors)"
                    except Exception:
                        continue

        return None, "CRC32 verification failed & RS uncorrectable"
