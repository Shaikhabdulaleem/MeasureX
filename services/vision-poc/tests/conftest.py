"""Shared test fixtures.

A MockDepthEstimator lets us exercise the depth → artifacts path without torch,
a GPU, or any downloaded weights.
"""

from __future__ import annotations

import numpy as np
import pytest

from measurex_vision.depth.base import DepthEstimator, DepthResult


class MockDepthEstimator(DepthEstimator):
    def __init__(self, focal_px: float = 1000.0, version: str = "mock") -> None:
        self.focal_px = focal_px
        self.version = version

    def estimate(self, image: np.ndarray) -> DepthResult:
        h, w = image.shape[:2]
        # A smooth 1.0..3.0 m gradient — a plausible, deterministic depth map.
        depth = np.linspace(1.0, 3.0, h * w, dtype=float).reshape(h, w)
        valid = np.isfinite(depth) & (depth > 0)
        return DepthResult(
            depth_m=depth,
            focal_px=self.focal_px,
            valid_ratio=float(valid.mean()),
            version=self.version,
        )


@pytest.fixture
def mock_estimator() -> MockDepthEstimator:
    return MockDepthEstimator()


@pytest.fixture
def sample_image() -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(8, 12, 3), dtype=np.uint8)
