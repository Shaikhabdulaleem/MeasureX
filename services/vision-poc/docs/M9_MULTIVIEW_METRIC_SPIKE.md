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
  a voxel survives when it is seen by at least `min_usable_views` frames (default
  **2**) and projects inside the mask for a `consensus` fraction of the frames that
  can see it. `consensus = 1.0` is the true visual hull (intersection); lower it
  only for noisy real masks (it inflates the hull). The `min_usable_views` rule is
  GT-independent: a voxel constrained by a single camera ray is unobservable in
  depth along that ray, so one-view survivors cannot belong to a metric hull.
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

**The gate is enforced, not advisory.** A METRIC result is refused
(`success=False`) when silhouette consistency is below `min_silhouette_consistency`
(→ `insufficient_silhouette_consistency`) or the leave-one-out spread exceeds
`max_dim_spread_frac` (→ `unstable_reconstruction`). Diagnostic dimensions are
retained in the failure payload (`debug_dimensions_mm`) for inspection, but the
public result never reports dimensions on weak geometry. (Leave-one-out spread is a
*necessary* not *sufficient* check — see the short-sweep finding below, where a
tight ring produces a low spread yet a grossly wrong length.)

## Capture-manifest contract (strict)

[`load_bundle`](../src/measurex_vision/multiview/schema.py) raises a typed
`ContractError` for any bundle that is not a well-formed METRIC capture: wrong
`schema_version`, `measurement_tier != "metric"`, wrong `pose_convention`/`units`,
a non-list/empty `frames`, or a missing/dimension-mismatched image or mask file. An
ESTIMATE manifest is rejected here — never silently accepted as METRIC. An optional
`support_plane` is validated (finite non-zero normal, finite offset, within 45° of
gravity-up — a floor, not an arbitrary tilt).

## Failure modes (typed — never a silent downgrade)

`metric_pose_unavailable`, `invalid_pose`, `invalid_intrinsics`,
`insufficient_frames`, `insufficient_baseline`, `insufficient_view_coverage`,
`invalid_gravity`, `invalid_support_plane`, `mask_mismatch`,
`reconstruction_failed`, `insufficient_hull_support`, `unstable_reconstruction`,
`insufficient_silhouette_consistency`. A METRIC request with no metric pose source
fails with `metric_pose_unavailable`; it never silently runs monocular depth and
calls the output METRIC.

## Synthetic validation

Analytic cuboid captures with known poses; for a convex solid the silhouette is
exactly the convex hull of the projected vertices, so masks need no renderer or
model ([`synthetic.py`](../src/measurex_vision/multiview/synthetic.py)). The proof
reports four **separate** experiments — the exact-pose aggregate is never mixed
with pose-noise or short-sweep results.

Reproduce (numbers below, `fine_divisions=90`):

```bash
python scripts/m9_synthetic_proof.py --out outputs/m9_proof
```

### 1. Exact-pose, full-coverage sanity test (NOT the warehouse workflow)

5 cartons × 3 independent sweeps, all `pose_noise_deg = 0`, 48 frames each (3
elevation rings × 330° azimuth). This is a generous geometry check.

**Aggregate (15 sequences / 45 dimensions):** accepted 15/15; absolute % error
**median 3.33%, P90 6.60%, P95 7.76%, max 10.00%**. Errors are a consistent small
*over*-estimate (the visual hull is a superset), never a scale error.

> **The exact-pose ≤2% gate did NOT pass.** The current generic visual hull sits at
> ~3.3% median on exact poses, not ≤2%. This is reported honestly; no correction
> factor, multiplier or carton-specific threshold is applied to reach a target.

### 2. Pose-noise robustness (reported separately)

Same full-coverage geometry, controlled per-frame rotation perturbations
(`pose_noise_deg` = 0.15 / 0.30 / 0.50). Aggregate: accepted 15/15; **median 2.62%,
P90 5.00%, P95 6.00%, max 7.50%**. Modest pose noise does not destabilise the
result (it slightly averages out the quantisation asymmetry). Kept apart from the
exact-pose aggregate above.

### 3. Practical short-sweep matrix (real carton, one continuous pass)

One hand-held pass — a single ring with a modest elevation ramp — over a small
azimuth span, which is what the warehouse workflow actually produces. Frames
{6,8,10,12} × azimuth {30,45,60,90,120}°.

**This capture pattern is not viable for a generic visual hull.** Sweeps with ≤8
frames are rejected (`unstable_reconstruction`). The sweeps that *are* accepted
report a low leave-one-out spread (0.06–0.09) yet over-estimate **length by
~+100–110%**: a single narrow ring cannot bound the box along the axis tangential
to the sweep, and dropping one frame from a tight ring barely moves the (wrong)
hull — so leave-one-out does not catch it. Width stays good (±8%), height
over-reports (+25–34%, no top-down view).

**Conclusion: a near-360° orbit is required to constrain a generic visual hull;**
the practical short sweep fundamentally under-determines length. This is stated
plainly rather than hidden by requiring a full orbit in the gate.

### 4. Resolution convergence & voxel quantisation (real carton, exact poses)

`fine_divisions` 60 → 160 (voxel 5.98 → 2.24 mm, 0.12M → 2.2M voxels):

| fine_divisions | voxel mm | abs err L/W/H mm | max abs % |
|---|---|---|---|
| 60  | 5.98 | 2/3/10 | 4.1% |
| 90  | 3.99 | 6/1/8  | 3.3% |
| 120 | 2.99 | 5/3/7  | 2.9% |
| 160 | 2.24 | 3/4/7  | 2.9% |

Error **does not converge to zero** — it floors at ~2.9%. At the finest voxel the
residual in voxels is L 1.3, W 1.8, **H 3.1**. Length/width are ~1–2 voxels
(quantisation + hull looseness); the height residual is ~3 voxels and does **not**
shrink with resolution, so it is **visual-hull/coverage geometry** (the top face is
only partially capped without a top-down view), not voxel quantisation. This is the
central limitation finding: beyond ~3 mm voxels, refining resolution buys nothing.

### Metric-scale equivariance (the key metric proof)

Scaling the scene **and** the camera translations by 2× (masks byte-identical) gave
reconstructed ratios **2.00 / 2.00 / 2.00** — scale is fixed by the poses, not a
monocular prior.

### Typed failures

`insufficient_baseline` (identical poses), `insufficient_view_coverage` (3° arc),
`reconstruction_failed` (voxel cap), `metric_pose_unavailable` (no-pose provider),
`unstable_reconstruction` (quality gate) — all returned correctly, no fabricated
dimensions.

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

- **Exact-pose accuracy floors at ~3%, not ≤2%** — the dominant residual is
  visual-hull/coverage geometry (height ~3 voxels over at any resolution), not
  quantisation. Refining the voxel below ~3 mm buys nothing.
- **A practical short sweep cannot constrain a generic visual hull** — a single
  narrow ring under-determines length (~+100%); a near-360° orbit is required.
- Above-only captures need the support plane to bound H (documented).
- CPU dense voxel carve — correctness first; no GPU/octree yet (not the 3 s target).
  The full proof script runs ~7–8 min on CPU at `fine_divisions=90` plus the
  convergence sweep; it is a research artifact, not run in CI.
- Masks are trusted inputs here; segmentation quality is validated separately.
- Real-device metric poses are not yet collected — the real gate is pending.

## Recommended next architecture step (NOT implemented in this spike)

The limitation is intrinsic to a *generic* visual hull: it is the largest solid
consistent with the silhouettes, so a sparse/narrow capture leaves it loose exactly
where no silhouette cuts it. But MeasureX measures **boxes**. The next research
option is a **metric-pose-constrained parametric cuboid fit** to the multi-view
silhouettes — fit the 9 DOF of an oriented box (centre, gravity-aligned yaw, L/W/H)
so its projection matches every mask, with metric scale still fixed by the poses.
A cuboid prior is constrained by far fewer, far-apart views than a free hull, so it
should tolerate a practical short sweep and remove the top-cap/length looseness.
**This patch deliberately does not implement cuboid fitting** — it first establishes
the visual-hull limitation above. No change to the measurement method was made to
hit a target.
