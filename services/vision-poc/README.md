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

## Status — Milestone 1 (depth)

M0 delivered the scaffold: domain contracts, provider interfaces, pure geometry,
and synthetic point-cloud tests. **M1 adds the depth stage** behind the
`DepthEstimator` interface plus depth debug artifacts. Detection, segmentation,
point-cloud build and L/W/H are still later milestones, so `cli image` runs depth
and emits depth diagnostics + artifacts — not a full measurement yet.

Depth providers (both behind the interface, see `MODELS.md`):

- **Depth Pro** — metric-depth baseline. Weights are **Apple-ASCL: research /
  benchmark only, NOT for production**.
- **Depth Anything V2** — commercial slot, _planned_ (raises `NotImplementedError`).

```
src/measurex_vision/
  contracts.py            # Dimensions, Confidence, Diagnostics, Success, Failure
  cli.py                  # `python -m measurex_vision.cli` (depth stage)
  io/image_loader.py      # load JPG/PNG -> RGB ndarray
  detection/base.py       # Detector interface (+ Detection)
  segmentation/base.py    # Segmenter interface
  depth/base.py           # DepthEstimator interface (+ DepthResult)
  depth/registry.py       # get_depth_estimator(name)
  depth/depth_pro.py      # DepthProEstimator (lazy torch)
  visualization/debug_export.py  # colorize_depth + save_depth_artifacts
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

The core install (NumPy only) plus the `dev` extra runs all of CI. The depth
model stack is separate — see below.

### Depth model (GPU workstation)

Real depth inference needs torch + a GPU and targets **Python 3.11/3.12** (not
3.14). It is **not** part of CI. On a workstation:

```bash
pip install -e ".[depth]"          # torch + Apple depth_pro
python scripts/download_models.py  # fetch Depth Pro checkpoint (Apple-ASCL, research only)
```

Weights are git-ignored and never committed. Read `MODELS.md` before downloading.

## Run

```bash
python -m measurex_vision.cli --help
python -m measurex_vision.cli image path/to/image.jpg --debug   # depth stage + artifacts (needs the depth extra)
python -m measurex_vision.cli video path/to/video.mp4 --debug   # not implemented yet
```

With `--debug`, depth artifacts (original, coloured depth, raw/masked depth,
`diagnostics.json`) are written under `outputs/` (override with
`MEASUREX_VISION_OUTPUT_DIR`).

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
