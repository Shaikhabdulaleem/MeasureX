"""Analytic synthetic capture sequences for the M9 proof and unit tests.

A cuboid of known size is placed in the world; cameras are posed on an arc around
it with known metric poses and intrinsics. For a convex solid the image silhouette
is exactly the convex hull of the projected vertices, so masks are generated
analytically (no renderer, no model). This lets the visual hull be validated
against exact ground truth before any phone capture.
"""

from __future__ import annotations

import numpy as np

from ..geometry.intrinsics import CameraIntrinsics
from . import camera as cam
from .carton import _convex_hull_2d, horizontal_basis, up_from_gravity
from .schema import CaptureBundle, ViewFrame


def look_at_pose(eye: np.ndarray, target: np.ndarray, up_world: np.ndarray) -> np.ndarray:
    """``T_world_from_camera`` for a camera at ``eye`` looking at ``target``.

    OpenCV camera frame (+X right, +Y down, +Z forward). The pose columns are the
    camera axes expressed in world coordinates."""
    eye = np.asarray(eye, dtype=float)
    z = target - eye
    z /= np.linalg.norm(z)
    x = np.cross(up_world, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    T = np.eye(4)
    T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = x, y, z, eye
    return T


def fill_convex_polygon(verts_px: np.ndarray, width: int, height: int) -> np.ndarray:
    """Rasterise the filled convex polygon (CCW vertices) to an ``(H, W)`` bool mask."""
    hull = _convex_hull_2d(verts_px)
    if hull.shape[0] < 3:
        return np.zeros((height, width), dtype=bool)
    x0 = max(int(np.floor(hull[:, 0].min())), 0)
    x1 = min(int(np.ceil(hull[:, 0].max())), width - 1)
    y0 = max(int(np.floor(hull[:, 1].min())), 0)
    y1 = min(int(np.ceil(hull[:, 1].max())), height - 1)
    mask = np.zeros((height, width), dtype=bool)
    if x1 < x0 or y1 < y0:
        return mask
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
    inside = np.ones(xs.shape, dtype=bool)
    n = hull.shape[0]
    for i in range(n):
        a = hull[i]
        b = hull[(i + 1) % n]
        # CCW polygon: inside points are to the left of every edge (cross >= 0).
        cross = (b[0] - a[0]) * (ys - a[1]) - (b[1] - a[1]) * (xs - a[0])
        inside &= cross >= -1e-6
    mask[y0 : y1 + 1, x0 : x1 + 1] = inside
    return mask


def _small_rotation(seed: int, deg: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    axis = rng.standard_normal(3)
    axis /= np.linalg.norm(axis)
    ang = np.radians(deg) * rng.standard_normal()
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * (k @ k)


def synthetic_capture(
    *,
    length_m: float,
    width_m: float,
    height_m: float,
    n_views: int = 16,
    distance_m: float = 1.5,
    azimuth_span_deg: float = 330.0,
    # A near-horizontal ring caps the top tightly; higher rings bound the sides and
    # footprint. Fewer/higher rings leave a pyramidal over-reconstruction above the
    # top face (no camera sees straight down). Coverage choice, not a GT fit.
    elevations_deg: tuple[float, ...] = (8.0, 35.0, 60.0),
    continuous_sweep: bool = False,
    image_wh: tuple[int, int] = (960, 1280),
    fx: float = 1004.5988,
    fy: float | None = None,
    world_origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    yaw_deg: float = 0.0,
    gravity_world: tuple[float, float, float] = (0.0, 1.0, 0.0),
    scale: float = 1.0,
    pose_noise_deg: float = 0.0,
    # Realistic trajectory variation (Phase T). The poses stay KNOWN EXACTLY — these
    # only make the ideal arc less ideal, so the fitter must consume the real poses
    # instead of assuming a smooth centred orbit. All default to 0 (the ideal arc).
    distance_jitter_frac: float = 0.0,   # radial distance ±frac (non-constant range)
    elevation_jitter_deg: float = 0.0,   # per-frame elevation wobble
    azimuth_jitter_deg: float = 0.0,     # non-uniform azimuth spacing
    lateral_jitter_m: float = 0.0,       # sideways/path jitter of the eye (metres)
    aim_jitter_m: float = 0.0,           # look-at target offset from the object centre
    seed: int = 0,
) -> tuple[CaptureBundle, dict]:
    """Build an in-memory synthetic capture bundle and its ground-truth dims.

    ``scale`` multiplies every metric quantity (box, distance, origin) so the
    scene and the camera translations scale together — the masks are unchanged and
    the recovered dimensions must scale by the same factor (metric-scale proof).

    ``continuous_sweep`` models one practical hand-held pass instead of full
    elevation rings: ``n_views`` are laid along the azimuth span with the elevation
    ramping linearly between ``elevations_deg[0]`` and ``elevations_deg[-1]`` (a
    modest natural tilt through the sweep), not the Cartesian product of rings."""
    w, h = image_wh
    fy = fy if fy is not None else fx
    intr = CameraIntrinsics(fx=fx, fy=fy, cx=w / 2.0, cy=h / 2.0)
    gravity = np.asarray(gravity_world, dtype=float)
    up = up_from_gravity(gravity)

    L, W, H = length_m * scale, width_m * scale, height_m * scale
    dist = distance_m * scale
    origin = np.asarray(world_origin, dtype=float) * scale

    a0, b0 = horizontal_basis(up)
    yaw = np.radians(yaw_deg)
    a = np.cos(yaw) * a0 + np.sin(yaw) * b0
    b = -np.sin(yaw) * a0 + np.cos(yaw) * b0

    centre = origin + up * (H / 2.0)
    corners = np.array(
        [centre + sx * (L / 2) * a + sy * (W / 2) * b + sz * (H / 2) * up
         for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    )

    frames: list[ViewFrame] = []
    # endpoint=False avoids a duplicate view when the azimuth span is a full ring.
    full_ring = azimuth_span_deg >= 359.0
    azimuths = np.linspace(
        -azimuth_span_deg / 2, azimuth_span_deg / 2, n_views, endpoint=not full_ring
    )
    if continuous_sweep:
        ramp = np.linspace(elevations_deg[0], elevations_deg[-1], n_views)
        view_angles = list(zip(ramp.tolist(), azimuths.tolist(), strict=True))
    else:
        view_angles = [(e, a) for e in elevations_deg for a in azimuths]
    traj_rng = np.random.default_rng(seed + 777)
    for i, (elevation_deg, az_deg) in enumerate(view_angles):
        elev = np.radians(elevation_deg + elevation_jitter_deg * traj_rng.standard_normal())
        az = np.radians(az_deg + azimuth_jitter_deg * traj_rng.standard_normal())
        horiz = np.cos(az) * a0 + np.sin(az) * b0
        direction = np.cos(elev) * horiz + np.sin(elev) * up
        dist_i = dist * (1.0 + distance_jitter_frac * traj_rng.standard_normal())
        eye = centre + dist_i * direction
        if lateral_jitter_m > 0:
            # offset the eye within the plane perpendicular to the view direction
            side = np.cross(direction, up)
            side /= max(np.linalg.norm(side), 1e-9)
            eye = eye + lateral_jitter_m * scale * (traj_rng.standard_normal() * side
                                                    + traj_rng.standard_normal() * up)
        target = centre + (aim_jitter_m * scale * traj_rng.standard_normal(3) if aim_jitter_m > 0 else 0.0)
        T = look_at_pose(eye, target, up)
        if pose_noise_deg > 0:
            T[:3, :3] = _small_rotation(seed + i, pose_noise_deg) @ T[:3, :3]
        P = cam.projection_matrix(intr, T)
        px, _ = cam.project_world(P, corners)
        mask = fill_convex_polygon(px, w, h)
        frames.append(ViewFrame(frame_id=f"{i:06d}", mask=mask, intrinsics=intr, T_world_from_camera=T))

    gt = {
        "length_mm": round(max(L, W) * 1000),
        "width_mm": round(min(L, W) * 1000),
        "height_mm": round(H * 1000),
    }
    # The carton rests on the ground through ``origin``; expose it as the metric
    # support plane (normal = up). Scale-invariant: origin scales with the scene.
    support = {"normal": [float(x) for x in up], "offset": float(-(up @ origin))}
    bundle = CaptureBundle(
        frames=frames, gravity_world=gravity, pose_source="synthetic", support_plane=support
    )
    return bundle, gt


def save_bundle(bundle: CaptureBundle, out_dir: str) -> str:
    """Write a capture bundle to ``out_dir`` as ``capture.json`` + mask PNGs.
    Returns the manifest path. Used for CLI demos and the dataset tooling."""
    import json
    import os

    from PIL import Image

    os.makedirs(os.path.join(out_dir, "masks"), exist_ok=True)
    doc_frames = []
    for f in bundle.frames:
        rel = f"masks/{f.frame_id}.png"
        Image.fromarray((f.mask * 255).astype(np.uint8)).save(os.path.join(out_dir, rel))
        doc_frames.append({
            "frame_id": f.frame_id,
            "image": rel,  # masks double as the only image in synthetic bundles
            "mask": rel,
            "intrinsics": {
                "fx": f.intrinsics.fx, "fy": f.intrinsics.fy,
                "cx": f.intrinsics.cx, "cy": f.intrinsics.cy,
                "width": f.width, "height": f.height,
            },
            "T_world_from_camera": f.T_world_from_camera.tolist(),
        })
    doc = {
        "schema_version": 1,
        "measurement_tier": "metric",
        "pose_source": bundle.pose_source,
        "pose_convention": "T_world_from_camera",
        "units": "meters",
        "gravity_world": [float(x) for x in bundle.gravity_world],
        "frames": doc_frames,
    }
    if bundle.support_plane is not None:
        doc["support_plane"] = bundle.support_plane
    path = os.path.join(out_dir, "capture.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return path
