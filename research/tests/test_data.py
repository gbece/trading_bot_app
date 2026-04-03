"""
Data integrity tests — all use synthetic data, NOT real data files.

TEST-DATA-01: OHLC consistency check
TEST-DATA-02: Duplicate timestamp detection
TEST-DATA-03: Gap detection
TEST-DATA-04: Daily-4H alignment timing (D+1 rule verified)
"""

from __future__ import annotations

import pytest
import numpy as np
import pandas as pd

from research.data.validate import (
    validate_ohlcv,
    check_no_duplicate_timestamps,
    check_no_large_gaps,
    check_ohlc_integrity,
    check_no_zero_volume,
    check_no_price_spikes,
    check_timestamp_monotonicity,
)
from research.data.align import align_daily_to_4h, align_regime_labels


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ohlcv(n: int = 100, freq: str = "4h", start: str = "2022-01-01") -> pd.DataFrame:
    """Create a clean synthetic OHLCV DataFrame."""
    timestamps = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    np.random.seed(42)
    close = 30000 + np.cumsum(np.random.randn(n) * 100)
    open_ = close + np.random.randn(n) * 50
    high = np.maximum(close, open_) + np.abs(np.random.randn(n) * 30)
    low = np.minimum(close, open_) - np.abs(np.random.randn(n) * 30)
    volume = np.abs(np.random.randn(n) * 1000) + 500

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ---------------------------------------------------------------------------
# TEST-DATA-01: OHLC consistency
# ---------------------------------------------------------------------------

class TestOHLCConsistency:
    """TEST-DATA-01"""

    def test_valid_ohlc_passes(self):
        df = make_ohlcv(50)
        # Should not raise
        check_ohlc_integrity(df)

    def test_high_less_than_low_raises(self):
        df = make_ohlcv(10)
        df.loc[5, "high"] = df.loc[5, "low"] - 1.0
        with pytest.raises(ValueError, match="CHECK-3"):
            check_ohlc_integrity(df)

    def test_high_less_than_open_raises(self):
        df = make_ohlcv(10)
        df.loc[3, "open"] = df.loc[3, "high"] + 10
        with pytest.raises(ValueError, match="CHECK-3"):
            check_ohlc_integrity(df)

    def test_high_less_than_close_raises(self):
        df = make_ohlcv(10)
        df.loc[3, "close"] = df.loc[3, "high"] + 10
        with pytest.raises(ValueError, match="CHECK-3"):
            check_ohlc_integrity(df)

    def test_low_greater_than_open_raises(self):
        df = make_ohlcv(10)
        df.loc[4, "open"] = df.loc[4, "low"] - 10
        with pytest.raises(ValueError, match="CHECK-3"):
            check_ohlc_integrity(df)

    def test_low_greater_than_close_raises(self):
        df = make_ohlcv(10)
        df.loc[4, "close"] = df.loc[4, "low"] - 10
        with pytest.raises(ValueError, match="CHECK-3"):
            check_ohlc_integrity(df)

    def test_validate_ohlcv_catches_ohlc_error(self):
        df = make_ohlcv(20)
        df.loc[10, "high"] = df.loc[10, "low"] - 1
        with pytest.raises(ValueError, match="CHECK-3"):
            validate_ohlcv(df, symbol="BTC", timeframe="4h")


# ---------------------------------------------------------------------------
# TEST-DATA-02: Duplicate timestamp detection
# ---------------------------------------------------------------------------

class TestDuplicateTimestamps:
    """TEST-DATA-02"""

    def test_no_duplicates_passes(self):
        df = make_ohlcv(20)
        check_no_duplicate_timestamps(df)  # should not raise

    def test_duplicate_raises(self):
        df = make_ohlcv(20)
        # Insert a duplicate at row 10
        dup_row = df.iloc[5:6].copy()
        df2 = pd.concat([df.iloc[:10], dup_row, df.iloc[10:]], ignore_index=True)
        with pytest.raises(ValueError, match="CHECK-1"):
            check_no_duplicate_timestamps(df2)

    def test_validate_ohlcv_catches_duplicate(self):
        df = make_ohlcv(20)
        dup_row = df.iloc[0:1].copy()
        df2 = pd.concat([df, dup_row], ignore_index=True).sort_values("timestamp").reset_index(drop=True)
        with pytest.raises(ValueError, match="CHECK-1"):
            validate_ohlcv(df2, symbol="BTC", timeframe="4h")

    def test_single_row_no_duplicate(self):
        df = make_ohlcv(1)
        check_no_duplicate_timestamps(df)  # should not raise


# ---------------------------------------------------------------------------
# TEST-DATA-03: Gap detection
# ---------------------------------------------------------------------------

class TestGapDetection:
    """TEST-DATA-03"""

    def test_no_gaps_passes(self):
        df = make_ohlcv(50, freq="4h")
        check_no_large_gaps(df, timeframe="4h")

    def test_single_missing_candle_allowed(self):
        """One missing 4H candle = gap of 8H — allowed (equals max of 2×4H)."""
        df = make_ohlcv(50, freq="4h")
        # Remove one row (creates 8H gap between adjacent bars)
        df2 = pd.concat([df.iloc[:20], df.iloc[21:]], ignore_index=True)
        check_no_large_gaps(df2, timeframe="4h")  # should not raise

    def test_two_missing_candles_raises(self):
        """Two missing 4H candles = gap of 12H — exceeds 2×4H = 8H."""
        df = make_ohlcv(50, freq="4h")
        # Remove two consecutive rows (creates 12H gap)
        df2 = pd.concat([df.iloc[:20], df.iloc[22:]], ignore_index=True)
        with pytest.raises(ValueError, match="CHECK-2"):
            check_no_large_gaps(df2, timeframe="4h")

    def test_validate_ohlcv_catches_gap(self):
        df = make_ohlcv(50, freq="4h")
        df2 = pd.concat([df.iloc[:20], df.iloc[23:]], ignore_index=True)
        with pytest.raises(ValueError, match="CHECK-2"):
            validate_ohlcv(df2, symbol="BTC", timeframe="4h")

    def test_daily_gap_detection(self):
        df = make_ohlcv(50, freq="1D")
        # Remove two rows — gap of 3 days > 2×1D allowed
        df2 = pd.concat([df.iloc[:20], df.iloc[23:]], ignore_index=True)
        with pytest.raises(ValueError, match="CHECK-2"):
            check_no_large_gaps(df2, timeframe="1d")


# ---------------------------------------------------------------------------
# TEST-DATA-04: Daily-4H alignment timing (D+1 rule)
# ---------------------------------------------------------------------------

class TestDailyAlignment:
    """TEST-DATA-04"""

    def test_daily_value_not_available_same_day(self):
        """
        Daily close from Jan 15 must NOT be available to 4H bars on Jan 15.
        It should first appear at Jan 16 00:00 UTC.
        """
        # Daily series: one value per day for Jan 12–20
        daily_dates = pd.date_range("2022-01-12", "2022-01-20", freq="D", tz="UTC")
        daily_values = pd.Series(range(len(daily_dates)), index=daily_dates, dtype=float)

        # 4H bars: every 4H from Jan 14 to Jan 18
        four_h_ts = pd.date_range("2022-01-14", "2022-01-18", freq="4h", tz="UTC")

        aligned = align_daily_to_4h(daily_values, four_h_ts)

        # Jan 14 00:00 UTC: daily value from Jan 13 (index 1) should be available
        # (Jan 13's value was published on Jan 13, available from Jan 14 onward)
        jan14_bar = pd.Timestamp("2022-01-14 00:00:00", tz="UTC")
        jan14_val = aligned[jan14_bar]
        jan13_val = daily_values[pd.Timestamp("2022-01-13", tz="UTC")]
        assert jan14_val == jan13_val, (
            f"4H bar on Jan 14 should see Jan 13's value ({jan13_val}), got {jan14_val}"
        )

    def test_daily_value_available_next_day(self):
        """
        Jan 15's daily value should first appear at Jan 16 00:00 UTC.
        """
        daily_dates = pd.date_range("2022-01-10", "2022-01-20", freq="D", tz="UTC")
        daily_values = pd.Series(
            [float(i * 100) for i in range(len(daily_dates))],
            index=daily_dates,
        )

        # 4H bars spanning Jan 15 and Jan 16
        four_h_ts = pd.date_range("2022-01-15", "2022-01-17", freq="4h", tz="UTC")

        aligned = align_daily_to_4h(daily_values, four_h_ts)

        jan15_val = daily_values[pd.Timestamp("2022-01-15", tz="UTC")]

        # Jan 15 00:00 4H bar: should see Jan 14's value, NOT Jan 15
        bar_jan15_0000 = pd.Timestamp("2022-01-15 00:00:00", tz="UTC")
        assert aligned[bar_jan15_0000] != jan15_val, (
            "Jan 15 00:00 4H bar must NOT see Jan 15 daily value (D+1 rule)"
        )

        # Jan 16 00:00 4H bar: should see Jan 15's value
        bar_jan16_0000 = pd.Timestamp("2022-01-16 00:00:00", tz="UTC")
        assert aligned[bar_jan16_0000] == jan15_val, (
            f"Jan 16 00:00 4H bar should see Jan 15 daily value ({jan15_val}), got {aligned[bar_jan16_0000]}"
        )

    def test_regime_label_alignment_uses_d_plus_1(self):
        """
        Regime labels follow the same D+1 rule as numeric indicators.
        """
        daily_dates = pd.date_range("2022-01-10", "2022-01-20", freq="D", tz="UTC")
        labels = ["STRONG_BULL", "WEAK_BULL", "TRANSITION", "BEAR", "HIGH_VOL_BEARISH",
                  "HIGH_VOL_BULLISH", "TRANSITION", "STRONG_BULL", "WEAK_BULL", "BEAR", "TRANSITION"]
        daily_labels = pd.Series(labels, index=daily_dates)

        four_h_ts = pd.date_range("2022-01-15", "2022-01-17", freq="4h", tz="UTC")
        aligned = align_regime_labels(daily_labels, four_h_ts)

        # Jan 16 00:00 bar should have Jan 15's label
        jan15_label = labels[5]  # index 5 = Jan 15
        bar_jan16 = pd.Timestamp("2022-01-16 00:00:00", tz="UTC")
        assert aligned[bar_jan16] == jan15_label, (
            f"Expected Jan 15 label at Jan 16 bar, got {aligned[bar_jan16]!r}"
        )

    def test_bars_before_first_daily_are_nan(self):
        """
        4H bars that predate the first daily value should return NaN.
        """
        daily_dates = pd.date_range("2022-01-15", "2022-01-20", freq="D", tz="UTC")
        daily_values = pd.Series(range(len(daily_dates)), index=daily_dates, dtype=float)

        # 4H bars starting before the daily data
        four_h_ts = pd.date_range("2022-01-13", "2022-01-16", freq="4h", tz="UTC")
        aligned = align_daily_to_4h(daily_values, four_h_ts)

        # Jan 14 00:00: daily data starts Jan 15, so D+1 means first available = Jan 16
        # All bars before Jan 16 00:00 should be NaN
        early_bars = aligned[aligned.index < pd.Timestamp("2022-01-16 00:00:00", tz="UTC")]
        assert early_bars.isna().all(), (
            f"Bars before first daily+1 should be NaN, got: {early_bars.dropna()}"
        )
