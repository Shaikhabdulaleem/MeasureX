"""M9 metric camera geometry: pose validation/inversion, projection, rays, baseline."""

from __future__ import annotations

import numpy as np
import pytest

from measurex_vision.geometry.intrinsics import CameraIntrinsics
from measurex_vision.multiview import camera as cam


def _pose(eye, yaw=0.3, pitch=-0.2):
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    T = np.eye(4)
    T[:3, :3] = rz @ rx
    T[:3, 3] = eye
    return T


def test_validate_pose_accepts_rigid_and_rejects_bad():
    T = _pose([0.1, 0.2, 1.0])
    assert cam.validate_pose(T) is not None
    with pytest.raises(cam.InvalidPose):
        cam.validate_pose(np.eye(3))  # wrong shape
    bad = T.copy(); bad[3, :] = [0, 0, 1, 1]
    with pytest.raises(cam.InvalidPose):
        cam.validate_pose(bad)         # bad bottom row
    refl = T.copy(); refl[:3, 0] = -refl[:3, 0]  # det -1 reflection
    with pytest.raises(cam.InvalidPose):
        cam.validate_pose(refl)


def test_invert_pose_is_inverse_and_centre():
    T = _pose([0.5, -0.3, 2.0])
    np.testing.assert_allclose(cam.invert_pose(T) @ T, np.eye(4), atol=1e-12)
    np.testing.assert_allclose(cam.camera_center(T), [0.5, -0.3, 2.0])


def test_projection_matches_intrinsics_and_depth_sign():
    intr = CameraIntrinsics(fx=800, fy=800, cx=320, cy=240)
    T = _pose([0.0, 0.0, 2.0])
    P = cam.projection_matrix(intr, T)
    # A world point in front of the camera (along its forward axis), plus offsets.
    fwd, right, down = T[:3, 2], T[:3, 0], T[:3, 1]
    X = (cam.camera_center(T) + 1.2 * fwd + 0.1 * right - 0.05 * down)[None, :]
    px, depth = cam.project_world(P, X)
    assert depth[0] > 0
    o, d = cam.pixel_ray(intr, T, px[0, 0], px[0, 1])
    # The point lies on the ray from the camera centre.
    v = X[0] - o
    v /= np.linalg.norm(v)
    np.testing.assert_allclose(v, d, atol=1e-9)


def test_point_behind_camera_has_negative_depth():
    intr = CameraIntrinsics(fx=800, fy=800, cx=320, cy=240)
    T = _pose([0.0, 0.0, 2.0])
    P = cam.projection_matrix(intr, T)
    behind = cam.camera_center(T) - T[:3, 2] * 0.5  # step backwards along view axis
    _, depth = cam.project_world(P, behind[None, :])
    assert depth[0] < 0


def test_nearest_point_to_rays_recovers_intersection():
    target = np.array([0.3, -0.2, 1.5])
    origins = np.array([[2.0, 0.0, 1.5], [0.0, 2.0, 1.5], [-1.5, -1.5, 2.0]])
    dirs = target - origins
    got = cam.nearest_point_to_rays(origins, dirs)
    np.testing.assert_allclose(got, target, atol=1e-9)


def test_parallel_rays_are_degenerate():
    origins = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float)
    dirs = np.tile([0, 0, 1.0], (3, 1))
    with pytest.raises(np.linalg.LinAlgError):
        cam.nearest_point_to_rays(origins, dirs)


def test_baseline_and_view_angle():
    a = _pose([1.0, 0.0, 0.0])
    b = _pose([-1.0, 0.0, 0.0])
    assert cam.baseline(a, b) == pytest.approx(2.0)
    assert cam.view_angle(a, b, np.zeros(3)) == pytest.approx(180.0)
