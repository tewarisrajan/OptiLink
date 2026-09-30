"""
OptiLink Optical - Color Calibration & Channel Equalization.

Dynamically adapts to ambient lighting, display gamma, and camera sensor color-cast
by sampling an in-frame optical calibration palette.
"""

from typing import List, Tuple, Dict
import numpy as np
from .colors import (
    CALIBRATION_PALETTE_NAMES,
    RGB_BY_NAME,
    MODE_COLOR_NAMES,
    rgb_to_bgr,
    bgr_to_rgb,
)


class ColorCalibrator:
    """
    Maintains calibrated reference colors for fundamental palette entries
    and classifies incoming cell colors with confidence scores.
    """

    def __init__(self, mode: int = 2):
        self.mode = mode
        # Initialize with ideal sRGB reference colors keyed by color name
        self.reference_colors: Dict[str, np.ndarray] = {
            name: np.array(rgb, dtype=np.float32)
            for name, rgb in RGB_BY_NAME.items()
        }
        self.is_calibrated = False

    def update_from_strip_samples(self, samples: List[Tuple[int, np.ndarray]]):
        """
        Updates reference color points using sampled RGB values from calibration strip cells.
        samples is a list of (strip_color_index, rgb_array).
        """
        for strip_idx, rgb_val in samples:
            if 0 <= strip_idx < len(CALIBRATION_PALETTE_NAMES):
                color_name = CALIBRATION_PALETTE_NAMES[strip_idx]
                if not self.is_calibrated:
                    self.reference_colors[color_name] = rgb_val.astype(np.float32)
                else:
                    self.reference_colors[color_name] = (
                        0.7 * self.reference_colors[color_name] + 0.3 * rgb_val.astype(np.float32)
                    )
        self.is_calibrated = True

    def classify_color(self, observed_bgr: np.ndarray, mode: int = None) -> Tuple[int, float]:
        """
        Classifies an observed cell BGR color to the closest symbol in the active mode.
        Returns: (best_symbol_index, confidence_score [0.0 - 1.0])
        """
        active_mode = mode or self.mode
        color_names = MODE_COLOR_NAMES.get(active_mode, MODE_COLOR_NAMES[2])

        # Convert observed BGR to RGB
        obs_rgb = np.array([observed_bgr[2], observed_bgr[1], observed_bgr[0]], dtype=np.float32)

        best_idx = 0
        min_dist = float("inf")
        second_min_dist = float("inf")

        # Color distance (Euclidean with perceptual luminance weighting)
        weights = np.array([0.30, 0.59, 0.11], dtype=np.float32)

        for sym_idx, name in enumerate(color_names):
            ref_rgb = self.reference_colors[name]
            diff = (obs_rgb - ref_rgb) ** 2
            dist = float(np.sqrt(np.sum(diff * weights)))

            if dist < min_dist:
                second_min_dist = min_dist
                min_dist = dist
                best_idx = sym_idx
            elif dist < second_min_dist:
                second_min_dist = dist

        # Confidence score
        if second_min_dist == 0:
            confidence = 0.0
        elif min_dist == 0:
            confidence = 1.0
        else:
            diff_ratio = (second_min_dist - min_dist) / (second_min_dist + 1e-5)
            confidence = max(0.0, min(1.0, diff_ratio))

        return best_idx, confidence
