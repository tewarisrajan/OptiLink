"""
OptiLink Protocol - Frame Header Definition & Serialization.

Format:
- Magic: 2 bytes ('OL' = 0x4F, 0x4C)
- Version: 1 byte (0x01)
- Frame Type: 1 byte (0=Announce, 1=Data, 2=FEC_Parity, 3=EOT)
- Session ID: 4 bytes (uint32)
- Sequence Number: 4 bytes (uint32)
- Total Source Frames: 4 bytes (uint32)
- Payload Length: 2 bytes (uint16)
- Modulation Mode: 1 byte (1=Binary, 2=4-Color, 3=8-Color, 4=Adaptive)
- Grid Rows: 1 byte (e.g. 32)
- Grid Cols: 1 byte (e.g. 32)
- FEC Scheme: 1 byte (0=None, 1=In-Frame RS, 2=Erasure, 3=Hybrid)
- FEC Parity Length: 1 byte (in-frame RS parity bytes)
- Header CRC16: 2 bytes
Total: 25 bytes fixed length.
"""

from dataclasses import dataclass
import enum
import struct
from .crc import compute_crc16, verify_crc16


class FrameType(enum.IntEnum):
    ANNOUNCE = 0
    DATA = 1
    FEC_PARITY = 2
    EOT = 3


class ModulationMode(enum.IntEnum):
    BINARY = 1    # 1 bit per cell (Black, White)
    COLOR_4 = 2   # 2 bits per cell (Black, Red, Green, Blue)
    COLOR_8 = 3   # 3 bits per cell (8 distinct colors)
    ADAPTIVE = 4  # Dynamically negotiated mode


class FECScheme(enum.IntEnum):
    NONE = 0
    IN_FRAME_RS = 1
    CROSS_FRAME_ERASURE = 2
    HYBRID = 3


HEADER_MAGIC = b"OL"
PROTOCOL_VERSION = 1
HEADER_FORMAT_NO_CRC = "!2sBBIIIHBBBBB"  # 2+1+1+4+4+4+2+1+1+1+1+1 = 23 bytes
HEADER_FORMAT = "!2sBBIIIHBBBBBH"        # 23 + 2 = 25 bytes
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


@dataclass
class FrameHeader:
    session_id: int
    seq_num: int
    total_frames: int
    payload_len: int
    frame_type: FrameType = FrameType.DATA
    modulation_mode: ModulationMode = ModulationMode.COLOR_4
    grid_rows: int = 32
    grid_cols: int = 32
    fec_scheme: FECScheme = FECScheme.HYBRID
    fec_parity_len: int = 8
    version: int = PROTOCOL_VERSION

    def pack(self) -> bytes:
        """Serializes header to 25 bytes with CRC16."""
        raw_header = struct.pack(
            HEADER_FORMAT_NO_CRC,
            HEADER_MAGIC,
            self.version,
            int(self.frame_type),
            self.session_id,
            self.seq_num,
            self.total_frames,
            self.payload_len,
            int(self.modulation_mode),
            self.grid_rows,
            self.grid_cols,
            int(self.fec_scheme),
            self.fec_parity_len,
        )
        crc = compute_crc16(raw_header)
        return raw_header + struct.pack("!H", crc)

    @classmethod
    def unpack(cls, data: bytes) -> "FrameHeader":
        """Deserializes header from bytes with strict magic and CRC16 validation."""
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Header too short: expected {HEADER_SIZE}, got {len(data)}")

        raw_header = data[:HEADER_SIZE - 2]
        expected_crc = struct.unpack("!H", data[HEADER_SIZE - 2:HEADER_SIZE])[0]

        if not verify_crc16(raw_header, expected_crc):
            raise ValueError("Header CRC16 mismatch - corrupted header")

        (
            magic,
            version,
            frame_type,
            session_id,
            seq_num,
            total_frames,
            payload_len,
            modulation_mode,
            grid_rows,
            grid_cols,
            fec_scheme,
            fec_parity_len,
        ) = struct.unpack(HEADER_FORMAT_NO_CRC, raw_header)

        if magic != HEADER_MAGIC:
            raise ValueError(f"Invalid magic: {magic} != {HEADER_MAGIC}")

        return cls(
            session_id=session_id,
            seq_num=seq_num,
            total_frames=total_frames,
            payload_len=payload_len,
            frame_type=FrameType(frame_type),
            modulation_mode=ModulationMode(modulation_mode),
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            fec_scheme=FECScheme(fec_scheme),
            fec_parity_len=fec_parity_len,
            version=version,
        )
