"""
OptiLink Benchmark - Performance Metrics Calculator.

Computes theoretical and empirical optical communication metrics:
- Raw Bitrate: symbols/sec * bits/symbol
- Effective Bitrate: payload bits / total transfer time
- Goodput: clean application bytes / elapsed time (excluding protocol/FEC overhead)
- Packet Error Rate (PER) & Bit Error Rate (BER)
"""

from typing import Dict


def calculate_raw_bitrate(grid_cells: int, bits_per_cell: int, fps: float) -> float:
    """Calculates theoretical raw channel bitrate in bits per second."""
    return float(grid_cells * bits_per_cell * fps)


def calculate_effective_bitrate(payload_bytes: int, elapsed_seconds: float) -> float:
    """Calculates empirical effective bitrate in bits per second."""
    if elapsed_seconds <= 0:
        return 0.0
    return float((payload_bytes * 8.0) / elapsed_seconds)


def calculate_goodput_kbps(file_bytes: int, elapsed_seconds: float) -> float:
    """Calculates clean application layer goodput in Kilobytes per second (KB/s)."""
    if elapsed_seconds <= 0:
        return 0.0
    return float((file_bytes / 1024.0) / elapsed_seconds)


def calculate_ber(total_bits_sent: int, bit_errors: int) -> float:
    """Calculates bit error rate."""
    if total_bits_sent <= 0:
        return 0.0
    return float(bit_errors / total_bits_sent)


def calculate_per(total_packets: int, failed_packets: int) -> float:
    """Calculates packet error rate."""
    if total_packets <= 0:
        return 0.0
    return float(failed_packets / total_packets)
