"""
Indicator tests — all use synthetic data.

TEST-IND-01: EMA warmup (period=21, first 20 values are NaN)
TEST-IND-02: EMA correctness against manually computed values
TEST-IND-03: ATR warmup (period=14, first 13 values are NaN)
TEST-IND-04: Volume SMA excludes current bar
TEST-IND-05: Regime label forward-fill timing (D+1 rule)
"""

from __future__ import annotations

import pytest
import numpy as np
import pandas as pd

from research.indicators.trend import compute_ema, compute_sma, compute_ema_slope
from research.indicators.volatility import compute_atr
from research.indicators.volume import compute_volume_sma, compute_relative_volume
from research.indicators.regime import classify_regime, compute_regime_labels
from research.data.align import align_regime_labels


# ---------------------------------------------------------------------------
# TEST-IND-01: EMA warmup
# ---------------------------------------------------------------------------

class TestEMAWarmup:
    """TEST-IND-01"""

    def test_ema_period_21_first_20_are_nan(self):
        series = pd.Series(range(1, 51), dtype=float)
        ema = compute_ema(series, period=21)

        # First 20 values (indices 0–19) must be NaN
        assert ema.iloc[:20].isna().all(), (
            f"Expected first 20 EMA values to be NaN, got: {ema.iloc[:20].tolist()}"
        )

    def test_ema_period_21_value_at_index_20_is_not_nan(self):
        series = pd.Series(range(1, 51), dtype=float)
        ema = compute_ema(series, period=21)
        assert not pd.isna(ema.iloc[20]), (
            f"EMA value at index 20 should not be NaN, got {ema.iloc[20]}"
        )

    def test_ema_period_1_no_warmup(self):
        """Period 1 means no warmup — all values present."""
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        ema = compute_ema(series, period=1)
        assert not ema.isna().any(), "Period-1 EMA should have no NaN values"

    def test_ema_period_5_first_4_are_nan(self):
        series = pd.Series(range(1, 21), dtype=float)
        ema = compute_ema(series, period=5)
        assert ema.iloc[:4].isna().all()
        assert not pd.isna(ema.iloc[4])

    def test_ema_invalid_period_raises(self):
        series = pd.Series([1.0, 2.0, 3.0])
        with pytest.raises(ValueError):
            compute_ema(series, period=0)


# ---------------------------------------------------------------------------
# TEST-IND-02: EMA correctness
# ---------------------------------------------------------------------------

class TestEMACorrectness:
    """TEST-IND-02"""

    def test_ema_manual_period_3(self):
        """
        Manually compute EMA(3) for a known series and verify.
        alpha = 2 / (3 + 1) = 0.5

        Series: [10, 20, 30, 40, 50]
        EMA[0] = 10
        EMA[1] = 0.5*20 + 0.5*10 = 15
        EMA[2] = 0.5*30 + 0.5*15 = 22.5

        With warmup enforcement: indices 0,1 are NaN, index 2 is first valid.
        """
        series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        ema = compute_ema(series, period=3)

        # First 2 values must be NaN
        assert pd.isna(ema.iloc[0])
        assert pd.isna(ema.iloc[1])

        # Index 2: pandas ewm(adjust=False) EMA
        # The ewm formula treats the first value as EMA[0]=series[0], then recurses.
        # EMA[2] = 0.5*30 + 0.5*(0.5*20 + 0.5*10) = 0.5*30 + 0.5*15 = 22.5
        assert abs(ema.iloc[2] - 22.5) < 1e-9, f"Expected 22.5 at index 2, got {ema.iloc[2]}"

        # Index 3: 0.5*40 + 0.5*22.5 = 31.25
        assert abs(ema.iloc[3] - 31.25) < 1e-9, f"Expected 31.25 at index 3, got {ema.iloc[3]}"

        # Index 4: 0.5*50 + 0.5*31.25 = 40.625
        assert abs(ema.iloc[4] - 40.625) < 1e-9, f"Expected 40.625 at index 4, got {ema.iloc[4]}"

    def test_ema_constant_series_equals_constant(self):
        """EMA of a constant series must equal that constant (after warmup)."""
        series = pd.Series([100.0] * 30)
        ema = compute_ema(series, period=10)
        valid = ema.dropna()
        assert (valid == 100.0).all(), "EMA of constant series must equal the constant"

    def test_ema_uses_adjust_false(self):
        """
        Verify ewm(adjust=False) behavior: first value is series[0], not an estimate.
        """
        series = pd.Series([10.0, 20.0, 30.0])
        ema = compute_ema(series, period=2)
        # alpha = 2/(2+1) = 2/3
        # EMA[0] = 10, EMA[1] = 2/3*20 + 1/3*10 = 16.667
        # With period=2: index 0 is NaN, index 1 is first valid
        assert not pd.isna(ema.iloc[1])
        expected = 2 / 3 * 20 + 1 / 3 * 10
        assert abs(ema.iloc[1] - expected) < 1e-9, (
            f"Expected {expected}, got {ema.iloc[1]}"
        )

    def test_sma_correctness(self):
        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        sma = compute_sma(series, period=3)
        assert pd.isna(sma.iloc[0])
        assert pd.isna(sma.iloc[1])
        assert abs(sma.iloc[2] - 2.0) < 1e-9  # (1+2+3)/3
        assert abs(sma.iloc[3] - 3.0) < 1e-9  # (2+3+4)/3
        assert abs(sma.iloc[4] - 4.0) < 1e-9  # (3+4+5)/3

    def test_ema_slope_positive(self):
        """EMA slope True when EMA[i] > EMA[i-3]."""
        series = pd.Series(range(1, 31), dtype=float)
        ema = compute_ema(series, period=5)
        slope = compute_ema_slope(ema, lookback=3)
        # In an ascending series, slope must be True for all valid bars
        valid_slope = slope[slope.index >= 3 + 4]  # skip NaN region
        assert valid_slope.all(), "EMA slope must be True for strictly ascending series"

    def test_ema_slope_false_on_descending(self):
        series = pd.Series(range(30, 0, -1), dtype=float)
        ema = compute_ema(series, period=5)
        slope = compute_ema_slope(ema, lookback=3)
        # For descending series: EMA[i] < EMA[i-3] → slope False
        valid_slope = slope[slope.index >= 3 + 4]
        assert not valid_slope.any(), "EMA slope must be False for strictly descending series"


# ---------------------------------------------------------------------------
# TEST-IND-03: ATR warmup
# ---------------------------------------------------------------------------

class TestATRWarmup:
    """TEST-IND-03"""

    def test_atr_period_14_first_13_are_nan(self):
        """
        ATR(14) should have NaN for indices 0–12 (first 13 values).

        TR[0] is valid: True Range uses max(high-low, |high-prev_close|, |low-prev_close|).
        At index 0, prev_close is NaN so the last two terms are NaN, but high-low is valid.
        pandas max() skips NaN, so TR[0] = high[0] - low[0] (a valid value).

        With 14 valid TR values needed (TR[0] is valid), rolling(14).mean() first fires
        at index 13. Therefore indices 0–12 (13 values) are NaN, index 13 is first valid.
        """
        n = 50
        np.random.seed(0)
        close = pd.Series(30000 + np.cumsum(np.random.randn(n) * 100))
        high = close + np.abs(np.random.randn(n) * 50)
        low = close - np.abs(np.random.randn(n) * 50)

        atr = compute_atr(high, low, close, period=14)

        # Indices 0 through 12 must be NaN (first 13 values)
        assert atr.iloc[:13].isna().all(), (
            f"Expected first 13 ATR values to be NaN, got: {atr.iloc[:13].tolist()}"
        )

    def test_atr_first_valid_at_index_13(self):
        """First valid ATR(14) appears at index 13 (14th bar, 0-indexed)."""
        n = 50
        np.random.seed(0)
        close = pd.Series(30000 + np.cumsum(np.random.randn(n) * 100))
        high = close + np.abs(np.random.randn(n) * 50)
        low = close - np.abs(np.random.randn(n) * 50)

        atr = compute_atr(high, low, close, period=14)
        assert not pd.isna(atr.iloc[13]), (
            f"ATR should be valid at index 13, got NaN"
        )

    def test_atr_positive_values(self):
        n = 50
        np.random.seed(1)
        close = pd.Series(30000 + np.cumsum(np.random.randn(n) * 100))
        high = close + np.abs(np.random.randn(n) * 50) + 10
        low = close - np.abs(np.random.randn(n) * 50) - 10

        atr = compute_atr(high, low, close, period=14)
        valid = atr.dropna()
        assert (valid > 0).all(), "All valid ATR values must be positive"

    def test_atr_zero_range_series(self):
        """ATR of a constant series is 0."""
        n = 30
        close = pd.Series([100.0] * n)
        high = close.copy()
        low = close.copy()
        atr = compute_atr(high, low, close, period=14)
        valid = atr.dropna()
        assert (valid == 0.0).all(), "ATR of flat series must be 0"


# ---------------------------------------------------------------------------
# TEST-IND-04: Volume SMA excludes current bar
# ---------------------------------------------------------------------------

class TestVolumeSMAExcludesCurrentBar:
    """TEST-IND-04"""

    def test_volume_sma_excludes_current_bar(self):
        """
        volume_sma.iloc[i] = mean(volume[i-period : i]) — does NOT include bar i.
        Test with period=3 on known values.
        """
        volume = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
        sma = compute_volume_sma(volume, period=3)

        # At index 3: should be mean(volume[0:3]) = mean(10,20,30) = 20
        # NOT mean(10,20,30,40) = 25
        assert abs(sma.iloc[3] - 20.0) < 1e-9, (
            f"volume_sma at index 3 should be 20 (mean of indices 0-2), got {sma.iloc[3]}"
        )

        # At index 4: should be mean(volume[1:4]) = mean(20,30,40) = 30
        assert abs(sma.iloc[4] - 30.0) < 1e-9, (
            f"volume_sma at index 4 should be 30 (mean of indices 1-3), got {sma.iloc[4]}"
        )

        # At index 5: should be mean(volume[2:5]) = mean(30,40,50) = 40
        assert abs(sma.iloc[5] - 40.0) < 1e-9, (
            f"volume_sma at index 5 should be 40 (mean of indices 2-4), got {sma.iloc[5]}"
        )

    def test_volume_sma_nan_for_first_period_bars(self):
        """
        With period=3, indices 0, 1, 2 must be NaN (need at least 3 prior bars).
        Index 3 is the first valid value.
        """
        volume = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        sma = compute_volume_sma(volume, period=3)

        # Indices 0, 1, 2, 3 should be NaN because at index 3 we need volume[0:3]
        # The shift(1) makes index 3 the first with 3 prior values
        assert sma.iloc[0:3].isna().all(), (
            f"First 3 values should be NaN, got: {sma.iloc[0:3].tolist()}"
        )

    def test_current_bar_spike_does_not_contaminate_sma(self):
        """
        Even if current bar has extreme volume, the SMA at that bar should not include it.
        """
        volume = pd.Series([10.0, 10.0, 10.0, 10.0, 10.0, 1_000_000.0])
        sma = compute_volume_sma(volume, period=3)

        # At index 5 (the spike): sma should be mean(volume[2:5]) = mean(10,10,10) = 10
        # NOT contaminated by the 1_000_000 spike
        assert abs(sma.iloc[5] - 10.0) < 1e-9, (
            f"Volume SMA at spike bar should be 10 (excludes spike), got {sma.iloc[5]}"
        )

    def test_relative_volume_calculation(self):
        volume = pd.Series([10.0, 20.0, 30.0, 60.0])
        sma = compute_volume_sma(volume, period=2)
        rel_vol = compute_relative_volume(volume, sma)

        # At index 3: sma = mean(volume[1:3]) = mean(20,30) = 25; rel_vol = 60/25 = 2.4
        assert abs(rel_vol.iloc[3] - 2.4) < 1e-9, (
            f"Expected relative volume 2.4 at index 3, got {rel_vol.iloc[3]}"
        )


# ---------------------------------------------------------------------------
# TEST-IND-05: Regime label forward-fill timing (D+1 rule)
# ---------------------------------------------------------------------------

class TestRegimeLabelForwardFill:
    """TEST-IND-05"""

    def test_regime_label_d_plus_1_rule(self):
        """
        Regime label from day D must only appear in 4H bars starting on D+1.
        """
        daily_dates = pd.date_range("2022-01-10", "2022-01-20", freq="D", tz="UTC")
        regime_sequence = [
            "TRANSITION", "WEAK_BULL", "STRONG_BULL", "STRONG_BULL", "HIGH_VOL_BULLISH",
            "HIGH_VOL_BEARISH", "BEAR", "WEAK_BULL", "TRANSITION", "STRONG_BULL", "BEAR"
        ]
        daily_labels = pd.Series(regime_sequence, index=daily_dates)

        four_h_ts = pd.date_range("2022-01-14 00:00", "2022-01-16 20:00", freq="4h", tz="UTC")
        aligned = align_regime_labels(daily_labels, four_h_ts)

        # Jan 15 00:00: should see Jan 14's regime (index 4 = HIGH_VOL_BULLISH)
        bar_jan15 = pd.Timestamp("2022-01-15 00:00", tz="UTC")
        jan14_regime = regime_sequence[4]  # daily_dates[4] = Jan 14
        assert aligned[bar_jan15] == jan14_regime, (
            f"4H bar on Jan 15 00:00 should see Jan 14 regime '{jan14_regime}', "
            f"got '{aligned[bar_jan15]}'"
        )

        # Jan 14 16:00: should also see Jan 13's regime (index 3 = STRONG_BULL)
        bar_jan14_1600 = pd.Timestamp("2022-01-14 16:00", tz="UTC")
        jan13_regime = regime_sequence[3]  # daily_dates[3] = Jan 13
        assert aligned[bar_jan14_1600] == jan13_regime, (
            f"4H bar on Jan 14 16:00 should see Jan 13 regime '{jan13_regime}', "
            f"got '{aligned[bar_jan14_1600]}'"
        )

    def test_regime_classify_nan_inputs_return_undefined(self):
        """classify_regime returns 'UNDEFINED' for any NaN input."""
        assert classify_regime(float("nan"), 30000, 32000, 0.05, 1.2) == "UNDEFINED"
        assert classify_regime(35000, float("nan"), 32000, 0.05, 1.2) == "UNDEFINED"
        assert classify_regime(35000, 30000, float("nan"), 0.05, 1.2) == "UNDEFINED"
        assert classify_regime(35000, 30000, 32000, float("nan"), 1.2) == "UNDEFINED"
        assert classify_regime(35000, 30000, 32000, 0.05, float("nan")) == "UNDEFINED"

    def test_regime_ordering_high_vol_before_weak_bull(self):
        """
        HIGH_VOL_BULLISH must match before WEAK_BULL when VOL_ratio >= 2.0.
        """
        # Conditions that qualify as BOTH HIGH_VOL_BULLISH and WEAK_BULL:
        # price > SMA200, ROC_20 > -0.05 (WEAK_BULL), vol_ratio >= 2.0 (HIGH_VOL_BULLISH)
        result = classify_regime(
            btc_close=35000,
            sma_200=30000,
            sma_50=32000,
            roc_20=0.02,    # > -0.05 → qualifies for WEAK_BULL
            vol_ratio=2.5,  # >= 2.0 → qualifies for HIGH_VOL_BULLISH
        )
        assert result == "HIGH_VOL_BULLISH", (
            f"Expected HIGH_VOL_BULLISH (must precede WEAK_BULL), got {result!r}"
        )

    def test_regime_ordering_high_vol_bearish_before_bear(self):
        """
        HIGH_VOL_BEARISH must match before BEAR when VOL_ratio >= 2.0 and price < SMA200.
        """
        result = classify_regime(
            btc_close=25000,
            sma_200=30000,
            sma_50=28000,
            roc_20=-0.10,   # < -0.05 → qualifies for BEAR
            vol_ratio=3.0,  # >= 2.0 → qualifies for HIGH_VOL_BEARISH
        )
        assert result == "HIGH_VOL_BEARISH", (
            f"Expected HIGH_VOL_BEARISH (must precede BEAR), got {result!r}"
        )

    def test_strong_bull_conditions(self):
        result = classify_regime(
            btc_close=32500,  # > 30000*1.05 = 31500
            sma_200=30000,
            sma_50=31000,
            roc_20=0.15,     # > 0.10
            vol_ratio=1.2,   # < 1.5
        )
        assert result == "STRONG_BULL", f"Expected STRONG_BULL, got {result!r}"

    def test_bear_conditions(self):
        result = classify_regime(
            btc_close=25000,
            sma_200=30000,
            sma_50=28000,
            roc_20=-0.10,
            vol_ratio=1.0,
        )
        assert result == "BEAR", f"Expected BEAR, got {result!r}"

    def test_transition_catch_all(self):
        """TRANSITION is the catch-all for anything that doesn't match above."""
        # price > SMA200 (not BEAR), roc_20 = -0.06 (< -0.05, not WEAK_BULL),
        # vol_ratio = 1.0 (< 2.0, not HIGH_VOL), price not far enough above for STRONG_BULL
        result = classify_regime(
            btc_close=30100,  # just above SMA200
            sma_200=30000,
            sma_50=31000,
            roc_20=-0.06,    # too negative for WEAK_BULL (> -0.05 required)
            vol_ratio=1.0,
        )
        assert result == "TRANSITION", f"Expected TRANSITION, got {result!r}"
