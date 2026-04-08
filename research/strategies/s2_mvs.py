"""
S2 MVS — Support Breakdown Short signal generation.

Implements the S2 signal evaluator as defined in
docs/Phase_2_5_Harness_Spec.md Section 5.

Strategy logic (MVS-S2):
  1. Active support levels must be pre-computed by the engine (no detector call here).
  2. For each active level, check breakdown: close < level_price * (1 - breakdown_threshold)
  3. Volume confirmation: volume > volume_sma20 * volume_multiplier
  4. If multiple levels qualify simultaneously: take highest touch_count, then most recent.
  5. Entry at close, stop 0.5× ATR above broken level, target 2× ATR below entry.

This module only GENERATES SIGNALS. It does not manage trades or run detectors.
The engine passes pre-computed active_levels to evaluate_s2_signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from research.config.params import S2Params
from research.detectors.support import SupportLevel


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class S2Signal:
    """Signal produced by evaluate_s2_signal()."""
    bar_index: int
    timestamp: pd.Timestamp
    detector_variant: str           # 'A' or 'B'

    # Populated on signal fire
    entry_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    support_level: Optional[float]
    touch_count: Optional[int]
    level_age_bars: Optional[int]   # bar_index - first_touch_bar
    volume_ratio: Optional[float]   # volume / vol_sma20
    regime: Optional[str]
    atr_at_entry: Optional[float]

    signal_fired: bool
    filter_rejection_reason: Optional[str]
    multiple_levels_conflict: bool  # True if tie-breaking was applied


# ---------------------------------------------------------------------------
# Signal evaluator
# ---------------------------------------------------------------------------

def evaluate_s2_signal(
    bar_index: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float,
    timestamp: pd.Timestamp,
    atr14: float,                   # ATR14 at bar_index
    vol_sma20: float,               # Volume SMA20 at bar_index (excludes bar_index)
    regime: str,
    active_levels: list[SupportLevel],
    params: S2Params,
    detector_variant: str,
) -> Optional[S2Signal]:
    """
    Evaluate whether S2 fires at bar_index given pre-computed support levels.

    Called once per bar, only when no open trade exists.

    Parameters
    ----------
    bar_index : int
        Current bar index in the full dataset.
    open_price, high_price, low_price, close_price, volume : float
        OHLCV for current bar.
    timestamp : pd.Timestamp
    atr14 : float
        ATR(14) at bar_index. NaN → skip bar.
    vol_sma20 : float
        Volume SMA(20) at bar_index (excludes current bar volume).
        NaN → skip bar.
    regime : str
    active_levels : list[SupportLevel]
        Pre-computed by the engine. Each level's last_touch_bar < bar_index
        (engine excludes levels where last_touch_bar == bar_index - 1).
    params : S2Params
        Frozen strategy parameters.
    detector_variant : str
        'A' or 'B'. Passed through to the signal record.

    Returns
    -------
    S2Signal if evaluated (fired or rejected).
    None if bar should be skipped (NaN indicators).
    """
    # Skip if indicators not ready
    if _is_nan(atr14) or atr14 <= 0 or _is_nan(vol_sma20) or vol_sma20 <= 0:
        return None

    if not active_levels:
        return S2Signal(
            bar_index=bar_index,
            timestamp=timestamp,
            detector_variant=detector_variant,
            entry_price=None,
            stop_price=None,
            target_price=None,
            support_level=None,
            touch_count=None,
            level_age_bars=None,
            volume_ratio=None,
            regime=regime,
            atr_at_entry=None,
            signal_fired=False,
            filter_rejection_reason="no_active_levels",
            multiple_levels_conflict=False,
        )

    # Evaluate all active levels for signal conditions
    qualifying: list[SupportLevel] = []

    for level in active_levels:
        breakdown_threshold_price = level.level_price * (1 - params.breakdown_threshold)

        # MVS-S2-2: Breakdown confirmation
        if close_price >= breakdown_threshold_price:
            continue

        # MVS-S2-3: Volume confirmation (strictly greater than threshold)
        if volume <= params.volume_multiplier * vol_sma20:
            continue

        qualifying.append(level)

    if not qualifying:
        vol_ratio = volume / vol_sma20 if not _is_nan(vol_sma20) and vol_sma20 > 0 else float("nan")
        return S2Signal(
            bar_index=bar_index,
            timestamp=timestamp,
            detector_variant=detector_variant,
            entry_price=None,
            stop_price=None,
            target_price=None,
            support_level=None,
            touch_count=None,
            level_age_bars=None,
            volume_ratio=vol_ratio,
            regime=regime,
            atr_at_entry=None,
            signal_fired=False,
            filter_rejection_reason="no_qualifying_breakdown",
            multiple_levels_conflict=False,
        )

    # Tie-breaking: highest touch_count, then most recently formed (last_touch_bar)
    multiple_levels_conflict = len(qualifying) > 1
    best = max(qualifying, key=lambda lv: (lv.touch_count, lv.last_touch_bar))

    # Entry
    # For short: slippage is applied in engine (effective_entry = close * (1 - slippage))
    entry_price = close_price
    stop_price = best.level_price + (params.stop_atr_multiplier * atr14)
    target_price = entry_price - (params.target_atr_multiplier * atr14)
    vol_ratio = volume / vol_sma20
    level_age = bar_index - best.first_touch_bar

    return S2Signal(
        bar_index=bar_index,
        timestamp=timestamp,
        detector_variant=detector_variant,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        support_level=best.level_price,
        touch_count=best.touch_count,
        level_age_bars=level_age,
        volume_ratio=vol_ratio,
        regime=regime,
        atr_at_entry=atr14,
        signal_fired=True,
        filter_rejection_reason=None,
        multiple_levels_conflict=multiple_levels_conflict,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_nan(v: float) -> bool:
    return v != v or (isinstance(v, float) and np.isnan(v))
