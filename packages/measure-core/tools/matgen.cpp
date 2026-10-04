// MeasureX mat generator (PRD §4: "mats can be reprinted").
//
// Renders the measuring-station mat: 8 DICT_4X4_50 markers (ids 0..7) around a
// marked central placement zone, with a printed station id. Output is a PNG;
// print it square at ~100 x 100 cm so each marker is ~10 cm (the default the
// engine assumes via MxParams.markerSizeMm = 100).
//
// Usage: measurex_matgen <output.png> [stationId] [canvasPx] [markerPx]
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/objdetect.hpp>

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
  if (argc < 2) {
    std::cerr << "usage: measurex_matgen <output.png> [stationId] [canvasPx] [markerPx]\n";
    return 2;
  }
  const std::string outPath = argv[1];
  const std::string stationId = argc >= 3 ? argv[2] : "STATION-01";
  const int canvas = argc >= 4 ? std::atoi(argv[3]) : 2000;
  const int marker = argc >= 5 ? std::atoi(argv[4]) : 240;
  if (canvas < 600 || marker < 80 || marker > canvas / 3) {
    std::cerr << "invalid sizes\n";
    return 2;
  }

  cv::Mat mat(canvas, canvas, CV_8UC1, cv::Scalar(255));
  const cv::aruco::Dictionary dict =
      cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_50);

  const int pad = marker / 3;
  const int mid = (canvas - marker) / 2;
  const int farEdge = canvas - marker - pad;

  // 8 markers: 4 corners + 4 edge midpoints (ids 0..7).
  const cv::Point tl[8] = {
      {pad, pad},           // 0 top-left
      {mid, pad},           // 1 top-mid
      {farEdge, pad},       // 2 top-right
      {pad, mid},           // 3 left-mid
      {farEdge, mid},       // 4 right-mid
      {pad, farEdge},       // 5 bottom-left
      {mid, farEdge},       // 6 bottom-mid
      {farEdge, farEdge},   // 7 bottom-right
  };
  for (int id = 0; id < 8; ++id) {
    cv::Mat img;
    cv::aruco::generateImageMarker(dict, id, marker, img, 1);
    img.copyTo(mat(cv::Rect(tl[id].x, tl[id].y, marker, marker)));
  }

  // Placement-zone outline (central square the box sits in).
  const int zoneInset = marker + pad * 2;
  cv::rectangle(mat, cv::Rect(zoneInset, zoneInset, canvas - 2 * zoneInset, canvas - 2 * zoneInset),
                cv::Scalar(0), 3);

  // Station id caption, centered just inside the bottom edge.
  const std::string caption = "MeasureX mat  -  " + stationId;
  int baseline = 0;
  const double fontScale = canvas / 1400.0;
  const cv::Size ts = cv::getTextSize(caption, cv::FONT_HERSHEY_SIMPLEX, fontScale, 2, &baseline);
  cv::putText(mat, caption, cv::Point((canvas - ts.width) / 2, mid + marker / 2 + ts.height / 2),
              cv::FONT_HERSHEY_SIMPLEX, fontScale, cv::Scalar(0), 2, cv::LINE_AA);

  if (!cv::imwrite(outPath, mat)) {
    std::cerr << "failed to write " << outPath << "\n";
    return 1;
  }
  std::cout << "wrote " << outPath << " (" << canvas << "x" << canvas
            << ", 8 markers, station " << stationId << ")\n";
  return 0;
}
