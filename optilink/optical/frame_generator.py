"""
OptiLink Optical - Frame Generator.

Renders complete high-contrast optical transmission frames containing:
- 4 Corner Fiducial Markers (ArUco IDs 0, 1, 2, 3)
- Optical Color Calibration Palette Strip
- Modulated Payload Data Grid
- Outer Quiet Zone
"""

from typing import Tuple, Optional
import cv2
import numpy as np

from .colors import (
    get_palette_rgb,
    get_bits_per_cell,
    CALIBRATION_PALETTE_RGB,
    rgb_to_bgr,
)
from .modulation import bytes_to_symbols
from .frame_layout import FrameLayout
from ..protocol.packet import OpticalPacket


class FrameGenerator:
    """Generates optical display frames from packets."""

    def __init__(self, layout: FrameLayout = None):
        self.layout = layout or FrameLayout(rows=32, cols=32, corner_size=6)
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

    def generate_grid_image(
        self,
        packet: OpticalPacket,
        target_size: int = 768,
        quiet_zone_px: int = 24,
    ) -> np.ndarray:
        """
        Renders an optical packet into a BGR image of dimensions target_size x target_size.
        """
        mode = int(packet.header.modulation_mode)
        bits_per_cell = get_bits_per_cell(mode)
        palette = get_palette_rgb(mode)

        # 1. Serialize packet to bytes
        packet_bytes = packet.serialize()

        # 2. Modulate bytes into symbol sequence
        symbols = bytes_to_symbols(packet_bytes, bits_per_cell)

        # 3. Create grid of cells (rows x cols x 3 BGR)
        rows, cols = self.layout.rows, self.layout.cols
        k = self.layout.corner_size
        grid_bgr = np.zeros((rows, cols, 3), dtype=np.uint8)

        # 4. Fill data cells
        data_cells = self.layout.data_cells
        max_symbols = len(data_cells)
        for i, (r, c) in enumerate(data_cells):
            if i < len(symbols):
                sym_val = int(symbols[i])
            else:
                sym_val = 0  # padding

            # Safety clamp to palette range
            if sym_val >= len(palette):
                sym_val = 0

            rgb_color = palette[sym_val]
            grid_bgr[r, c] = rgb_to_bgr(rgb_color)

        # 5. Fill calibration strip (row 0, columns k to cols - k)
        cal_cols = cols - 2 * k
        for step, c in enumerate(range(k, cols - k)):
            cal_color_idx = step % len(CALIBRATION_PALETTE_RGB)
            rgb_color = CALIBRATION_PALETTE_RGB[cal_color_idx]
            grid_bgr[0, c] = rgb_to_bgr(rgb_color)

        # 6. Fill ArUco corner markers into the corners with white margin
        # Corner box is k x k (white background)
        # Marker is 6 x 6 centered at offset (1, 1)
        grid_bgr[0:k, 0:k] = (255, 255, 255)
        grid_bgr[0:k, cols - k : cols] = (255, 255, 255)
        grid_bgr[rows - k : rows, cols - k : cols] = (255, 255, 255)
        grid_bgr[rows - k : rows, 0:k] = (255, 255, 255)

        m0 = cv2.aruco.generateImageMarker(self.aruco_dict, 0, 6)
        m1 = cv2.aruco.generateImageMarker(self.aruco_dict, 1, 6)
        m2 = cv2.aruco.generateImageMarker(self.aruco_dict, 2, 6)
        m3 = cv2.aruco.generateImageMarker(self.aruco_dict, 3, 6)

        offset_r = (k - 6) // 2
        offset_c = (k - 6) // 2

        grid_bgr[offset_r : offset_r + 6, offset_c : offset_c + 6] = cv2.cvtColor(m0, cv2.COLOR_GRAY2BGR)
        grid_bgr[offset_r : offset_r + 6, cols - k + offset_c : cols - k + offset_c + 6] = cv2.cvtColor(m1, cv2.COLOR_GRAY2BGR)
        grid_bgr[rows - k + offset_r : rows - k + offset_r + 6, cols - k + offset_c : cols - k + offset_c + 6] = cv2.cvtColor(m2, cv2.COLOR_GRAY2BGR)
        grid_bgr[rows - k + offset_r : rows - k + offset_r + 6, offset_c : offset_c + 6] = cv2.cvtColor(m3, cv2.COLOR_GRAY2BGR)

        # 7. Scale up to target display size with nearest-neighbor to preserve sharp cell boundaries
        content_size = target_size - (2 * quiet_zone_px)
        scaled_content = cv2.resize(
            grid_bgr,
            (content_size, content_size),
            interpolation=cv2.INTER_NEAREST,
        )

        # 8. Create final frame with high-contrast quiet zone border
        final_frame = np.ones((target_size, target_size, 3), dtype=np.uint8) * 255
        qz = quiet_zone_px
        final_frame[qz : qz + content_size, qz : qz + content_size] = scaled_content

        # Add thin outer black registration line around the active area
        cv2.rectangle(
            final_frame,
            (qz - 2, qz - 2),
            (qz + content_size + 1, qz + content_size + 1),
            (0, 0, 0),
            thickness=2,
        )

        return final_frame
