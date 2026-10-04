// Box base-rectangle measurement (PRD §4).
//
// B1 first cut: segment the darkest/most-distinct object inside the placement
// zone (Otsu threshold → contours), take the largest contour's minimum-area
// rectangle as the box base, and convert its side lengths to mm with the
// marker-derived scale. L = longer horizontal side, W = shorter (orientation
// rule). Height is NOT derived here (needs camera pose; B2).
#include "internal.hpp"

#include <opencv2/imgproc.hpp>
#include <algorithm>
#include <cmath>

namespace measurex {

bool measureBoxBase(const cv::Mat& gray, double mmPerPx, int zoneMarginPx,
                    int minContourAreaPx, int& lengthMm, int& widthMm) {
  if (gray.empty() || mmPerPx <= 0.0) return false;

  // Restrict to the placement zone by ignoring a margin around the frame edge
  // (markers live near the edges; the box sits in the middle).
  const int m = std::max(0, zoneMarginPx);
  cv::Rect zone(m, m, std::max(1, gray.cols - 2 * m), std::max(1, gray.rows - 2 * m));
  zone &= cv::Rect(0, 0, gray.cols, gray.rows);
  const cv::Mat roi = gray(zone);

  // Blur + Otsu threshold. The box is assumed distinct from a light mat; invert
  // so the object becomes foreground regardless of relative brightness.
  cv::Mat blurred, bin;
  cv::GaussianBlur(roi, blurred, cv::Size(5, 5), 0);
  cv::threshold(blurred, bin, 0, 255, cv::THRESH_BINARY_INV | cv::THRESH_OTSU);

  // Close small gaps so the box base is one blob.
  const cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(7, 7));
  cv::morphologyEx(bin, bin, cv::MORPH_CLOSE, kernel);

  std::vector<std::vector<cv::Point>> contours;
  cv::findContours(bin, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
  if (contours.empty()) return false;

  // Largest contour by area, above the minimum.
  int bestIdx = -1;
  double bestArea = 0.0;
  for (size_t i = 0; i < contours.size(); ++i) {
    const double area = cv::contourArea(contours[i]);
    if (area > bestArea) {
      bestArea = area;
      bestIdx = static_cast<int>(i);
    }
  }
  if (bestIdx < 0 || bestArea < static_cast<double>(std::max(1, minContourAreaPx))) {
    return false;
  }

  const cv::RotatedRect rect = cv::minAreaRect(contours[bestIdx]);
  const double sideAPx = rect.size.width;
  const double sideBPx = rect.size.height;
  const double longPx = std::max(sideAPx, sideBPx);
  const double shortPx = std::min(sideAPx, sideBPx);

  lengthMm = static_cast<int>(std::lround(longPx * mmPerPx));
  widthMm = static_cast<int>(std::lround(shortPx * mmPerPx));
  return lengthMm > 0 && widthMm > 0;
}

} // namespace measurex
