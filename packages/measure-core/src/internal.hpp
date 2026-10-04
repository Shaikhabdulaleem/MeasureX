// MeasureX vision core — internal C++ helpers (not part of the public C ABI).
#ifndef MEASUREX_INTERNAL_HPP
#define MEASUREX_INTERNAL_HPP

#include <opencv2/core.hpp>
#include <vector>

namespace measurex {

// ArUco detection result for one frame.
struct Detection {
  std::vector<int> ids;
  std::vector<std::vector<cv::Point2f>> corners; // 4 corners per marker
};

// Detect DICT_4X4_50 markers in a grayscale image (aruco_detect.cpp).
Detection detectMarkers(const cv::Mat& gray);

// mm-per-pixel from the detected markers' side length vs the known marker size
// (plane_scale.cpp). Returns 0 when no usable markers were found.
double mmPerPxFromMarkers(const Detection& det, double markerSizeMm);

// Fit the box's base rectangle inside the placement zone and return L/W in mm
// (box_measure.cpp). L >= W (orientation rule). Returns false when no box-like
// contour is found. `mmPerPx` must be > 0.
bool measureBoxBase(const cv::Mat& gray, double mmPerPx, int zoneMarginPx,
                    int minContourAreaPx, int& lengthMm, int& widthMm);

// Per-frame confidence hint from marker count (confidence.cpp). The final
// High/Medium/Low (including frame-to-frame spread) is decided by the caller.
int confidenceHint(int markerCount);

} // namespace measurex

#endif // MEASUREX_INTERNAL_HPP
