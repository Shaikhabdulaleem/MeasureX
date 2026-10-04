// MeasureX vision core — C ABI implementation (PRD §4, Phase B / B1).
#include "measurex/measure.h"
#include "internal.hpp"

#include <opencv2/core.hpp>
#include <cstdio>
#include <cstring>
#include <string>

namespace {

// Defaults applied when the caller passes NULL or zero-initialised params.
MxParams withDefaults(const MxParams* p) {
  MxParams out;
  out.markerSizeMm = (p && p->markerSizeMm > 0) ? p->markerSizeMm : 100;
  out.zoneMarginPx = (p && p->zoneMarginPx > 0) ? p->zoneMarginPx : 0;
  out.minContourAreaPx = (p && p->minContourAreaPx > 0) ? p->minContourAreaPx : 1500;
  return out;
}

} // namespace

extern "C" int measurex_measure_frame(const uint8_t* gray, int width, int height,
                                      const MxParams* params, MxResult* out) {
  if (gray == nullptr || out == nullptr || width <= 0 || height <= 0) {
    return 1; // bad argument
  }

  std::memset(out, 0, sizeof(*out));
  const MxParams p = withDefaults(params);

  // Wrap the caller's buffer without copying (row-major 8-bit grayscale).
  const cv::Mat image(height, width, CV_8UC1,
                      const_cast<void*>(static_cast<const void*>(gray)));

  const measurex::Detection det = measurex::detectMarkers(image);
  out->markerCount = static_cast<int>(det.ids.size());
  out->confidence = measurex::confidenceHint(out->markerCount);

  const double mmPerPx = measurex::mmPerPxFromMarkers(det, p.markerSizeMm);
  out->mmPerPx = mmPerPx;
  if (mmPerPx <= 0.0) {
    return 0; // no scale → no measurement, but not an error
  }

  int lengthMm = 0;
  int widthMm = 0;
  const bool measured = measurex::measureBoxBase(image, mmPerPx, p.zoneMarginPx,
                                                 p.minContourAreaPx, lengthMm, widthMm);
  if (measured) {
    out->ok = 1;
    out->lengthMm = lengthMm;
    out->widthMm = widthMm;
    out->heightMm = 0; // B1: height needs pose (B2)
  }
  return 0;
}

extern "C" const char* measurex_version(void) {
  static std::string v =
      std::string("measurex 0.1.0 (opencv ") + CV_VERSION + ")";
  return v.c_str();
}
