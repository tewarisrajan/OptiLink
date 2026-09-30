"""
OptiLink Test Suite.

Comprehensive unit and integration tests verifying:
- Frame header serialization and CRC16 validation
- CRC32 verification and packet parsing
- AES-256-GCM authenticated encryption and tamper detection
- In-Frame Reed-Solomon error correction
- Cross-Frame 2D Erasure coding for missing packet recovery
- Bit modulation/demodulation across Binary, 4-Color, 8-Color modes
- Dynamic optical color calibration and cell classification
- Homography perspective rectification
- End-to-end simulated file transmission with 100% SHA-256 verification
"""

import os
import pytest
import numpy as np
import cv2

from optilink.protocol.crc import compute_crc16, verify_crc16, compute_crc32, verify_crc32
from optilink.protocol.header import FrameHeader, FrameType, ModulationMode, FECScheme, HEADER_SIZE
from optilink.protocol.fec import InFrameRSCodec, CrossFrameErasureCodec
from optilink.protocol.session import SessionMetadata, calculate_sha256
from optilink.protocol.packet import OpticalPacket
from optilink.sender.encryptor import StreamEncryptor
from optilink.sender.compressor import StreamCompressor
from optilink.sender.chunker import StreamChunker
from optilink.sender.transmitter import OpticalTransmitter
from optilink.optical.colors import (
    get_palette_rgb,
    get_bits_per_cell,
    CALIBRATION_PALETTE_RGB,
    PALETTE_BINARY_RGB,
    PALETTE_4COLOR_RGB,
    PALETTE_8COLOR_RGB,
)
from optilink.optical.modulation import bytes_to_symbols, symbols_to_bytes
from optilink.optical.frame_layout import FrameLayout
from optilink.optical.calibration import ColorCalibrator
from optilink.optical.frame_generator import FrameGenerator
from optilink.receiver.detector import FrameDetector
from optilink.receiver.perspective import PerspectiveRectifier
from optilink.receiver.color_decoder import ColorCellDecoder
from optilink.receiver.reassembler import SessionReassembler
from optilink.benchmark.simulator import run_optical_simulation, OpticalChannelSimulator


def test_crc_and_header():
    """Verifies CRC32, CRC16, and header packing/unpacking."""
    data = b"OptiLink Protocol Packet Checksum Verification"
    crc32_val = compute_crc32(data)
    assert verify_crc32(data, crc32_val)
    assert not verify_crc32(data + b"X", crc32_val)

    hdr = FrameHeader(
        session_id=98765,
        seq_num=42,
        total_frames=100,
        payload_len=128,
        frame_type=FrameType.DATA,
        modulation_mode=ModulationMode.COLOR_4,
        grid_rows=32,
        grid_cols=32,
        fec_scheme=FECScheme.HYBRID,
        fec_parity_len=8,
    )
    packed = hdr.pack()
    assert len(packed) == HEADER_SIZE

    unpacked = FrameHeader.unpack(packed)
    assert unpacked.session_id == 98765
    assert unpacked.seq_num == 42
    assert unpacked.total_frames == 100
    assert unpacked.payload_len == 128
    assert unpacked.frame_type == FrameType.DATA
    assert unpacked.modulation_mode == ModulationMode.COLOR_4

    # Header CRC corruption test
    corrupted_header = bytearray(packed)
    corrupted_header[5] ^= 0xFF
    with pytest.raises(ValueError):
        FrameHeader.unpack(bytes(corrupted_header))


def test_encryption_and_compression():
    """Verifies AES-256-GCM encryption, decryption, authentication, and zlib compression."""
    plaintext = b"Top secret optical transmission payload." * 50

    # Compression
    compressed, effective = StreamCompressor.compress(plaintext)
    assert effective
    assert len(compressed) < len(plaintext)
    decompressed = StreamCompressor.decompress(compressed)
    assert decompressed == plaintext

    # Encryption
    encryptor = StreamEncryptor()
    ciphertext, nonce, tag = encryptor.encrypt(plaintext)
    assert ciphertext != plaintext

    # Valid decryption
    decrypted = StreamEncryptor.decrypt(encryptor.key, ciphertext, nonce, tag)
    assert decrypted == plaintext

    # Tampered ciphertext detection
    tampered_ct = bytearray(ciphertext)
    tampered_ct[0] ^= 0x01
    with pytest.raises(Exception):
        StreamEncryptor.decrypt(encryptor.key, bytes(tampered_ct), nonce, tag)


def test_in_frame_rs_fec():
    """Verifies in-frame Reed-Solomon error correction for corrupted bytes."""
    codec = InFrameRSCodec(parity_len=8)  # can fix up to 4 byte errors
    msg = b"Reliable Optical Communications via Screen-to-Camera Link"
    encoded = codec.encode(msg)
    assert len(encoded) == len(msg) + 8

    # Introduce 3 random byte errors
    corrupted = bytearray(encoded)
    corrupted[2] ^= 0x55
    corrupted[10] ^= 0xAA
    corrupted[18] ^= 0x33

    repaired, count = codec.decode(bytes(corrupted))
    assert repaired == msg
    assert count == 3


def test_cross_frame_erasure_coding():
    """Verifies 2D packet erasure code: recovering lost frames without retransmission."""
    k = 8
    m = 3
    packet_len = 64
    src_packets = [os.urandom(packet_len) for _ in range(k)]

    codec = CrossFrameErasureCodec(k=k, m=m, packet_len=packet_len)
    parity_packets = codec.encode(src_packets)
    assert len(parity_packets) == m

    # Simulate dropping 2 source frames and 1 parity frame (e.g. frames 2, 5, and parity 1)
    rcvd = {i: src_packets[i] for i in range(k) if i not in (2, 5)}
    rcvd[k + 0] = parity_packets[0]
    rcvd[k + 2] = parity_packets[2]

    # Reconstruct
    reconstructed, recovered_count = codec.decode(rcvd)
    assert recovered_count == 2
    assert reconstructed == src_packets


def test_modulation_modes():
    """Verifies symbol packing/unpacking across 1, 2, and 3 bits/cell."""
    test_bytes = os.urandom(256)
    for bpc in (1, 2, 3):
        symbols = bytes_to_symbols(test_bytes, bits_per_cell=bpc)
        max_sym = (1 << bpc)
        assert np.all(symbols < max_sym)
        recovered = symbols_to_bytes(symbols, bits_per_cell=bpc, expected_byte_len=len(test_bytes))
        assert recovered == test_bytes


def test_optical_end_to_end_simulation():
    """Verifies end-to-end transmission with physical blur, noise, tilt, and dropped frames."""
    original_data = b"Optical Link Verification Document Content.\n" * 40
    expected_hash = calculate_sha256(original_data)

    channel = OpticalChannelSimulator(
        frame_drop_rate=0.06,  # 6% dropped frames
        tilt_degrees=8.0,      # 8 degree tilt
        noise_sigma=4.0,       # sensor noise
        blur_kernel_size=3,    # slight defocus
    )

    results = run_optical_simulation(
        file_bytes=original_data,
        filename="verify.txt",
        modulation_mode=2,
        grid_rows=32,
        grid_cols=32,
        fec_ratio=0.25,
        simulator=channel,
    )

    assert results["file_recovered_100pct"] == True
    assert results["sha256"] == expected_hash
