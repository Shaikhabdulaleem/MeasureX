"""Tests for even_indices frame sampling (no codec needed)."""

from __future__ import annotations

from measurex_vision.io import even_indices


def test_picks_k_spread_out_indices():
    idx = even_indices(100, 8)
    assert len(idx) == 8
    assert idx == sorted(idx)
    assert len(set(idx)) == 8
    assert all(0 <= i < 100 for i in idx)
    # Spread across the clip, not clustered at the ends.
    assert idx[0] < 20 and idx[-1] > 80


def test_k_ge_n_returns_all():
    assert even_indices(5, 8) == [0, 1, 2, 3, 4]


def test_edge_cases():
    assert even_indices(0, 8) == []
    assert even_indices(10, 0) == []
    assert even_indices(10, 1) == [5]
