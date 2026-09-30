"""
OptiLink Adaptive - Transmission Adaptation Engine.

Dynamically selects modulation mode, grid resolution, cell size, and FEC redundancy
to maximize reliable goodput under varying optical channel conditions (lighting, distance, blur).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np


@dataclass
class ChannelState:
    decode_success_rate: float     # 0.0 to 1.0 (valid CRC/RS / total frames)
    average_confidence: float      # 0.0 to 1.0 (color classification margin)
    in_frame_error_rate: float     # errors per frame
    dropped_frame_rate: float      # frame skip frequency
    estimated_snr_db: float        # proxy SNR derived from color cluster distances


@dataclass
class AdaptiveConfig:
    modulation_mode: int  # 1=Binary, 2=4-Color, 3=8-Color
    grid_rows: int
    grid_cols: int
    fec_ratio: float      # 0.10 to 0.40
    target_fps: int
    reason: str


class AdaptiveTransmissionEngine:
    """Calculates channel quality metrics and recommends optimal transmission parameters."""

    def __init__(self):
        self.history: List[Tuple[bool, float, int]] = []  # (success, conf, err_count)
        self.window_size = 20

    def record_frame_event(self, success: bool, confidence: float, in_frame_errors: int = 0):
        """Records reception outcome for sliding window analysis."""
        self.history.append((success, confidence, in_frame_errors))
        if len(self.history) > self.window_size:
            self.history.pop(0)

    def estimate_channel_state(self) -> ChannelState:
        """Estimates optical channel characteristics from recent frame history."""
        if not self.history:
            return ChannelState(
                decode_success_rate=1.0,
                average_confidence=1.0,
                in_frame_error_rate=0.0,
                dropped_frame_rate=0.0,
                estimated_snr_db=25.0,
            )

        successes = sum(1 for s, _, _ in self.history if s)
        total = len(self.history)
        success_rate = successes / total

        confidences = [c for _, c, _ in self.history]
        avg_conf = float(np.mean(confidences)) if confidences else 1.0

        errors = [e for _, _, e in self.history]
        avg_errs = float(np.mean(errors)) if errors else 0.0

        # Proxy SNR: map confidence to dB scale [5 dB to 30 dB]
        snr_proxy_db = 5.0 + (avg_conf * 25.0)

        return ChannelState(
            decode_success_rate=success_rate,
            average_confidence=avg_conf,
            in_frame_error_rate=avg_errs,
            dropped_frame_rate=max(0.0, 1.0 - success_rate),
            estimated_snr_db=round(snr_proxy_db, 1),
        )

    def recommend_configuration(self, current_mode: int = 2) -> AdaptiveConfig:
        """
        Recommends parameter adaptation that maximizes reliable goodput:
        - Excellent channel (high SNR, high confidence, 0 errors):
          8-color, 48x48 grid, low FEC (10%), 60 FPS
        - Normal channel:
          4-color, 32x32 grid, moderate FEC (20%), 30 FPS
        - Degraded channel (glare, blur, low light, distance):
          Binary (high noise margin), 24x24 grid (large cells), high FEC (35%), 20 FPS
        """
        state = self.estimate_channel_state()

        if state.decode_success_rate > 0.92 and state.average_confidence > 0.78:
            # Channel is clean - push for high throughput
            return AdaptiveConfig(
                modulation_mode=3,  # 8-color
                grid_rows=48,
                grid_cols=48,
                fec_ratio=0.15,
                target_fps=45,
                reason="EXCELLENT CHANNEL: Switching to 8-Color 48x48 for maximum goodput",
            )
        elif state.decode_success_rate > 0.75 and state.average_confidence > 0.55:
            # Channel is moderate
            return AdaptiveConfig(
                modulation_mode=2,  # 4-color
                grid_rows=32,
                grid_cols=32,
                fec_ratio=0.20,
                target_fps=30,
                reason="MODERATE CHANNEL: Stable 4-Color 32x32 configuration",
            )
        else:
            # Channel is noisy/distorted - switch to maximum resilience
            return AdaptiveConfig(
                modulation_mode=1,  # Binary
                grid_rows=24,
                grid_cols=24,
                fec_ratio=0.35,
                target_fps=20,
                reason="DEGRADED CHANNEL: Switching to high-contrast Binary 24x24 with 35% FEC redundancy",
            )
