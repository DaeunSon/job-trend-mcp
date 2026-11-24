"""scripts/measure_api_latency.py — percentile (nearest-rank)."""
from __future__ import annotations

import pytest

from scripts.measure_api_latency import percentile


def test_percentile_nearest_rank():
    values = [float(v) for v in range(1, 101)]
    assert (percentile(values, 50), percentile(values, 95), percentile(values, 100)) == (50.0, 95.0, 100.0)
    assert percentile([7.0], 95) == 7.0


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 95)
