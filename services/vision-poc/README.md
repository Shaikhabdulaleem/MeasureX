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

## Status — Milestone 8 (consolidation & production-safe baseline)

The POC runs end to end for still images and short videos. M0–M5 delivered the
contracts, metric depth, target segmentation, support-plane geometry, integer-mm
L/W/H, robust temporal stabilization, and the benchmark harness. M7 added the
Grounding DINO target proposer and the Depth Anything V2 commercial-path depth
provider. **M8 consolidates these into one production-oriented path:** a camera
intrinsics resolver, a code-enforced model/license policy, and fuller output
diagnostics. Production integration into the app remains out of scope until real
benchmark evidence exists and an accuracy/confidence policy is approved.

Production path: **Grounding DINO → SAM 2 → Depth Anything V2 Metric Small →
CameraIntrinsicsResolver → geometry → L/W/H → temporal → confidence.**

Depth providers (both behind the interface, see `MODELS.md` / `models.py`):

- **Depth Pro** — metric-depth baseline. Weights are **Apple-ASCL: research /
  benchmark only** (`production_approved = false`; the production gate refuses it).
- **Depth Anything V2 Metric Small** — commercial-path default (Apache-2.0). No
  focal prediction; scale resolved by the `CameraIntrinsicsResolver`.

```
src/measurex_vision/
  contracts.py            # Dimensions, Confidence, Diagnostics, Success, Failure
  cli.py                  # image + stabilized-video measurement commands
  benchmark.py            # manifest validation, metrics, summary + SVG reports
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
  temporal/               # TemporalStabilizer interface + MAD/median implementation
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
python -m measurex_vision.cli image path/to/image.jpg --debug
python -m measurex_vision.cli video path/to/video.mp4 --debug

# Approved production stack — resolves GDINO -> SAM 2 -> DA-V2 automatically
# and refuses central_candidate / box_mask / depth_pro:
python -m measurex_vision.cli image box.jpg --production --fov-deg 65
```

With `--debug`, inspectable artifacts are written under `outputs/` (override
with `MEASUREX_VISION_OUTPUT_DIR`). `--production` resolves the approved stack
(Grounding DINO → SAM 2.1 Small → Depth Anything V2 Metric Indoor Small, pinned
revisions) and refuses any model whose `production_approved` is not true (it
prints the resolved providers and revisions to stderr first); `--fov-deg` sets
the fallback FOV used when no
focal is known (the output reports `intrinsics_source` and penalizes confidence
when scale is assumed). EXIF focal, when present, is used automatically.

## Benchmark

Copy `data/benchmark-manifest.example.csv` to
`data/benchmark/manifest.csv`, add physically measured integer-mm ground truth,
and place media at paths relative to the manifest. The benchmark directory and
generated reports are Git-ignored.

```bash
python scripts/benchmark.py data/benchmark/manifest.csv \
  --false-success-tolerance-pct 10 \
  --output-dir outputs/benchmark
```

The false-success tolerance is required intentionally: M5 does not invent an
accuracy SLA. A success is a false success when any one of L/W/H exceeds that
run's tolerance. The command produces `results.csv`, `summary.json`, dimension
error distributions, grouped error charts, single-frame versus multi-frame
comparison, and failure-code counts.

To recalculate reports in CI or on a machine without models/codecs, pass
`--predictions recorded-results.jsonl`. Each JSONL object contains `sample_id`
plus the normal engine success/failure payload; IDs must exactly match the
manifest. The two `data/*example*` files form a model-free smoke test.

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
