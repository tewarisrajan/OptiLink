"""
OptiLink Optical - Modulation & Demodulation.

Converts byte streams to discrete symbol sequences based on bits per cell:
- Binary: 1 bit / symbol (values 0..1)
- 4-Color: 2 bits / symbol (values 0..3)
- 8-Color: 3 bits / symbol (values 0..7)
"""

from typing import List
import numpy as np


def bytes_to_symbols(data: bytes, bits_per_cell: int) -> np.ndarray:
    """
    Converts raw bytes into an array of symbol indices in range [0, 2^bits_per_cell - 1].
    """
    if bits_per_cell not in (1, 2, 3):
        raise ValueError(f"Unsupported bits_per_cell: {bits_per_cell}. Must be 1, 2, or 3.")

    # Convert bytes into array of bits (MSB first)
    byte_arr = np.frombuffer(data, dtype=np.uint8)
    # Unpack 8 bits per byte
    bits = np.unpackbits(byte_arr)

    # Calculate padding needed to align to bits_per_cell
    rem = len(bits) % bits_per_cell
    if rem != 0:
        pad_len = bits_per_cell - rem
        bits = np.concatenate([bits, np.zeros(pad_len, dtype=np.uint8)])

    # Group into symbols
    if bits_per_cell == 1:
        symbols = bits
    elif bits_per_cell == 2:
        bits_reshaped = bits.reshape(-1, 2)
        symbols = (bits_reshaped[:, 0] << 1) | bits_reshaped[:, 1]
    elif bits_per_cell == 3:
        bits_reshaped = bits.reshape(-1, 3)
        symbols = (bits_reshaped[:, 0] << 2) | (bits_reshaped[:, 1] << 1) | bits_reshaped[:, 2]

    return symbols.astype(np.uint8)


def symbols_to_bytes(symbols: np.ndarray, bits_per_cell: int, expected_byte_len: int = None) -> bytes:
    """
    Converts symbol indices back into raw bytes.
    Truncates to expected_byte_len if specified.
    """
    if bits_per_cell not in (1, 2, 3):
        raise ValueError(f"Unsupported bits_per_cell: {bits_per_cell}")

    symbols = np.asarray(symbols, dtype=np.uint8).flatten()

    if bits_per_cell == 1:
        bits = symbols & 0x01
    elif bits_per_cell == 2:
        b0 = (symbols >> 1) & 0x01
        b1 = symbols & 0x01
        bits = np.column_stack((b0, b1)).flatten()
    elif bits_per_cell == 3:
        b0 = (symbols >> 2) & 0x01
        b1 = (symbols >> 1) & 0x01
        b2 = symbols & 0x01
        bits = np.column_stack((b0, b1, b2)).flatten()

    # Pack bits into uint8 bytes
    packed_bytes = np.packbits(bits).tobytes()

    if expected_byte_len is not None:
        return packed_bytes[:expected_byte_len]
    return packed_bytes
