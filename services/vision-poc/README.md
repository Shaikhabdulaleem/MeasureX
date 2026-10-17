# MeasureX Vision Engine POC

Camera-only shipment dimensioning research service. Estimates bounding
**Length × Width × Height** from an ordinary RGB phone image or short video —
**no mat, no marker, no known-size reference object, no mandatory LiDAR / ARCore
/ ARKit**.

This is an isolated research POC. It does **not** touch the Flutter app, the
NestJS API, the web dashboard, the database, billing, scale, sync, or audit
code. It communicates only through files / CLI JSON.

Read first: [`docs/VISION_DECISION.md`](../../docs/VISION_DECISION.md),
[`docs/VISION_ENGINE_POC.md`](../../docs/VISION_ENGINE_POC.md),
[`docs/VISION_BENCHMARK.md`](../../docs/VISION_BENCHMARK.md), and
[`CLAUDE.md`](CLAUDE.md).

## Status — Milestone 0 (scaffold)

Implemented: domain contracts, provider interfaces, pure geometry utilities, and
synthetic point-cloud tests. **No AI models are integrated yet** and no weights
are downloaded. The CLI parses but the measurement pipeline is not wired.

```
src/measurex_vision/
  contracts.py            # Dimensions, Confidence, Diagnostics, Success, Failure
  cli.py                  # `python -m measurex_vision.cli` (placeholder)
  detection/base.py       # Detector interface (+ Detection)
  segmentation/base.py    # Segmenter interface
  depth/base.py           # DepthEstimator interface (+ DepthResult)
  geometry/
    base.py               # GeometryEstimator interface
    intrinsics.py         # CameraIntrinsics + forward projection
    pointcloud.py         # back-projection, depth-map -> point cloud
    bounding_box.py       # PCA oriented bounding box
    dimensions.py         # axis/orientation normalization + L/W/H + mm conversion
  temporal/stabilizer.py  # TemporalStabilizer interface
  quality/confidence.py   # ConfidenceEstimator interface
```

## Setup

Target runtime is **Python 3.11** (see `CLAUDE.md`); the pure-geometry layer
runs on 3.11+. Core install needs only NumPy.

```bash
cd services/vision-poc
python -m venv .venv
# Windows:  .venv\Scripts\activate
# POSIX:    source .venv/bin/activate
pip install -e ".[dev]"
```

Model/vision extras (OpenCV, Open3D, …) are declared under the `vision` extra
and installed in later milestones, not now.

## Run

```bash
python -m measurex_vision.cli --help
python -m measurex_vision.cli image path/to/image.jpg --debug   # not implemented in M0
python -m measurex_vision.cli video path/to/video.mp4 --debug   # not implemented in M0
```

## Test

```bash
pytest
```

The P0 synthetic tests build known cuboids (400×300×200, 600×400×350,
1200×800×600 mm), apply arbitrary rotation + translation, and verify the
geometry layer recovers the dimensions — no GPU or model inference required.

## Output contract

Metres internally; **integer millimetres only at the contract boundary**.
Success and typed-failure JSON shapes are defined by `contracts.py` and match
`docs/VISION_ENGINE_POC.md`. The engine returns an explicit failure (never
fabricated dimensions) when geometry is weak.
