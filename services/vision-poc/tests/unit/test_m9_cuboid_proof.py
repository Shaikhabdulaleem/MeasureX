"""M9 cuboid-proof aggregation logic (Fixes 6, 8, 9).

The ``scripts/m9_cuboid_proof.py`` statistics helpers are pure functions over row
dicts, so they are tested with fabricated rows (no fitting, no GPU, no network). The
script is standalone (not part of the package), so it is loaded by path."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "m9_cuboid_proof.py"
_spec = importlib.util.spec_from_file_location("m9_cuboid_proof", _SCRIPT)
assert _spec and _spec.loader
proof = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof)


def _row(l: float, w: float, h: float, frames: int = 6, span: float = 45.0, accepted: bool = True) -> dict:
    row = {"accepted": accepted, "frames": frames, "span": span}
    if accepted:
        row["err_pct"] = {"length_mm": l, "width_mm": w, "height_mm": h}
    else:
        row["reason"] = "insufficient_silhouette_consistency"
    return row


# --- Fix 8: per-dimension aggregate gate (ALL three dims, not just pooled) ---- #

def test_per_dimension_gate_requires_all_three_dims():
    good = [_row(1.0, 1.0, 1.0) for _ in range(5)]
    assert proof._per_dim_stats(good)["per_dimension_median_le_2pct_passed"] is True
    # length & width fine, but height median 5% -> the gate must FAIL (pooled might pass)
    bad_h = [_row(1.0, 1.0, 5.0) for _ in range(5)]
    stats = proof._per_dim_stats(bad_h)
    assert stats["per_dimension"]["height_mm"]["p50"] == 5.0
    assert stats["per_dimension_median_le_2pct_passed"] is False


def test_per_dimension_stats_report_percentiles_per_dim():
    rows = [_row(float(i), 1.0, 1.0) for i in range(1, 11)]  # L errors 1..10
    s = proof._per_dim_stats(rows)["per_dimension"]["length_mm"]
    assert s["max"] == 10.0
    assert s["p50"] <= s["p90"] <= s["p95"] <= s["max"]


# --- Fix 9: false-accept evaluator ------------------------------------------- #

def test_false_accept_evaluator_counts_thresholds():
    rows = [_row(1, 1, 1), _row(6, 1, 1), _row(1, 12, 1), _row(1, 1, 25)]
    fa = proof._false_accepts(rows)
    assert fa["accepted"] == 4
    assert fa["gt_gt_5pct"] == 3    # 6, 12, 25
    assert fa["gt_gt_10pct"] == 2   # 12, 25
    assert fa["gt_gt_20pct"] == 1   # 25
    assert fa["worst_accepted_err_pct"] == 25.0


# --- Fix 6: robust minimum-viable grouping (not one lucky row) --------------- #

def test_robust_viable_requires_whole_group_to_pass():
    rows = (
        [_row(1, 1, 1, frames=6, span=45.0) for _ in range(4)]          # clean group -> viable
        + [_row(1, 1, 1, frames=8, span=45.0), _row(6, 1, 1, frames=8, span=45.0)]  # a false accept
        + [_row(1, 1, 1, frames=10, span=45.0), _row(0, 0, 0, frames=10, span=45.0, accepted=False)]  # a rejection
    )
    rv = proof.robust_viable(rows)
    by = {(t["frames"], t["span"]): t for t in rv["table"]}
    assert by[(6, 45.0)]["robustly_viable"] is True
    assert by[(8, 45.0)]["robustly_viable"] is False   # false accept in the group
    assert by[(10, 45.0)]["robustly_viable"] is False  # not 100% accepted
    assert rv["smallest_viable"] == {"frames": 6, "azimuth_span_deg": 45.0}


def test_robust_viable_none_when_nothing_qualifies():
    rows = [_row(9, 1, 1, frames=6, span=45.0)]  # a lone >5% accept -> no group qualifies
    assert proof.robust_viable(rows)["smallest_viable"] is None
