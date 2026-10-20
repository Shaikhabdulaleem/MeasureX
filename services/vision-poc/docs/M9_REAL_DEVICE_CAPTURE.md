# M9 Real-Device Capture (research spike)

**Status:** research data-capture stage. This is **not** production integration and
**not** a warehouse SLA. The phone app is a *data-capture instrument only* — it
records real metric pose data and computes no dimensions. All measurement happens
offline with the existing Grounding DINO / SAM 2 + M9 parametric cuboid fitter.

> Synthetic M9 (frozen, PR #21) proved the method works on exact poses/masks. This
> stage asks a narrower physical question: **are real ARCore VIO camera poses +
> real RGB silhouettes enough to recover a carton's metric dimensions?** M8 already
> showed single-frame monocular metric depth is not billing-grade; ARCore depth and
> monocular depth are used **nowhere** here for scale.

## Objective

Collect, from an Android phone with ARCore:

- real RGB frames (native pixel orientation),
- metric camera poses (ARCore VIO, converted to the M9 convention),
- per-frame camera intrinsics (CPU image intrinsics),
- gravity, and an optional metric support plane,

then process them offline:

```
ARCore capture  →  raw_capture.json (+ frames/)   [phone, no dimensions]
                →  validate raw geometry           [m9_validate_raw_capture.py]
                →  select exactly 8 frames          [m9_select_real_frames.py]
                →  segment to strict capture.json   [m9_prepare_real_capture.py]
                →  7-DOF + 6-DOF cuboid fit          [m9_run_real_capture.py]
                →  evaluate vs ground truth          [m9_evaluate_real_results.py]
```

## Android / ARCore architecture

Isolated research app at [`tools/m9-capture-android/`](../../../tools/m9-capture-android)
— Kotlin + Android SDK + Google ARCore SDK. **No** backend, auth, database, WMS,
Bluetooth, billing or production UI, and it is **not** wired into the production
MeasureX Flutter app. Its only job is to export valid metric-pose data.

Pure, unit-tested logic (runs on the JVM, no device):

| File | Responsibility |
|------|----------------|
| `Mat4.kt` | 4×4 math; **column-major → row-major** de-serialisation; rigid inverse; determinant |
| `PoseConvention.kt` | ARCore → M9 pose/gravity/support-plane conversion; azimuth |
| `RawManifest.kt` | `raw_capture.json` data model + hand-rolled JSON writer |
| `CaptureController.kt` | candidate eligibility, azimuth coverage, completion |

Device/GL glue (on-device only): `ArCoreAvailabilityChecker`, `BackgroundRenderer`,
`YuvToRgb`, `Exporter`, `CaptureActivity`.

## ARCore availability (the device rule)

Not every Android phone supports ARCore — the current test device (Samsung Galaxy
A16 4G / SM-A165F) is **not** on the certified list. At launch the app calls
`ArCoreApk.checkAvailability` and handles `SUPPORTED_INSTALLED`,
`SUPPORTED_NOT_INSTALLED`, `SUPPORTED_APK_TOO_OLD`, `UNSUPPORTED_DEVICE_NOT_CAPABLE`
and `UNKNOWN_CHECKING`. If unsupported it shows a blocking message —

> *Metric pose unavailable on this device. M9 metric capture cannot run.*

— and **never** falls back to monocular depth or calls an RGB-only result metric.
Installable-but-missing ARCore follows the official `requestInstall` flow.

## Exact ARCore → M9 coordinate transform

M9 pose convention (fixed everywhere, see
[`multiview/camera.py`](../src/measurex_vision/multiview/camera.py)):

```
X_world = T_world_from_camera @ X_camera     # metres
```

camera axes are OpenCV/pinhole: **+X right, +Y down, +Z forward**. ARCore's camera
axes are OpenGL-style: **+X right, +Y up, −Z forward**. They differ by a 180°
rotation about the camera X axis:

```
                       ⎡ 1  0  0  0 ⎤
C_arcore_from_m9_camera=⎢ 0 -1  0  0 ⎥        (det = +1, a proper rotation)
                       ⎢ 0  0 -1  0 ⎥
                       ⎣ 0  0  0  1 ⎦

T_world_from_camera_M9 = T_world_from_camera_ARCore @ C_arcore_from_m9_camera
```

**Column-major gotcha.** `Pose.toMatrix()` writes an OpenGL **column-major** float
array: element `(row, col)` is at index `col*4 + row`. Serialising that array as
JSON rows would transpose the pose. `Mat4.fromColumnMajor` de-column-majors it into
a mathematical row-major matrix *first*; the frame conversion is applied *then*; the
result is serialised as ordinary row-major nested arrays.

Mandatory, deterministic test (`PoseConventionTest`): a point 1 m in front of the
ARCore camera (`[0, 0, −1]` in ARCore camera coords) maps to `[0, 0, +1]` in the M9
camera frame (depth > 0, projects at the principal point); `det R = +1`;
`T_camera_from_world @ T_world_from_camera = I`.

## Gravity convention

M9's `gravity_world` is the direction gravity **points**. ARCore world is
gravity-aligned with **+Y up**, so:

```
gravity_world ≈ [0, -1, 0]        M9 up = -gravity_world = +Y
```

Do not invert it. The app writes `gravity_world = [0, -1, 0]`.

## Image / intrinsics convention

For every saved frame the intrinsics are the **CPU image** intrinsics
(`Camera.getImageIntrinsics()`), never the GPU texture intrinsics. The saved JPEG is
the camera's **native pixel orientation** — **no rotate, no mirror, no crop, no
resize** — so stored `width/height/fx/fy/cx/cy` describe exactly the saved pixels.
The preview may be rotated for the user independently. As a runtime guard the app
rejects any candidate whose CPU image grid (`image.width/height`) does not equal its
intrinsics grid (`imageDimensions`) and counts it in `rejected_dim_mismatch` — a
cheap trap for a native orientation/rotation bug. `diagnostics.json` records
orientation context only: `display_rotation`, CPU image and intrinsics width/height,
`camera_id` and `sensor_orientation_deg` (the chosen physical camera's sensor
mounting rotation when the platform exposes it, else `null` — never fabricated).
YUV_420_888 → RGB respects each plane's `rowStride`/`pixelStride` (`YuvToRgb.kt`).

## Camera config

Supported configs are enumerated before the session starts; the app prefers a stable
30 FPS config with the highest practical CPU image resolution and records the chosen
`cpu_image_width/height`, FPS and camera id. No production resolution threshold is
set yet — but note synthetic research showed low object-pixel coverage drives error,
so keep the carton large in frame.

## Timestamp synchronisation

Each saved frame records `frame_timestamp_ns` (ARCore `Frame.getTimestamp`) and
`image_timestamp_ns` (the acquired CPU `Image.getTimestamp`) and their delta. ARCore
delivers the CPU image for the frame it came from, so the delta is ~0; a candidate
whose delta exceeds 5 ms is rejected rather than pairing a pose with the wrong image.

## Raw capture format (`raw_capture.json`)

`capture_type: "m9_real_raw"` — **no masks, no dimensions** (distinct from the strict
`capture.json`, `measurement_tier: "metric"`, that the fitter consumes). Fields:
`schema_version`, `capture_type`, `pose_source`, `pose_convention`
(`T_world_from_camera`), `camera_convention` (`opencv_x_right_y_down_z_forward`),
`units` (`meters`), `gravity_world`, `device`, `guidance_target_world`,
`support_plane` (nullable), and `frames[]` each with `frame_timestamp_ns`,
`image_timestamp_ns`, `image`, `intrinsics{fx,fy,cx,cy,width,height}`,
`T_world_from_camera` (row-major 4×4), `tracking_state`, `guidance_angle_deg`,
`camera_distance_to_target_m`.

## Capture flow and frame eligibility

A candidate is saved only when tracking state is `TRACKING`, a new CPU image is
available, timestamps are paired, and the viewpoint is ≥ ~8° from the previous
candidate (so near-duplicate views are not repeated).

On-device completion requires **≥ 12 candidates across ≥ 125° coverage**
(`targetCoverageDeg`) — a deliberate margin above the **120° offline research
minimum** that the raw validator and frame selector still enforce, so selection has
slack without moving the research gate. Sweep 12–20 candidates (start ~60° to one
side, move smoothly across the front, finish ~65° on the other side; keep the whole
carton visible; never walk behind it). The app shows tracking status, candidate
count, coverage, progress and instructions — and **never** displays an estimated
dimension.

## New sweep = new ARCore session

**NEW SWEEP** really recreates the session: the old `Session` is paused, closed and
replaced with a freshly created and configured one (new `session_id`, recorded in
`diagnostics.json` with `sweep_index`), on the GL thread. The three sweeps therefore
initialise VIO — world origin and metric scale — independently; poses are never
averaged across sessions.

## Target / support anchor

The user aims a centre reticle at the carton base and taps **SET CARTON TARGET**; an
ARCore hit test creates a real `Anchor` used only for sweep guidance and view-angle
maths — it imposes no carton dimensions. The anchor is detached on NEW SWEEP and on
exit. `guidance_target_world` is the anchor's pose sampled on the render thread at
the latest tracked frame before EXPORT, in the same world frame as the camera poses.
If the hit is on a `HORIZONTAL_UPWARD_FACING` plane, that plane is also exported as
the optional metric `support_plane` (`normal · X + offset = 0`, unit normal oriented
gravity-up, `offset = -normal·P`, world metres); the raw validator requires
`normal · up ≥ cos 45°`, so a downward (sign-flipped) normal fails fast. A
feature-point-only hit is a guidance target but **not** a support plane. The support
plane never supplies metric scale — scale is from the camera-pose translations.

## Export waits for completed image writes

JPEG compression runs off the GL thread, so EXPORT must not race it. Every accepted
candidate's write is tracked; **EXPORT stays disabled while any write is pending or a
referenced image failed**, and the `raw_capture.json` / ZIP are written only after a
final check that every referenced frame exists on disk and is non-empty. A failed
write is dropped from both the manifest and the capture controller (so it is never a
valid manifest frame) and capture re-opens to replace it with another candidate.

## Offline frame selection

`m9_select_real_frames.py` is GT-free: it computes each camera's azimuth around the
guidance target (gravity-up), takes the best contiguous ≥120° arc, and selects 8
approximately evenly spaced positions across it, preserving chronological sweep
order. Frames are never selected by resulting dimension accuracy.

## Segmentation preparation

`m9_prepare_real_capture.py` runs Grounding DINO (prompt `"cardboard box."`) then
SAM 2 on each selected frame, requiring exactly one strong target and a clean,
on-frame, reasonably sized mask. Failures are recorded as typed frame failures — a
mask is never fabricated. Debug overlays (`overlays/overlay_<id>.jpg`) and
`segmentation_diagnostics.json` (detector score, mask area ratio, bbox px, border
contact) are written for every frame. Output is the strict `capture.json` with masks,
intrinsics, poses, gravity and the optional support plane. No monocular depth.

## 6-DOF vs 7-DOF evaluation

`m9_run_real_capture.py` runs **both** configurations independently and never picks
between them from accuracy (it has no ground truth):

- **7-DOF free** cuboid fit — always;
- **6-DOF support-plane** fit — only when a valid support plane is present.

It also records `image_quantization_uncertainty()` (does *not* set a new production
`min_mask_bbox_px` threshold yet). For each fit it records success/failure, L/W/H,
mean/min IoU, boundary residual, identifiability, leave-one-out evidence and spread,
view coverage, baseline, minimum mask bbox px, quantisation uncertainty, optimiser
status and runtime.

## First physical research gate (predeclared)

For the **same** carton across **3 independent sweeps**, the desired first proof is:

- median absolute error per dimension **≤ 5 %**, **and**
- no accepted sweep over **10 %** error on any dimension, **and**
- cross-sweep repeatability range **≤ 5 %** per dimension,

with **no** pose/intrinsics convention failure, **no** quality-gate bypass, **no**
GT-based correction, **no** scale multiplier and **no** manual dimension adjustment.
If this fails, **report the failure** — do not tune against the test carton and rerun.

Ground truth (`ground_truth.json`) is read **only** by
`m9_evaluate_real_results.py`. The measurement / fitting code never opens it.

## Failure modes to watch

pose scale · pose orientation convention · intrinsics · segmentation · support plane
· image resolution (low object-pixel coverage) · insufficient coverage · optimiser
non-convergence. The run diagnostics record the variables needed to attribute a
failure to one of these.

## Transfer commands

Pull an exported sweep over USB (bundle lives under the app external-files dir):

```bash
adb shell ls /sdcard/Android/data/com.aymakan.measurex.m9capture/files/captures
adb pull /sdcard/Android/data/com.aymakan.measurex.m9capture/files/captures/M9_<ts>_sweep_01 ./sweep_01
```

(or use the in-app **EXPORT CAPTURE** share sheet to send the zip to yourself.)

## Exact processing commands

Run from `services/vision-poc` with the `seg` extra installed (GPU recommended) for
`prepare`; the other steps need only the core + `dev` extra:

```bash
# 1. validate raw geometry (stops here if invalid)
python scripts/m9_validate_raw_capture.py sweep_01/raw_capture.json

# 2. select exactly 8 frames (GT-free)
python scripts/m9_select_real_frames.py sweep_01/raw_capture.json

# 3. segment selected frames -> strict capture.json (Grounding DINO + SAM 2)
python scripts/m9_prepare_real_capture.py sweep_01/raw_capture.json \
    --selection sweep_01/selected_frames.json --out sweep_01/processed

# 4. run 7-DOF + 6-DOF cuboid fit (no GT)
python scripts/m9_run_real_capture.py sweep_01/processed/capture.json

# repeat 1–4 for sweep_02, sweep_03, then evaluate all three against GT
python scripts/m9_evaluate_real_results.py ground_truth.json \
    sweep_01/processed/run_result.json \
    sweep_02/processed/run_result.json \
    sweep_03/processed/run_result.json
```

## Physical capture procedure

1. Place one rigid carton on a flat table/conveyor; good lighting; only one carton in view.
2. Tape-measure ground truth separately — **do not enter it into the app**.
3. Open M9 Capture; confirm ARCore tracking.
4. Aim the centre reticle at the carton/table centre and tap **SET CARTON TARGET**.
5. Start ~60° to one side; sweep smoothly around the front; finish ~60° on the other side.
6. Keep the whole carton visible; do not walk behind it.
7. Let the app reach ≥125° coverage and ≥12 candidate frames, then **EXPORT CAPTURE**
   (EXPORT stays disabled until all image writes have finished).
8. Tap **NEW SWEEP** (a fresh ARCore session) and repeat for 3 independent sessions
   (`sweep_01/02/03`).

## Limitations

- The Samsung A16 4G may report `UNSUPPORTED_DEVICE`; metric capture then cannot run
  on it and a certified ARCore device is required.
- The on-device GL/camera/ARCore glue is validated only on hardware — the mandatory
  coordinate/serialisation logic is unit-tested, the device path is not.
- No connected-component mask fragmentation check yet (single-target is enforced at
  detection); add once real SAM 2 masks are labelled.
- No production resolution / `min_mask_bbox_px` threshold is set from this stage.
