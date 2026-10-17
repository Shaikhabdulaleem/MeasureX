"""GeometryEstimator provider interface — clean point cloud -> Dimensions.

The pure functions in this package implement the baseline; a provider wrapper
(e.g. Open3D-backed minimum-volume OBB) can be swapped in behind this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..contracts import Dimensions


class GeometryEstimator(ABC):
    @abstractmethod
    def extract(self, points_m: np.ndarray, up: tuple[float, float, float] = (0.0, 0.0, 1.0)) -> Dimensions:
        """Fit a box to an (N, 3) metre point cloud and return L/W/H in mm."""
