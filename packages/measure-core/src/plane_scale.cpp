// Real-world scale from detected markers (PRD §4).
//
// B1 first cut: each DICT_4X4_50 marker is a known physical square
// (markerSizeMm). Its side length in pixels gives mm-per-pixel; we average over
// all four sides of every detected marker. This is accurate when the mat is
// roughly fronto-parallel to the camera. Full perspective correction (a
// homography from the mat's known marker layout) is a B2 refinement.
#include "internal.hpp"

#include <opencv2/core.hpp>

namespace measurex {

double mmPerPxFromMarkers(const Detection& det, double markerSizeMm) {
  if (det.corners.empty() || markerSizeMm <= 0.0) return 0.0;

  double totalPx = 0.0;
  int sides = 0;
  for (const auto& quad : det.corners) {
    if (quad.size() != 4) continue;
    for (int i = 0; i < 4; ++i) {
      totalPx += cv::norm(quad[i] - quad[(i + 1) % 4]);
      ++sides;
    }
  }
  if (sides == 0) return 0.0;

  const double avgSidePx = totalPx / sides;
  if (avgSidePx <= 0.0) return 0.0;
  return markerSizeMm / avgSidePx; // mm per pixel
}

} // namespace measurex
