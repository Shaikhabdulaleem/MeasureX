"""P0 synthetic point-cloud tests.

Build cuboids of known size, apply arbitrary rotation + translation, and verify
the pure geometry layer recovers the original L/W/H. No camera, depth, or model
inference involved — this proves the math before any real image is trusted.
"""

from __future__ import annotations

import numpy as np
import pytest

from measurex_vision.contracts import Dimensions
from measurex_vision.geometry import (
    CameraIntrinsics,
    backproject,
    extract_dimensions,
    normalize_axes_to_lwh,
    oriented_box,
)

# (length_mm, width_mm, height_mm) ground truth. Distinct edges per box (PCA OBB
# is rotationally degenerate for equal edges — see oriented_box docstring).
BOXES_MM = [
    (400, 300, 200),
    (600, 400, 350),
    (1200, 800, 600),
]


def cuboid_surface_points(l_m: float, w_m: float, h_m: float, step: float = 0.02) -> np.ndarray:
    """Dense points on the 6 faces of an axis-aligned box centred at the origin.

    linspace includes the endpoints, so the true edge extents are present exactly.
    """

    def axis(length: float) -> np.ndarray:
        n = max(2, round(length / step) + 1)
        return np.linspace(-length / 2.0, length / 2.0, n)

    xs, ys, zs = axis(l_m), axis(w_m), axis(h_m)
    faces = []
    for const, (a, b, which) in [
        (l_m / 2.0, (ys, zs, "x")),
        (-l_m / 2.0, (ys, zs, "x")),
        (w_m / 2.0, (xs, zs, "y")),
        (-w_m / 2.0, (xs, zs, "y")),
        (h_m / 2.0, (xs, ys, "z")),
        (-h_m / 2.0, (xs, ys, "z")),
    ]:
        g1, g2 = np.meshgrid(a, b, indexing="ij")
        g1 = g1.ravel()
        g2 = g2.ravel()
        c = np.full_like(g1, const)
        if which == "x":
            faces.append(np.stack([c, g1, g2], axis=-1))
        elif which == "y":
            faces.append(np.stack([g1, c, g2], axis=-1))
        else:
            faces.append(np.stack([g1, g2, c], axis=-1))
    return np.concatenate(faces, axis=0)


def random_rotation(seed: int) -> np.ndarray:
    """A random proper rotation matrix (det = +1) via QR of a Gaussian matrix."""
    rng = np.random.default_rng(seed)
    q, r = np.linalg.qr(rng.standard_normal((3, 3)))
    q = q @ np.diag(np.sign(np.diag(r)))  # fix QR sign ambiguity
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


def yaw_rotation(angle_rad: float) -> np.ndarray:
    """Rotation about the vertical (+Z) axis — keeps height vertical."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


@pytest.mark.parametrize("box_mm", BOXES_MM)
def test_sorted_extents_recovered_under_arbitrary_rotation(box_mm):
    l_m, w_m, h_m = (v / 1000.0 for v in box_mm)
    points = cuboid_surface_points(l_m, w_m, h_m)
    for seed in range(5):
        rot = random_rotation(seed)
        translation = np.array([1.3, -0.7, 4.2])
        transformed = points @ rot.T + translation

        box = oriented_box(transformed)
        recovered = np.sort(box.extents)[::-1] * 1000.0  # mm, descending
        expected = np.sort(np.array(box_mm, dtype=float))[::-1]
        # ~0.5 mm tolerance: endpoints are exact, so only float noise remains.
        np.testing.assert_allclose(recovered, expected, atol=0.5)


@pytest.mark.parametrize("box_mm", BOXES_MM)
def test_lwh_assignment_under_yaw(box_mm):
    length_mm, width_mm, height_mm = box_mm
    # Ground-truth geometry: longest horizontal, shorter horizontal, vertical.
    l_m, w_m, h_m = length_mm / 1000.0, width_mm / 1000.0, height_mm / 1000.0
    points = cuboid_surface_points(l_m, w_m, h_m)
    for angle in (0.0, 0.5, 1.2, 2.9):
        transformed = points @ yaw_rotation(angle).T + np.array([2.0, 3.0, 1.0])
        dims = extract_dimensions(transformed, up=(0.0, 0.0, 1.0))
        assert isinstance(dims, Dimensions)
        assert dims.length_mm == length_mm
        assert dims.width_mm == width_mm
        assert dims.height_mm == height_mm
        assert dims.length_mm >= dims.width_mm  # orientation invariant


def test_normalize_axes_picks_vertical_as_height():
    extents = np.array([0.4, 0.3, 0.2])
    axes = np.eye(3)  # columns = x, y, z
    length, width, height = normalize_axes_to_lwh(extents, axes, up=(0.0, 0.0, 1.0))
    assert (length, width, height) == (0.4, 0.3, 0.2)
    # If y is "up", height should be the y-extent (0.3), length/width from x,z.
    length2, width2, height2 = normalize_axes_to_lwh(extents, axes, up=(0.0, 1.0, 0.0))
    assert height2 == 0.3
    assert (length2, width2) == (0.4, 0.2)


def test_backprojection_roundtrip():
    intr = CameraIntrinsics.from_focal(focal_px=1000.0, width=1920, height=1080)
    pts = np.array([[0.1, -0.2, 2.0], [-0.5, 0.3, 1.5], [0.0, 0.0, 3.0]])
    pixels = intr.project(pts)
    back = backproject(pixels[:, 0], pixels[:, 1], pts[:, 2], intr)
    np.testing.assert_allclose(back, pts, atol=1e-9)
