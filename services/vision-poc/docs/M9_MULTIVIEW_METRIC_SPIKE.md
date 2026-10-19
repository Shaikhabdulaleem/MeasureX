# M9 — Multi-frame metric reconstruction spike

**Status:** research spike (offline). Not production, not merged, not wired into
Flutter/NestJS/DB/billing/scale. See [`../../docs/ADR_RGB_METRIC_SCALE.md`](../../docs/ADR_RGB_METRIC_SCALE.md).

## Goal

Recover **absolute metric** L × W × H of one carton from:

- multiple RGB frames,
- **known metric camera poses**,
- camera intrinsics,
- object segmentation masks,

**without** using monocular metric depth to establish physical scale. M8 proved
single-frame RGB-only monocular metric depth is ESTIMATE-only (~+50% height,
>+200% L/W on the real carton). M9 gets scale from a real metric baseline (the
camera poses) instead of learned priors.

## Non-goals (this milestone)

Production Flutter/NestJS integration, DB/schema, WMS/Aymakan, billing, Bluetooth
scale, deployment, final UX, custom Android VIO, mandatory LiDAR/mat/marker/
reference object. No ground-truth correction factor anywhere. PR #20 is **not**
merged and M8 is unchanged.

## Coordinate convention (one, everywhere)

```
X_world = T_world_from_camera @ X_camera        # 4x4 homogeneous, metres
```

- Camera frame is OpenCV pinhole: **+X right, +Y down, +Z forward**, matching
  `measurex_vision.geometry.intrinsics` (`u = fx·X/Z + cx`, `v = fy·Y/Z + cy`).
- Camera centre in world = `T_world_from_camera[:3, 3]`.
- `T_camera_from_world = invert_pose(T_world_from_camera)` (`[Rᵀ | −Rᵀt]`, never a
  numeric inverse).
- Projection matrix `P = K · [R|t]_camera_from_world` (3×4).
- **gravity_world** is a unit vector; "up" is its negation. Gravity is
  authoritative for the vertical direction.

Helpers and validation live in [`src/measurex_vision/multiview/camera.py`](../src/measurex_vision/multiview/camera.py).
`camera-to-world` and `world-to-camera` are never mixed implicitly.

## Where metric scale comes from

**Only the camera-pose translations (metres).** The visual hull is carved in
world metres; voxel positions and camera centres share one metric frame. Monocular
depth is not loaded and cannot rescale the result. This is proved by the
**scale-equivariance** test: scale the scene *and* the camera translations by 2×
(masks unchanged) and the recovered dimensions scale by exactly 2× — impossible if
scale came from a learned monocular prior.

## Capture bundle schema (`capture.json`)

Portable, offline, model-independent. The core consumes `ViewFrame` objects, so
masks can be precomputed by any segmenter (or generated analytically in tests).

```json
{
  "schema_version": 1,
  "measurement_tier": "metric",
  "pose_source": "external_metric_pose",
  "pose_convention": "T_world_from_camera",
  "units": "meters",
  "gravity_world": [0, 1, 0],
  "support_plane": {"normal": [0, 1, 0], "offset": 0.0},
  "frames": [
    {
      "frame_id": "000000",
      "image": "frames/000000.jpg",
      "mask": "masks/000000.png",
      "intrinsics": {"fx": 1004.6, "fy": 1004.6, "cx": 480, "cy": 640, "width": 960, "height": 1280},
      "T_world_from_camera": [[...4x4...]]
    }
  ]
}
```

Schema + strict validation: [`schema.py`](../src/measurex_vision/multiview/schema.py).
`support_plane` is optional (see below).

## Visual-hull architecture

Chosen as the primary geometry because cartons are weakly textured, so
feature-only triangulation fails but silhouettes do not.

```
masks + intrinsics + metric poses
  → object locus = nearest point to the central rays       (camera geometry only)
  → conservative metric ROI from mask solid-angles × distance
  → coarse voxel carve over the ROI  (resolution ∝ object)
  → tighten to occupied bounds → fine carve
  → largest connected voxel component (drop stray blobs)
  → gravity-fixed vertical + optional support-plane clip
  → horizontal footprint → convex hull → minimum-area rectangle → L/W
  → vertical extent above support → H
```

- **Carving** ([`visual_hull.py`](../src/measurex_vision/multiview/visual_hull.py)):
  a voxel survives when it projects in front of the camera, inside the image and
  inside the mask for a `consensus` fraction of the frames that can see it.
  `consensus = 1.0` is the true visual hull (intersection); lower it only for
  noisy real masks (it inflates the hull).
- **ROI** is derived from rays/frusta, never from a known carton size, with a hard
  `roi_max_half_extent_m` cap and a `max_voxels` memory guard.
- **Resolution is adaptive** (`coarse/fine_divisions`): voxel size scales with the
  object so relative accuracy is size-independent; `min_voxel_m` floors memory.
- **Geometry** ([`carton.py`](../src/measurex_vision/multiview/carton.py)): gravity
  is the fixed vertical (M8's unconstrained PCA/OBB is **not** reused); L/W from a
  principled minimum-area rectangle (rotating calipers over the convex hull), not
  GT-fit percentiles.

## Support plane (optional, Phase 7)

A carton sits on a table, so no camera sees its underside and an above-only visual
hull cannot cap the bottom face (it leaves a downward cone → inflated height). When
the capture supplies a metric support plane, voxels below it are rejected and H is
the extent **above** the plane. **Metric scale still comes from the poses, never
from the plane.** Gravity remains authoritative for the vertical direction. Without
a support plane, H is the full hull extent and over-reports for above-only
captures — a documented limitation, not a silent fallback.

## Quality gate (geometric observability, not a model score)

[`quality.py`](../src/measurex_vision/multiview/quality.py). The old monocular
confidence value is **not** reused. Quality derives from: frame count, metric
baseline, viewpoint diversity (max pairwise view angle at the object), per-frame
silhouette agreement, and **leave-one-out** stability (reconstruct repeatedly
dropping one frame; report the relative L/W/H spread). Thresholds are explicit and
object-independent.

## Failure modes (typed — never a silent downgrade)

`metric_pose_unavailable`, `invalid_pose`, `invalid_intrinsics`,
`insufficient_frames`, `insufficient_baseline`, `insufficient_view_coverage`,
`invalid_gravity`, `mask_mismatch`, `reconstruction_failed`,
`insufficient_hull_support`. A METRIC request with no metric pose source fails with
`metric_pose_unavailable`; it never silently runs monocular depth and calls the
output METRIC.

## Synthetic validation

Analytic cuboid captures with exact poses; for a convex solid the silhouette is
exactly the convex hull of the projected vertices, so masks need no renderer or
model ([`synthetic.py`](../src/measurex_vision/multiview/synthetic.py)).

Reproduce:

```bash
python scripts/m9_synthetic_proof.py --out outputs/m9_proof
```

Latest run — 5 cartons × 3 independent sweeps (varied yaw / world origin / seed /
mild pose noise), 48 frames each, exact metric poses, adaptive resolution
(`fine_divisions=90`). Representative sweep per carton shown; full 15-row table in
`scripts/m9_synthetic_proof.py` output:

| carton | GT L/W/H (mm) | pred L/W/H (mm) | err% L/W/H | quality |
|---|---|---|---|---|
| small parcel | 200/150/120 | 206/155/127 | +3.0 / +3.3 / +5.8 | medium |
| real carton  | 345/290/245 | 351/291/253 | +1.7 / +0.3 / +3.3 | medium |
| medium carton| 600/400/350 | 614/407/351 | +2.3 / +1.8 / +0.3 | medium |
| large carton | 800/600/500 | 814/620/513 | +1.8 / +3.3 / +2.6 | medium |
| tall narrow  | 250/240/800 | 257/248/821 | +2.8 / +3.3 / +2.6 | medium |

**Aggregate over all 15 sequences / 45 dimensions:** accepted **15/15**; absolute
% error **median 3.3%, P90 6.6%, P95 7.8%, max 10.0%**. Errors are a consistent
small *over*-estimate (visual hull is a superset), never a scale error.

**Metric-scale equivariance (the key proof):** scaling the scene **and** the camera
translations by 2× (masks byte-identical) gave reconstructed ratios
**2.00 / 2.00 / 2.00** — scale is fixed by the poses, not a monocular prior.

**Typed failures:** `insufficient_baseline` (identical poses),
`insufficient_view_coverage` (3° arc), `reconstruction_failed` (voxel cap),
`metric_pose_unavailable` (no-pose provider) — all returned correctly, no
fabricated dimensions.

Interpretation: on exact poses the error is dominated by (a) perspective
visual-hull looseness, which tightens with denser/farther view coverage, and (b)
voxel quantisation (~one voxel per dimension). It is **not** a scale error —
scale-equivariance is exact. Small dimensions (≲150 mm) carry the largest relative
error at a fixed capture distance; a guided capture frames the carton to keep the
relative voxel size small.

## Real-capture validation plan (Phase 12)

Dataset layout; **ground truth is read only by the evaluator**
([`evaluate.py`](../src/measurex_vision/multiview/evaluate.py)), never by the
reconstruction core:

```
dataset/carton_XXX/{capture.json, frames/, masks/, ground_truth.json}
```

Pre-declared M9 research gate (not the production SLA): ≥5 physical cartons × 3
sweeps (≥15 sequences); target **median absolute % error per dimension ≤ 5%**, with
no more than 10% per dimension on the great majority of accepted captures; report
mm errors too. If it fails, record the failure honestly.

## ARCore / ARKit boundary & A16 4G uncertainty

The core depends on the abstract `MetricPoseProvider`
([`pose_provider.py`](../src/measurex_vision/multiview/pose_provider.py)), never on
ARCore directly. The test device **Samsung Galaxy A16 4G (SM-A165F/DS)** is *not*
confirmed on the ARCore certified-device list (only the A16 **5G** is currently
listed). So a provider must honestly return `metric_pose_available() == False` when
no VIO is present, and the engine fails `metric_pose_unavailable`. Future adapters
(`ARCoreMetricPoseProvider`, `ARKitMetricPoseProvider`) are documented stubs — not
faked. The only implemented provider is `OfflineManifestProvider`. Custom VIO is
out of scope.

## Exact commands

```bash
# reconstruct a capture bundle
python -m measurex_vision.cli multiview --manifest path/to/capture.json --output outputs/m9_run --debug

# synthetic proof (table + scale + failures + debug artifacts)
python scripts/m9_synthetic_proof.py --out outputs/m9_proof

# tests + lint (no GPU / models / network)
ruff check .
pytest -q
```

## Known limitations

- Above-only captures need the support plane to bound H (documented).
- Visual hull over-reports without near-complete angular coverage; a near-horizontal
  sweep ring is needed to cap the top tightly.
- CPU dense voxel carve — correctness first; no GPU/octree yet (not the 3 s target).
- Masks are trusted inputs here; segmentation quality is validated separately.
- Real-device metric poses are not yet collected — the real gate is pending.
