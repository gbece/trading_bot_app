"""
Data integrity checks for OHLCV DataFrames.
Implements CHECK-1 through CHECK-6 as defined in docs/Phase_2_5_Harness_Spec.md.

All checks raise descriptive exceptions on failure with the exact row/value.
Returns a ValidatedOHLCV wrapper on success.
"""

from __future__ import annotations
from dataclasses import dataclass

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Validated wrapper
# ---------------------------------------------------------------------------

@dataclass
class ValidatedOHLCV:
    """
    Wrapper returned by validate_ohlcv() on success.
    df contains the cleaned DataFrame (zero-volume rows removed per CHECK-4).
    """
    df: pd.DataFrame
    symbol: str
    timeframe: str
    checks_passed: list[str]

    def __repr__(self) -> str:
        return (
            f"ValidatedOHLCV(symbol={self.symbol!r}, timeframe={self.timeframe!r}, "
            f"rows={len(self.df)}, checks={self.checks_passed})"
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_no_duplicate_timestamps(df: pd.DataFrame) -> None:
    """CHECK-1: No duplicate timestamps."""
    dupes = df[df["timestamp"].duplicated(keep=False)]
    if not dupes.empty:
        first_dupe = dupes.iloc[0]
        raise ValueError(
            f"CHECK-1 FAILED: Duplicate timestamps found. "
            f"First duplicate: row {first_dupe.name}, timestamp={first_dupe['timestamp']}"
        )


def check_no_large_gaps(df: pd.DataFrame, timeframe: str) -> None:
    """
    CHECK-2: No gaps larger than 2 consecutive candles.
    For 4H data: max gap = 8H (2 candles × 4H).
    For 1D data: max gap = 2 days.
    """
    if len(df) < 2:
        return

    tf_lower = timeframe.lower()
    if "4h" in tf_lower or "4hour" in tf_lower:
        expected_delta = pd.Timedelta(hours=4)
    elif "1d" in tf_lower or "1day" in tf_lower or "d" == tf_lower:
        expected_delta = pd.Timedelta(days=1)
    else:
        # Generic: infer from median gap
        deltas = df["timestamp"].diff().dropna()
        expected_delta = deltas.median()

    max_allowed_gap = expected_delta * 2

    deltas = df["timestamp"].diff()
    large_gaps = df[deltas > max_allowed_gap]

    if not large_gaps.empty:
        row = large_gaps.iloc[0]
        gap = deltas.loc[row.name]
        raise ValueError(
            f"CHECK-2 FAILED: Gap of {gap} exceeds maximum allowed {max_allowed_gap}. "
            f"At row {row.name}, timestamp={row['timestamp']}"
        )


def check_ohlc_integrity(df: pd.DataFrame) -> None:
    """
    CHECK-3: OHLC integrity.
    high >= low, high >= max(open, close), low <= min(open, close)
    """
    bad_hl = df[df["high"] < df["low"]]
    if not bad_hl.empty:
        row = bad_hl.iloc[0]
        raise ValueError(
            f"CHECK-3 FAILED: high < low at row {row.name}, timestamp={row['timestamp']}, "
            f"high={row['high']}, low={row['low']}"
        )

    bad_high = df[df["high"] < df[["open", "close"]].max(axis=1)]
    if not bad_high.empty:
        row = bad_high.iloc[0]
        raise ValueError(
            f"CHECK-3 FAILED: high < max(open, close) at row {row.name}, "
            f"timestamp={row['timestamp']}, open={row['open']}, close={row['close']}, high={row['high']}"
        )

    bad_low = df[df["low"] > df[["open", "close"]].min(axis=1)]
    if not bad_low.empty:
        row = bad_low.iloc[0]
        raise ValueError(
            f"CHECK-3 FAILED: low > min(open, close) at row {row.name}, "
            f"timestamp={row['timestamp']}, open={row['open']}, close={row['close']}, low={row['low']}"
        )


def check_no_zero_volume(df: pd.DataFrame) -> pd.DataFrame:
    """
    CHECK-4: No zero or negative volume candles.
    Flags and removes them; returns the cleaned DataFrame.
    """
    bad_vol = df[df["volume"] <= 0]
    if not bad_vol.empty:
        import warnings
        warnings.warn(
            f"CHECK-4: Removing {len(bad_vol)} candle(s) with zero/negative volume. "
            f"First offender: row {bad_vol.index[0]}, timestamp={bad_vol.iloc[0]['timestamp']}, "
            f"volume={bad_vol.iloc[0]['volume']}"
        )
        df = df[df["volume"] > 0].reset_index(drop=True)
    return df


def check_no_price_spikes(df: pd.DataFrame, max_deviation: float = 0.50) -> None:
    """
    CHECK-5: No price values that deviate by more than max_deviation (50%) from the prior candle.
    Checks close price against prior close.
    """
    if len(df) < 2:
        return

    prior_close = df["close"].shift(1)
    pct_change = (df["close"] - prior_close).abs() / prior_close

    spikes = df[pct_change > max_deviation]
    if not spikes.empty:
        row = spikes.iloc[0]
        deviation = pct_change.loc[row.name]
        raise ValueError(
            f"CHECK-5 FAILED: Price spike of {deviation:.1%} at row {row.name}, "
            f"timestamp={row['timestamp']}, close={row['close']}, "
            f"prior_close={prior_close.loc[row.name]:.2f}"
        )


def check_timestamp_monotonicity(df: pd.DataFrame) -> None:
    """CHECK-6: Timestamp monotonicity — each timestamp strictly greater than prior."""
    if len(df) < 2:
        return

    deltas = df["timestamp"].diff().dropna()
    non_monotone = df.loc[deltas.index[deltas <= pd.Timedelta(0)]]

    if not non_monotone.empty:
        row = non_monotone.iloc[0]
        raise ValueError(
            f"CHECK-6 FAILED: Non-monotone timestamp at row {row.name}, "
            f"timestamp={row['timestamp']}"
        )


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def validate_ohlcv(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    timeframe: str = "4h",
) -> ValidatedOHLCV:
    """
    Run all 6 integrity checks on an OHLCV DataFrame.

    Raises ValueError with the exact row/value on any failure.
    Returns ValidatedOHLCV on success.

    CHECK-4 is the only check that modifies the data (removes zero-volume rows).
    All other checks are read-only and halt on failure.
    """
    df = df.copy()

    # Ensure timestamp column is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    elif df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")

    checks_passed: list[str] = []

    # CHECK-1
    check_no_duplicate_timestamps(df)
    checks_passed.append("CHECK-1: no_duplicate_timestamps")

    # CHECK-6 (monotonicity before gap check — gaps can't be measured on non-sorted data)
    check_timestamp_monotonicity(df)
    checks_passed.append("CHECK-6: timestamp_monotonicity")

    # CHECK-2
    check_no_large_gaps(df, timeframe)
    checks_passed.append("CHECK-2: no_large_gaps")

    # CHECK-3
    check_ohlc_integrity(df)
    checks_passed.append("CHECK-3: ohlc_integrity")

    # CHECK-4 (modifies df — run before spike check so spike check uses clean data)
    df = check_no_zero_volume(df)
    checks_passed.append("CHECK-4: no_zero_volume")

    # CHECK-5
    check_no_price_spikes(df)
    checks_passed.append("CHECK-5: no_price_spikes")

    return ValidatedOHLCV(df=df, symbol=symbol, timeframe=timeframe, checks_passed=checks_passed)
