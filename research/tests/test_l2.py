"""
L2 strategy tests.

TEST-L2-01: MVS_FULL requires all three conditions
TEST-L2-02: MACRO_ONLY fires whenever macro passes
TEST-L2-03: TOUCH_ONLY fires on touch regardless of macro
TEST-L2-04: MVS_NO_CONFIRM fires without confirmation
TEST-L2-05: Stop anchored to EMA, not to entry price
TEST-L2-06: Target anchored to entry price
TEST-L2-07a: Fee model applied correctly
TEST-L2-07b: Funding rate cost applied
TEST-L2-07c: Slippage adjustment on effective_entry_price
"""

from __future__ import annotations

import math
import pytest
import pandas as pd
import numpy as np

from research.config.params import L2Params, BacktestParams
from research.strategies.l2_mvs import L2SignalMode, evaluate_l2_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PARAMS = L2Params()
TS = pd.Timestamp("2023-06-01 04:00:00", tz="UTC")

def _eval(
    mode: L2SignalMode,
    open_p: float = 30500.0,
    high_p: float = 31000.0,
    low_p: float = 29800.0,   # touches EMA at 30000 (within 0.3%)
    close_p: float = 30600.0, # bullish close (> open)
    ema21: float = 30000.0,
    atr14: float = 400.0,
    sma200: float = 25000.0,   # BTC above SMA200 → macro passes
    btc_close: float = 35000.0,
    regime: str = "STRONG_BULL",
    params: L2Params = PARAMS,
) -> object:
    return evaluate_l2_signal(
        bar_index=1500,
        open_price=open_p,
        high_price=high_p,
        low_price=low_p,
        close_price=close_p,
        timestamp=TS,
        ema21=ema21,
        atr14=atr14,
        daily_sma200_aligned=sma200,
        btc_daily_close_aligned=btc_close,
        regime=regime,
        mode=mode,
        params=params,
    )


# ---------------------------------------------------------------------------
# TEST-L2-01: MVS_FULL all conditions
# ---------------------------------------------------------------------------

class TestMVSFull:
    """TEST-L2-01"""

    def test_mvs_full_fires_when_all_conditions_met(self):
        sig = _eval(L2SignalMode.MVS_FULL)
        assert sig is not None
        assert sig.signal_fired is True

    def test_mvs_full_rejected_when_macro_fails(self):
        sig = _eval(
            L2SignalMode.MVS_FULL,
            sma200=40000.0,   # BTC below SMA200
            btc_close=35000.0,
        )
        assert sig is not None
        assert sig.signal_fired is False
        assert "macro" in sig.filter_rejection_reason

    def test_mvs_full_rejected_when_no_ema_touch(self):
        # low far above EMA
        sig = _eval(
            L2SignalMode.MVS_FULL,
            low_p=31000.0,  # far above EMA at 30000
            ema21=30000.0,
        )
        assert sig.signal_fired is False
        assert "touch" in sig.filter_rejection_reason

    def test_mvs_full_rejected_when_no_bullish_close(self):
        # close <= open (bearish candle)
        sig = _eval(
            L2SignalMode.MVS_FULL,
            open_p=30500.0,
            close_p=30400.0,  # close < open → bearish
        )
        assert sig.signal_fired is False
        assert "confirmation" in sig.filter_rejection_reason

    def test_mvs_full_touch_tolerance(self):
        """
        Touch is detected when low <= ema21 * (1 + touch_tolerance).
        touch_tolerance = 0.003 → touch if low <= ema21 * 1.003.
        """
        ema = 30000.0
        touch_threshold = ema * (1 + PARAMS.touch_tolerance)

        # Exactly at threshold → touch
        sig = _eval(L2SignalMode.MVS_FULL, low_p=touch_threshold, ema21=ema)
        assert sig.signal_fired is True

        # Just above threshold → no touch
        sig = _eval(L2SignalMode.MVS_FULL, low_p=touch_threshold + 1.0, ema21=ema)
        assert sig.signal_fired is False


# ---------------------------------------------------------------------------
# TEST-L2-02: MACRO_ONLY mode
# ---------------------------------------------------------------------------

class TestMacroOnly:
    """TEST-L2-02"""

    def test_macro_only_fires_without_touch(self):
        """MACRO_ONLY does not require EMA touch."""
        sig = _eval(
            L2SignalMode.MACRO_ONLY,
            low_p=32000.0,  # well above EMA — no touch
        )
        assert sig is not None
        assert sig.signal_fired is True

    def test_macro_only_fires_without_bullish_close(self):
        """MACRO_ONLY does not require bullish confirmation."""
        sig = _eval(
            L2SignalMode.MACRO_ONLY,
            open_p=30600.0,
            close_p=30400.0,  # bearish
        )
        assert sig.signal_fired is True

    def test_macro_only_rejected_when_macro_fails(self):
        sig = _eval(
            L2SignalMode.MACRO_ONLY,
            sma200=40000.0,
            btc_close=35000.0,
        )
        assert sig.signal_fired is False


# ---------------------------------------------------------------------------
# TEST-L2-03: TOUCH_ONLY mode
# ---------------------------------------------------------------------------

class TestTouchOnly:
    """TEST-L2-03"""

    def test_touch_only_fires_in_bear_market(self):
        """TOUCH_ONLY ignores macro filter — fires even below SMA200."""
        sig = _eval(
            L2SignalMode.TOUCH_ONLY,
            sma200=40000.0,  # bear market
            btc_close=35000.0,
        )
        assert sig.signal_fired is True

    def test_touch_only_rejected_when_no_touch(self):
        sig = _eval(
            L2SignalMode.TOUCH_ONLY,
            low_p=31000.0,  # above EMA
        )
        assert sig.signal_fired is False

    def test_touch_only_fires_without_bullish_close(self):
        """TOUCH_ONLY does not require confirmation."""
        sig = _eval(
            L2SignalMode.TOUCH_ONLY,
            open_p=30600.0,
            close_p=30400.0,  # bearish
        )
        assert sig.signal_fired is True


# ---------------------------------------------------------------------------
# TEST-L2-04: MVS_NO_CONFIRM mode
# ---------------------------------------------------------------------------

class TestMVSNoConfirm:
    """TEST-L2-04"""

    def test_mvs_no_confirm_fires_with_bearish_close(self):
        """MVS_NO_CONFIRM requires macro + touch but NOT confirmation candle."""
        sig = _eval(
            L2SignalMode.MVS_NO_CONFIRM,
            open_p=30600.0,
            close_p=30400.0,  # bearish — would fail MVS_FULL
        )
        assert sig.signal_fired is True

    def test_mvs_no_confirm_still_requires_macro(self):
        sig = _eval(
            L2SignalMode.MVS_NO_CONFIRM,
            sma200=40000.0,
            btc_close=35000.0,
        )
        assert sig.signal_fired is False

    def test_mvs_no_confirm_still_requires_touch(self):
        sig = _eval(
            L2SignalMode.MVS_NO_CONFIRM,
            low_p=32000.0,  # no touch
        )
        assert sig.signal_fired is False


# ---------------------------------------------------------------------------
# TEST-L2-05: Stop anchored to EMA, not entry
# ---------------------------------------------------------------------------

class TestStopAnchor:
    """TEST-L2-05"""

    def test_stop_anchored_to_ema(self):
        """
        stop_price = ema21 * (1 - touch_tolerance) - stop_atr_multiplier * atr14
        NOT = close - stop_atr_multiplier * atr14
        """
        ema = 30000.0
        atr = 400.0
        expected_stop = ema * (1 - PARAMS.touch_tolerance) - PARAMS.stop_atr_multiplier * atr

        sig = _eval(L2SignalMode.MVS_FULL, ema21=ema, atr14=atr)
        assert sig.signal_fired is True
        assert abs(sig.stop_price - expected_stop) < 1e-9, (
            f"Expected stop {expected_stop}, got {sig.stop_price}"
        )

    def test_stop_is_below_entry(self):
        sig = _eval(L2SignalMode.MVS_FULL)
        assert sig.stop_price < sig.entry_price, "Stop must be below entry for long trades"


# ---------------------------------------------------------------------------
# TEST-L2-06: Target anchored to entry
# ---------------------------------------------------------------------------

class TestTargetAnchor:
    """TEST-L2-06"""

    def test_target_is_entry_plus_atr_multiple(self):
        """
        target_price = entry_price + target_atr_multiplier * atr14
        """
        close = 30600.0
        atr = 400.0
        expected_target = close + PARAMS.target_atr_multiplier * atr

        sig = _eval(L2SignalMode.MVS_FULL, close_p=close, atr14=atr)
        assert sig.signal_fired is True
        assert abs(sig.target_price - expected_target) < 1e-9, (
            f"Expected target {expected_target}, got {sig.target_price}"
        )


# ---------------------------------------------------------------------------
# TEST-L2-07c: Slippage on effective_entry_price
# (Full fee tests are in test_accounting.py — this tests the engine integration)
# ---------------------------------------------------------------------------

class TestSlippage:
    """TEST-L2-07c"""

    def test_entry_price_is_close(self):
        """entry_price (signal price) must equal close_price."""
        close = 30600.0
        sig = _eval(L2SignalMode.MVS_FULL, close_p=close)
        assert abs(sig.entry_price - close) < 1e-9

    def test_nan_atr_returns_none_for_non_random_modes(self):
        """Bars with NaN ATR should return None (warmup skip)."""
        for mode in [L2SignalMode.MVS_FULL, L2SignalMode.TOUCH_ONLY, L2SignalMode.MACRO_ONLY]:
            result = _eval(mode, atr14=float("nan"))
            assert result is None, f"Expected None for NaN ATR in {mode}"

    def test_random_mode_skips_on_nan_atr(self):
        result = _eval(L2SignalMode.RANDOM, atr14=float("nan"))
        assert result is None
