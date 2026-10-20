"""Real-capture validation tooling (Phase 12).

Dataset layout::

    dataset/
      carton_001/
        capture.json
        frames/            # optional RGB (not needed by the core)
        masks/
        ground_truth.json  # {"length_mm","width_mm","height_mm"}

**Ground truth is read ONLY here, in the evaluator.** The reconstruction core
never opens ``ground_truth.json`` — no GT correction factor can leak into a
measurement. Collect real cartons later; this module does not fabricate data.
"""

from __future__ import annotations

import json
import os
from typing import Any

import numpy as np

from .pipeline import reconstruct_from_provider
from .pose_provider import OfflineManifestProvider
from .schema import ReconstructionConfig

_DIMS = ("length_mm", "width_mm", "height_mm")


def evaluate_carton(manifest_path: str, gt_path: str, config: ReconstructionConfig | None = None) -> dict[str, Any]:
    """Reconstruct one carton and compare to tape-measured ground truth."""
    result = reconstruct_from_provider(OfflineManifestProvider(manifest_path), config)
    with open(gt_path, encoding="utf-8") as fh:
        gt = json.load(fh)

    row: dict[str, Any] = {"manifest": manifest_path, "gt_mm": {k: gt[k] for k in _DIMS}}
    if not result.get("success"):
        row.update(success=False, reason=result.get("reason"))
        return row

    pred = result["dimensions"]
    abs_err = {k: abs(pred[k] - gt[k]) for k in _DIMS}
    pct_err = {k: 100.0 * abs_err[k] / gt[k] for k in _DIMS}
    vol_pred = np.prod([pred[k] for k in _DIMS])
    vol_gt = np.prod([gt[k] for k in _DIMS])
    diag = result.get("diagnostics", {})
    row.update(
        success=True,
        pred_mm=pred,
        abs_err_mm=abs_err,
        pct_err=pct_err,
        volume_pct_err=100.0 * abs(vol_pred - vol_gt) / vol_gt,
        frames_accepted=result.get("frames_accepted"),
        total_baseline_mm=diag.get("total_baseline_mm"),
        max_view_angle_deg=diag.get("max_view_angle_deg"),
        quality=result.get("quality", {}).get("level"),
    )
    return row


def evaluate_dataset(dataset_dir: str, config: ReconstructionConfig | None = None) -> dict[str, Any]:
    """Evaluate every ``carton_*`` subdirectory and aggregate the error stats."""
    rows: list[dict[str, Any]] = []
    for name in sorted(os.listdir(dataset_dir)):
        d = os.path.join(dataset_dir, name)
        manifest = os.path.join(d, "capture.json")
        gt = os.path.join(d, "ground_truth.json")
        if os.path.isdir(d) and os.path.exists(manifest) and os.path.exists(gt):
            rows.append(evaluate_carton(manifest, gt, config))

    ok = [r for r in rows if r.get("success")]
    pct = np.array([max(r["pct_err"].values()) for r in ok]) if ok else np.array([])
    agg = {
        "cartons": len(rows),
        "accepted": len(ok),
        "failure_rate": 1.0 - len(ok) / len(rows) if rows else 0.0,
        "median_pct_err": float(np.median(pct)) if pct.size else None,
        "p90_pct_err": float(np.percentile(pct, 90)) if pct.size else None,
        "p95_pct_err": float(np.percentile(pct, 95)) if pct.size else None,
        "max_pct_err": float(pct.max()) if pct.size else None,
    }
    return {"aggregate": agg, "rows": rows}
