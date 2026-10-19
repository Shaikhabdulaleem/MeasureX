"""M9 gravity-fixed carton geometry: footprint, height, cleanup."""

from __future__ import annotations

import numpy as np

from measurex_vision.multiview.carton import (
    carton_dimensions,
    horizontal_basis,
    largest_component,
    min_area_rect,
    up_from_gravity,
)


def test_horizontal_basis_orthonormal():
    up = np.array([0.1, -0.2, 0.97])
    up /= np.linalg.norm(up)
    e1, e2 = horizontal_basis(up)
    for v in (e1, e2):
        assert abs(np.linalg.norm(v) - 1) < 1e-9
        assert abs(v @ up) < 1e-9
    assert abs(e1 @ e2) < 1e-9


def test_min_area_rect_recovers_rotated_rectangle():
    a, b = 0.40, 0.25
    xs = np.linspace(-a / 2, a / 2, 40)
    ys = np.linspace(-b / 2, b / 2, 25)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel()], axis=-1)
    ang = np.radians(31.0)
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    long_m, short_m = min_area_rect(pts @ R.T + np.array([3.0, -2.0]))
    np.testing.assert_allclose([long_m, short_m], [a, b], atol=1e-6)


def test_largest_component_drops_outlier():
    voxel = 0.01
    xs = np.arange(0, 0.1, voxel)
    gx, gy, gz = np.meshgrid(xs, xs, xs)
    blob = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=-1)
    outlier = np.array([[5.0, 5.0, 5.0]])
    out = largest_component(np.vstack([blob, outlier]), voxel)
    assert out.shape[0] == blob.shape[0]


def test_carton_dimensions_on_solid_cuboid():
    step = 0.01
    L, W, H = 0.40, 0.30, 0.20
    xs = np.arange(-L / 2, L / 2 + step / 2, step)
    ys = np.arange(-W / 2, W / 2 + step / 2, step)
    zs = np.arange(0.0, H + step / 2, step)
    gx, gy, gz = np.meshgrid(xs, ys, zs)
    pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=-1)
    geo = carton_dimensions(pts, gravity_world=(0, 0, -1), voxel_m=step)
    assert abs(geo.dimensions.length_mm - 400) <= 12
    assert abs(geo.dimensions.width_mm - 300) <= 12
    assert abs(geo.dimensions.height_mm - 200) <= 12
    assert geo.dimensions.length_mm >= geo.dimensions.width_mm


def test_carton_height_uses_support_plane():
    step = 0.01
    xs = np.arange(-0.2, 0.2 + step / 2, step)
    zs = np.arange(0.0, 0.25 + step / 2, step)
    gx, gy, gz = np.meshgrid(xs, xs, zs)
    pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=-1)
    # Add a spurious low voxel below the plane; support clipping must ignore it.
    pts = np.vstack([pts, [[0.0, 0.0, -0.10]]])
    support = {"normal": [0, 0, 1], "offset": 0.0}
    geo = carton_dimensions(pts, gravity_world=(0, 0, -1), voxel_m=step, support_plane=support)
    assert abs(geo.dimensions.height_mm - 250) <= 10


def test_up_from_gravity():
    np.testing.assert_allclose(up_from_gravity([0, 2, 0]), [0, -1, 0])
