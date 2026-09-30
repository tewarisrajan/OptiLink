"""
OptiLink Receiver - Perspective Rectification & Homography.

Warps distorted, tilted, or rotated camera frames into a canonical normalized grid.
"""

from typing import Tuple, Optional
import cv2
import numpy as np


class PerspectiveRectifier:
    """Calculates perspective homography and rectifies camera captures."""

    def __init__(self, canonical_size: int = 512, grid_rows: int = 32, grid_cols: int = 32, corner_size: int = 8):
        self.canonical_size = canonical_size
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.corner_size = corner_size
        self._update_destination_points()

    def update_grid(self, grid_rows: int, grid_cols: int, corner_size: int = 8):
        self.grid_rows = grid_rows
        self.grid_cols = grid_cols
        self.corner_size = corner_size
        self._update_destination_points()

    def _update_destination_points(self):
        """
        Computes canonical destination coordinates corresponding to the 4 ArUco outer corners.
        Marker 0 (TL): starts at (0, 0), marker inside is at offset (1, 1).
        Marker 1 (TR): starts at (0, cols-8), marker right edge is at col (cols - 1).
        Marker 2 (BR): bottom-right corner is at (cols - 1, rows - 1).
        Marker 3 (BL): bottom-left corner is at (1, rows - 1).
        """
        cell_px = self.canonical_size / self.grid_rows
        c_right = (self.grid_cols - 1) * cell_px
        r_bottom = (self.grid_rows - 1) * cell_px
        c_left = 1 * cell_px
        r_top = 1 * cell_px

        self.dst_pts = np.array([
            [c_left, r_top],      # Marker 0 (TL)
            [c_right, r_top],     # Marker 1 (TR)
            [c_right, r_bottom],  # Marker 2 (BR)
            [c_left, r_bottom],   # Marker 3 (BL)
        ], dtype=np.float32)

        # Full outer boundary for contour detection
        self.dst_pts_full = np.array([
            [0.0, 0.0],
            [float(self.canonical_size - 1), 0.0],
            [float(self.canonical_size - 1), float(self.canonical_size - 1)],
            [0.0, float(self.canonical_size - 1)],
        ], dtype=np.float32)

    def rectify(self, frame: np.ndarray, src_quad_pts: np.ndarray, method: str = "ARUCO_FIDUCIAL") -> Tuple[np.ndarray, np.ndarray]:
        """
        Warps the detected quad into canonical normalized size.
        src_quad_pts must be a 4x2 array of points ordered [TL, TR, BR, BL].
        Returns: (rectified_frame, homography_matrix)
        """
        src_pts = np.asarray(src_quad_pts, dtype=np.float32)
        dst = self.dst_pts_full if method == "CONTOUR_QUAD" else self.dst_pts
        M = cv2.getPerspectiveTransform(src_pts, dst)
        warped = cv2.warpPerspective(
            frame,
            M,
            (self.canonical_size, self.canonical_size),
            flags=cv2.INTER_LINEAR,
        )
        return warped, M
