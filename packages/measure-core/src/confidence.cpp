// Per-frame confidence hint (PRD §4).
//
// The authoritative High/Medium/Low is decided by the Dart aggregator, which
// also factors in the frame-to-frame spread over 5–10 frames. This hint is the
// marker-count half of that rule, surfaced per frame for the live UI:
//   >= 4 markers → High hint, >= 2 → Medium, else Low.
#include "internal.hpp"
#include "measurex/measure.h"

namespace measurex {

int confidenceHint(int markerCount) {
  if (markerCount >= 4) return MX_CONF_HIGH;
  if (markerCount >= 2) return MX_CONF_MEDIUM;
  return MX_CONF_LOW;
}

} // namespace measurex
