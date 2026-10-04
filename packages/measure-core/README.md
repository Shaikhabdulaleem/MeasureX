# packages/measure-core

C++17 + OpenCV (ArUco) measurement core, shared by Android and iOS and called
from Flutter through Dart FFI (PRD §4). Built with CMake (no pnpm workspace).

**Status: Phase B / B1 feasibility spike (Android-first).** Implemented:

- ArUco marker detection (`DICT_4X4_50`) via OpenCV's `objdetect` module
  (OpenCV ≥ 4.7 — the only ArUco on the official OpenCV Android SDK).
- mm-per-pixel scale from the markers' known side length (`src/plane_scale.cpp`).
- Box base rectangle → length/width in mm, orientation rule L ≥ W
  (`src/box_measure.cpp`).
- Per-frame confidence hint from marker count (`src/confidence.cpp`); the final
  High/Medium/Low (with frame-to-frame spread) is decided by the Dart engine.
- Printable mat generator CLI (`tools/matgen.cpp`).

**Not yet (B2 / B3):** full camera pose from the mat layout (needed for accurate
**height** and perspective-correct L/W — B1 returns height = 0), robust box
segmentation, and the calibration that proves the ≤ 1 cm accuracy gate.

## Public interface

`include/measurex/measure.h` is the stable C ABI the FFI binds to:
`measurex_measure_frame(gray, width, height, params, out)` and
`measurex_version()`. One grayscale frame in → markers + L/W (mm) out.

## Building (host, for tests)

Needs desktop OpenCV ≥ 4.7 (e.g. conda-forge `opencv`). CI builds it this way.

```
cmake -S packages/measure-core -B build \
  -DMEASUREX_BUILD_TESTS=ON -DMEASUREX_BUILD_TOOLS=ON
cmake --build build -j
ctest --test-dir build --output-on-failure
./build/measurex_matgen mat.png STATION-01   # print square at ~100x100 cm
```

## Android

Built into the app as `libmeasurex.so` via `apps/mobile/android/app/src/main/cpp/CMakeLists.txt`
(NDK + the OpenCV Android SDK, `OpenCV_DIR` → `sdk/native/jni`). See the mobile
app's native build notes.

Phase C AR (ARCore/ARKit, LiDAR) will run in thin native modules behind the same
engine interface.
