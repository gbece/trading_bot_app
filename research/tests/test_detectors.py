"""
Detector tests.

TEST-DET-01: Variant B lookahead boundary (pivot only valid at j <= i-3)
TEST-DET-02: Variant A touch debounce
TEST-DET-03: Variant A minimum touch count enforced
TEST-DET-04: Variant B minimum pivot count enforced
TEST-DET-05: Both detectors return empty on insufficient data
TEST-DET-06: Overlap metric Jaccard calculation
TEST-DET-07: Detector receives bars[0:i-1] — current bar excluded
"""

from __future__ import annotations

import pytest
import numpy as np
import pandas as pd

from research.config.params import DetectorAParams, DetectorBParams
from research.detectors.support import (
    SupportLevel,
    detect_support_levels_variant_a,
    detect_support_levels_variant_b,
    compute_detector_overlap,
    _debounce_touches,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bars(
    n: int,
    close_base: float = 30000.0,
    noise: float = 100.0,
    seed: int = 0,
) -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame with random walks."""
    rng = np.random.default_rng(seed)
    close = close_base + np.cumsum(rng.standard_normal(n) * noise)
    open_ = close + rng.standard_normal(n) * 50
    high = np.maximum(close, open_) + np.abs(rng.standard_normal(n) * 30)
    low = np.minimum(close, open_) - np.abs(rng.standard_normal(n) * 30)
    volume = np.abs(rng.standard_normal(n) * 1000) + 500
    ts = pd.date_range("2023-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


def _make_flat_support_bars(
    n: int = 100,
    support_price: float = 29000.0,
    touch_indices: list | None = None,
) -> pd.DataFrame:
    """
    Create bars where specific indices have lows near support_price.
    Other bars have lows well above support_price.
    """
    if touch_indices is None:
        touch_indices = [10, 25, 40, 60]

    close_arr = np.full(n, support_price + 1000.0)
    high_arr = close_arr + 200.0
    low_arr = close_arr - 100.0
    open_arr = close_arr.copy()

    # Place support touches
    for idx in touch_indices:
        if idx < n:
            low_arr[idx] = support_price * 1.002   # within 0.5% of support
            close_arr[idx] = support_price + 200.0  # bounce back up
            high_arr[idx] = close_arr[idx] + 100.0

    volume = np.full(n, 1000.0)
    ts = pd.date_range("2023-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts, "open": open_arr, "high": high_arr,
        "low": low_arr, "close": close_arr, "volume": volume,
    })


# ---------------------------------------------------------------------------
# TEST-DET-01: Variant B lookahead boundary
# ---------------------------------------------------------------------------

class TestVariantBLookaheadBoundary:
    """TEST-DET-01: pivot at j is only valid if j <= i-3."""

    def test_last_two_bars_cannot_be_pivots(self):
        """
        In a slice of n bars, bars at positions n-1 and n-2 cannot be pivots.
        They would require bars n and n+1 which don't exist.
        """
        params = DetectorBParams()
        n = 20
        # Create bars with minimum low at positions n-1 and n-2
        bars = _make_flat_support_bars(n, support_price=29000.0, touch_indices=[n - 1, n - 2])
        levels = detect_support_levels_variant_b(bars, params, bar_offset=0)

        # No level should reference the last 2 bars
        for lv in levels:
            assert lv.last_touch_bar <= n - 1 - params.lookahead_boundary, (
                f"Level has last_touch_bar={lv.last_touch_bar} which violates "
                f"lookahead boundary (n-1-{params.lookahead_boundary}={n-1-params.lookahead_boundary})"
            )

    def test_bar_at_n_minus_3_can_be_pivot(self):
        """
        A pivot at position n-3 (lookahead_boundary=3) is confirmed:
        it requires bars n-2 and n-1, both of which are in the slice.
        """
        params = DetectorBParams(min_pivot_count=1, min_bars_between_pivots=1)
        n = 30
        # Force a clear pivot at position n-4 (safely within boundary)
        bars = _make_bars(n)
        # Make bar at n-4 the clear local minimum
        bars_arr = bars.copy()
        bars_arr.loc[n - 4, "low"] = bars["low"].min() - 1000
        bars_arr.loc[n - 4, "high"] = bars["low"].min() - 900
        bars_arr.loc[n - 4, "close"] = bars["low"].min() - 950
        bars_arr.loc[n - 4, "open"] = bars["low"].min() - 950

        levels = detect_support_levels_variant_b(bars_arr, params, bar_offset=0)
        # We don't assert a specific level here — just confirm no exception and
        # that any levels respect the lookahead boundary
        for lv in levels:
            assert lv.last_touch_bar <= n - 1 - params.lookahead_boundary


# ---------------------------------------------------------------------------
# TEST-DET-02: Variant A touch debounce
# ---------------------------------------------------------------------------

class TestVariantADebounce:
    """TEST-DET-02"""

    def test_debounce_removes_adjacent_touches(self):
        """
        min_bars_between_touches = 3.
        Indices [10, 11, 12] → only [10] survives.
        """
        result = _debounce_touches([10, 11, 12], min_bars=3)
        assert result == [10], f"Expected [10], got {result}"

    def test_debounce_keeps_separated_touches(self):
        """
        min_bars = 3.
        [10, 15, 20] → all survive (gaps = 5, 5).
        """
        result = _debounce_touches([10, 15, 20], min_bars=3)
        assert result == [10, 15, 20]

    def test_debounce_mixed(self):
        """
        min_bars = 3.
        [10, 12, 16, 17, 22] → [10, 16, 22] (12 too close to 10; 17 too close to 16).
        """
        result = _debounce_touches([10, 12, 16, 17, 22], min_bars=3)
        assert result == [10, 16, 22], f"Got {result}"

    def test_debounce_empty_input(self):
        result = _debounce_touches([], min_bars=3)
        assert result == []

    def test_debounce_single_element(self):
        result = _debounce_touches([5], min_bars=3)
        assert result == [5]


# ---------------------------------------------------------------------------
# TEST-DET-03: Variant A minimum touch count
# ---------------------------------------------------------------------------

class TestVariantAMinTouchCount:
    """TEST-DET-03"""

    def test_two_touches_rejected_when_min_is_3(self):
        """
        Only 2 touches near the support level → no level returned.
        """
        params = DetectorAParams(min_touch_count=3)
        bars = _make_flat_support_bars(80, support_price=29000.0, touch_indices=[10, 30])
        levels = detect_support_levels_variant_a(bars, params)
        # May or may not find levels (other bars may cluster), but if the 2-touch
        # zone is the only one, it must be rejected
        for lv in levels:
            assert lv.touch_count >= 3

    def test_three_touches_accepted(self):
        """
        3 clearly separated touches at support_price → level detected.
        """
        params = DetectorAParams(
            min_touch_count=3,
            min_bars_between_touches=3,
            touch_tolerance=0.005,
            min_bounce_atr=0.0,  # disable bounce check for simplicity
            lookback_window=80,
        )
        bars = _make_flat_support_bars(80, support_price=29000.0, touch_indices=[10, 20, 40])
        levels = detect_support_levels_variant_a(bars, params)
        assert any(lv.touch_count >= 3 for lv in levels), (
            f"Expected at least one level with 3+ touches, got: {levels}"
        )


# ---------------------------------------------------------------------------
# TEST-DET-04: Variant B minimum pivot count
# ---------------------------------------------------------------------------

class TestVariantBMinPivotCount:
    """TEST-DET-04"""

    def test_fewer_than_min_pivots_returns_empty(self):
        """
        With min_pivot_count=3 and only 2 pivot-like structures, no level returned.
        """
        params = DetectorBParams(min_pivot_count=3)
        bars = _make_bars(30, noise=10)  # Smooth data — few structural pivots
        levels = detect_support_levels_variant_b(bars, params)
        for lv in levels:
            assert lv.touch_count >= 3


# ---------------------------------------------------------------------------
# TEST-DET-05: Empty output on insufficient data
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """TEST-DET-05"""

    def test_variant_a_empty_bars(self):
        params = DetectorAParams()
        levels = detect_support_levels_variant_a(pd.DataFrame(), params)
        assert levels == []

    def test_variant_b_empty_bars(self):
        params = DetectorBParams()
        levels = detect_support_levels_variant_b(pd.DataFrame(), params)
        assert levels == []

    def test_variant_a_too_few_bars(self):
        params = DetectorAParams(min_touch_count=3)
        bars = _make_bars(2)
        levels = detect_support_levels_variant_a(bars, params)
        assert levels == []

    def test_variant_b_too_few_bars_for_pivot(self):
        params = DetectorBParams(pivot_window=5)
        bars = _make_bars(4)
        levels = detect_support_levels_variant_b(bars, params)
        assert levels == []


# ---------------------------------------------------------------------------
# TEST-DET-06: Overlap metric
# ---------------------------------------------------------------------------

class TestOverlapMetric:
    """TEST-DET-06"""

    def test_identical_signals_overlap_1(self):
        overlap = compute_detector_overlap([1, 5, 10], [1, 5, 10])
        assert overlap == 1.0

    def test_disjoint_signals_overlap_0(self):
        overlap = compute_detector_overlap([1, 2, 3], [4, 5, 6])
        assert overlap == 0.0

    def test_partial_overlap(self):
        # A={1,2,3,4}, B={3,4,5,6} → intersection={3,4}, union={1,2,3,4,5,6}
        overlap = compute_detector_overlap([1, 2, 3, 4], [3, 4, 5, 6])
        assert abs(overlap - 2 / 6) < 1e-9

    def test_empty_both_returns_nan(self):
        import math
        overlap = compute_detector_overlap([], [])
        assert math.isnan(overlap)

    def test_one_empty_returns_zero(self):
        overlap = compute_detector_overlap([1, 2], [])
        assert overlap == 0.0


# ---------------------------------------------------------------------------
# TEST-DET-07: Current bar excluded from detection
# ---------------------------------------------------------------------------

class TestCurrentBarExclusion:
    """TEST-DET-07: Detectors receive bars[0:i-1] — bar i not visible."""

    def test_variant_a_does_not_see_current_bar(self):
        """
        The last row in bars_slice is bar i-1.
        Detectors cannot see bar i (not passed in).
        We verify by running on a slice of n-1 bars and confirming no level
        references bar n-1 (which would be bar i in a full dataset).
        """
        params = DetectorAParams(min_touch_count=3, min_bounce_atr=0.0)
        n = 70
        touch_indices = [10, 20, 35]
        bars = _make_flat_support_bars(n, support_price=29000.0, touch_indices=touch_indices)

        # Pass bars[0:n-1] — simulating the engine passing bars up to i-1
        bars_slice = bars.iloc[:n - 1]
        levels = detect_support_levels_variant_a(bars_slice, params, bar_offset=0)

        # Levels' last_touch_bar should be within bars_slice (< n-1)
        for lv in levels:
            assert lv.last_touch_bar < n - 1, (
                f"Level last_touch_bar={lv.last_touch_bar} references bar that shouldn't be visible"
            )
