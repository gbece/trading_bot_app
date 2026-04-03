"""
Trend indicators: EMA, SMA, EMA slope.

Convention (from docs/Phase_2_5_Harness_Spec.md Section 3.2):
  indicator.iloc[i] is computed from data[0:i+1].
  The first period-1 values are NaN (warmup).

EMA uses pandas ewm(adjust=False) which implements the standard recursive formula:
  EMA[0] = close[0]
  EMA[i] = alpha * close[i] + (1 - alpha) * EMA[i-1]
  where alpha = 2 / (period + 1)
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average using pandas ewm(adjust=False).

    First period-1 values are NaN (warmup period respected).
    indicator.iloc[i] is available after bar i closes.

    Parameters
    ----------
    series : pd.Series
        Input price series (typically close).
    period : int
        EMA period (span). alpha = 2 / (period + 1).

    Returns
    -------
    pd.Series with NaN for the first period-1 bars.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    ema = series.ewm(span=period, adjust=False).mean()

    # Enforce warmup: first period-1 values are NaN
    # pandas ewm starts computing from the very first value, but
    # by convention we treat the first period-1 bars as undefined.
    result = ema.copy()
    result.iloc[:period - 1] = np.nan
    return result


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average.

    First period-1 values are NaN (warmup period respected).
    indicator.iloc[i] = mean of series[i-period+1 : i+1].

    Parameters
    ----------
    series : pd.Series
    period : int

    Returns
    -------
    pd.Series with NaN for the first period-1 bars.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")
    return series.rolling(window=period, min_periods=period).mean()


def compute_ema_slope(ema_series: pd.Series, lookback: int = 3) -> pd.Series:
    """
    Boolean Series: True where EMA is rising over the last `lookback` bars.

    slope.iloc[i] = True  iff  ema_series.iloc[i] > ema_series.iloc[i - lookback]

    Used in ESS-L2-8: EMA slope check with lookback=3 (EMA21[0] > EMA21[3]).

    Parameters
    ----------
    ema_series : pd.Series
        Pre-computed EMA values.
    lookback : int
        Number of bars to look back. Default 3.

    Returns
    -------
    pd.Series of bool (False where NaN or insufficient history).
    """
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")

    prior = ema_series.shift(lookback)
    slope = ema_series > prior

    # Where either value is NaN, slope is False (not enough data)
    slope = slope & ema_series.notna() & prior.notna()
    return slope
