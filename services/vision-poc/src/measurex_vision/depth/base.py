"""DepthEstimator provider interface — monocular metric depth.

Primary implementation (Depth Pro) lands in a later milestone. Geometry code
depends only on this interface so alternative depth models can be benchmarked
without change (VISION_ENGINE_POC.md §4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DepthResult:
    depth_m: np.ndarray  # (H, W) metres; <=0 / NaN mark invalid pixels
    focal_px: float      # estimated focal length in pixels
    valid_ratio: float   # fraction of pixels with usable depth
    version: str         # model/checkpoint identifier


class DepthEstimator(ABC):
    @abstractmethod
    def estimate(self, image: np.ndarray) -> DepthResult:
        """Return a metric depth map for an (H, W, 3) RGB image."""
