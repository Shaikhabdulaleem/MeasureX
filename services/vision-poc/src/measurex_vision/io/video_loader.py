"""Sample frames from a short video.

Frame decoding uses OpenCV (lazy import, in the `vision` extra). The index
choice is factored into a pure helper so it is unit-tested without a codec."""

from __future__ import annotations

import numpy as np


def even_indices(n_frames: int, k: int) -> list[int]:
    """Up to k evenly-spaced, de-duplicated frame indices in [0, n_frames).

    shortcut: evenly spaced, not blur/sharpness-aware — upgrade when real clips
    are benchmarked."""
    if n_frames <= 0 or k <= 0:
        return []
    if k >= n_frames:
        return list(range(n_frames))
    # Midpoints of k equal buckets -> spread out, never the very first/last only.
    return sorted({int((i + 0.5) * n_frames / k) for i in range(k)})


def sample_frames(path: str, max_frames: int = 8) -> list[np.ndarray]:
    """Return up to max_frames evenly-spaced RGB (H,W,3) uint8 frames."""
    import cv2

    cap = cv2.VideoCapture(path)
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        wanted = even_indices(total, max_frames) if total > 0 else list(range(max_frames))
        frames: list[np.ndarray] = []
        for idx in wanted:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, bgr = cap.read()
            if ok:
                frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        return frames
    finally:
        cap.release()
