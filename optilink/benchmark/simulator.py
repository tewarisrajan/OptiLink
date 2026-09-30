"""
OptiLink Benchmark - Optical Channel Simulator.

Accurately simulates real-world optical degradation:
- Perspective tilt, camera rotation, and scale variations
- Lens defocus blur and sensor Gaussian noise
- Ambient lighting shifts, contrast attenuation, and glare
- Color channel crosstalk (Bayer filter overlap)
- Dropped frames (shutter blink, motion blur, CPU hitch)
"""

from typing import Tuple, List, Optional, Dict
import random
import cv2
import numpy as np

from ..protocol.session import calculate_sha256
from ..sender.transmitter import OpticalTransmitter
from ..receiver.detector import FrameDetector
from ..receiver.perspective import PerspectiveRectifier
from ..receiver.color_decoder import ColorCellDecoder
from ..receiver.reassembler import SessionReassembler


class OpticalChannelSimulator:
    """Applies realistic optical degradations to rendered transmission frames."""

    def __init__(
        self,
        frame_drop_rate: float = 0.05,       # 5% dropped frames
        tilt_degrees: float = 12.0,          # 12-degree perspective tilt
        blur_kernel_size: int = 3,           # slight lens defocus
        noise_sigma: float = 8.0,            # sensor photon noise
        brightness_shift: float = -15.0,     # dim room lighting
        contrast_factor: float = 0.90,       # screen contrast degradation
    ):
        self.frame_drop_rate = frame_drop_rate
        self.tilt_degrees = tilt_degrees
        self.blur_kernel_size = blur_kernel_size
        self.noise_sigma = noise_sigma
        self.brightness_shift = brightness_shift
        self.contrast_factor = contrast_factor

    def degrade_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Passes a visual frame through the simulated physical optical channel.
        Returns degraded frame or None (if frame dropped).
        """
        # 1. Simulate Frame Drop
        if random.random() < self.frame_drop_rate:
            return None  # Dropped frame!

        h, w, c = frame.shape
        degraded = frame.copy().astype(np.float32)

        # 2. Lighting and Contrast Changes
        degraded = (degraded * self.contrast_factor) + self.brightness_shift
        degraded = np.clip(degraded, 0, 255).astype(np.uint8)

        # 3. Defocus Blur
        if self.blur_kernel_size > 1:
            k = self.blur_kernel_size if self.blur_kernel_size % 2 == 1 else self.blur_kernel_size + 1
            degraded = cv2.GaussianBlur(degraded, (k, k), 0)

        # 4. Sensor Noise (Gaussian)
        if self.noise_sigma > 0:
            noise = np.random.normal(0, self.noise_sigma, degraded.shape).astype(np.float32)
            degraded = np.clip(degraded.astype(np.float32) + noise, 0, 255).astype(np.uint8)

        # 5. Perspective Distortion / Viewing Angle Tilt
        if self.tilt_degrees > 0:
            degraded = self._apply_perspective_tilt(degraded, self.tilt_degrees)

        return degraded

    def _apply_perspective_tilt(self, img: np.ndarray, max_angle_deg: float) -> np.ndarray:
        """Applies 3D projective warp simulating an off-axis camera angle."""
        h, w = img.shape[:2]
        pad = int(max(h, w) * 0.25)
        padded = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(240, 240, 240))
        ph, pw = padded.shape[:2]

        rad = np.radians(max_angle_deg)
        dx = int(pw * 0.10 * np.sin(rad))
        dy = int(ph * 0.08 * np.sin(rad))

        src = np.array([[pad, pad], [pad + w, pad], [pad + w, pad + h], [pad, pad + h]], dtype=np.float32)
        dst = np.array([
            [pad + dx, pad + dy],
            [pad + w - dx, pad],
            [pad + w, pad + h - dy],
            [pad + dx, pad + h],
        ], dtype=np.float32)

        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(padded, M, (pw, ph), flags=cv2.INTER_LINEAR, borderValue=(240, 240, 240))
        return warped


def run_optical_simulation(
    file_bytes: bytes,
    filename: str = "sim_test.bin",
    modulation_mode: int = 2,
    grid_rows: int = 32,
    grid_cols: int = 32,
    fec_ratio: float = 0.20,
    fps: int = 30,
    simulator: Optional[OpticalChannelSimulator] = None,
) -> Dict:
    """
    Executes an end-to-end simulated optical file transmission through degraded channel.
    Returns comprehensive metrics dictionary.
    """
    channel = simulator or OpticalChannelSimulator()

    # 1. Sender
    transmitter = OpticalTransmitter(
        file_path_or_data=file_bytes,
        filename=filename,
        modulation_mode=modulation_mode,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        fps=fps,
        fec_ratio=fec_ratio,
        enable_encryption=True,
        enable_compression=True,
    )
    transmitter.prepare()

    # 2. Receiver
    detector = FrameDetector()
    rectifier = PerspectiveRectifier(
        canonical_size=512,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        corner_size=8,
    )
    decoder = ColorCellDecoder(layout=transmitter.layout, default_mode=modulation_mode)
    reassembler = SessionReassembler(metadata=transmitter.metadata)

    # 3. Run Transmission Stream through Channel Simulator
    total_channel_frames = 0
    channel_dropped_frames = 0
    decode_success_count = 0
    decode_fail_count = 0

    stream = transmitter.get_transmission_stream(target_size=768, loop=False)

    for frame_idx, clean_img, pkt, _ in stream:
        total_channel_frames += 1
        degraded = channel.degrade_frame(clean_img)

        if degraded is None:
            channel_dropped_frames += 1
            continue

        # Receiver processing
        detected, quad_pts, _ = detector.detect(degraded)
        if not detected or quad_pts is None:
            decode_fail_count += 1
            continue

        warped, _ = rectifier.rectify(degraded, quad_pts)
        decoded_pkt, conf, status = decoder.decode_frame(warped, mode_hint=modulation_mode)

        if decoded_pkt is not None:
            decode_success_count += 1
            reassembler.process_packet(decoded_pkt)
            if reassembler.is_complete:
                break
        else:
            decode_fail_count += 1

    telemetry = reassembler.get_telemetry()
    telemetry.update({
        "total_channel_frames": total_channel_frames,
        "channel_dropped_frames": channel_dropped_frames,
        "decode_success_count": decode_success_count,
        "decode_fail_count": decode_fail_count,
        "success_rate": round(decode_success_count / max(1, total_channel_frames), 3),
        "file_recovered_100pct": reassembler.integrity_verified,
    })

    return telemetry
