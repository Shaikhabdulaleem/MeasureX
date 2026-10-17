"""Download the Depth Pro checkpoint to the configured weights dir.

Weights are git-ignored and never committed. Depth Pro weights are Apple-ASCL
(research only, no commercial use) — see MODELS.md.

    python scripts/download_models.py

Honours MEASUREX_VISION_WEIGHTS_DIR (default ./weights) and, if set,
MEASUREX_DEPTH_CHECKPOINT as the exact output path. The source URL can be
overridden with MEASUREX_DEPTH_URL.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

# Apple's canonical checkpoint (see apple/ml-depth-pro get_pretrained_models.sh).
DEFAULT_URL = "https://ml-site.cdn-apple.com/models/depth-pro/depth_pro.pt"

_LICENSE_REMINDER = (
    "Depth Pro weights are Apple-ASCL: research/benchmark use only, NOT for "
    "commercial/production use (MODELS.md). Do not ship them in a MeasureX build."
)


def main() -> int:
    url = os.environ.get("MEASUREX_DEPTH_URL", DEFAULT_URL)
    dest = os.environ.get("MEASUREX_DEPTH_CHECKPOINT")
    if not dest:
        weights_dir = os.environ.get("MEASUREX_VISION_WEIGHTS_DIR", "./weights")
        os.makedirs(weights_dir, exist_ok=True)
        dest = os.path.join(weights_dir, "depth_pro.pt")

    print(f"!! {_LICENSE_REMINDER}")
    if os.path.exists(dest):
        print(f"Already present: {dest}")
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    print(f"Downloading {url}\n        -> {dest}")
    tmp = dest + ".part"
    try:
        urllib.request.urlretrieve(url, tmp)
    except (OSError, urllib.error.URLError) as exc:  # pragma: no cover - network path
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1
    os.replace(tmp, dest)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
