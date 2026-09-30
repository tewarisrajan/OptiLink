"""
OptiLink Receiver - Optical Frame & Fiducial Detector.

Detects the transmission pattern in live camera video using:
1. Primary: Sub-pixel ArUco fiducial corner detection (IDs 0, 1, 2, 3)
2. Secondary Fallback: High-contrast quadrilateral contour analysis
"""

from typing import Tuple, Optional, List, Dict
import cv2
import numpy as np


class FrameDetector:
    """Detects optical transmission frames in camera streams."""

    def __init__(self):
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.params = cv2.aruco.DetectorParameters()
        self.params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.params)

    def detect(self, frame: np.ndarray) -> Tuple[bool, Optional[np.ndarray], str]:
        """
        Detects 4 corner registration points [TL, TR, BR, BL].
        Returns: (detected: bool, quad_points: (4, 2) float32, detection_method: str)
        """
        # Primary strategy: ArUco fiducials (4 markers, with 3-marker extrapolation fallback)
        corners, ids, _ = self.detector.detectMarkers(frame)
        if ids is not None and len(ids) >= 3:
            id_map: Dict[int, np.ndarray] = {
                int(m_id): corners[i][0] for i, m_id in enumerate(ids.flatten())
            }
            if all(k in id_map for k in (0, 1, 2, 3)):
                tl = id_map[0][0]  # Marker 0 outer TL
                tr = id_map[1][1]  # Marker 1 outer TR
                br = id_map[2][2]  # Marker 2 outer BR
                bl = id_map[3][3]  # Marker 3 outer BL
                quad = np.array([tl, tr, br, bl], dtype=np.float32)
                return True, quad, "ARUCO_FIDUCIAL"

            # 3-marker geometric extrapolation if 1 corner marker is temporarily occluded
            if 0 in id_map and 1 in id_map and 3 in id_map:
                tl, tr, bl = id_map[0][0], id_map[1][1], id_map[3][3]
                br = tr + (bl - tl)
                return True, np.array([tl, tr, br, bl], dtype=np.float32), "ARUCO_FIDUCIAL_3PT"
            elif 0 in id_map and 1 in id_map and 2 in id_map:
                tl, tr, br = id_map[0][0], id_map[1][1], id_map[2][2]
                bl = tl + (br - tr)
                return True, np.array([tl, tr, br, bl], dtype=np.float32), "ARUCO_FIDUCIAL_3PT"
            elif 0 in id_map and 2 in id_map and 3 in id_map:
                tl, br, bl = id_map[0][0], id_map[2][2], id_map[3][3]
                tr = tl + (br - bl)
                return True, np.array([tl, tr, br, bl], dtype=np.float32), "ARUCO_FIDUCIAL_3PT"
            elif 1 in id_map and 2 in id_map and 3 in id_map:
                tr, br, bl = id_map[1][1], id_map[2][2], id_map[3][3]
                tl = tr + (bl - br)
                return True, np.array([tl, tr, br, bl], dtype=np.float32), "ARUCO_FIDUCIAL_3PT"

        # Secondary strategy: Quadrilateral contour detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = frame.shape[0] * frame.shape[1]

        best_quad = None
        max_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < frame_area * 0.05:  # Require at least 5% of screen
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)

            if len(approx) == 4 and cv2.isContourConvex(approx):
                if area > max_area:
                    max_area = area
                    best_quad = approx.reshape(4, 2)

        if best_quad is not None:
            ordered_quad = self._order_points_clockwise(best_quad)
            return True, ordered_quad, "CONTOUR_QUAD"

        return False, None, "NONE"

    @staticmethod
    def _order_points_clockwise(pts: np.ndarray) -> np.ndarray:
        """Orders 4 points in clockwise order: [top-left, top-right, bottom-right, bottom-left]."""
        pts = pts.astype(np.float32)
        # Sum of coords: top-left has smallest x+y, bottom-right has largest x+y
        s = pts.sum(axis=1)
        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]

        # Difference of coords (y - x): top-right has smallest diff, bottom-left has largest diff
        diff = np.diff(pts, axis=1)
        tr = pts[np.argmin(diff)]
        bl = pts[np.argmax(diff)]

        return np.array([tl, tr, br, bl], dtype=np.float32)

    def draw_overlay(self, frame: np.ndarray, detected: bool, quad_pts: Optional[np.ndarray], status_text: str = "") -> np.ndarray:
        """Draws visual tracking box and telemetry overlay on camera frame."""
        vis = frame.copy()
        if detected and quad_pts is not None:
            pts_int = quad_pts.astype(np.int32)
            cv2.polylines(vis, [pts_int], isClosed=True, color=(0, 255, 0), thickness=3)

            labels = ["TL", "TR", "BR", "BL"]
            colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 255, 255)]
            for pt, label, col in zip(pts_int, labels, colors):
                cv2.circle(vis, tuple(pt), 6, col, -1)
                cv2.putText(vis, label, (pt[0] + 8, pt[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

            msg = f"SIGNAL LOCKED [{status_text}]"
            cv2.putText(vis, msg, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(vis, "SEARCHING FOR OPTILINK SIGNAL...", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

        return vis
