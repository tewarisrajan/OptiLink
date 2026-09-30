"""
OptiLink Optical - Color Palettes and Color Space Transformations.

Defines optimal color spaces for screen-to-camera transmission:
- Mode 1: Binary (Black / White)
- Mode 2: 4-Color (Black, Red, Green, Blue)
- Mode 3: 8-Color (Vertices of RGB Color Cube)
"""

from typing import List, Tuple, Dict
import numpy as np


# Fundamental Reference Colors
COLOR_NAMES = ["black", "blue", "green", "cyan", "red", "magenta", "yellow", "white"]

RGB_BLACK   = (0, 0, 0)
RGB_WHITE   = (255, 255, 255)
RGB_RED     = (255, 0, 0)
RGB_GREEN   = (0, 255, 0)
RGB_BLUE    = (0, 0, 255)
RGB_CYAN    = (0, 255, 255)
RGB_MAGENTA = (255, 0, 255)
RGB_YELLOW  = (255, 255, 0)

RGB_BY_NAME: Dict[str, Tuple[int, int, int]] = {
    "black":   RGB_BLACK,
    "blue":    RGB_BLUE,
    "green":   RGB_GREEN,
    "cyan":    RGB_CYAN,
    "red":     RGB_RED,
    "magenta": RGB_MAGENTA,
    "yellow":  RGB_YELLOW,
    "white":   RGB_WHITE,
}

# The calibration strip displays all 8 reference colors in this deterministic order:
CALIBRATION_PALETTE_NAMES: List[str] = [
    "black", "blue", "green", "cyan", "red", "magenta", "yellow", "white"
]
CALIBRATION_PALETTE_RGB: List[Tuple[int, int, int]] = [
    RGB_BY_NAME[name] for name in CALIBRATION_PALETTE_NAMES
]

# Mode-to-color mappings:
MODE_COLOR_NAMES: Dict[int, List[str]] = {
    1: ["black", "white"],                           # Mode 1: Binary (1 bit)
    2: ["black", "red", "green", "blue"],            # Mode 2: 4-Color (2 bits)
    3: CALIBRATION_PALETTE_NAMES,                    # Mode 3: 8-Color (3 bits)
    4: ["black", "red", "green", "blue"],            # Mode 4: Adaptive (starts at 4-color)
}

PALETTE_BINARY_RGB: List[Tuple[int, int, int]] = [RGB_BY_NAME[n] for n in MODE_COLOR_NAMES[1]]
PALETTE_4COLOR_RGB: List[Tuple[int, int, int]] = [RGB_BY_NAME[n] for n in MODE_COLOR_NAMES[2]]
PALETTE_8COLOR_RGB: List[Tuple[int, int, int]] = [RGB_BY_NAME[n] for n in MODE_COLOR_NAMES[3]]


def rgb_to_bgr(rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return (rgb[2], rgb[1], rgb[0])


def bgr_to_rgb(bgr: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return (bgr[2], bgr[1], bgr[0])


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def get_palette_rgb(mode: int) -> List[Tuple[int, int, int]]:
    names = MODE_COLOR_NAMES.get(mode, MODE_COLOR_NAMES[2])
    return [RGB_BY_NAME[n] for n in names]


def get_bits_per_cell(mode: int) -> int:
    if mode == 1:
        return 1
    elif mode == 2:
        return 2
    elif mode == 3:
        return 3
    elif mode == 4:
        return 2
    else:
        raise ValueError(f"Unknown modulation mode: {mode}")
