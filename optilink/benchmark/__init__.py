"""OptiLink Benchmark Package."""

from .simulator import OpticalChannelSimulator, run_optical_simulation
from .metrics import (
    calculate_raw_bitrate,
    calculate_effective_bitrate,
    calculate_goodput_kbps,
    calculate_ber,
    calculate_per,
)
from .experiments import BenchmarkSuite

__all__ = [
    "OpticalChannelSimulator",
    "run_optical_simulation",
    "calculate_raw_bitrate",
    "calculate_effective_bitrate",
    "calculate_goodput_kbps",
    "calculate_ber",
    "calculate_per",
    "BenchmarkSuite",
]
