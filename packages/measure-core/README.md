# packages/measure-core

> ## ⚠️ DEPRECATED / SUPERSEDED (M8)
>
> The **marker-mat / ArUco** measurement approach described below is **superseded**
> by the camera-only vision engine (no mat, no marker, no reference object) in
> [`services/vision-poc`](../../services/vision-poc/) — see
> [`docs/VISION_DECISION.md`](../../docs/VISION_DECISION.md). The ArUco C++/FFI
> core is **not the current direction** and is retained only for historical
> reference; do not build new work on it. The `MeasurementEngine` interface and
> integer-mm output contract still stand; the *method* behind them has changed.
> (Root `CLAUDE.md` / PRD still mention the mat and will be reconciled to v3 in a
> later, separate change — not here.)

C++17 + OpenCV (ArUco) measurement core, shared by Android and iOS and called
from Flutter through Dart FFI. **Skeleton only** in Milestone 0 — the vision
code begins in Phase B (B1 feasibility spike).

Responsibilities (PRD §4):

- Detect ArUco markers (`DICT_4X4_50`) → camera pose, floor plane, real-world
  scale.
- Segment the box in the placement zone; fit the base rectangle (L, W) and top
  edges (H); median over 5–10 frames; frame spread → confidence.
- Store millimetres; orientation rule L ≥ W horizontal, H vertical.

Phase C AR (ARCore/ARKit, LiDAR) runs in thin native modules behind the same
`MeasurementEngine` interface. Built with CMake (no pnpm workspace).
