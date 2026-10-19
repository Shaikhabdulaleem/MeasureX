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


def _rotation(tilt_deg: float, yaw_deg: float) -> np.ndarray:
    t, y = np.radians(tilt_deg), np.radians(yaw_deg)
    rx = np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
    rz = np.array([[np.cos(y), -np.sin(y), 0], [np.sin(y), np.cos(y), 0], [0, 0, 1]])
    return rz @ rx


def make_object_and_support(
    l_mm: int, w_mm: int, h_mm: int, *, tilt_deg: float = 8.0, yaw_deg: float = 25.0
) -> tuple[np.ndarray, np.ndarray]:
    """``(object_points_m, support_points_m)``: a cuboid (top + 4 sides) and the
    dense floor slab it sits on, kept separate as the camera-only pipeline keeps
    them. Both rigidly rotated (tilt+yaw) and translated. Metres."""
    l, w, h = l_mm / 1000.0, w_mm / 1000.0, h_mm / 1000.0

    # Dense, large floor so it is the dominant plane (as a warehouse floor is,
    # relative to the shipment). See the plane-selection note in planes.py.
    gx = gy = np.linspace(-1.0, 1.0, 100)
    fx, fy = np.meshgrid(gx, gy)
    floor = np.stack([fx.ravel(), fy.ravel(), np.zeros(fx.size)], axis=-1)

    def axis(length: float) -> np.ndarray:
        return np.linspace(-length / 2.0, length / 2.0, max(2, round(length / 0.02) + 1))

    xs, ys = axis(l), axis(w)
    zs = np.linspace(0.0, h, max(2, round(h / 0.02) + 1))
    faces = []
    gx2, gy2 = np.meshgrid(xs, ys)
    faces.append(np.stack([gx2.ravel(), gy2.ravel(), np.full(gx2.size, h)], axis=-1))  # top
    gy3, gz3 = np.meshgrid(ys, zs)
    faces.append(np.stack([np.full(gy3.size, l / 2), gy3.ravel(), gz3.ravel()], axis=-1))
    faces.append(np.stack([np.full(gy3.size, -l / 2), gy3.ravel(), gz3.ravel()], axis=-1))
    gx4, gz4 = np.meshgrid(xs, zs)
    faces.append(np.stack([gx4.ravel(), np.full(gx4.size, w / 2), gz4.ravel()], axis=-1))
    faces.append(np.stack([gx4.ravel(), np.full(gx4.size, -w / 2), gz4.ravel()], axis=-1))

    rot, shift = _rotation(tilt_deg, yaw_deg).T, np.array([0.1, -0.2, 2.0])
    obj = np.concatenate(faces, axis=0) @ rot + shift
    support = floor @ rot + shift
    return obj, support


def make_box_on_floor(
    l_mm: int, w_mm: int, h_mm: int, *, tilt_deg: float = 8.0, yaw_deg: float = 25.0
) -> np.ndarray:
    """The combined cuboid+floor cloud (for pure plane/geometry primitive tests)."""
    obj, support = make_object_and_support(l_mm, w_mm, h_mm, tilt_deg=tilt_deg, yaw_deg=yaw_deg)
    return np.concatenate([support, obj], axis=0)


@pytest.fixture
def box_on_floor():
    return make_box_on_floor


@pytest.fixture
def object_and_support():
    return make_object_and_support
