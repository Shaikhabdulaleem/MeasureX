// Host unit tests for the MeasureX vision core (PRD §4, B1).
//
// Builds a synthetic scene — real DICT_4X4_50 markers of a known pixel size on
// a white canvas plus a dark rectangle of known pixel dimensions — so marker
// detection, the mm-per-pixel scale, and the base L/W measurement can be checked
// against known values without a camera or a printed mat. Self-contained (no
// gtest); returns the number of failures so ctest flags a non-zero exit.
#include "measurex/measure.h"

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/objdetect.hpp>

#include <cmath>
#include <cstdio>
#include <string>

static int g_failures = 0;

#define CHECK(cond, msg)                                                      \
  do {                                                                        \
    if (!(cond)) {                                                            \
      std::printf("FAIL: %s\n", (msg));                                       \
      ++g_failures;                                                           \
    } else {                                                                  \
      std::printf("ok:   %s\n", (msg));                                       \
    }                                                                         \
  } while (0)

// Render a scene: 4 markers (100px) near the corners + a filled dark rectangle
// (boxW x boxH px) centered. With markerSizeMm=100 the scale is 1 mm/px, so the
// expected L/W in mm equal the rectangle's pixel dimensions.
static cv::Mat buildScene(int canvas, int markerPx, int boxW, int boxH) {
  cv::Mat img(canvas, canvas, CV_8UC1, cv::Scalar(255));
  const cv::aruco::Dictionary dict =
      cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_50);
  const int pad = 60;
  const cv::Point tl[4] = {
      {pad, pad},
      {canvas - markerPx - pad, pad},
      {pad, canvas - markerPx - pad},
      {canvas - markerPx - pad, canvas - markerPx - pad},
  };
  for (int id = 0; id < 4; ++id) {
    cv::Mat m;
    cv::aruco::generateImageMarker(dict, id, markerPx, m, 1);
    m.copyTo(img(cv::Rect(tl[id].x, tl[id].y, markerPx, markerPx)));
  }
  cv::rectangle(img,
                cv::Rect((canvas - boxW) / 2, (canvas - boxH) / 2, boxW, boxH),
                cv::Scalar(30), cv::FILLED);
  return img;
}

static void testDetectAndMeasure() {
  const int canvas = 1000, markerPx = 100, boxW = 300, boxH = 200;
  const cv::Mat scene = buildScene(canvas, markerPx, boxW, boxH);

  MxParams params{};
  params.markerSizeMm = 100; // marker is 100px → 1 mm/px

  MxResult r{};
  const int rc = measurex_measure_frame(scene.data, scene.cols, scene.rows, &params, &r);
  CHECK(rc == 0, "measure returns success rc");
  CHECK(r.markerCount == 4, "detects all four markers");
  CHECK(r.confidence == MX_CONF_HIGH, "four markers → High confidence hint");
  CHECK(std::fabs(r.mmPerPx - 1.0) < 0.05, "scale is ~1 mm/px");
  CHECK(r.ok == 1, "a box measurement was produced");
  // Orientation rule: L is the longer side.
  CHECK(r.lengthMm >= r.widthMm, "length >= width (orientation rule)");
  CHECK(std::abs(r.lengthMm - 300) <= 6, "length within 6mm of 300");
  CHECK(std::abs(r.widthMm - 200) <= 6, "width within 6mm of 200");
  CHECK(r.heightMm == 0, "height is 0 in B1 (pose is B2)");
}

static void testNoMarkers() {
  cv::Mat blank(400, 400, CV_8UC1, cv::Scalar(255));
  MxResult r{};
  const int rc = measurex_measure_frame(blank.data, blank.cols, blank.rows, nullptr, &r);
  CHECK(rc == 0, "blank frame is not an error");
  CHECK(r.markerCount == 0, "no markers on a blank frame");
  CHECK(r.ok == 0, "no measurement without a scale");
  CHECK(r.confidence == MX_CONF_LOW, "no markers → Low confidence hint");
}

static void testBadArgs() {
  MxResult r{};
  CHECK(measurex_measure_frame(nullptr, 10, 10, nullptr, &r) != 0, "null buffer rejected");
  cv::Mat img(10, 10, CV_8UC1, cv::Scalar(0));
  CHECK(measurex_measure_frame(img.data, 10, 10, nullptr, nullptr) != 0, "null out rejected");
  CHECK(measurex_measure_frame(img.data, 0, 10, nullptr, &r) != 0, "bad width rejected");
}

static void testVersion() {
  const std::string v = measurex_version();
  CHECK(v.find("measurex") != std::string::npos, "version mentions measurex");
  CHECK(v.find("opencv") != std::string::npos, "version mentions opencv");
}

int main() {
  testDetectAndMeasure();
  testNoMarkers();
  testBadArgs();
  testVersion();
  std::printf("\n%s (%d failure(s))\n", g_failures == 0 ? "PASSED" : "FAILED", g_failures);
  return g_failures == 0 ? 0 : 1;
}
