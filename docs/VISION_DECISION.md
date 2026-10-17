# MeasureX Vision Decision — Camera-Only Measurement

**Status:** Approved product direction  
**Date:** 2026-10-17  
**Scope:** Measurement engine only  
**Supersedes:** Any current PRD/CLAUDE/README requirement that mandates a printed marker mat, ArUco markers, a known-size reference object, LiDAR, ARCore, or ARKit as a prerequisite for automatic measurement.

## 1. Product decision

MeasureX automatic dimensioning must work from a normal RGB phone camera without requiring the worker to place the shipment on a measurement mat or beside a known-size reference object.

The intended worker experience is:

```
Scan AWB -> point camera at shipment -> MeasureX detects the shipment ->
dimensions stabilize -> review -> confirm
```

The baseline product must not require:

- Printed ArUco/AprilTag/QR measurement mats.
- Credit cards, rulers, A4 sheets, coins, calibration cards, or other known-size reference objects.
- LiDAR.
- Time-of-Flight depth sensors.
- ARCore support.
- ARKit support.

If a phone exposes hardware depth, LiDAR, ToF, ARCore, or ARKit data, MeasureX may use it later as an optional accuracy signal. It must not be the baseline dependency.

## 2. Technical direction

The first camera-only POC will be implemented as a Python research service and will not replace the existing Flutter, NestJS, Next.js, scale, sync, shipment, audit, or billing code.

Initial reference pipeline:

```
RGB frame(s)
  -> shipment detection / candidate selection
  -> precise segmentation mask
  -> monocular metric depth
  -> camera intrinsics / focal estimate
  -> masked 3D point cloud
  -> background/floor rejection
  -> oriented 3D bounding box
  -> L/W/H in metres
  -> convert to integer millimetres
  -> temporal stabilization across frames
  -> confidence + diagnostics
```

Initial model candidates:

1. **Depth Pro** — primary metric-depth candidate.
2. **SAM 2** — segmentation and video mask propagation.
3. **Grounding DINO** — optional open-vocabulary automatic shipment detection.
4. **Open3D** — point-cloud filtering, plane handling, geometry, oriented bounding boxes.

Alternative depth models may be benchmarked behind the same provider interface. Do not tightly couple the MeasureX domain code to one AI model.

## 3. Important engineering truth

A single ordinary RGB image does not provide guaranteed industrial physical scale in all environments. Monocular metric-depth models infer scale statistically.

Therefore MeasureX must treat camera-only dimensioning as an estimated measurement with a confidence score until a warehouse benchmark proves an acceptable error range.

Do not advertise or hard-code an accuracy SLA before benchmark results exist.

## 4. POC first, mobile integration later

Do not begin by embedding large AI models in Flutter, Android, iOS, C++, or `packages/measure-core`.

First prove the algorithm on a workstation/GPU using recorded warehouse images/videos.

POC success order:

1. Single known carton, offline image.
2. Reliable shipment mask.
3. Metric depth.
4. 3D reconstruction.
5. Bounding dimensions.
6. Repeatability over multiple images.
7. Short video / multi-frame stabilization.
8. Benchmark on multiple phones and shipment sizes.
9. Only then choose production deployment: on-device, edge workstation, backend GPU service, hybrid, or optimized native model.

## 5. Existing code to preserve

The following are already valuable and must not be rewritten as part of the vision POC:

- `apps/mobile` Flutter worker/team-leader app.
- `apps/api` NestJS API.
- `apps/web` admin dashboard.
- Bluetooth scale adapters and stability logic.
- Offline/sync system.
- AWB scanning.
- Package numbering and remeasurement workflow.
- Audit/versioning.
- Billing formulas.
- Photo storage.
- Role/branch security.

The POC must expose a clean output contract that can later plug into the existing capture flow.

## 6. Measurement output contract

Vision results use metric values internally, but MeasureX persists integer base units.

POC output:

```json
{
  "length_mm": 1204,
  "width_mm": 801,
  "height_mm": 598,
  "confidence": 0.91,
  "confidence_level": "high",
  "method": "rgb_ai",
  "model_versions": {
    "depth": "...",
    "segmenter": "...",
    "detector": "..."
  },
  "diagnostics": {
    "depth_valid_ratio": 0.93,
    "mask_area_ratio": 0.31,
    "frame_count": 8,
    "dimension_spread_mm": {
      "length": 9,
      "width": 7,
      "height": 8
    }
  }
}
```

Orientation rule remains:

- Length = longest horizontal dimension.
- Width = shorter horizontal dimension.
- Height = vertical dimension.

For irregular objects, output represents **bounding dimensions**, not the exact physical surface shape.

## 7. No silent fallback to fake precision

The engine must fail explicitly when it cannot produce a trustworthy measurement.

Examples:

- shipment not fully visible,
- multiple plausible target objects,
- insufficient segmentation quality,
- unusable depth,
- excessive frame-to-frame spread,
- strong occlusion,
- extreme blur,
- geometry degeneracy.

Return a structured failure reason and user guidance rather than inventing dimensions.

## 8. Model/license policy

Before adding a dependency or checkpoint:

- Record repository URL.
- Record code license.
- Record checkpoint/weights license separately.
- Record commercial-use status.
- Do not commit third-party model weights to this repository.
- Do not use a non-commercial checkpoint in a production path.

A dedicated model/license manifest is required before productionization.

## 9. Relationship to current PRD

Until `docs/PRD.md` is revised to v3, this document is the source of truth for the measurement method and supersedes marker-mat-specific statements in the existing PRD and root `CLAUDE.md`.

All non-measurement rules in the existing PRD continue to apply unless explicitly changed elsewhere.
