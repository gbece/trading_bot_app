"""
Volatility indicators: ATR (Average True Range).

Three-term True Range:
  TR[i] = max(high[i] - low[i],
              abs(high[i] - close[i-1]),
              abs(low[i]  - close[i-1]))

ATR[i] = SMA(TR, period) — first period-1 values are NaN (warmup).
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int,
) -> pd.Series:
    """
    Average True Range using a Simple Moving Average of True Range.

    Parameters
    ----------
    high, low, close : pd.Series
        OHLCV price series (same index).
    period : int
        ATR period (typically 14).

    Returns
    -------
    pd.Series with NaN for the first period-1 bars (warmup).
    The first True Range (index 0) requires a prior close, so index 0 is NaN,
    and the ATR warmup propagates: valid from index period-1 onward.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    prev_close = close.shift(1)

    tr_hl = high - low
    tr_hc = (high - prev_close).abs()
    tr_lc = (low - prev_close).abs()

    tr = pd.concat([tr_hl, tr_hc, tr_lc], axis=1).max(axis=1)

    # TR at index 0 is NaN because prev_close is NaN there.
    # Rolling SMA with min_periods=period ensures ATR is NaN until period bars of TR are available.
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr
