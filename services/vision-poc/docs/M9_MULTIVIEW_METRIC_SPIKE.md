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
`insufficient_silhouette_consistency`. The parametric cuboid fit adds
`cuboid_fit_failed` (optimiser did not converge), `ambiguous_cuboid_fit` (a fitted
DOF is unobservable), `unstable_cuboid_fit` (leave-one-out spread too large), and
`insufficient_image_resolution` (object too small in pixels). A METRIC request with
no metric pose source fails with `metric_pose_unavailable`; it never silently runs
monocular depth and calls the output METRIC.

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

**Conclusion (evidence-accurate):** the 30–120° practical short sweeps tested here
were insufficient for the generic visual hull; the 330° full-coverage benchmark was
substantially better (median ~3.3% vs grossly wrong length). The 120–330°
intermediate angular coverage was **not** exhaustively tested, so this does not
establish that a near-360° orbit is mathematically *required* — only that the tested
short sweeps under-determine a generic hull's length. Either way the warehouse UX
cannot depend on a near-full orbit, which motivates the carton-prior fit below.

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
- **A practical short sweep cannot constrain a *generic* visual hull** — the tested
  30–120° narrow rings under-determine length (~+100%); 330° full coverage was
  substantially better (120–330° not exhaustively tested). The parametric cuboid fit
  below removes this limitation on the same short sweeps.
- Above-only captures need the support plane to bound H (documented).
- CPU dense voxel carve — correctness first; no GPU/octree yet (not the 3 s target).
  The full proof script runs ~7–8 min on CPU at `fine_divisions=90` plus the
  convergence sweep; it is a research artifact, not run in CI.
- Masks are trusted inputs here; segmentation quality is validated separately.
- Real-device metric poses are not yet collected — the real gate is pending.

## Parametric cuboid-fit experiment (the carton prior)

The limitation above is intrinsic to a *generic* visual hull: it is the largest
solid consistent with the silhouettes, so a sparse/narrow capture leaves it loose
exactly where no silhouette cuts it. But MeasureX measures **boxes**, so this
experiment replaces the free-form hull hypothesis with a **metric-pose-constrained
parametric cuboid fit**: fit the few parameters of a gravity-aligned box so its
projected silhouette matches every mask. The visual hull is kept as the diagnostic
baseline/comparison method — it is not deleted or replaced.
[`cuboid_fit.py`](../src/measurex_vision/multiview/cuboid_fit.py).

### Degrees of freedom (corrected)

A general oriented cuboid has 9 DOF (translation 3 + rotation 3 + dimensions 3). But
**gravity fixes roll and pitch**, so the box only yaws:

| configuration | parameters | DOF |
|---|---|---|
| no support plane | centre (3) + yaw (1) + L/W/H (3) | **7** |
| bottom face on a known metric support plane | horizontal centre (2) + yaw (1) + L/W/H (3) | **6** |

The earlier text calling this a "9 DOF" fit was wrong; the lowest physically
justified parameterisation is 6 DOF (plane) / 7 DOF (no plane), and both are
implemented and reported. **Metric scale still comes only from the camera-pose
translations** — the support plane supplies orientation and one vertical datum, not
a scale, and must never introduce a correction factor.

### Parameterisation, objective and optimiser

- **Model:** `CuboidParameters` = centre (u, v [, w]) + yaw + L/W/H in a
  gravity-aligned frame; the bottom face lies on the support plane in the 6-DOF
  case. `length > 0, width > 0, height > 0`; the final output is canonicalised to
  `length >= width` with yaw wrapped into `[-90°, 90°)` (resolving the natural
  `(L, W, yaw) ≡ (W, L, yaw+90°)` symmetry so equivalent solutions are not treated
  as different failures).
- **Objective (silhouette agreement, GT-free):** per frame, the candidate box is
  projected and its exact convex silhouette is compared to the observed mask by
  **IoU** (computed analytically as a convex-polygon intersection, not rasterised in
  the loop), plus small mask-centroid and boundary regularisers. The centroid term
  compares the **true polygon-area centroid** of the predicted silhouette to the
  mask's area centroid (same geometric quantity on both sides — not the mean of the
  projected vertices). The boundary term is a true **point-to-contour** distance
  (each vertex to the nearest edge of the other polygon), not a vertex-to-vertex
  nearest distance. IoU is symmetric — an oversized box spills outside the mask and
  is penalised — unlike the hull's "fraction of surviving voxels inside the mask".
  The scoring primitives run as scalar Python over the ≤8-vertex polygons (~10× the
  array version) so the full grid is tractable; the maths is unchanged (the unit
  tests lock it).
- **Optimiser:** a deterministic, hard-bounded pure-NumPy pattern search
  (Hooke–Jeeves) from several generic yaw/scale starts. Initialisation (centre, scale,
  yaw) comes from the multi-view mask locus and the mask-solid-angle ROI — **never**
  from ground truth; bounds come from capture geometry, not a known box size. The
  optimiser reports its **real termination** — `converged` (the step shrank below
  the tolerance), `hit_max_iter`, `final_step_size`, `at_parameter_bound`,
  `iterations` — and a fit that stops only because it hit the iteration cap is **not**
  reported as a successful optimiser result (it fails `cuboid_fit_failed`). A bound
  contact is recorded but does not by itself fail the fit.
- **Observability gates (typed failures, never a silent bad dimension):**
  `cuboid_fit_failed` (optimiser did not converge), `insufficient_silhouette_consistency`
  (mean/min IoU or boundary residual), `ambiguous_cuboid_fit` (perturbing **any
  fitted DOF** — centre u/v[/w], yaw, L/W/H, each with a parameter-appropriate
  perturbation — barely changes the loss → a flat, unobservable direction; yaw is
  exempt for a near-square footprint, where the L/W + 90° symmetry makes it
  unobservable but harmless), `unstable_cuboid_fit` (leave-one-frame-out L/W/H spread
  too large), and an optional `insufficient_image_resolution` (observed mask bbox
  below a GT-free pixel floor — off by default on the deliberately tiny synthetic
  grid, calibrated from the ±1 px quantisation study for real captures). **The
  leave-one-out refit is leak-free:** every subset rebuilds its own object locus,
  ROI and cuboid frame from only the frames it keeps, so the omitted frame
  contributes nothing. Thresholds are explicit, image-space and object-independent
  (not tuned per carton).

### Result: the full spec grid (400 exact-pose sequences, complete gate)

The headline numbers below come from the **full 400-sequence spec grid** (5 sizes ×
4 yaws × frames {6,8,10,12} × spans {30,45,60,90,120}°) with the **complete metric
gate including leave-one-out** — not a hand-picked quick grid. A bounded LOO (3
leak-free refits) and the GT-free gates decide acceptance; ground truth is compared
only after the fact.

> Reproduce (research artifact, not run in CI — the pure-NumPy optimiser is ~an hour
> for the full grid, not the warehouse speed target):
>
> ```bash
> python scripts/m9_cuboid_proof.py           # quick developer grid (fast)
> python scripts/m9_cuboid_proof.py --full    # the full 400-sequence spec grid
> ```

**Aggregate:** accepted **303/400 (75.7%)**. Acceptance by gate stage (GT-free):
optimizer-converged 396, silhouette 399, identifiability 384, leave-one-out 310,
**final metric 303**.

**Per-dimension `|error %|` over accepted sequences:**

| dim | P50 | P90 | P95 | max |
|---|---|---|---|---|
| length | 0.29 | 2.0 | 3.0 | 25.12 |
| width  | 0.34 | 2.0 | 2.0 | 14.17 |
| height | 0.20 | 0.83 | 0.86 | 6.40 |
| pooled | 0.33 | 2.0 | 2.0 | 25.12 |

- **The per-dimension median ≤ 2% research gate PASSES** (median |L| 0.29%, |W|
  0.34%, |H| 0.20% — each independently ≤ 2%). Median `|err%|` by size: large 0.20,
  medium 0.17, real 0.34, tall-narrow 0.25, **small parcel 1.33** (the small parcel
  at the 200 px grid image is the worst); by yaw: 0° 0.34, 20° 0.34, 45° 0.29, 70° 0.40.
- **The preferred P95 ≤ 5% per dimension holds pooled**, but **not uniformly across
  every capture configuration** (see the viable-sweep table — some narrow/few-frame
  groups blow past it).

**Research false accepts (the gate is NOT perfect).** GT is used only by the
evaluator here. Of the 303 accepted sequences: **15 have a dimension error > 5%, 4 >
10%, and 1 > 20%** (worst accepted error **25.12%** — the small parcel at 200 px, a
resolution artifact). **So the quality gates do NOT catch every large synthetic
error.** The honest claim is *"most large errors are rejected"*, not *"bad results
are never silently accepted"*.

**Robustly viable capture configurations.** Grouping every `(frames, span)` across
all sizes and yaws, a configuration is viable only if the **whole group** is 100%
accepted, has 0 false accepts, and P95 ≤ 5% per dimension. **The only robustly viable
sweep is 8 frames over 120°** (the previous "6 frames / 45°" claim was a single lucky
row, not a grouped result). Narrower/fewer-frame sweeps have lower acceptance and
occasional large errors.

**Visual hull vs cuboid fit on the *same* short sweeps** (err % L/W/H) — the carton
prior removes the hull's length over-estimate on exactly the captures that defeat it:

| frames | span | visual hull | cuboid fit |
|---|---|---|---|
| 8  | 45°  | **+120 / +17 / +25** | −0.3 / −0.3 / 0.0 |
| 10 | 60°  | **+99 / +9 / +22**   | 0.0 / −0.3 / −0.4 |
| 10 | 90°  | **+66 / +12 / +20**  | −0.3 / −0.3 / 0.0 |
| 12 | 120° | **+29 / +11 / +18**  | 0.0 / −0.3 / −0.4 |

**6-DOF support-plane vs 7-DOF free fit.** Both recover to ~0.4% on 10f/90° and
12f/120°; on an 8f/60° sweep the 6-DOF plane fit failed (`cuboid_fit_failed`, did not
converge) while the 7-DOF free fit succeeded. **MeasureX does not strictly require a
detected support plane** — the free fit is at least as robust on these sweeps.

**Image-resolution sensitivity (200 / 480 / 960 px, FOV held constant).** This is the
cause of the large small-parcel errors:

| case | 200 px (bbox, err%, ±1px unc mm) | 480 px | 960 px |
|---|---|---|---|
| small parcel | bbox 27, L −1.5/W −2.0, unc 11.5/9.5/4.5 | bbox 67, ≤0.5%, unc 5.0/4.5/2.0 | bbox 133, 0%, unc 2.5/2.0/1.0 |
| real carton  | bbox 56, ≤0.3%, unc 10.5/9.0/5.0 | bbox 133, 0%, unc 4.5/3.5/2.0 | bbox 266, ≤0.6%, unc 2.5/2.0/1.0 |
| tall narrow  | bbox 35, ≤0.8%, unc 11/13.5/6.5 | bbox 85, 0%, unc 4.5/6.0/2.5 | bbox 170, ≤0.4%, unc 2.0/3.0/1.5 |

The **GT-free ±1 px quantisation uncertainty** (perturb each silhouette by ±1 px,
refit) falls ~4–5× from 200→960 px and tracks the true error — a real observability
diagnostic for deciding when a projected object is too small to measure (hence the
optional `insufficient_image_resolution` gate). The 200 px small-parcel case is the
25% outlier's origin; the algorithm was **not** changed to fit it.

- **Support-plane error sensitivity** (poses exact): plane **offset** 1/3/5/10 mm →
  max dim error 0.6/1.2/1.6/**3.7**% (H is the most affected, as expected — it is
  measured from the plane). Plane **tilt** 0.1/0.25/0.5/1.0/2.0° → 0.3/0.6/0.3/0.7/**2.3**%.
- **Metric-pose scale bias** (correlated, NOT compensated): a ±0.5/1/2% scale on all
  camera translations propagates **~1:1** into dimensions (−2% → −2.0…−2.4%; +2% →
  +1.7…+2.0%). This defines the accuracy requirement for the future metric-pose
  provider: its metric scale must be good to ≈ the target dimensional tolerance.
- **Realistic trajectory variation** (non-uniform spacing, radial/elevation/lateral
  jitter, aim off-centre, and all combined — poses known exactly): every variant
  stays at 0.3–0.4% max error, i.e. unchanged from the ideal arc. The fitter consumes
  the real poses; it does not rely on a smooth centred orbit.
- **Mask-error robustness:** clean / undersized / shifted / one-missing frame all
  recovered to ≤0.4%; an **oversized or heavily-noisy** mask is **rejected typed**
  (`insufficient_silhouette_consistency`).
- **Pose-noise degradation** (reported separately from exact-pose): rotation 0.1→1.0°
  → max dim error 0.3→2.4%; translation 1→10 mm → 0.4→1.7%. This is the pose quality a
  future ARCore/ARKit/VIO source would need to meet.
- Metric-scale equivariance still holds (2× scene + 2× camera translations → 2.00×
  dimensions).

### Honest scope

The cuboid fit is a **synthetic exact-mask / exact-pose** proof. The masks are
generated from the **same ideal cuboid camera model the fitter optimises**, so this
is a mathematical / implementation proof — it is **not** evidence of real-world
segmentation accuracy, and it does **not** show the warehouse workflow is ready. No
ground truth enters the fit, no correction multiplier is applied, and no threshold is
tuned to a carton.

What it does and does not establish, honestly:

- **Does:** given exact metric poses and exact masks, the carton prior removes the
  generic hull's short-sweep length over-estimate (≈+100% → ≈0%); the per-dimension
  median error is ≤ 2%; mask/pose/plane/scale/trajectory perturbations behave as a
  correct geometry would; metric scale comes only from the poses.
- **Does not:** it does not prove real-device accuracy, and **the quality gates are
  not a guarantee** — on the full grid 15 accepted sequences still exceeded 5% error
  (one 25%), driven mainly by low image resolution on the smallest parcel. A real
  deployment needs adequate resolution (≥ ~480 px object projection here), a robust
  capture configuration (only 8f/120° was robustly viable across all sizes/yaws), and
  metric-pose scale good to ≈ the target tolerance (scale bias propagates ~1:1).

Real-capture validation (masks from SAM 2, metric poses from ARCore/ARKit VIO)
remains the pending gate — see the ARCore/ARKit boundary note above. PR #20 is not
merged and M8 is unchanged.
