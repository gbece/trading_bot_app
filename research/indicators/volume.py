"""
Volume indicators: Volume SMA and Relative Volume.

CRITICAL (from docs/Phase_2_5_Harness_Spec.md and Phase_5_Deployment.md):
  volume_sma.iloc[i] = mean of volume[i-period : i]
  This does NOT include bar i (current bar is excluded).
  This is a look-BACK window that excludes the current observation.

Why: when checking whether the current bar's volume exceeds the average,
including the current bar in the average would contaminate the comparison.
"""

from __future__ import annotations
import pandas as pd
import numpy as np


def compute_volume_sma(volume: pd.Series, period: int) -> pd.Series:
    """
    Volume Simple Moving Average — excludes the current bar.

    volume_sma.iloc[i] = mean(volume[i-period : i])
                        = mean of the prior `period` bars, NOT including bar i.

    Equivalent to: rolling(period).mean().shift(1) — the shift(1) moves
    the window so that at index i we see the average of [i-period, i-1].

    First period values are NaN (insufficient history).

    Parameters
    ----------
    volume : pd.Series
    period : int

    Returns
    -------
    pd.Series, NaN for first `period` bars.
    """
    if period < 1:
        raise ValueError(f"period must be >= 1, got {period}")

    # rolling(period).mean() at index i = mean(volume[i-period+1 : i+1]) — includes i
    # .shift(1) at index i = mean(volume[i-period : i]) — excludes i ✓
    return volume.rolling(window=period, min_periods=period).mean().shift(1)


def compute_relative_volume(volume: pd.Series, sma: pd.Series) -> pd.Series:
    """
    Relative volume: volume[i] / volume_sma[i].

    Returns NaN where sma is NaN or zero.

    Parameters
    ----------
    volume : pd.Series
    sma : pd.Series
        Output of compute_volume_sma.

    Returns
    -------
    pd.Series
    """
    return volume / sma.replace(0, np.nan)
