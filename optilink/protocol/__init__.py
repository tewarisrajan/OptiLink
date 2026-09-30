"""OptiLink Protocol Package."""

from .crc import compute_crc32, verify_crc32, compute_crc16, verify_crc16
from .header import FrameHeader, FrameType, ModulationMode, FECScheme, HEADER_SIZE
from .fec import InFrameRSCodec, CrossFrameErasureCodec
from .session import SessionMetadata, calculate_sha256
from .packet import OpticalPacket

__all__ = [
    "compute_crc32",
    "verify_crc32",
    "compute_crc16",
    "verify_crc16",
    "FrameHeader",
    "FrameType",
    "ModulationMode",
    "FECScheme",
    "HEADER_SIZE",
    "InFrameRSCodec",
    "CrossFrameErasureCodec",
    "SessionMetadata",
    "calculate_sha256",
    "OpticalPacket",
]
