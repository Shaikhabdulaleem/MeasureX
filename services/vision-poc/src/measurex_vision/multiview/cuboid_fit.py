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
    max_iter: int = 40
    step_shrink: float = 0.5
    min_step_frac: float = 1e-3        # stop when every step < this × ROI half-extent
    min_dim_m: float = 0.02            # lower dimension bound (operational safety)
    max_dim_roi_mult: float = 4.0      # upper dimension bound = mult × ROI half-extent
    # Silhouette-consistency gate (image space). Provisional floors — the box must
    # explain most of each silhouette's overlap; real-mask capture will calibrate
    # them. Not derived from any carton's GT dimensions.
    min_mean_iou: float = 0.88
    min_min_iou: float = 0.75
    max_boundary_frac: float = 0.05    # boundary residual as a fraction of image diagonal
    # Identifiability: a dimension perturbed by ``identifiability_rel`` must raise the
    # loss by at least ``min_identifiability`` — otherwise the dimension is not
    # observable (a flat objective direction) and the metric result is refused.
    identifiability_rel: float = 0.15
    min_identifiability: float = 0.02
    # Leave-one-out stability (relative L/W/H spread when dropping one frame).
    leave_one_out: bool = True
    leave_one_out_max_runs: int = 4
    max_dim_spread_frac: float = 0.10


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

def _signed_area(poly: np.ndarray) -> float:
    if poly.shape[0] < 3:
        return 0.0
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _poly_area(poly: np.ndarray) -> float:
    """Shoelace area of a simple polygon (vertices in order)."""
    return abs(_signed_area(poly))


def _ccw(poly: np.ndarray) -> np.ndarray:
    """Reorder to a positive signed area, so winding is fixed regardless of the
    image y-down axis convention (``_convex_hull_2d`` output is CW in image space)."""
    return poly[::-1] if _signed_area(poly) < 0 else poly


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


def _clip_convex(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Sutherland–Hodgman clip of convex ``subject`` by convex ``clip`` (both CCW).
    Returns the intersection polygon's vertices (possibly empty)."""
    out = subject
    m = clip.shape[0]
    for i in range(m):
        if out.shape[0] == 0:
            break
        a = clip[i]
        b = clip[(i + 1) % m]
        ex, ey = b[0] - a[0], b[1] - a[1]
        side = ex * (out[:, 1] - a[1]) - ey * (out[:, 0] - a[0])  # >=0 is inside (CCW)
        new: list[np.ndarray] = []
        n = out.shape[0]
        for j in range(n):
            cur, prv = out[j], out[j - 1]
            dc, dp = side[j], side[j - 1]
            if dc >= 0:
                if dp < 0:
                    new.append(_seg_line_isect(prv, cur, a, b))
                new.append(cur)
            elif dp >= 0:
                new.append(_seg_line_isect(prv, cur, a, b))
        out = np.array(new) if new else np.empty((0, 2))
    return out


def _seg_line_isect(p: np.ndarray, q: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Intersection of segment ``p→q`` with the infinite line ``a→b``."""
    r = q - p
    s = b - a
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-12:
        return q
    t = ((a[0] - p[0]) * s[1] - (a[1] - p[1]) * s[0]) / denom
    return p + t * r


def _poly_iou(pred_hull: np.ndarray, obs_hull: np.ndarray) -> float:
    """IoU of two convex polygons (CCW). Exact and fast — the carton silhouette is
    convex, so both the projected cuboid and the observed mask are represented by
    their convex hulls."""
    pred, obs = _ccw(pred_hull), _ccw(obs_hull)
    ap, ao = _poly_area(pred), _poly_area(obs)
    if ap <= 0 or ao <= 0:
        return 0.0
    inter = _poly_area(_clip_convex(pred, obs))
    union = ap + ao - inter
    return inter / union if union > 0 else 0.0


# --------------------------------------------------------------------------- #
# Phase D — silhouette objective against the observed masks (no GT)
# --------------------------------------------------------------------------- #

@dataclass
class _ViewCache:
    P: np.ndarray              # 3x4 world->pixel projection (precomputed; the hot path)
    obs_hull: np.ndarray       # CCW convex hull of the observed mask (the box silhouette)
    obs_centroid: np.ndarray   # (x, y)
    diag: float                # image diagonal (px) for normalisation


def _cache_views(frames: list[ViewFrame]) -> list[_ViewCache]:
    caches: list[_ViewCache] = []
    for f in frames:
        ys, xs = np.nonzero(f.mask)
        pts = np.stack([xs, ys], axis=-1).astype(float)
        caches.append(_ViewCache(
            P=cam.projection_matrix(f.intrinsics, f.T_world_from_camera),
            obs_hull=_simplify_convex(_convex_hull_2d(pts)),
            obs_centroid=np.array([xs.mean(), ys.mean()]),
            diag=float(np.hypot(f.width, f.height)),
        ))
    return caches


def _chamfer(a: np.ndarray, b: np.ndarray) -> float:
    """Symmetric mean nearest-vertex distance between two small point sets (px)."""
    if a.shape[0] == 0 or b.shape[0] == 0:
        return float("inf")
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    return float(0.5 * (d.min(axis=1).mean() + d.min(axis=0).mean()))


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
        pred_hull = _simplify_convex(_convex_hull_2d(px))
        ious.append(_poly_iou(pred_hull, c.obs_hull))
        centroids.append(float(np.linalg.norm(pred_hull.mean(axis=0) - c.obs_centroid) / c.diag))
        boundaries.append(_chamfer(pred_hull, c.obs_hull) / c.diag)
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
) -> tuple[np.ndarray, float, int]:
    """Hooke–Jeeves coordinate pattern search with shrinking steps. Deterministic
    (no RNG); hard-bounded by ``[lo, hi]``."""
    x = np.clip(x0, lo, hi)
    fx = objective(x)
    step = step0.copy()
    iters = 0
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
                break
    return x, fx, iters


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

    best: tuple[np.ndarray, float] | None = None
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
            xf, ff, it = _pattern_search(x0, lo, hi, step0, objective_vec, cfg, min_step)
            total_iters += it
            starts += 1
            if best is None or ff < best[1]:
                best = (xf, ff)
    assert best is not None
    params = _unpack(best[0], frame)
    status = {"optimizer_success": True, "iterations": total_iters, "starts": starts}
    return params, float(first_initial), float(best[1]), status


def _identifiability(p: CuboidParameters, frame: CuboidFrame, caches: list[_ViewCache], base_loss: float, cfg: CuboidFitConfig) -> dict[str, Any]:
    """Perturb L/W/H around the optimum and measure how much silhouette loss rises.
    A dimension whose perturbation barely changes the loss is not observable — the
    fit is ambiguous even though the optimiser converged."""
    out: dict[str, float] = {}
    worst = float("inf")
    for name in ("length", "width", "height"):
        val = getattr(p, name)
        delta = cfg.identifiability_rel * val
        rises = []
        for sgn in (1.0, -1.0):
            perturbed = _replace_dim(p, name, val + sgn * delta)
            rises.append(_loss(perturbed, frame, caches, cfg) - base_loss)
        sensitivity = float(min(rises))  # the easiest direction to move without cost
        out[name] = sensitivity
        worst = min(worst, sensitivity)
    out["min_sensitivity"] = worst
    out["identifiable"] = bool(worst >= cfg.min_identifiability)
    return out


def _replace_dim(p: CuboidParameters, name: str, value: float) -> CuboidParameters:
    kw = p.as_dict()
    return CuboidParameters(
        cu=kw["centre_u_m"], cv=kw["centre_v_m"], cw=kw["centre_w_m"], yaw=kw["yaw_rad"],
        length=value if name == "length" else p.length,
        width=value if name == "width" else p.width,
        height=value if name == "height" else p.height,
    )


def _leave_one_out(frames: list[ViewFrame], frame: CuboidFrame, locus: np.ndarray, half: float, cfg: CuboidFitConfig) -> dict[str, Any]:
    """Refit dropping one frame at a time; report the relative L/W/H spread. A
    practical METRIC measurement must not swing when a single view is removed."""
    n = len(frames)
    drop = np.unique(np.linspace(0, n - 1, min(cfg.leave_one_out_max_runs, n)).astype(int))
    runs: list[tuple[float, float, float]] = []
    for i in drop:
        subset = frames[:i] + frames[i + 1 :]
        if len(subset) < 4:
            continue
        caches = _cache_views(subset)
        p, _, _, _ = _fit_once(frame, caches, locus, half, cfg)
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
    except MetricReconstructionError as e:
        return {"success": False, "measurement_tier": "metric", "method": "multiview_cuboid_fit",
                "reason": e.code.value, "detail": e.detail, "frames_total": frames_total}

    frame = build_frame(bundle)
    if on_plane is not None and on_plane != frame.on_plane:
        if on_plane and bundle.support_plane is None:
            return {"success": False, "measurement_tier": "metric", "method": "multiview_cuboid_fit",
                    "reason": FailureCode.INVALID_SUPPORT_PLANE.value,
                    "detail": "on_plane requested but bundle has no support plane", "frames_total": frames_total}
        up = up_from_gravity(bundle.gravity_world)
        e1, e2 = horizontal_basis(up)
        frame = CuboidFrame(anchor=np.asarray(locus, dtype=float), e1=e1, e2=e2, up=up, on_plane=False)

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
        loo = _leave_one_out(bundle.frames, frame, np.asarray(locus, dtype=float), half, cfg)
    timings["leave_one_out_ms"] = (time.perf_counter() - t2) * 1000

    obs = observability_metrics(bundle, sil["per_frame_iou"])
    mean_boundary_px = float(np.mean(sil["boundary_px"]))
    diag = caches[0].diag if caches else 1.0

    diagnostics: dict[str, Any] = {
        "dof": frame.dof,
        "on_plane": frame.on_plane,
        "parameters": params.as_dict(),
        "optimizer_success": status["optimizer_success"],
        "iterations": status["iterations"],
        "starts": status["starts"],
        "initial_loss": initial_loss,
        "final_loss": final_loss,
        "mean_iou": sil["mean_iou"],
        "min_iou": sil["min_iou"],
        "per_frame_iou": sil["per_frame_iou"],
        "boundary_error_px": mean_boundary_px,
        "parameter_identifiability": ident,
        "leave_one_out_spread": loo,
        "pose_baseline_mm": obs["total_baseline_mm"],
        "view_coverage_deg": obs["max_view_angle_deg"],
        "frames_used": frames_total,
        "timing_ms": timings,
    }

    dims = metres_to_dimensions(params.length, params.width, params.height)
    reason = _gate(sil, ident, loo, mean_boundary_px / diag, cfg)
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


def _gate(sil: dict, ident: dict, loo: dict, boundary_frac: float, cfg: CuboidFitConfig) -> FailureCode | None:
    """The typed failure a cuboid fit must return when the metric dimensions are
    not trustworthy, or ``None`` when every gate passes. Silhouette consistency
    first (bad fit), then identifiability (ambiguous), then stability (unstable)."""
    if (sil["mean_iou"] < cfg.min_mean_iou or sil["min_iou"] < cfg.min_min_iou
            or boundary_frac > cfg.max_boundary_frac):
        return FailureCode.INSUFFICIENT_SILHOUETTE_CONSISTENCY
    if not ident["identifiable"]:
        return FailureCode.AMBIGUOUS_CUBOID_FIT
    spread = loo.get("spread_frac_max")
    if spread is not None and spread > cfg.max_dim_spread_frac:
        return FailureCode.UNSTABLE_CUBOID_FIT
    return None
