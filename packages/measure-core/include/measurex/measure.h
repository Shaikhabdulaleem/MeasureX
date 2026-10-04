/*
 * MeasureX vision core — C ABI (Phase B / B1).
 *
 * A stable, plain-C interface so Flutter can call the C++/OpenCV engine through
 * Dart FFI without C++ name mangling. One frame in → a measurement out; the
 * caller (the Dart MeasurementEngine) runs this over several frames and takes
 * the median + spread to decide the final confidence (PRD §4).
 *
 * B1 scope: ArUco detection (DICT_4X4_50) + a first-cut base L/W from the box's
 * base rectangle scaled by the markers' known size. Height needs full camera
 * pose (homography from the mat layout) and is a B2 refinement — in B1 it is
 * returned as 0 and never drives High confidence.
 */
#ifndef MEASUREX_MEASURE_H
#define MEASUREX_MEASURE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Per-call tuning. Zero-initialise and the engine fills sensible defaults. */
typedef struct MxParams {
  int markerSizeMm;     /* printed ArUco marker side length in mm (default 100) */
  int zoneMarginPx;     /* ignore contours touching this margin of the frame edge (default 0) */
  int minContourAreaPx; /* ignore contours smaller than this (default 1500) */
} MxParams;

/* Confidence hint for a single frame (the Dart side decides the final level). */
typedef enum MxConfidence {
  MX_CONF_LOW = 0,
  MX_CONF_MEDIUM = 1,
  MX_CONF_HIGH = 2
} MxConfidence;

typedef struct MxResult {
  int ok;          /* 1 if a box measurement was produced, else 0 */
  int markerCount; /* ArUco markers detected this frame */
  int lengthMm;    /* longer horizontal side (L >= W), 0 if not measured */
  int widthMm;     /* shorter horizontal side */
  int heightMm;    /* B1: always 0 (needs pose, B2) */
  double mmPerPx;  /* scale used, 0 if no markers */
  int confidence;  /* MxConfidence hint for this frame */
} MxResult;

/*
 * Measure one grayscale frame (8-bit, row-major, `width*height` bytes).
 * Returns 0 on success (inspect out->ok for whether a box was found), non-zero
 * on a bad argument. `params` may be NULL to use defaults.
 */
int measurex_measure_frame(const uint8_t* gray, int width, int height,
                           const MxParams* params, MxResult* out);

/* Library version string, e.g. "measurex 0.1.0 (opencv 4.10.0)". */
const char* measurex_version(void);

#ifdef __cplusplus
}
#endif

#endif /* MEASUREX_MEASURE_H */
