"""
Support level detection for S2 (Support Breakdown Short).

Two variants are implemented, as mandated by docs/Phase_2_5_Harness_Spec.md Section 6:

  Variant A — Fixed-Tolerance Price Clustering
    Uses raw low prices clustered by proximity tolerance (0.5%).
    Detects price zones where lows repeatedly cluster.

  Variant B — Pivot Low Structural Detection
    Uses confirmed structural pivot lows (2-left, 2-right).
    A pivot at bar j is only confirmed at bar j+2 (lookahead boundary).
    At current bar i, only pivots at bars j <= i-3 are valid.

CRITICAL LOOKAHEAD RULE:
  Both detectors receive bars[0 : i-1] only — they cannot see bar i.
  This is enforced by the engine (backtest.py), not by the detectors.
  The detectors trust their input slice.

Both detectors share the SupportLevel dataclass interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from research.config.params import DetectorAParams, DetectorBParams


# ---------------------------------------------------------------------------
# Shared data structure
# ---------------------------------------------------------------------------

@dataclass
class SupportLevel:
    """
    A detected support level.

    level_price : float
        Representative price of the support zone.
    touch_count : int
        Number of confirmed touches at this level.
    first_touch_bar : int
        Bar index (relative to full dataset) of the first touch.
    last_touch_bar : int
        Bar index (relative to full dataset) of the most recent touch.
    detector_variant : str
        'A' or 'B'.
    """
    level_price: float
    touch_count: int
    first_touch_bar: int
    last_touch_bar: int
    detector_variant: str


# ---------------------------------------------------------------------------
# Variant A — Fixed-Tolerance Price Clustering
# ---------------------------------------------------------------------------

def detect_support_levels_variant_a(
    bars_slice: pd.DataFrame,
    params: DetectorAParams,
    bar_offset: int = 0,
) -> list[SupportLevel]:
    """
    Detect support levels using fixed-tolerance price clustering.

    Parameters
    ----------
    bars_slice : pd.DataFrame
        Slice of the full OHLCV DataFrame, ending at i-1 (exclusive of current bar).
        Must contain columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume'].
        Bar indices in bars_slice are 0-based within the slice; bar_offset converts
        them to indices in the full dataset.
    params : DetectorAParams
        Frozen parameters for Variant A.
    bar_offset : int
        Index of bars_slice.iloc[0] in the full dataset.
        Used to fill first_touch_bar / last_touch_bar in absolute terms.

    Returns
    -------
    list[SupportLevel], possibly empty.
    """
    if bars_slice.empty or len(bars_slice) < params.min_touch_count:
        return []

    # Limit to lookback window
    window = bars_slice.iloc[-params.lookback_window:]
    if len(window) < params.min_touch_count:
        return []

    lows = window["low"].values
    highs = window["high"].values
    closes = window["close"].values

    # We need ATR for bounce validation. Compute a simple proxy:
    # use high-low range as TR (close[i-1] not available here easily)
    # This is acceptable for the bounce criterion which checks ">= 1 ATR move"
    hl_ranges = highs - lows
    # Rolling ATR(14) approximation using HL range
    atr_proxy = _rolling_mean(hl_ranges, 14)

    n = len(window)
    used = [False] * n  # track which lows are already assigned to a level

    levels: list[SupportLevel] = []

    for seed_idx in range(n):
        if used[seed_idx]:
            continue

        zone_center = lows[seed_idx]
        lower = zone_center * (1 - params.touch_tolerance)
        upper = zone_center * (1 + params.touch_tolerance)

        # Collect all lows within the zone
        cluster_indices = [
            j for j in range(n) if lower <= lows[j] <= upper
        ]

        if len(cluster_indices) < params.min_touch_count:
            continue

        # Sort by bar index (already sorted since window is sequential)
        cluster_indices.sort()

        # Debounce: remove touches within min_bars_between_touches of the prior one
        debounced = _debounce_touches(cluster_indices, params.min_bars_between_touches)

        if len(debounced) < params.min_touch_count:
            continue

        # Bounce validation: each touch must be followed by a move >= min_bounce_atr * ATR
        validated = []
        for idx in debounced:
            atr_at_touch = atr_proxy[idx] if idx < len(atr_proxy) else hl_ranges[idx]
            if np.isnan(atr_at_touch) or atr_at_touch <= 0:
                # If ATR unavailable, accept the touch (conservative — don't discard)
                validated.append(idx)
                continue

            # Check max close in the next min_bars_between_touches bars
            look_end = min(idx + params.min_bars_between_touches + 1, n)
            if look_end > idx + 1:
                max_close_after = closes[idx + 1:look_end].max()
                if max_close_after >= lows[idx] + params.min_bounce_atr * atr_at_touch:
                    validated.append(idx)
            # If not enough bars after touch (near end of window), accept the touch
            elif idx == n - 1:
                validated.append(idx)

        if len(validated) < params.min_touch_count:
            continue

        # Mark cluster members as used
        for j in cluster_indices:
            used[j] = True

        # Level price = median of validated touch lows
        level_lows = [lows[j] for j in validated]
        if params.level_price_calc == "median":
            level_price = float(np.median(level_lows))
        else:
            level_price = float(np.min(level_lows))

        first_abs = bar_offset + (len(bars_slice) - len(window)) + validated[0]
        last_abs = bar_offset + (len(bars_slice) - len(window)) + validated[-1]

        levels.append(SupportLevel(
            level_price=level_price,
            touch_count=len(validated),
            first_touch_bar=first_abs,
            last_touch_bar=last_abs,
            detector_variant="A",
        ))

    # Deduplicate overlapping clusters: merge levels within touch_tolerance of each other
    levels = _deduplicate_levels(levels, params.touch_tolerance)
    return levels


# ---------------------------------------------------------------------------
# Variant B — Pivot Low Structural Detection
# ---------------------------------------------------------------------------

def detect_support_levels_variant_b(
    bars_slice: pd.DataFrame,
    params: DetectorBParams,
    bar_offset: int = 0,
) -> list[SupportLevel]:
    """
    Detect support levels using confirmed pivot lows.

    CRITICAL LOOKAHEAD BOUNDARY:
    A pivot low at bar j requires bars j+1 and j+2 to be known.
    At current bar i, pivot at j is valid only if j <= i - 3.
    In the bars_slice (which ends at i-1), the last valid pivot is at
    position len(bars_slice) - 1 - params.lookahead_boundary.
    (lookahead_boundary = 3 from params, derived from pivot_window)

    Parameters
    ----------
    bars_slice : pd.DataFrame
        Slice ending at i-1. No bar i data.
    params : DetectorBParams
    bar_offset : int
        Absolute index of bars_slice.iloc[0].

    Returns
    -------
    list[SupportLevel]
    """
    if bars_slice.empty:
        return []

    # Limit to lookback window
    window = bars_slice.iloc[-params.lookback_window:]
    n = len(window)

    if n < params.pivot_window:
        return []

    lows = window["low"].values
    half = params.pivot_window // 2  # 2 for pivot_window=5

    # Step 1: Identify pivot lows
    # pivot at j: low[j] == min(low[j-2..j+2])
    # Confirmed only if j+half bars available after j.
    # Last valid j in the window = n - 1 - params.lookahead_boundary
    # (lookahead_boundary=3 ensures j+1 and j+2 exist within the slice)
    last_valid_pivot = n - 1 - params.lookahead_boundary

    pivot_indices: list[int] = []
    pivot_lows: list[float] = []

    for j in range(half, last_valid_pivot + 1):
        neighborhood = lows[j - half: j + half + 1]
        if lows[j] == neighborhood.min():
            pivot_indices.append(j)
            pivot_lows.append(lows[j])

    if len(pivot_indices) < params.min_pivot_count:
        return []

    # Step 2: Group nearby pivots by proximity
    used = [False] * len(pivot_indices)
    levels: list[SupportLevel] = []

    for seed in range(len(pivot_indices)):
        if used[seed]:
            continue

        p_price = pivot_lows[seed]
        lower = p_price * (1 - params.proximity_pct)
        upper = p_price * (1 + params.proximity_pct)

        group = [
            k for k in range(len(pivot_indices))
            if lower <= pivot_lows[k] <= upper
        ]

        if len(group) < params.min_pivot_count:
            continue

        # Debounce within the group
        group_bar_indices = [pivot_indices[k] for k in group]
        group_bar_indices.sort()
        debounced = _debounce_touches(group_bar_indices, params.min_bars_between_pivots)

        if len(debounced) < params.min_pivot_count:
            continue

        for k in group:
            used[k] = True

        # Level price = lowest pivot in group (most conservative)
        group_lows = [lows[pivot_indices[k]] for k in group if pivot_indices[k] in debounced]
        if params.level_price_calc == "lowest":
            level_price = float(min(group_lows)) if group_lows else p_price
        else:
            level_price = float(np.median(group_lows)) if group_lows else p_price

        window_start = len(bars_slice) - n
        first_abs = bar_offset + window_start + debounced[0]
        last_abs = bar_offset + window_start + debounced[-1]

        levels.append(SupportLevel(
            level_price=level_price,
            touch_count=len(debounced),
            first_touch_bar=first_abs,
            last_touch_bar=last_abs,
            detector_variant="B",
        ))

    levels = _deduplicate_levels(levels, params.proximity_pct)
    return levels


# ---------------------------------------------------------------------------
# Overlap metric
# ---------------------------------------------------------------------------

def compute_detector_overlap(
    signals_a: list[int],
    signals_b: list[int],
) -> float:
    """
    Compute the Jaccard overlap between two sets of signal bar indices.

    overlap = |A ∩ B| / |A ∪ B|

    Parameters
    ----------
    signals_a : list[int]
        Bar indices where Variant A triggered a signal.
    signals_b : list[int]
        Bar indices where Variant B triggered a signal.

    Returns
    -------
    float in [0, 1]. 1.0 = identical signals, 0.0 = no overlap.
    """
    set_a = set(signals_a)
    set_b = set(signals_b)
    union = set_a | set_b
    if not union:
        return float("nan")
    intersection = set_a & set_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _debounce_touches(indices: list[int], min_bars: int) -> list[int]:
    """
    Remove touches that occur within min_bars of the prior accepted touch.
    Keeps the first touch in each cluster.

    Parameters
    ----------
    indices : list[int]
        Sorted bar indices.
    min_bars : int
        Minimum bars between consecutive touches.

    Returns
    -------
    list[int]: debounced subset of indices.
    """
    if not indices:
        return []
    result = [indices[0]]
    for idx in indices[1:]:
        if idx - result[-1] >= min_bars:
            result.append(idx)
    return result


def _deduplicate_levels(
    levels: list[SupportLevel],
    tolerance: float,
) -> list[SupportLevel]:
    """
    Merge overlapping support levels (centers within tolerance of each other).
    Keeps the level with the higher touch count.

    Parameters
    ----------
    levels : list[SupportLevel]
    tolerance : float
        Proximity fraction (e.g. 0.005 = 0.5%).

    Returns
    -------
    list[SupportLevel]: deduplicated list.
    """
    if not levels:
        return []

    levels = sorted(levels, key=lambda lv: -lv.touch_count)
    used = [False] * len(levels)
    result: list[SupportLevel] = []

    for i, lv in enumerate(levels):
        if used[i]:
            continue
        result.append(lv)
        for j in range(i + 1, len(levels)):
            if used[j]:
                continue
            if abs(levels[j].level_price - lv.level_price) / lv.level_price <= tolerance:
                used[j] = True
    return result


def _rolling_mean(arr: np.ndarray, window: int) -> np.ndarray:
    """Simple rolling mean with NaN for warmup bars."""
    result = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        result[i] = arr[i - window + 1: i + 1].mean()
    return result
