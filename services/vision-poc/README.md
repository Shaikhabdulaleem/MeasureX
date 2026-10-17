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

## Status — Milestone 5 (benchmark harness)

The POC now runs end to end for still images and short videos. M0–M4 delivered
the contracts, metric depth, target segmentation, support-plane geometry,
integer-mm L/W/H, and robust temporal stabilization. **M5 adds the reproducible
manifest benchmark and report generator.** Production integration remains out
of scope until real benchmark evidence exists and an accuracy/confidence policy
is approved.

Depth providers (both behind the interface, see `MODELS.md`):

- **Depth Pro** — metric-depth baseline. Weights are **Apple-ASCL: research /
  benchmark only, NOT for production**.
- **Depth Anything V2** — commercial slot, _planned_ (raises `NotImplementedError`).

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

**No local GPU?** Run the real pipeline on a cloud GPU with the M6 validation
notebook — it clones the repo, installs the stack, downloads weights, runs a real
photo + video, and benchmarks against your tape-measured box:
- Google Colab (primary): [`notebooks/MeasureX_GPU_Validation.ipynb`](notebooks/MeasureX_GPU_Validation.ipynb)
- Kaggle (fallback): [`docs/KAGGLE_GPU_SETUP.md`](docs/KAGGLE_GPU_SETUP.md)

Record results in [`docs/REAL_GPU_VALIDATION_REPORT.md`](docs/REAL_GPU_VALIDATION_REPORT.md).

## Run

```bash
python -m measurex_vision.cli --help
python -m measurex_vision.cli image path/to/image.jpg --debug
python -m measurex_vision.cli video path/to/video.mp4 --debug
```

With `--debug`, inspectable artifacts are written under `outputs/` (override
with `MEASUREX_VISION_OUTPUT_DIR`).

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
