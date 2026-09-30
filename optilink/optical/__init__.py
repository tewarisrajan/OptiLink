"""OptiLink Optical Package."""

from .colors import (
    RGB_BLACK,
    RGB_WHITE,
    RGB_RED,
    RGB_GREEN,
    RGB_BLUE,
    RGB_CYAN,
    RGB_MAGENTA,
    RGB_YELLOW,
    PALETTE_BINARY_RGB,
    PALETTE_4COLOR_RGB,
    PALETTE_8COLOR_RGB,
    CALIBRATION_PALETTE_RGB,
    get_palette_rgb,
    get_bits_per_cell,
    rgb_to_bgr,
    bgr_to_rgb,
    rgb_to_hex,
)
from .modulation import bytes_to_symbols, symbols_to_bytes
from .frame_layout import FrameLayout
from .calibration import ColorCalibrator
from .frame_generator import FrameGenerator

__all__ = [
    "RGB_BLACK",
    "RGB_WHITE",
    "RGB_RED",
    "RGB_GREEN",
    "RGB_BLUE",
    "RGB_CYAN",
    "RGB_MAGENTA",
    "RGB_YELLOW",
    "PALETTE_BINARY_RGB",
    "PALETTE_4COLOR_RGB",
    "PALETTE_8COLOR_RGB",
    "CALIBRATION_PALETTE_RGB",
    "get_palette_rgb",
    "get_bits_per_cell",
    "rgb_to_bgr",
    "bgr_to_rgb",
    "rgb_to_hex",
    "bytes_to_symbols",
    "symbols_to_bytes",
    "FrameLayout",
    "ColorCalibrator",
    "FrameGenerator",
]
