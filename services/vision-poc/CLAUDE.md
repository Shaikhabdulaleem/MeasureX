# CLAUDE.md — MeasureX Vision POC

This directory is an isolated research POC for **camera-only shipment dimensioning**.

Read these documents before making changes:

1. `../../docs/VISION_DECISION.md`
2. `../../docs/VISION_ENGINE_POC.md`
3. `../../docs/VISION_BENCHMARK.md`
4. Root `CLAUDE.md` for general MeasureX coding/security/data rules.

## Priority rule

For measurement-method decisions inside this directory, `docs/VISION_DECISION.md` supersedes old marker-mat / ArUco requirements in the root PRD and root CLAUDE.md until those documents are updated to v3.

## Mission

Given an ordinary RGB image or short video of a warehouse shipment, estimate bounding Length x Width x Height with:

- no mat,
- no marker,
- no known-size reference object,
- no mandatory LiDAR,
- no mandatory ARCore/ARKit.

## Build strategy

POC first. Do not touch Flutter integration until benchmark evidence justifies it.

Use modular provider interfaces:

- Detector
- Segmenter
- DepthEstimator
- GeometryEstimator
- TemporalStabilizer
- ConfidenceEstimator

The pipeline/domain layer must not import model-specific internals directly.

## Initial providers

- Metric depth: Depth Pro.
- Segmentation: SAM 2.
- Automatic open-vocabulary detection: Grounding DINO when needed.
- Geometry: Open3D + NumPy.

Do not vendor upstream repositories into MeasureX. Add normal dependencies where possible or document reproducible setup scripts.

## Python

Use Python 3.11 unless an upstream model has a hard compatibility constraint that requires another supported version. If so, document it before changing the project version.

Use a modern `pyproject.toml` and pinned/reproducible dependency strategy.

## Model weights

Never commit model checkpoints or third-party datasets.

All checkpoint locations must be configurable.

Add downloaded weights, generated point clouds, benchmark media, and debug output to Git ignore rules before downloading them.

## Base units

MeasureX persists:

- dimensions: integer millimetres,
- weight: integer grams.

Vision algorithms can operate in float metres internally. Convert only at the output contract.

Never return centimetre floats as authoritative storage values.

## Output safety

Never invent dimensions when geometry is weak.

Return a typed failure with diagnostics.

Examples:

- `no_target`
- `multiple_targets`
- `object_not_fully_visible`
- `segmentation_unstable`
- `depth_invalid`
- `pointcloud_sparse`
- `geometry_degenerate`
- `temporal_instability`

## Debuggability

Every integration test must make it possible to inspect intermediate artifacts.

Keep pure geometry functions testable without GPU/model inference.

Synthetic point-cloud tests are mandatory before trusting real-image output.

## Commercial/license discipline

Before adding a new model/checkpoint, update a model manifest with:

- upstream URL,
- version/commit,
- code license,
- weight license,
- commercial-use status,
- download source.

Do not introduce a non-commercial checkpoint into a path intended for production.

## Scope guard

Do not modify these as part of the initial POC unless explicitly requested:

- shipment API,
- database schema,
- billing formulas,
- Bluetooth scale modules,
- sync engine,
- web dashboard,
- package numbering,
- audit system.

The POC initially communicates through files/CLI JSON only.

## First task sequence

1. Scaffold this Python service.
2. Add contracts and provider interfaces.
3. Add synthetic geometry tests.
4. Integrate Depth Pro.
5. Generate depth debug artifacts.
6. Add target selection/segmentation.
7. Build masked point cloud.
8. Fit bounding dimensions.
9. Run one-carton benchmark.
10. Add video temporal stabilization.
11. Generate benchmark report.

Do not skip directly to mobile integration.
