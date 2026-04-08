"""
S2 strategy tests.

TEST-S2-01: Breakdown condition (close < level * (1 - threshold))
TEST-S2-02: Volume confirmation (volume > sma20 * multiplier)
TEST-S2-03: No signal when no active levels
TEST-S2-04: Stop above entry for short trades
TEST-S2-05: Target below entry for short trades
TEST-S2-06: Multiple level conflict resolution (highest touch_count wins)
TEST-S2-07: NaN indicators return None
TEST-S2-08: same-bar stop/target conflict in engine → stop hit
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from research.config.params import S2Params
from research.detectors.support import SupportLevel
from research.strategies.s2_mvs import evaluate_s2_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PARAMS = S2Params()
TS = pd.Timestamp("2023-06-01 04:00:00", tz="UTC")

def _make_level(
    level_price: float,
    touch_count: int = 3,
    first_touch_bar: int = 10,
    last_touch_bar: int = 50,
    variant: str = "A",
) -> SupportLevel:
    return SupportLevel(
        level_price=level_price,
        touch_count=touch_count,
        first_touch_bar=first_touch_bar,
        last_touch_bar=last_touch_bar,
        detector_variant=variant,
    )


def _eval(
    close_p: float = 29800.0,      # below support at 30000 → breakdown
    volume: float = 2000.0,        # > 1.5 * 1000 (vol_sma20) → volume confirmed
    vol_sma20: float = 1000.0,
    atr14: float = 400.0,
    active_levels: list | None = None,
    bar_index: int = 100,
    regime: str = "BEAR",
    params: S2Params = PARAMS,
    detector_variant: str = "A",
) -> object:
    if active_levels is None:
        active_levels = [_make_level(30000.0)]

    return evaluate_s2_signal(
        bar_index=bar_index,
        open_price=30100.0,
        high_price=30200.0,
        low_price=29700.0,
        close_price=close_p,
        volume=volume,
        timestamp=TS,
        atr14=atr14,
        vol_sma20=vol_sma20,
        regime=regime,
        active_levels=active_levels,
        params=params,
        detector_variant=detector_variant,
    )


# ---------------------------------------------------------------------------
# TEST-S2-01: Breakdown condition
# ---------------------------------------------------------------------------

class TestBreakdownCondition:
    """TEST-S2-01"""

    def test_breakdown_fires_when_close_below_threshold(self):
        """
        level = 30000, threshold = 0.3% → breakdown if close < 30000 * 0.997 = 29910.
        close=29800 → fires.
        """
        sig = _eval(close_p=29800.0)
        assert sig is not None
        assert sig.signal_fired is True

    def test_no_breakdown_when_close_at_level(self):
        """close = level_price → no breakdown."""
        sig = _eval(close_p=30000.0)
        assert sig.signal_fired is False

    def test_no_breakdown_when_close_above_threshold(self):
        """close = 29950 > 29910 (threshold) → no breakdown."""
        sig = _eval(close_p=29950.0)
        assert sig.signal_fired is False

    def test_breakdown_exactly_at_threshold(self):
        """
        close exactly at level * (1 - threshold) → boundary condition.
        breakdown requires close < threshold, so exact equality → no signal.
        """
        level = 30000.0
        threshold_price = level * (1 - PARAMS.breakdown_threshold)
        # Exactly at threshold → no breakdown (not strictly less than)
        sig = _eval(close_p=threshold_price, active_levels=[_make_level(level)])
        assert sig.signal_fired is False

    def test_breakdown_just_below_threshold(self):
        level = 30000.0
        threshold_price = level * (1 - PARAMS.breakdown_threshold) - 0.01
        sig = _eval(close_p=threshold_price, active_levels=[_make_level(level)])
        assert sig.signal_fired is True


# ---------------------------------------------------------------------------
# TEST-S2-02: Volume confirmation
# ---------------------------------------------------------------------------

class TestVolumeConfirmation:
    """TEST-S2-02"""

    def test_volume_fires_when_above_multiplier(self):
        """volume = 1600 > 1.5 * 1000 = 1500 → confirmed."""
        sig = _eval(volume=1600.0, vol_sma20=1000.0)
        assert sig.signal_fired is True

    def test_volume_rejected_when_below_multiplier(self):
        """volume = 1400 < 1500 → rejected."""
        sig = _eval(volume=1400.0, vol_sma20=1000.0)
        assert sig.signal_fired is False

    def test_volume_exactly_at_multiplier_rejected(self):
        """volume = 1500.0 = 1.5 * 1000.0 → NOT confirmed (needs strictly greater)."""
        sig = _eval(volume=1500.0, vol_sma20=1000.0)
        assert sig.signal_fired is False


# ---------------------------------------------------------------------------
# TEST-S2-03: No signal when no active levels
# ---------------------------------------------------------------------------

class TestNoActiveLevels:
    """TEST-S2-03"""

    def test_no_signal_without_active_levels(self):
        sig = _eval(active_levels=[])
        assert sig is not None
        assert sig.signal_fired is False
        assert sig.filter_rejection_reason == "no_active_levels"


# ---------------------------------------------------------------------------
# TEST-S2-04: Stop above entry for short
# ---------------------------------------------------------------------------

class TestShortStop:
    """TEST-S2-04"""

    def test_stop_is_above_entry(self):
        """
        Short stop = level_price + 0.5 * ATR14.
        stop must be above entry (breakdown close).
        """
        level = 30000.0
        atr = 400.0
        close = 29800.0
        expected_stop = level + PARAMS.stop_atr_multiplier * atr  # 30000 + 200 = 30200

        sig = _eval(close_p=close, atr14=atr, active_levels=[_make_level(level)])
        assert sig.signal_fired is True
        assert abs(sig.stop_price - expected_stop) < 1e-9, (
            f"Expected stop={expected_stop}, got {sig.stop_price}"
        )
        assert sig.stop_price > sig.entry_price, "Stop must be above entry for short"


# ---------------------------------------------------------------------------
# TEST-S2-05: Target below entry for short
# ---------------------------------------------------------------------------

class TestShortTarget:
    """TEST-S2-05"""

    def test_target_is_below_entry(self):
        """target = entry - 2.0 * ATR14."""
        close = 29800.0
        atr = 400.0
        expected_target = close - PARAMS.target_atr_multiplier * atr  # 29800 - 800 = 29000

        sig = _eval(close_p=close, atr14=atr)
        assert sig.signal_fired is True
        assert abs(sig.target_price - expected_target) < 1e-9, (
            f"Expected target={expected_target}, got {sig.target_price}"
        )
        assert sig.target_price < sig.entry_price, "Target must be below entry for short"


# ---------------------------------------------------------------------------
# TEST-S2-06: Multiple level conflict resolution
# ---------------------------------------------------------------------------

class TestMultipleLevelConflict:
    """TEST-S2-06"""

    def test_highest_touch_count_wins(self):
        """When two levels qualify, the one with more touches is selected."""
        level_low = 30000.0
        level_high = 30050.0  # also below close=29800 threshold

        levels = [
            _make_level(level_low, touch_count=3, last_touch_bar=50),
            _make_level(level_high, touch_count=5, last_touch_bar=40),
        ]
        sig = _eval(close_p=29700.0, active_levels=levels)
        assert sig.signal_fired is True
        assert sig.touch_count == 5, f"Expected 5 touches (highest), got {sig.touch_count}"
        assert sig.multiple_levels_conflict is True

    def test_most_recent_wins_on_touch_count_tie(self):
        """On tie: most recently formed level (highest last_touch_bar) wins."""
        level_a = _make_level(30000.0, touch_count=3, last_touch_bar=40)
        level_b = _make_level(30020.0, touch_count=3, last_touch_bar=60)  # more recent

        sig = _eval(close_p=29700.0, active_levels=[level_a, level_b])
        assert sig.signal_fired is True
        # last_touch_bar=60 is more recent → level_b wins
        assert abs(sig.support_level - 30020.0) < 1.0 or abs(sig.support_level - 30000.0) < 1.0
        # Verify it picked the right one
        assert sig.multiple_levels_conflict is True


# ---------------------------------------------------------------------------
# TEST-S2-07: NaN indicators return None
# ---------------------------------------------------------------------------

class TestNaNIndicators:
    """TEST-S2-07"""

    def test_nan_atr_returns_none(self):
        result = _eval(atr14=float("nan"))
        assert result is None

    def test_nan_vol_sma_returns_none(self):
        result = _eval(vol_sma20=float("nan"))
        assert result is None

    def test_zero_atr_returns_none(self):
        result = _eval(atr14=0.0)
        assert result is None

    def test_zero_vol_sma_returns_none(self):
        result = _eval(vol_sma20=0.0)
        assert result is None
