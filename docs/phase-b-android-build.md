# Phase B — Android native build (libmeasurex.so)

The vision core (`packages/measure-core`) is compiled into the app as
`libmeasurex.so` and called over Dart FFI (`lib/src/features/measure/
measurement_engine.dart`). Because Flutter **regenerates and git-ignores**
`apps/mobile/android/`, the native wiring is documented here so it can be
recreated on any machine. (Making `android/` first-class/tracked is a B2 step.)

## 1. OpenCV Android SDK (one-time)

Download the **OpenCV 4.x Android SDK** (4.10.0 used here; 4.x matches the
`objdetect` ArUco API the core uses) and extract it so that this path exists:

```
third_party/OpenCV-android-sdk/sdk/native/jni/OpenCVConfig.cmake
```

`third_party/` is git-ignored. Source:
`https://github.com/opencv/opencv/releases/download/4.10.0/opencv-4.10.0-android-sdk.zip`

## 2. `apps/mobile/android/app/src/main/cpp/CMakeLists.txt`

Builds `libmeasurex.so` from the shared core sources, statically linking the
OpenCV SDK. (Checked in a copy under version control is not possible while
`android/` is ignored — the exact file is reproduced below.)

```cmake
cmake_minimum_required(VERSION 3.18)
project(measurex_android LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
find_package(OpenCV REQUIRED COMPONENTS core imgproc objdetect)
add_library(measurex SHARED
  ${MEASUREX_CORE_DIR}/src/measure.cpp
  ${MEASUREX_CORE_DIR}/src/aruco_detect.cpp
  ${MEASUREX_CORE_DIR}/src/plane_scale.cpp
  ${MEASUREX_CORE_DIR}/src/box_measure.cpp
  ${MEASUREX_CORE_DIR}/src/confidence.cpp
)
target_include_directories(measurex PRIVATE
  ${MEASUREX_CORE_DIR}/include ${MEASUREX_CORE_DIR}/src ${OpenCV_INCLUDE_DIRS})
target_link_libraries(measurex ${OpenCV_LIBS})
```

## 3. `apps/mobile/android/app/build.gradle.kts`

Add, inside `android { }`:

```kotlin
externalNativeBuild {
    cmake {
        path = file("src/main/cpp/CMakeLists.txt")
        version = "3.22.1"
    }
}
```

and inside `android { defaultConfig { } }`:

```kotlin
externalNativeBuild {
    cmake {
        // Forward slashes — CMake treats a backslash in a -D string as an
        // escape, so raw Windows paths break. projectDir = .../android/app.
        val repoRoot = projectDir.resolve("../../../..").canonicalFile.path.replace("\\", "/")
        arguments += listOf(
            "-DOpenCV_DIR=$repoRoot/third_party/OpenCV-android-sdk/sdk/native/jni",
            "-DMEASUREX_CORE_DIR=$repoRoot/packages/measure-core",
            "-DANDROID_STL=c++_static"
        )
    }
    ndk { abiFilters += listOf("arm64-v8a") }
}
```

## 4. Build & run

```
flutter run -d <device> --dart-define=API_URL=http://localhost:3000/api/v1
```

(Use `adb reverse tcp:3000 tcp:3000` so the phone reaches the dev API over USB.)
On launch the FFI engine loads `libmeasurex.so`; if it is missing the app falls
back to the no-op engine and only manual entry is shown.

## 5. Mat

Generate the printable mat from the core's CLI:

```
./build/measurex_matgen mat.png STATION-01     # print square at ~100 x 100 cm
```

Marker side must print at **10 cm** (the engine's default `markerSizeMm = 100`).
