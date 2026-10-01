# packages/measure-core

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
