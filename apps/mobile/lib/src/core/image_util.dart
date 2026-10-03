import 'dart:typed_data';
import 'package:image/image.dart' as img;

/// Downscale + re-encode a captured photo for upload (PRD §10 rule 4): longest
/// edge ≤ [maxEdge] px, JPEG quality [quality] (~300 KB). Returns the original
/// bytes unchanged if decoding fails, so a save never blocks on image quirks.
Uint8List compressForUpload(
  List<int> bytes, {
  int maxEdge = 1600,
  int quality = 80,
}) {
  final input = bytes is Uint8List ? bytes : Uint8List.fromList(bytes);
  final decoded = img.decodeImage(input);
  if (decoded == null) return input;

  final longest = decoded.width >= decoded.height ? decoded.width : decoded.height;
  final resized = longest > maxEdge
      ? img.copyResize(
          decoded,
          width: decoded.width >= decoded.height ? maxEdge : null,
          height: decoded.height > decoded.width ? maxEdge : null,
        )
      : decoded;

  return img.encodeJpg(resized, quality: quality);
}
