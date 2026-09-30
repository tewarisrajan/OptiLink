"""
OptiLink Receiver - Color Cell Segmentation & Demodulation.

Extracts data cells from rectified canonical frames, samples the calibration strip,
and decodes optical packets.
"""

from typing import Tuple, Optional, List
import cv2
import numpy as np

from ..optical.frame_layout import FrameLayout
from ..optical.calibration import ColorCalibrator
from ..optical.colors import CALIBRATION_PALETTE_NAMES, get_bits_per_cell
from ..optical.modulation import symbols_to_bytes
from ..protocol.packet import OpticalPacket


class ColorCellDecoder:
    """Decodes data cells from a rectified canonical frame."""

    def __init__(self, layout: FrameLayout = None, default_mode: int = 2):
        self.layout = layout or FrameLayout(rows=32, cols=32, corner_size=8)
        self.calibrator = ColorCalibrator(mode=default_mode)
        self.current_mode = default_mode

    def update_layout(self, rows: int, cols: int, corner_size: int = 8):
        self.layout = FrameLayout(rows=rows, cols=cols, corner_size=corner_size)

    def decode_frame(self, rectified_bgr: np.ndarray, mode_hint: int = None) -> Tuple[Optional[OpticalPacket], float, str]:
        """
        Processes a canonical rectified image:
        1. Calibrates colors using top strip.
        2. Samples data cells.
        3. Demodulates symbols into packet bytes.
        4. Validates CRC32 & in-frame Reed-Solomon.
        Returns: (decoded_packet, average_confidence, status_string)
        """
        h, w, _ = rectified_bgr.shape
        rows, cols = self.layout.rows, self.layout.cols
        cell_w = w / cols
        cell_h = h / rows

        k = self.layout.corner_size

        # 1. Sample calibration strip along row 0
        cal_samples = []
        for step, c in enumerate(range(k, cols - k)):
            strip_idx = step % len(CALIBRATION_PALETTE_NAMES)
            cy = int((0 + 0.5) * cell_h)
            cx = int((c + 0.5) * cell_w)
            bgr = self._sample_cell_center(rectified_bgr, cx, cy, int(cell_w * 0.4))
            rgb = np.array([bgr[2], bgr[1], bgr[0]], dtype=np.float32)
            cal_samples.append((strip_idx, rgb))

        self.calibrator.update_from_strip_samples(cal_samples)

        # 2. Sample data cells
        active_mode = mode_hint or self.current_mode
        bpc = get_bits_per_cell(active_mode)

        symbols = []
        confidences = []
        sample_radius = max(1, int(min(cell_w, cell_h) * 0.25))

        for r, c in self.layout.data_cells:
            cy = int((r + 0.5) * cell_h)
            cx = int((c + 0.5) * cell_w)
            cell_bgr = self._sample_cell_center(rectified_bgr, cx, cy, sample_radius)
            sym, conf = self.calibrator.classify_color(cell_bgr, mode=active_mode)
            symbols.append(sym)
            confidences.append(conf)

        avg_conf = float(np.mean(confidences)) if confidences else 0.0

        # 3. Demodulate symbols to bytes
        symbols_arr = np.array(symbols, dtype=np.uint8)
        raw_bytes = symbols_to_bytes(symbols_arr, bits_per_cell=bpc)

        # 4. Parse packet
        pkt, status = OpticalPacket.parse(raw_bytes)
        if pkt is not None:
            # Update mode if packet indicated different mode
            self.current_mode = int(pkt.header.modulation_mode)
            return pkt, avg_conf, status

        return None, avg_conf, status

    @staticmethod
    def _sample_cell_center(img: np.ndarray, cx: int, cy: int, radius: int) -> np.ndarray:
        """Takes median of center pixel patch to eliminate noise and specular glints."""
        h, w, _ = img.shape
        y1 = max(0, cy - radius)
        y2 = min(h, cy + radius + 1)
        x1 = max(0, cx - radius)
        x2 = min(w, cx + radius + 1)

        patch = img[y1:y2, x1:x2]
        if patch.size == 0:
            return img[min(cy, h - 1), min(cx, w - 1)]

        # Median along spatial dimensions
        return np.median(patch, axis=(0, 1)).astype(np.uint8)
