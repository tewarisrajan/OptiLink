"""
OptiLink Receiver - Video Stream & Hardware Camera Capture.

Interfaces with USB webcams, phone cameras via RTSP/HTTP, or video feeds.
"""

from typing import Tuple, Optional
import cv2
import numpy as np


class CameraCapture:
    """Manages OpenCV camera device capture."""

    def __init__(self, device_index: int = 0, target_width: int = 1280, target_height: int = 720, target_fps: int = 30):
        self.device_index = device_index
        self.target_width = target_width
        self.target_height = target_height
        self.target_fps = target_fps
        self.cap: Optional[cv2.VideoCapture] = None

    def open(self) -> bool:
        """Opens video capture device."""
        self.cap = cv2.VideoCapture(self.device_index)
        if not self.cap.isOpened():
            return False

        # Configure hardware resolution and FPS
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
        self.cap.set(cv2.CAP_PROP_FPS, self.target_fps)
        return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Reads a single camera frame."""
        if not self.cap or not self.cap.isOpened():
            return False, None
        return self.cap.read()

    def get_actual_properties(self) -> dict:
        """Returns actual hardware camera properties."""
        if not self.cap or not self.cap.isOpened():
            return {"connected": False}
        return {
            "connected": True,
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(self.cap.get(cv2.CAP_PROP_FPS)),
        }

    def close(self):
        """Releases camera resource."""
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None
