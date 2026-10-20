"""Metric multi-view camera geometry: world <-> camera, projection, rays, baselines.

**Coordinate convention (fixed everywhere in M9).** One pose convention only::

    X_world = T_world_from_camera @ X_camera        # 4x4 homogeneous, metres

``T_world_from_camera`` maps a point from the camera frame into the world frame.
The camera frame is the pinhole / OpenCV convention used by
``measurex_vision.geometry.intrinsics``: ``+X`` right, ``+Y`` down, ``+Z``
forward (into the scene). The camera centre in world coordinates is the
translation column ``T_world_from_camera[:3, 3]``.

Metric scale comes *only* from the translations in these poses (metres). No
monocular depth is involved anywhere in this module — that is what makes the
reconstruction metric rather than an estimate.
"""

from __future__ import annotations

import numpy as np

from ..geometry.intrinsics import CameraIntrinsics


class InvalidPose(ValueError):
    """A pose matrix is not a valid metric rigid transform."""


class InvalidIntrinsics(ValueError):
    """Camera intrinsics are missing, non-finite or non-physical."""


def k_matrix(intr: CameraIntrinsics) -> np.ndarray:
    """3x3 pinhole calibration matrix ``K`` for ``intr``."""
    return np.array(
        [[intr.fx, 0.0, intr.cx], [0.0, intr.fy, intr.cy], [0.0, 0.0, 1.0]], dtype=float
    )


def validate_intrinsics(intr: CameraIntrinsics, width: int, height: int) -> None:
    """Raise :class:`InvalidIntrinsics` unless fx/fy are finite and > 0 and the
    principal point is finite and plausibly inside the image."""
    vals = (intr.fx, intr.fy, intr.cx, intr.cy)
    if not all(np.isfinite(vals)):
        raise InvalidIntrinsics(f"non-finite intrinsics: {vals}")
    if intr.fx <= 0 or intr.fy <= 0:
        raise InvalidIntrinsics(f"fx/fy must be > 0, got fx={intr.fx}, fy={intr.fy}")
    # A principal point far outside the frame is almost always a units/convention
    # bug; allow a 20% margin for genuine cropped sensors.
    mx, my = 0.2 * width, 0.2 * height
    if not (-mx <= intr.cx <= width + mx and -my <= intr.cy <= height + my):
        raise InvalidIntrinsics(
            f"principal point ({intr.cx}, {intr.cy}) implausible for {width}x{height}"
        )


def validate_pose(T: np.ndarray, *, atol: float = 1e-3) -> np.ndarray:
    """Return ``T`` as a float ``(4, 4)`` array, or raise :class:`InvalidPose`.

    Checks the shape, finiteness, the homogeneous bottom row ``[0, 0, 0, 1]``, an
    orthonormal rotation block (``R Rᵀ ≈ I``) and a proper rotation
    (``det R ≈ +1``, i.e. no reflection). Translations must be finite metres."""
    T = np.asarray(T, dtype=float)
    if T.shape != (4, 4):
        raise InvalidPose(f"pose must be 4x4, got {T.shape}")
    if not np.all(np.isfinite(T)):
        raise InvalidPose("pose has non-finite entries")
    if not np.allclose(T[3, :], [0.0, 0.0, 0.0, 1.0], atol=atol):
        raise InvalidPose(f"pose bottom row must be [0,0,0,1], got {T[3, :]}")
    R = T[:3, :3]
    if not np.allclose(R @ R.T, np.eye(3), atol=atol):
        raise InvalidPose("rotation block is not orthonormal")
    det = float(np.linalg.det(R))
    if not np.isclose(det, 1.0, atol=max(atol, 1e-2)):
        raise InvalidPose(f"rotation determinant must be +1 (proper), got {det:.4f}")
    return T


def camera_center(T_world_from_camera: np.ndarray) -> np.ndarray:
    """World-frame camera centre ``(3,)`` — the pose translation column."""
    return np.asarray(T_world_from_camera, dtype=float)[:3, 3].copy()


def invert_pose(T_world_from_camera: np.ndarray) -> np.ndarray:
    """``T_camera_from_world`` — the inverse rigid transform.

    For a rigid ``[R|t]`` the inverse is ``[Rᵀ | -Rᵀ t]`` (never a numeric
    ``inv`` — exact and cheap)."""
    T = np.asarray(T_world_from_camera, dtype=float)
    R, t = T[:3, :3], T[:3, 3]
    out = np.eye(4)
    out[:3, :3] = R.T
    out[:3, 3] = -R.T @ t
    return out


def projection_matrix(intr: CameraIntrinsics, T_world_from_camera: np.ndarray) -> np.ndarray:
    """3x4 world->pixel projection ``P = K [R|t]_camera_from_world``."""
    return k_matrix(intr) @ invert_pose(T_world_from_camera)[:3, :4]


def project_world(P: np.ndarray, points_world: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project world points ``(N, 3)`` with a 3x4 matrix ``P``.

    Returns ``(pixels (N, 2), depth (N,))`` where ``depth`` is the camera-frame
    ``Z`` (the homogeneous scale): ``depth > 0`` means the point is in front of
    the camera. Pixels for points at/behind the camera are not meaningful and the
    caller must gate on ``depth``."""
    pts = np.asarray(points_world, dtype=float)
    homog = np.concatenate([pts, np.ones((pts.shape[0], 1))], axis=1)
    proj = homog @ P.T  # (N, 3): [u*w, v*w, w]
    depth = proj[:, 2]
    safe = np.where(np.abs(depth) < 1e-12, 1e-12, depth)
    pixels = proj[:, :2] / safe[:, None]
    return pixels, depth


def pixel_ray(
    intr: CameraIntrinsics, T_world_from_camera: np.ndarray, u: float, v: float
) -> tuple[np.ndarray, np.ndarray]:
    """World-frame ray ``(origin, unit_direction)`` through pixel ``(u, v)``."""
    T = np.asarray(T_world_from_camera, dtype=float)
    d_cam = np.array([(u - intr.cx) / intr.fx, (v - intr.cy) / intr.fy, 1.0])
    d_world = T[:3, :3] @ d_cam
    d_world /= np.linalg.norm(d_world)
    return camera_center(T), d_world


def baseline(T_a: np.ndarray, T_b: np.ndarray) -> float:
    """Metric distance (metres) between two camera centres."""
    return float(np.linalg.norm(camera_center(T_a) - camera_center(T_b)))


def view_angle(T_a: np.ndarray, T_b: np.ndarray, target_world: np.ndarray) -> float:
    """Angle in **degrees** subtended at ``target_world`` by two camera centres —
    the viewpoint-diversity measure (how far apart the two views see the object
    from)."""
    target = np.asarray(target_world, dtype=float)
    a = camera_center(T_a) - target
    b = camera_center(T_b) - target
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    cos = float(np.clip(a @ b / (na * nb), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def nearest_point_to_rays(origins: np.ndarray, directions: np.ndarray) -> np.ndarray:
    """Least-squares world point closest to a set of rays ``(N, 3)`` each.

    Minimises the sum of squared perpendicular distances to the lines; used to
    locate the object centroid from the central rays of several views. Requires
    directions spanning more than one direction (non-degenerate), else raises."""
    O = np.asarray(origins, dtype=float)
    D = np.asarray(directions, dtype=float)
    D = D / np.linalg.norm(D, axis=1, keepdims=True)
    eye = np.eye(3)
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for o, d in zip(O, D):
        proj = eye - np.outer(d, d)  # projects onto the plane perpendicular to d
        A += proj
        b += proj @ o
    if np.linalg.matrix_rank(A, tol=1e-6) < 3:
        raise np.linalg.LinAlgError("rays are degenerate (parallel) — no unique intersection")
    return np.linalg.solve(A, b)
