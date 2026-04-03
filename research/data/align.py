"""
Daily-to-4H alignment with D+1 forward-fill rule.

CRITICAL RULE (from docs/Phase_2_5_Harness_Spec.md Section 3.2):
  The daily value from day D is available at 4H bars opening on D+1, NOT D.
  A daily candle from 2024-01-15 is NOT available to a 4H candle opening at
  2024-01-15 00:00 UTC — it is available from 2024-01-16 00:00 UTC onward.

Implementation:
  - Shift daily series by 1 day (so day D's value maps to timestamps >= D+1 00:00 UTC)
  - Forward-fill into 4H index using merge_asof / reindex + ffill
"""

from __future__ import annotations

import pandas as pd


def align_daily_to_4h(
    daily_series: pd.Series,
    four_h_timestamps: pd.DatetimeIndex | pd.Series,
) -> pd.Series:
    """
    Align a daily Series to 4H bar timestamps using the D+1 forward-fill rule.

    Parameters
    ----------
    daily_series : pd.Series
        Index must be a DatetimeIndex (or Series of timestamps) at daily resolution.
        Values represent the daily indicator (e.g., SMA200 computed from close of day D).
    four_h_timestamps : DatetimeIndex or Series
        The timestamps of the 4H bars to align to.

    Returns
    -------
    pd.Series
        Same length as four_h_timestamps. For each 4H bar at timestamp T,
        the value is the most recent daily value whose date is strictly before
        T's calendar date (i.e., available from D+1 00:00 UTC onward).
        Bars where no prior daily value exists will have NaN.
    """
    # Normalise inputs
    if isinstance(four_h_timestamps, pd.Series):
        four_h_idx = pd.DatetimeIndex(four_h_timestamps)
    else:
        four_h_idx = four_h_timestamps

    # Get daily index — must be UTC
    daily_idx = daily_series.index
    if not isinstance(daily_idx, pd.DatetimeIndex):
        raise TypeError("daily_series.index must be a DatetimeIndex")
    if daily_idx.tz is None:
        daily_idx = daily_idx.tz_localize("UTC")
        daily_series = daily_series.copy()
        daily_series.index = daily_idx

    if four_h_idx.tz is None:
        four_h_idx = four_h_idx.tz_localize("UTC")

    # D+1 shift: move each daily value to the NEXT day's midnight.
    # After the shift, a value originally at 2024-01-15 00:00 UTC
    # is now at 2024-01-16 00:00 UTC — the first moment it's available.
    shifted_index = daily_idx + pd.Timedelta(days=1)
    shifted_series = pd.Series(daily_series.values, index=shifted_index, name=daily_series.name)

    # Forward-fill into 4H bars: for each 4H timestamp, use the most recent
    # shifted daily value with index <= 4H timestamp.
    aligned = shifted_series.reindex(shifted_series.index.union(four_h_idx))
    aligned = aligned.ffill()
    result = aligned.reindex(four_h_idx)
    result.index = four_h_idx
    return result


def align_regime_labels(
    daily_labels: pd.Series,
    four_h_timestamps: pd.DatetimeIndex | pd.Series,
) -> pd.Series:
    """
    Align daily regime label strings to 4H bar timestamps using the D+1 forward-fill rule.

    Identical to align_daily_to_4h() but typed for string labels.
    4H bars before the first available daily label return NaN (which will
    appear as NaN in the result — callers should treat NaN as 'UNDEFINED').

    Parameters
    ----------
    daily_labels : pd.Series
        String regime labels indexed by daily DatetimeIndex.
    four_h_timestamps : DatetimeIndex or Series

    Returns
    -------
    pd.Series of str (or NaN where unavailable).
    """
    return align_daily_to_4h(daily_labels, four_h_timestamps)
