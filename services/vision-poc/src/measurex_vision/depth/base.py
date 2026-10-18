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
    # True when focal_px is derived from an assumed FOV rather than predicted by
    # the model (e.g. Depth Anything V2). The intrinsics resolver must not treat
    # such a focal as a trustworthy scale source — see geometry/intrinsics.py.
    focal_is_assumed: bool = False


class DepthEstimator(ABC):
    @abstractmethod
    def estimate(self, image: np.ndarray) -> DepthResult:
        """Return a metric depth map for an (H, W, 3) RGB image."""
