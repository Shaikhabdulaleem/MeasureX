"""Parametric gravity-aligned cuboid fit to multi-view silhouettes (M9 Phase B–P).

MeasureX measures **boxes**, not arbitrary solids. A generic visual hull is the
*largest* solid consistent with the silhouettes, so a sparse/narrow capture leaves
it loose exactly where no silhouette cuts it (the short-sweep length over-estimate,
see ``docs/M9_MULTIVIEW_METRIC_SPIKE.md``). This module replaces the free-form hull
hypothesis with a cuboid prior: given **known metric camera poses**, gravity, and
object masks, fit the few parameters of a gravity-aligned box so its projected
silhouette agrees with every mask.

**Degrees of freedom.** Gravity fixes roll and pitch (the box stands upright), so a
general 9-DOF oriented cuboid (translation 3 + rotation 3 + dimensions 3) collapses:

* no support plane — centre (3) + yaw (1) + L/W/H (3) = **7 DOF**;
* bottom face on a known metric support plane — horizontal centre (2) + yaw (1) +
  L/W/H (3) = **6 DOF** (the preferred warehouse configuration).

**Metric scale comes only from the camera-pose translations (metres)** — never from
the support plane (which supplies orientation + one vertical datum, not a scale) and
never from monocular depth. Ground-truth dimensions are used *nowhere* — not as a
bound, prior, initialisation or threshold.

The visual hull is kept as the diagnostic baseline/comparison method; this module
does not replace or delete it.
"""

from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..geometry.dimensions import metres_to_dimensions
from . import camera as cam
from .carton import _convex_hull_2d, horizontal_basis, up_from_gravity
from .quality import observability_metrics
from .schema import (
    CaptureBundle,
    FailureCode,
    MetricReconstructionError,
    ReconstructionConfig,
    ViewFrame,
    validate_bundle,
)
from .synthetic import fill_convex_polygon
from .visual_hull import estimate_roi


@dataclass(frozen=True)
class CuboidFitConfig:
    """Explicit, GT-free cuboid-fit parameters.

    Every threshold is expressed in image space (silhouette agreement) or as a
    relative spread — never fit to a particular test carton. Scale/centre bounds
    come from capture geometry (the mask solid-angle ROI), not a known box size."""

    # Objective weights — silhouette IoU is the main evidence; the centroid and
    # boundary terms are small geometric regularisers (see _loss).
    centroid_weight: float = 0.25
    boundary_weight: float = 0.25
    # Deterministic bounded optimiser (pure-NumPy pattern search, multi-start).
    yaw_starts_deg: tuple[float, ...] = (0.0, 30.0, 60.0)  # [0,90) covers the L/W symmetry
    scale_starts: tuple[float, ...] = (1.0,)  # × ROI half-extent as initial L=W=H
    max_iter: int = 120                # enough sweeps for the step to shrink to min_step
    step_shrink: float = 0.5
    min_step_frac: float = 1e-3        # stop when every step < this × ROI half-extent
    require_convergence: bool = True   # fail cuboid_fit_failed if the best start only
    # stopped because it hit max_iter (never shrank below min_step) — an unconverged
    # optimiser is not a trustworthy metric result.
    min_dim_m: float = 0.02            # lower dimension bound (operational safety)
    max_dim_roi_mult: float = 4.0      # upper dimension bound = mult × ROI half-extent
    # Silhouette-consistency gate (image space). Provisional floors — the box must
    # explain most of each silhouette's overlap; real-mask capture will calibrate
    # them. Not derived from any carton's GT dimensions.
    min_mean_iou: float = 0.88
    min_min_iou: float = 0.75
    max_boundary_frac: float = 0.05    # boundary residual as a fraction of image diagonal
    # Identifiability: every fitted DOF is perturbed around the optimum and must
    # raise the loss by at least ``min_identifiability`` — otherwise that parameter
    # is not observable (a flat objective direction) and the metric result is
    # refused. Perturbations are parameter-appropriate: dimensions relative, the
    # horizontal/vertical centre metric (a fraction of the object scale), yaw
    # angular.
    identifiability_rel: float = 0.15             # relative, for L/W/H
    identifiability_centre_frac: float = 0.15     # × mean object dimension, for the centre
    identifiability_yaw_deg: float = 10.0         # angular, for yaw
    min_identifiability: float = 0.02
    lw_square_tol: float = 0.05        # |L-W|/max(L,W) below this → yaw is exempt from
    # the gate (a square footprint's yaw is genuinely unobservable but harmless: the
    # L/W + 90° symmetry means it does not change the measured dimensions).
    # Leave-one-out stability (relative L/W/H spread when dropping one frame). Each
    # LOO run rebuilds the locus/ROI/frame from the SUBSET so the omitted frame
    # contributes nothing (no leakage).
    leave_one_out: bool = True
    leave_one_out_max_runs: int = 4
    max_dim_spread_frac: float = 0.10
    # Image-resolution gate (image space, GT-free): the smaller side of the observed
    # mask bounding box, minimised over frames, must exceed this many pixels — below
    # it, mask rasterisation dominates and the metric dimension is not reliable.
    # Default 0.0 = disabled (the synthetic grid uses tiny images deliberately);
    # real captures set it from the quantisation study, not from one carton.
    min_mask_bbox_px: float = 0.0


@dataclass(frozen=True)
class CuboidFrame:
    """The fixed gravity-aligned coordinate frame the cuboid is parameterised in.

    ``anchor`` is the frame origin: a point on the support plane (``on_plane``) or
    the object locus (free). ``e1``/``e2`` span the horizontal plane; ``up`` is
    gravity-up. When ``on_plane`` the box bottom face sits on the plane through
    ``anchor`` (6 DOF); otherwise the vertical centre is free (7 DOF)."""

    anchor: np.ndarray
    e1: np.ndarray
    e2: np.ndarray
    up: np.ndarray
    on_plane: bool

    @property
    def dof(self) -> int:
        return 6 if self.on_plane else 7


@dataclass(frozen=True)
class CuboidParameters:
    """A gravity-aligned metric cuboid. ``length >= width`` is enforced on the final
    canonical output (Phase F), not on intermediate candidates."""

    cu: float      # horizontal centre along e1 (metres from anchor)
    cv: float      # horizontal centre along e2
    cw: float      # vertical centre along up (metres from anchor)
    yaw: float     # radians, about up
    length: float
    width: float
    height: float

    def as_dict(self) -> dict[str, float]:
        return {
            "centre_u_m": self.cu, "centre_v_m": self.cv, "centre_w_m": self.cw,
            "yaw_rad": self.yaw, "length_m": self.length,
            "width_m": self.width, "height_m": self.height,
        }


# --------------------------------------------------------------------------- #
# Phase C — pure geometry: parameters -> world vertices -> pixels -> silhouette
# --------------------------------------------------------------------------- #

def build_frame(bundle: CaptureBundle) -> CuboidFrame:
    """The 6-DOF support-plane frame when the bundle has a (canonical) support
    plane, else the 7-DOF free frame anchored at the object locus."""
    up = up_from_gravity(bundle.gravity_world)
    e1, e2 = horizontal_basis(up)
    if bundle.support_plane is not None:
        n = np.asarray(bundle.support_plane["normal"], dtype=float)
        n = n / np.linalg.norm(n)
        d = float(bundle.support_plane["offset"])
        anchor = -d * n            # a point on the plane  (n·anchor + d = 0)
        return CuboidFrame(anchor=anchor, e1=e1, e2=e2, up=n, on_plane=True)
    locus, _ = estimate_roi(bundle, ReconstructionConfig())
    return CuboidFrame(anchor=np.asarray(locus, dtype=float), e1=e1, e2=e2, up=up, on_plane=False)


def _resolve_frame(bundle: CaptureBundle, locus: np.ndarray, on_plane: bool | None) -> CuboidFrame:
    """The fit frame, honouring an explicit ``on_plane`` override (Phase G: report
    the 6-DOF plane fit and the 7-DOF free fit independently). ``None`` keeps the
    bundle's natural choice (plane if present, else free)."""
    frame = build_frame(bundle)
    if on_plane is None or on_plane == frame.on_plane:
        return frame
    if on_plane and bundle.support_plane is None:
        raise MetricReconstructionError(
            FailureCode.INVALID_SUPPORT_PLANE, "on_plane requested but bundle has no support plane"
        )
    up = up_from_gravity(bundle.gravity_world)
    e1, e2 = horizontal_basis(up)
    return CuboidFrame(anchor=np.asarray(locus, dtype=float), e1=e1, e2=e2, up=up, on_plane=False)


def _centre_world(p: CuboidParameters, frame: CuboidFrame) -> np.ndarray:
    cw = p.height / 2.0 if frame.on_plane else p.cw  # bottom face on the plane
    return frame.anchor + p.cu * frame.e1 + p.cv * frame.e2 + cw * frame.up


def cuboid_vertices(p: CuboidParameters, frame: CuboidFrame) -> np.ndarray:
    """The 8 world-space cuboid vertices ``(8, 3)`` for ``p`` in ``frame``."""
    a = np.cos(p.yaw) * frame.e1 + np.sin(p.yaw) * frame.e2  # length axis
    b = -np.sin(p.yaw) * frame.e1 + np.cos(p.yaw) * frame.e2  # width axis
    centre = _centre_world(p, frame)
    hl, hw, hh = p.length / 2.0, p.width / 2.0, p.height / 2.0
    return np.array(
        [centre + sx * hl * a + sy * hw * b + sz * hh * frame.up
         for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    )


def project_cuboid(vertices: np.ndarray, frame_view: ViewFrame) -> tuple[np.ndarray, np.ndarray]:
    """Project the 8 cuboid vertices into one view: ``(pixels (8,2), depth (8,))``.

    Uses the fixed M9 projection (``P = K[R|t]_camera_from_world`` via
    ``T_world_from_camera``) — no monocular depth."""
    P = cam.projection_matrix(frame_view.intrinsics, frame_view.T_world_from_camera)
    return cam.project_world(P, vertices)


def cuboid_silhouette(vertices_px: np.ndarray, width: int, height: int) -> np.ndarray:
    """The exact convex 2D silhouette of the projected cuboid as an ``(H, W)`` bool
    mask (a convex solid projects to the convex hull of its projected vertices).
    Kept for inspection/tests; the fit objective scores silhouettes analytically
    (``_poly_iou``) without rasterising."""
    return fill_convex_polygon(vertices_px, width, height)


# --- analytic convex-polygon IoU (no rasterisation in the optimiser loop) ----
#
# The silhouettes are tiny convex polygons (≤8 vertices), evaluated ~10⁴ times per
# fit. NumPy's per-call overhead on 2-element arrays dominates there, so the hot
# scoring path works on plain Python lists of ``(x, y)`` float tuples with scalar
# arithmetic — the same maths as the earlier array version, ~10× faster. ``*_xy``
# helpers take/return such lists.

Pt = tuple[float, float]


def _signed_area_xy(poly: list[Pt]) -> float:
    n = len(poly)
    if n < 3:
        return 0.0
    s = 0.0
    x0, y0 = poly[-1]
    for x1, y1 in poly:
        s += x0 * y1 - x1 * y0
        x0, y0 = x1, y1
    return 0.5 * s


def _poly_area_xy(poly: list[Pt]) -> float:
    return abs(_signed_area_xy(poly))


def _ccw_xy(poly: list[Pt]) -> list[Pt]:
    """Reorder to a positive signed area (CCW), fixing winding regardless of the
    image y-down convention."""
    return poly[::-1] if _signed_area_xy(poly) < 0 else poly


def _poly_centroid_xy(poly: list[Pt]) -> Pt:
    """True area (centre-of-mass) centroid of a simple polygon — NOT the mean of its
    vertices, which is biased toward wherever the vertices crowd. This matches the
    observed-mask centroid (the mean of the filled pixels, an area centroid), so the
    two centroid terms are the same geometric quantity."""
    n = len(poly)
    if n == 0:
        return (0.0, 0.0)
    if n < 3:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    a = cx = cy = 0.0
    x0, y0 = poly[-1]
    for x1, y1 in poly:
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
        x0, y0 = x1, y1
    a *= 0.5
    if abs(a) < 1e-12:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    return (cx / (6.0 * a), cy / (6.0 * a))


def _hull_ccw_xy(points: np.ndarray) -> list[Pt]:
    """CCW convex hull of a small point set as a list of ``(x, y)`` tuples (Andrew's
    monotone chain, scalar). Used on the ≤8 projected cuboid vertices every objective
    evaluation — avoids ``np.unique``/``lexsort`` overhead on a tiny array."""
    pts = sorted({(float(x), float(y)) for x, y in points})
    if len(pts) <= 2:
        return pts

    def cross(o: Pt, a: Pt, b: Pt) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Pt] = []
    for q in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(q)
    upper: list[Pt] = []
    for q in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(q)
    return lower[:-1] + upper[:-1]


def _simplify_convex(hull: np.ndarray, tol_px: float = 2.0) -> np.ndarray:
    """Drop near-collinear vertices from a convex hull (a filled mask's pixel hull
    has a long staircase of nearly collinear points). Keeps the true corners, which
    makes the polygon IoU faster and cleaner. A box silhouette is a convex polygon
    of at most six edges, so this is lossless for the signal. Iterates to a fixed
    point because removing a vertex can expose a newly-collinear neighbour."""
    out = hull
    while out.shape[0] > 3:
        keep = []
        n = out.shape[0]
        for i in range(n):
            a, b, c = out[i - 1], out[i], out[(i + 1) % n]
            tri = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if tri > tol_px:  # twice the triangle area; drop vertices on a straight edge
                keep.append(b)
        if len(keep) == n or len(keep) < 3:
            break
        out = np.array(keep)
    return out


def _isect_xy(p: Pt, q: Pt, a: Pt, b: Pt) -> Pt:
    """Intersection of segment ``p→q`` with the infinite line ``a→b`` (scalar)."""
    rx, ry = q[0] - p[0], q[1] - p[1]
    sx, sy = b[0] - a[0], b[1] - a[1]
    denom = rx * sy - ry * sx
    if abs(denom) < 1e-12:
        return q
    t = ((a[0] - p[0]) * sy - (a[1] - p[1]) * sx) / denom
    return (p[0] + t * rx, p[1] + t * ry)


def _clip_convex_xy(subject: list[Pt], clip: list[Pt]) -> list[Pt]:
    """Sutherland–Hodgman clip of convex ``subject`` by convex ``clip`` (both CCW).
    Scalar, on ``(x, y)`` tuple lists. Returns the intersection polygon (maybe
    empty)."""
    out = subject
    m = len(clip)
    for i in range(m):
        if not out:
            break
        ax, ay = clip[i]
        bx, by = clip[(i + 1) % m]
        ex, ey = bx - ax, by - ay
        new: list[Pt] = []
        n = len(out)
        prv = out[-1]
        dp = ex * (prv[1] - ay) - ey * (prv[0] - ax)  # >=0 is inside (CCW)
        for j in range(n):
            cur = out[j]
            dc = ex * (cur[1] - ay) - ey * (cur[0] - ax)
            if dc >= 0:
                if dp < 0:
                    new.append(_isect_xy(prv, cur, (ax, ay), (bx, by)))
                new.append(cur)
            elif dp >= 0:
                new.append(_isect_xy(prv, cur, (ax, ay), (bx, by)))
            prv, dp = cur, dc
        out = new
    return out


def _poly_iou_xy(pred: list[Pt], obs: list[Pt]) -> float:
    """IoU of two convex polygons (CCW ``(x, y)`` lists). Exact — both the projected
    cuboid and the observed mask are convex, so each is its convex hull."""
    pred, obs = _ccw_xy(pred), _ccw_xy(obs)
    ap, ao = _poly_area_xy(pred), _poly_area_xy(obs)
    if ap <= 0 or ao <= 0:
        return 0.0
    inter = _poly_area_xy(_clip_convex_xy(pred, obs))
    union = ap + ao - inter
    return inter / union if union > 0 else 0.0


# --------------------------------------------------------------------------- #
# Phase D — silhouette objective against the observed masks (no GT)
# --------------------------------------------------------------------------- #

@dataclass
class _ViewCache:
    P: np.ndarray              # 3x4 world->pixel projection (precomputed; the hot path)
    obs_xy: list[Pt]           # CCW convex hull of the observed mask as (x,y) tuples
    obs_centroid: Pt           # (x, y) area centroid of the mask
    diag: float                # image diagonal (px) for normalisation


def _cache_views(frames: list[ViewFrame]) -> list[_ViewCache]:
    caches: list[_ViewCache] = []
    for f in frames:
        ys, xs = np.nonzero(f.mask)
        pts = np.stack([xs, ys], axis=-1).astype(float)
        obs = _simplify_convex(_convex_hull_2d(pts))
        caches.append(_ViewCache(
            P=cam.projection_matrix(f.intrinsics, f.T_world_from_camera),
            obs_xy=_ccw_xy([(float(x), float(y)) for x, y in obs]),
            obs_centroid=(float(xs.mean()), float(ys.mean())),
            diag=float(np.hypot(f.width, f.height)),
        ))
    return caches


def _min_mask_bbox_px(bundle: CaptureBundle) -> float:
    """The smaller side of each observed mask's bounding box, minimised over frames
    (px) — a GT-free proxy for how well-resolved the object is. Masks are non-empty
    (checked in ``validate_bundle``)."""
    sides = []
    for f in bundle.frames:
        ys, xs = np.nonzero(f.mask)
        sides.append(min(int(ys.max() - ys.min()) + 1, int(xs.max() - xs.min()) + 1))
    return float(min(sides)) if sides else 0.0


def _mean_point_to_edges_xy(points: list[Pt], poly: list[Pt]) -> float:
    """Mean distance from each point to the nearest EDGE (segment) of a closed
    polygon — a true point-to-contour distance, not point-to-nearest-vertex. Scalar
    over tiny polygons."""
    m = len(poly)
    total = 0.0
    for px, py in points:
        best = float("inf")
        for i in range(m):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % m]
            abx, aby = bx - ax, by - ay
            d2 = abx * abx + aby * aby
            t = 0.0 if d2 < 1e-12 else ((px - ax) * abx + (py - ay) * aby) / d2
            t = max(0.0, min(1.0, t))
            dx, dy = px - (ax + t * abx), py - (ay + t * aby)
            best = min(best, dx * dx + dy * dy)
        total += best ** 0.5
    return total / len(points)


def _boundary_distance_xy(a: list[Pt], b: list[Pt]) -> float:
    """Symmetric mean point-to-contour distance between two convex polygons (px).

    Each polygon's vertices are measured to the nearest EDGE of the other, so two
    silhouettes sharing an edge but with vertices at different places along it score
    ~0 (a vertex-to-vertex nearest distance would not). A weak boundary regulariser /
    diagnostic — IoU remains the primary silhouette evidence."""
    if len(a) < 2 or len(b) < 2:
        return float("inf")
    return 0.5 * (_mean_point_to_edges_xy(a, b) + _mean_point_to_edges_xy(b, a))


def per_frame_iou(p: CuboidParameters, frame: CuboidFrame, caches: list[_ViewCache]) -> dict[str, Any]:
    """Project the candidate into every view and score silhouette agreement.

    Returns per-frame IoU, the mean/min IoU and the mean boundary residual (px).
    IoU is the measurement evidence; the boundary residual is a reported
    diagnostic (and a small objective term)."""
    verts = cuboid_vertices(p, frame)
    ious: list[float] = []
    centroids: list[float] = []
    boundaries: list[float] = []
    for c in caches:
        px, depth = cam.project_world(c.P, verts)
        if not np.all(depth > 1e-6):  # box (partly) behind the camera — invalid view
            ious.append(0.0)
            centroids.append(1.0)
            boundaries.append(1.0)
            continue
        pred = _hull_ccw_xy(px)
        ious.append(_poly_iou_xy(pred, c.obs_xy))
        cen = _poly_centroid_xy(pred)
        centroids.append(np.hypot(cen[0] - c.obs_centroid[0], cen[1] - c.obs_centroid[1]) / c.diag)
        boundaries.append(_boundary_distance_xy(pred, c.obs_xy) / c.diag)
    return {
        "per_frame_iou": ious,
        "mean_iou": float(np.mean(ious)),
        "min_iou": float(np.min(ious)),
        "centroid_norm": centroids,
        "boundary_norm": boundaries,
        "boundary_px": [b * c.diag for b, c in zip(boundaries, caches, strict=True)],
    }


def _loss(p: CuboidParameters, frame: CuboidFrame, caches: list[_ViewCache], cfg: CuboidFitConfig) -> float:
    """Silhouette-disagreement loss: mean ``1 - IoU`` plus small centroid and
    boundary regularisers. Symmetric in a way the hull "fraction of surviving
    voxels inside mask" was not — an oversized box lowers IoU because it spills
    outside the mask (union grows, intersection does not)."""
    s = per_frame_iou(p, frame, caches)
    iou_loss = 1.0 - float(np.mean(s["per_frame_iou"]))
    centroid = float(np.mean(s["centroid_norm"]))
    boundary = float(np.mean(s["boundary_norm"]))
    return iou_loss + cfg.centroid_weight * centroid + cfg.boundary_weight * boundary


# --------------------------------------------------------------------------- #
# Phase E — deterministic bounded optimiser (pure NumPy pattern search)
# --------------------------------------------------------------------------- #

def _pack(p: CuboidParameters, frame: CuboidFrame) -> np.ndarray:
    if frame.on_plane:
        return np.array([p.cu, p.cv, p.yaw, p.length, p.width, p.height])
    return np.array([p.cu, p.cv, p.cw, p.yaw, p.length, p.width, p.height])


def _unpack(x: np.ndarray, frame: CuboidFrame) -> CuboidParameters:
    if frame.on_plane:
        cu, cv, yaw, L, W, H = x
        cw = 0.0  # derived in _centre_world
    else:
        cu, cv, cw, yaw, L, W, H = x
    return CuboidParameters(cu=cu, cv=cv, cw=cw, yaw=yaw, length=L, width=W, height=H)


def _bounds(frame: CuboidFrame, locus: np.ndarray, half: float, cfg: CuboidFitConfig) -> tuple[np.ndarray, np.ndarray]:
    """Box bounds in parameter space from capture geometry only (ROI half-extent),
    never a known carton size."""
    rel = locus - frame.anchor
    cu0, cv0, cw0 = rel @ frame.e1, rel @ frame.e2, rel @ frame.up
    dim_lo, dim_hi = cfg.min_dim_m, cfg.max_dim_roi_mult * half
    yaw_lo, yaw_hi = -np.pi, np.pi
    if frame.on_plane:
        lo = np.array([cu0 - half, cv0 - half, yaw_lo, dim_lo, dim_lo, dim_lo])
        hi = np.array([cu0 + half, cv0 + half, yaw_hi, dim_hi, dim_hi, dim_hi])
    else:
        lo = np.array([cu0 - half, cv0 - half, cw0 - half, yaw_lo, dim_lo, dim_lo, dim_lo])
        hi = np.array([cu0 + half, cv0 + half, cw0 + half, yaw_hi, dim_hi, dim_hi, dim_hi])
    return lo, hi


def _pattern_search(
    x0: np.ndarray, lo: np.ndarray, hi: np.ndarray, step0: np.ndarray,
    objective, cfg: CuboidFitConfig, min_step: float,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    """Hooke–Jeeves coordinate pattern search with shrinking steps. Deterministic
    (no RNG); hard-bounded by ``[lo, hi]``.

    Reports the real termination reason, not an unconditional success: ``converged``
    is True only when the step actually shrank below ``min_step``; ``hit_max_iter``
    means the loop stopped at the iteration cap while still moving/shrinking.
    ``at_parameter_bound`` flags that the optimum sits against a box bound (recorded,
    not by itself a rejection — the geometry may legitimately support it)."""
    x = np.clip(x0, lo, hi)
    fx = objective(x)
    step = step0.copy()
    iters = 0
    converged = False
    while iters < cfg.max_iter:
        improved = False
        for i in range(len(x)):
            for sgn in (1.0, -1.0):
                trial = x.copy()
                trial[i] = np.clip(trial[i] + sgn * step[i], lo[i], hi[i])
                ft = objective(trial)
                if ft < fx - 1e-12:
                    x, fx, improved = trial, ft, True
                    break
        iters += 1
        if not improved:
            step = step * cfg.step_shrink
            if np.all(step < min_step):
                converged = True
                break
    span = np.maximum(hi - lo, 1e-12)
    at_bound = bool(np.any((x - lo) / span < 1e-3) or np.any((hi - x) / span < 1e-3))
    status = {
        "iterations": iters,
        "converged": converged,
        "hit_max_iter": (not converged) and iters >= cfg.max_iter,
        "final_step_size": float(np.max(step)),
        "at_parameter_bound": at_bound,
    }
    return x, fx, status


# --------------------------------------------------------------------------- #
# Phase F — canonicalise the L/W/yaw symmetry
# --------------------------------------------------------------------------- #

def canonicalise(p: CuboidParameters) -> CuboidParameters:
    """Resolve the natural ``(L, W, yaw)`` ≡ ``(W, L, yaw+90°)`` ambiguity: enforce
    ``length >= width`` and wrap yaw into the documented canonical interval
    ``[-90°, 90°)`` (a cuboid's yaw has 180° periodicity). Positive dimensions are
    enforced here too."""
    L, W, yaw = abs(p.length), abs(p.width), p.yaw
    if L < W:
        L, W = W, L
        yaw += np.pi / 2.0
    yaw = (yaw + np.pi / 2.0) % np.pi - np.pi / 2.0  # -> [-pi/2, pi/2)
    return CuboidParameters(cu=p.cu, cv=p.cv, cw=p.cw, yaw=yaw, length=L, width=W, height=abs(p.height))


# --------------------------------------------------------------------------- #
# Phase E/J/K — fit one candidate, identifiability, leave-one-out
# --------------------------------------------------------------------------- #

def _fit_once(frame: CuboidFrame, caches: list[_ViewCache], locus: np.ndarray, half: float, cfg: CuboidFitConfig) -> tuple[CuboidParameters, float, float, dict]:
    """Multi-start pattern search. Returns ``(best_params, initial_loss,
    final_loss, status)``. Initialisation is from capture geometry (ROI + mask
    locus) and generic yaw/scale hypotheses — never from ground truth."""
    lo, hi = _bounds(frame, locus, half, cfg)
    rel = locus - frame.anchor
    cu0, cv0, cw0 = rel @ frame.e1, rel @ frame.e2, rel @ frame.up
    min_step = cfg.min_step_frac * half

    def objective_vec(x: np.ndarray) -> float:
        return _loss(_unpack(x, frame), frame, caches, cfg)

    best: tuple[np.ndarray, float, dict[str, Any]] | None = None
    first_initial = None
    total_iters = 0
    starts = 0
    for scale in cfg.scale_starts:
        dim0 = max(scale * half, 2 * cfg.min_dim_m)
        for yaw_deg in cfg.yaw_starts_deg:
            yaw0 = np.radians(yaw_deg)
            if frame.on_plane:
                x0 = np.array([cu0, cv0, yaw0, dim0, dim0, dim0])
                step0 = np.array([half * 0.3, half * 0.3, np.radians(20), dim0 * 0.5, dim0 * 0.5, dim0 * 0.5])
            else:
                x0 = np.array([cu0, cv0, cw0, yaw0, dim0, dim0, dim0])
                step0 = np.array([half * 0.3, half * 0.3, half * 0.3, np.radians(20), dim0 * 0.5, dim0 * 0.5, dim0 * 0.5])
            if first_initial is None:
                first_initial = objective_vec(np.clip(x0, lo, hi))
            xf, ff, st = _pattern_search(x0, lo, hi, step0, objective_vec, cfg, min_step)
            total_iters += st["iterations"]
            starts += 1
            if best is None or ff < best[1]:
                best = (xf, ff, st)
    assert best is not None
    params = _unpack(best[0], frame)
    bst = best[2]
    # The optimiser is "successful" only when the winning start actually converged
    # (step shrank below min_step), not merely because it returned a value. A bound
    # contact is recorded but does not by itself fail the fit.
    status = {
        "optimizer_success": bool(bst["converged"]),
        "converged": bool(bst["converged"]),
        "hit_max_iter": bool(bst["hit_max_iter"]),
        "final_step_size": float(bst["final_step_size"]),
        "at_parameter_bound": bool(bst["at_parameter_bound"]),
        "iterations": total_iters,
        "starts": starts,
    }
    return params, float(first_initial), float(best[1]), status


def _identifiability(p: CuboidParameters, frame: CuboidFrame, caches: list[_ViewCache], base_loss: float, cfg: CuboidFitConfig) -> dict[str, Any]:
    """Perturb **every fitted DOF** around the optimum and measure how much
    silhouette loss rises. A parameter whose perturbation barely changes the loss is
    not observable — the fit is ambiguous even though the optimiser converged.

    Perturbations are parameter-appropriate (the M9 spec): dimensions relative, the
    horizontal/vertical centre metric (a fraction of the object scale), yaw angular.
    The fitted DOF are centre (cu, cv [, cw for 7-DOF]) + yaw + L/W/H.

    The ``(L, W, yaw) ≡ (W, L, yaw+90°)`` symmetry means a square footprint has an
    unobservable yaw that does **not** change the measured dimensions — so yaw is
    reported but exempt from the gate when ``|L-W|/max(L,W) < lw_square_tol``. GT is
    never used."""
    mean_dim = (abs(p.length) + abs(p.width) + abs(p.height)) / 3.0
    centre_delta = cfg.identifiability_centre_frac * mean_dim
    yaw_delta = np.radians(cfg.identifiability_yaw_deg)
    specs = [
        ("length", cfg.identifiability_rel * abs(p.length)),
        ("width", cfg.identifiability_rel * abs(p.width)),
        ("height", cfg.identifiability_rel * abs(p.height)),
        ("cu", centre_delta),
        ("cv", centre_delta),
        ("yaw", yaw_delta),
    ]
    if not frame.on_plane:
        specs.insert(5, ("cw", centre_delta))

    square = abs(p.length - p.width) / max(abs(p.length), abs(p.width), 1e-9) < cfg.lw_square_tol
    per_dof: dict[str, float] = {}
    gated = []
    for name, delta in specs:
        val = getattr(p, name)
        rises = [
            _loss(_replace_param(p, name, val + sgn * delta), frame, caches, cfg) - base_loss
            for sgn in (1.0, -1.0)
        ]
        sensitivity = float(min(rises))  # the easiest direction to move without cost
        per_dof[name] = sensitivity
        if name == "yaw" and square:
            continue  # square footprint: yaw is unobservable but harmless (symmetry)
        gated.append(sensitivity)
    worst = float(min(gated))
    return {
        **per_dof,
        "per_dof": per_dof,
        "square_footprint": bool(square),
        "min_sensitivity": worst,
        "identifiable": bool(worst >= cfg.min_identifiability),
    }


def _replace_param(p: CuboidParameters, name: str, value: float) -> CuboidParameters:
    """Return ``p`` with one named parameter (cu/cv/cw/yaw/length/width/height)
    replaced — used by the identifiability perturbations."""
    fields = {"cu": p.cu, "cv": p.cv, "cw": p.cw, "yaw": p.yaw,
              "length": p.length, "width": p.width, "height": p.height}
    fields[name] = value
    return CuboidParameters(**fields)


def _leave_one_out(bundle: CaptureBundle, config: ReconstructionConfig, cfg: CuboidFitConfig, on_plane: bool | None) -> dict[str, Any]:
    """Refit dropping one frame at a time; report the relative L/W/H spread. A
    practical METRIC measurement must not swing when a single view is removed.

    **Leak-free (Phase K fix):** every subset rebuilds its OWN locus, ROI half-extent
    and cuboid frame from only the frames it keeps, so the omitted frame contributes
    nothing to the refit — not through the object locus, the ROI, or the frame
    anchor. A subset that breaks observability when a frame is dropped is skipped
    (that is itself stability signal), not fitted on stale geometry."""
    frames = bundle.frames
    n = len(frames)
    drop = np.unique(np.linspace(0, n - 1, min(cfg.leave_one_out_max_runs, n)).astype(int))
    runs: list[tuple[float, float, float]] = []
    for i in drop:
        subset = frames[:i] + frames[i + 1 :]
        if len(subset) < config.min_frames:
            continue
        sub = dataclasses.replace(bundle, frames=subset)
        try:
            validate_bundle(sub, config)
            locus, half = estimate_roi(sub, config)
            frame = _resolve_frame(sub, np.asarray(locus, dtype=float), on_plane)
        except MetricReconstructionError:
            continue  # dropped frame breaking observability is itself signal
        p, _, _, _ = _fit_once(frame, _cache_views(subset), np.asarray(locus, dtype=float), half, cfg)
        p = canonicalise(p)
        runs.append((p.length, p.width, p.height))
    if len(runs) < 2:
        return {"runs": len(runs), "spread_frac_max": None}
    arr = np.array(runs)
    frac = (arr.max(axis=0) - arr.min(axis=0)) / np.maximum(arr.mean(axis=0), 1e-9)
    return {
        "runs": len(runs),
        "spread_frac": {"length": float(frac[0]), "width": float(frac[1]), "height": float(frac[2])},
        "spread_frac_max": float(frac.max()),
    }


# --------------------------------------------------------------------------- #
# Phase P — top-level fit returning the typed result
# --------------------------------------------------------------------------- #

def fit_cuboid(
    bundle: CaptureBundle,
    cfg: CuboidFitConfig | None = None,
    *,
    config: ReconstructionConfig | None = None,
    on_plane: bool | None = None,
) -> dict[str, Any]:
    """Fit a gravity-aligned metric cuboid to the bundle's silhouettes.

    ``on_plane=None`` uses the 6-DOF support-plane fit when the bundle has a support
    plane (preferred), else the 7-DOF free fit; pass ``True``/``False`` to force one
    (so the no-plane configuration can be reported independently, Phase G).

    Returns the typed result dict: a successful metric measurement only when the
    optimiser converged **and** the fit is silhouette-consistent, identifiable and
    stable; otherwise ``success=False`` with a typed reason and no fabricated
    dimensions (diagnostic dims are retained under ``debug_dimensions_mm``)."""
    cfg = cfg or CuboidFitConfig()
    config = config or ReconstructionConfig()
    frames_total = len(bundle.frames)
    timings: dict[str, float] = {}

    try:
        validate_bundle(bundle, config)
        locus, half = estimate_roi(bundle, config)
        frame = _resolve_frame(bundle, np.asarray(locus, dtype=float), on_plane)
    except MetricReconstructionError as e:
        return {"success": False, "measurement_tier": "metric", "method": "multiview_cuboid_fit",
                "reason": e.code.value, "detail": e.detail, "frames_total": frames_total}

    # Image-resolution gate (GT-free): below a minimum observed mask bbox the metric
    # dimension is dominated by mask rasterisation — refuse rather than fabricate.
    min_bbox_px = _min_mask_bbox_px(bundle)
    if cfg.min_mask_bbox_px > 0 and min_bbox_px < cfg.min_mask_bbox_px:
        return {"success": False, "measurement_tier": "metric", "method": "multiview_cuboid_fit",
                "reason": FailureCode.INSUFFICIENT_IMAGE_RESOLUTION.value,
                "detail": f"min mask bbox {min_bbox_px:.0f}px < required {cfg.min_mask_bbox_px:.0f}px",
                "frames_total": frames_total}

    caches = _cache_views(bundle.frames)
    t1 = time.perf_counter()
    params, initial_loss, final_loss, status = _fit_once(frame, caches, np.asarray(locus, dtype=float), half, cfg)
    params = canonicalise(params)
    timings["fit_ms"] = (time.perf_counter() - t1) * 1000

    sil = per_frame_iou(params, frame, caches)
    ident = _identifiability(params, frame, caches, final_loss, cfg)

    t2 = time.perf_counter()
    loo: dict[str, Any] = {"runs": 0, "spread_frac_max": None}
    if cfg.leave_one_out:
        loo = _leave_one_out(bundle, config, cfg, on_plane)
    timings["leave_one_out_ms"] = (time.perf_counter() - t2) * 1000

    obs = observability_metrics(bundle, sil["per_frame_iou"])
    mean_boundary_px = float(np.mean(sil["boundary_px"]))
    diag = caches[0].diag if caches else 1.0

    diagnostics: dict[str, Any] = {
        "dof": frame.dof,
        "on_plane": frame.on_plane,
        "parameters": params.as_dict(),
        "optimizer_success": status["optimizer_success"],
        "optimizer_converged": status["converged"],
        "optimizer_hit_max_iter": status["hit_max_iter"],
        "optimizer_final_step_size": status["final_step_size"],
        "optimizer_at_parameter_bound": status["at_parameter_bound"],
        "iterations": status["iterations"],
        "starts": status["starts"],
        "initial_loss": initial_loss,
        "final_loss": final_loss,
        "mean_iou": sil["mean_iou"],
        "min_iou": sil["min_iou"],
        "per_frame_iou": sil["per_frame_iou"],
        "boundary_error_px": mean_boundary_px,
        "min_mask_bbox_px": min_bbox_px,
        "parameter_identifiability": ident,
        "leave_one_out_spread": loo,
        "pose_baseline_mm": obs["total_baseline_mm"],
        "view_coverage_deg": obs["max_view_angle_deg"],
        "frames_used": frames_total,
        "timing_ms": timings,
    }

    dims = metres_to_dimensions(params.length, params.width, params.height)
    reason = _gate(status, sil, ident, loo, mean_boundary_px / diag, cfg)
    if reason is not None:
        return {"success": False, "measurement_tier": "metric", "method": "multiview_cuboid_fit",
                "reason": reason.value, "frames_total": frames_total,
                "debug_dimensions_mm": dims.to_dict(), "diagnostics": diagnostics}

    return {
        "success": True,
        "measurement_tier": "metric",
        "method": "multiview_cuboid_fit",
        "dimensions": dims.to_dict(),
        "pose_source": bundle.pose_source,
        "frames_total": frames_total,
        "frames_accepted": frames_total,
        "diagnostics": diagnostics,
    }


def _gate(status: dict, sil: dict, ident: dict, loo: dict, boundary_frac: float, cfg: CuboidFitConfig) -> FailureCode | None:
    """The typed failure a cuboid fit must return when the metric dimensions are
    not trustworthy, or ``None`` when every gate passes. Convergence first (the
    optimiser must have actually finished), then silhouette consistency (bad fit),
    then identifiability (ambiguous), then stability (unstable)."""
    if cfg.require_convergence and not status["converged"]:
        return FailureCode.CUBOID_FIT_FAILED
    if (sil["mean_iou"] < cfg.min_mean_iou or sil["min_iou"] < cfg.min_min_iou
            or boundary_frac > cfg.max_boundary_frac):
        return FailureCode.INSUFFICIENT_SILHOUETTE_CONSISTENCY
    if not ident["identifiable"]:
        return FailureCode.AMBIGUOUS_CUBOID_FIT
    spread = loo.get("spread_frac_max")
    if spread is not None and spread > cfg.max_dim_spread_frac:
        return FailureCode.UNSTABLE_CUBOID_FIT
    return None


# --------------------------------------------------------------------------- #
# Phase K2 — image-space quantisation uncertainty (GT-free observability)
# --------------------------------------------------------------------------- #

def _dilate1(mask: np.ndarray) -> np.ndarray:
    """4-neighbour 1-pixel dilation (grow the silhouette by ~1px)."""
    m = mask.copy()
    m[1:, :] |= mask[:-1, :]
    m[:-1, :] |= mask[1:, :]
    m[:, 1:] |= mask[:, :-1]
    m[:, :-1] |= mask[:, 1:]
    return m


def _erode1(mask: np.ndarray) -> np.ndarray:
    """4-neighbour 1-pixel erosion (shrink the silhouette by ~1px)."""
    return ~_dilate1(~mask)


def image_quantization_uncertainty(
    bundle: CaptureBundle,
    cfg: CuboidFitConfig | None = None,
    *,
    config: ReconstructionConfig | None = None,
    on_plane: bool | None = None,
) -> dict[str, Any]:
    """Estimate the metric dimension uncertainty (mm) from image-space quantisation,
    **without ground truth**: perturb every observed silhouette boundary by ~±1px
    (erode / dilate), refit, and report the half-range of L/W/H across the nominal,
    eroded and dilated fits. A large uncertainty relative to the dimension means the
    measurement is limited by pixel coverage, not by the algorithm — the signal for
    an ``insufficient_image_resolution`` decision on a real capture.

    Refits are run with leave-one-out disabled (this is a per-mask perturbation
    study, not a stability study) so it stays cheap enough to call per case."""
    cfg = dataclasses.replace(cfg or CuboidFitConfig(), leave_one_out=False, require_convergence=False)
    variants: dict[str, tuple[float, float, float]] = {}
    for name, op in (("nominal", None), ("eroded", _erode1), ("dilated", _dilate1)):
        frames = (bundle.frames if op is None
                  else [dataclasses.replace(f, mask=op(f.mask)) for f in bundle.frames])
        if any(not f.mask.any() for f in frames):
            continue  # erosion wiped a thin silhouette — skip that variant
        r = fit_cuboid(dataclasses.replace(bundle, frames=frames), cfg, config=config, on_plane=on_plane)
        d = r.get("dimensions") or r.get("debug_dimensions_mm")
        if d is not None:
            variants[name] = (d["length_mm"], d["width_mm"], d["height_mm"])
    if len(variants) < 2:
        return {"runs": len(variants), "length_mm": None, "width_mm": None, "height_mm": None,
                "min_mask_bbox_px": _min_mask_bbox_px(bundle)}
    arr = np.array(list(variants.values()), dtype=float)
    unc = (arr.max(axis=0) - arr.min(axis=0)) / 2.0
    return {
        "runs": len(variants),
        "length_mm": float(unc[0]), "width_mm": float(unc[1]), "height_mm": float(unc[2]),
        "min_mask_bbox_px": _min_mask_bbox_px(bundle),
        "variants": {k: [float(x) for x in v] for k, v in variants.items()},
    }
