// ArUco marker detection (DICT_4X4_50) — PRD §4.
//
// Uses the ArUco API in OpenCV's `objdetect` module (OpenCV >= 4.7). This is
// the only ArUco available on the official OpenCV Android SDK (no contrib), so
// the host build and the Android build share one API.
#include "internal.hpp"

#include <opencv2/objdetect.hpp>

namespace measurex {

Detection detectMarkers(const cv::Mat& gray) {
  static const cv::aruco::Dictionary dict =
      cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_50);
  static const cv::aruco::DetectorParameters params;
  static const cv::aruco::ArucoDetector detector(dict, params);

  Detection det;
  std::vector<std::vector<cv::Point2f>> rejected;
  detector.detectMarkers(gray, det.corners, det.ids, rejected);
  return det;
}

} // namespace measurex
