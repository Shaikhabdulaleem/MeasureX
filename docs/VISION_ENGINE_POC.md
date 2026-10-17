# MeasureX Vision Engine POC

## Goal

Prove whether MeasureX can estimate shipment Length x Width x Height from an ordinary RGB phone camera with no mat, no reference object, and no mandatory LiDAR/AR capability.

This POC is an accuracy experiment first, not a production mobile implementation.

## Non-goals for the first POC

Do not:

- redesign the existing mobile app,
- change shipment/package APIs,
- change billing formulas,
- replace Bluetooth scale work,
- add production authentication,
- deploy model inference to phones,
- train a custom model from scratch,
- promise an accuracy SLA.

## Proposed repository location

Create a standalone Python service:

```
services/
  vision-poc/
    CLAUDE.md
    README.md
    pyproject.toml
    .env.example
    configs/
      default.yaml
    src/
      measurex_vision/
        __init__.py
        cli.py
        pipeline.py
        contracts.py
        io/
          image_loader.py
          video_loader.py
        detection/
          base.py
          grounding_dino.py
          central_candidate.py
        segmentation/
          base.py
          sam2.py
        depth/
          base.py
          depth_pro.py
        geometry/
          intrinsics.py
          pointcloud.py
          planes.py
          bounding_box.py
          dimensions.py
        temporal/
          stabilizer.py
        quality/
          confidence.py
          failure_reasons.py
        visualization/
          overlay.py
          debug_export.py
    scripts/
      download_models.py
      run_image.py
      run_video.py
      benchmark.py
    tests/
      unit/
      integration/
      fixtures/
    data/
      README.md
      samples/
      benchmark/
    outputs/
      .gitkeep
```

Model checkpoints and large benchmark media must be ignored by Git.

## Pipeline v0

### Step 1 — input

Accept:

- JPG/PNG image.
- Short MP4/MOV video.
- Optional camera focal length/intrinsics if available.

Do not require EXIF intrinsics.

### Step 2 — target detection

Goal: identify the intended shipment automatically.

First implementation options:

1. Grounding DINO text prompts such as:
   `box . carton . parcel . package . pallet . bag . furniture`
2. A deterministic central-object candidate fallback for controlled POC images.

Detection output must include:

- bounding box,
- score,
- label,
- selected-target reason.

Do not silently choose between two similarly strong targets; return `multiple_targets`.

### Step 3 — segmentation

Use SAM 2 to convert the selected box/candidate into a pixel-accurate shipment mask.

For video, propagate the selected mask through subsequent frames where practical.

Reject masks that:

- touch too many image boundaries,
- are implausibly tiny,
- cover nearly the full frame,
- fragment badly,
- jump abruptly between adjacent frames.

### Step 4 — metric depth

Primary provider: Depth Pro.

Capture:

- depth map in metres,
- estimated focal length in pixels,
- valid depth ratio,
- model/checkpoint version.

The depth provider must be an interface so alternative models can be benchmarked later without changing geometry code.

### Step 5 — reconstruct 3D

Use the depth map plus intrinsics/focal estimate to back-project masked pixels into 3D.

For pixel `(u,v)`, depth `Z`, focal values `fx,fy`, principal point `cx,cy`:

```
X = (u - cx) * Z / fx
Y = (v - cy) * Z / fy
Z = depth
```

If only one focal length is predicted, start with `fx = fy` and image centre as the principal point; record this assumption in diagnostics.

### Step 6 — clean geometry

Using Open3D / NumPy:

- retain shipment-mask points,
- remove invalid depth,
- statistical/radius outlier removal,
- reject obvious background leakage,
- estimate/support a floor or support plane where possible,
- retain the coherent shipment cluster.

Every transformation must be testable independently.

### Step 7 — dimensions

Fit an oriented/minimum oriented bounding box to the clean shipment point cloud.

Map extents to:

- longest horizontal -> length,
- shorter horizontal -> width,
- vertical -> height.

Convert metres to integer millimetres only at the final contract boundary.

For the first carton POC, assume rigid approximately cuboid objects. Do not claim bag/furniture accuracy until separately benchmarked.

### Step 8 — temporal stabilization

For video:

- sample useful frames, not every frame,
- compute dimensions per accepted frame,
- reject outlier frames,
- stabilize with robust statistics such as median,
- calculate spread for L/W/H.

The worker experience may eventually be "point and hold", while internally 5-10 useful frames are processed.

### Step 9 — confidence

Confidence is not model softmax alone.

Combine evidence such as:

- detector confidence,
- segmentation stability,
- mask completeness,
- valid depth ratio,
- point-cloud density,
- plane/geometry quality,
- frame-to-frame dimension spread,
- target visibility / border contact.

Initial levels:

- high,
- medium,
- low,
- failed.

Thresholds remain experimental until benchmark results exist.

## CLI acceptance interface

Single image:

```bash
python -m measurex_vision.cli image path/to/image.jpg --debug
```

Short video:

```bash
python -m measurex_vision.cli video path/to/video.mp4 --debug
```

Expected JSON result:

```json
{
  "success": true,
  "dimensions": {
    "length_mm": 1204,
    "width_mm": 801,
    "height_mm": 598
  },
  "confidence": 0.91,
  "confidence_level": "high",
  "method": "rgb_ai",
  "timing_ms": {
    "detection": 0,
    "segmentation": 0,
    "depth": 0,
    "geometry": 0,
    "total": 0
  },
  "diagnostics": {}
}
```

Failure:

```json
{
  "success": false,
  "failure_code": "object_not_fully_visible",
  "user_guidance": "Move back until the whole shipment is visible.",
  "diagnostics": {}
}
```

## Debug artifacts

For every POC run with `--debug`, save:

- original image/frame,
- detected target overlay,
- segmentation mask,
- coloured depth map,
- masked depth,
- point-cloud file,
- bounding-box visualization,
- final overlay,
- JSON diagnostics.

These artifacts are mandatory because numeric output alone is not enough to diagnose errors.

## Test order

### P0 — geometry unit tests

Test projection and bounding-box logic with synthetic point clouds where true dimensions are exactly known.

### P1 — one carton / one phone

10+ captures of a single known carton from realistic warehouse angles/distances.

### P2 — multiple cuboid sizes

At least small, medium, large, and bulky cartons.

### P3 — multiple phones

Test several Android/iPhone RGB cameras without using their depth sensors.

### P4 — warehouse conditions

Lighting variation, clutter, labels, dark cartons, reflective wrap, partial background occlusion.

### P5 — short video stabilization

Compare single-frame error against stabilized multi-frame error.

### P6 — alternate depth provider benchmark

Only after the baseline works, add another metric-depth provider behind the same interface and compare using exactly the same benchmark set.

## Exit criteria for the POC

The POC is considered technically promising only when:

1. It runs end-to-end from image/video to L/W/H with debug evidence.
2. It never requires a mat/reference object.
3. Failed scenes fail explicitly rather than producing obviously fabricated dimensions.
4. Benchmark output is reproducible.
5. Error is reported separately for L, W, H and CBM.
6. Multi-frame stability is measured.
7. Runtime is measured.
8. Model/license usage is documented.

A production accuracy threshold will be chosen from real benchmark results, not invented before testing.

## Production decision after POC

After benchmark data exists, choose one:

- on-device optimized models,
- warehouse edge workstation,
- backend GPU inference service,
- hybrid (fast local + server verification),
- camera-only baseline plus optional hardware-depth fusion.

Do not make that decision before the benchmark.
