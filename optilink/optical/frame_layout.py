"""
OptiLink Optical - Frame Geometry and Layout Definition.

Defines the spatial arrangement of optical frames:
- 4 Corner Synchronization Markers (ArUco / nested fiducials)
- Calibration Palette Strip (8 reference colors)
- Structured Data Cell Grid
- Deterministic cell allocation mapping
"""

from typing import List, Tuple, Set
import numpy as np


class FrameLayout:
    """Manages spatial coordinates and cell allocation of an optical frame."""

    def __init__(self, rows: int = 32, cols: int = 32, corner_size: int = 8):
        if rows < 16 or cols < 16:
            raise ValueError(f"Grid dimensions must be at least 16x16, got {rows}x{cols}")
        if corner_size * 2 >= min(rows, cols):
            raise ValueError(f"Corner marker size {corner_size} is too large for grid {rows}x{cols}")

        self.rows = rows
        self.cols = cols
        self.corner_size = corner_size

        # Reserved cell set: (r, c) coordinates that cannot be used for data
        self.reserved_cells: Set[Tuple[int, int]] = set()
        self._init_reserved_cells()

        # Usable data cells in linear order (row-major)
        self.data_cells: List[Tuple[int, int]] = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in self.reserved_cells
        ]

    def _init_reserved_cells(self):
        k = self.corner_size

        # 1. Top-Left Corner (TL)
        for r in range(k):
            for c in range(k):
                self.reserved_cells.add((r, c))

        # 2. Top-Right Corner (TR)
        for r in range(k):
            for c in range(self.cols - k, self.cols):
                self.reserved_cells.add((r, c))

        # 3. Bottom-Left Corner (BL)
        for r in range(self.rows - k, self.rows):
            for c in range(k):
                self.reserved_cells.add((r, c))

        # 4. Bottom-Right Corner (BR)
        for r in range(self.rows - k, self.rows):
            for c in range(self.cols - k, self.cols):
                self.reserved_cells.add((r, c))

        # 5. Calibration strip between TL and TR at row 0 and 1
        # Reserve row 0 between column k and (cols - k)
        for c in range(k, self.cols - k):
            self.reserved_cells.add((0, c))

    @property
    def total_cells(self) -> int:
        return self.rows * self.cols

    @property
    def usable_cell_count(self) -> int:
        return len(self.data_cells)

    def get_max_packet_bytes(self, bits_per_cell: int) -> int:
        """Returns total packet bytes (header + payload + fec + crc) that fit in this frame."""
        total_bits = self.usable_cell_count * bits_per_cell
        return total_bits // 8

    def get_max_payload_bytes(self, bits_per_cell: int, header_size: int = 25, fec_parity_len: int = 8, crc_len: int = 4) -> int:
        """Returns pure payload capacity after deducting protocol overhead."""
        max_pkt = self.get_max_packet_bytes(bits_per_cell)
        overhead = header_size + fec_parity_len + crc_len
        if max_pkt <= overhead:
            raise ValueError(f"Grid capacity {max_pkt} bytes too small for overhead {overhead} bytes")
        return max_pkt - overhead
