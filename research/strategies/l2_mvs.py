"""
L2 MVS — EMA Pullback Long signal generation.

Implements all 5 component decomposition modes as defined in
docs/Phase_2_5_Harness_Spec.md Section 4.1:

  MODE_RANDOM        — Enter at every bar (no filters), same stop/target structure
  MODE_MACRO_ONLY    — Macro filter only, enter at every passing bar
  MODE_TOUCH_ONLY    — EMA touch condition only, no macro filter, no confirmation
  MODE_MVS_NO_CONFIRM — Macro + touch, no confirmation candle
  MODE_MVS_FULL      — Full MVS (same-bar: touch AND bullish close in same candle)

CRITICAL DESIGN DECISIONS (from docs/Phase_3_Implementation.md Section 4.1):
  - Same-bar confirmation: touch detected AND bullish close in the SAME 4H bar
  - Entry at the close of that bar (market order, slippage applied)
  - Stop anchored to EMA value at touch, not to entry price
  - stop_price = ema21 * (1 - touch_tolerance) - (stop_atr_multiplier * atr14)
  - target_price = entry_price + (target_atr_multiplier * atr14)

This module only GENERATES SIGNALS. It does not manage trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from research.config.params import L2Params


# ---------------------------------------------------------------------------
# Mode enum
# ---------------------------------------------------------------------------

class L2SignalMode(str, Enum):
    """Component decomposition modes for L2."""
    RANDOM        = "RANDOM"
    MACRO_ONLY    = "MACRO_ONLY"
    TOUCH_ONLY    = "TOUCH_ONLY"
    MVS_NO_CONFIRM = "MVS_NO_CONFIRM"
    MVS_FULL      = "MVS_FULL"


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class L2Signal:
    """
    Signal produced by evaluate_l2_signal().

    If a signal fires, all price fields are populated.
    If rejected, entry_price=None and filter_rejection_reason explains why.
    """
    bar_index: int
    timestamp: pd.Timestamp
    mode: L2SignalMode

    # Populated on entry signal
    entry_price: Optional[float]             # Close of bar (before slippage)
    stop_price: Optional[float]
    target_price: Optional[float]
    ema21_at_entry: Optional[float]
    atr_at_entry: Optional[float]
    regime: Optional[str]

    # Rejection tracking
    signal_fired: bool
    filter_rejection_reason: Optional[str]   # e.g. 'macro_filter', 'no_touch', 'no_confirmation'


# ---------------------------------------------------------------------------
# Signal evaluator
# ---------------------------------------------------------------------------

def evaluate_l2_signal(
    bar_index: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    timestamp: pd.Timestamp,
    ema21: float,                   # EMA21 value at bar_index (NaN if warmup)
    atr14: float,                   # ATR14 value at bar_index (NaN if warmup)
    daily_sma200_aligned: float,    # Daily SMA200 forward-filled to 4H (NaN if warmup)
    btc_daily_close_aligned: float, # Daily BTC close forward-filled to 4H (NaN if warmup)
    regime: str,                    # Regime label for this bar
    mode: L2SignalMode,
    params: L2Params,
) -> Optional[L2Signal]:
    """
    Evaluate whether the L2 EMA Pullback Long strategy fires at bar_index.

    Called once per bar, for bars where no open trade exists.
    Returns L2Signal on signal fire, or L2Signal with signal_fired=False on rejection,
    or None if the bar should be skipped entirely (NaN indicators — warmup).

    Parameters
    ----------
    bar_index : int
        Current bar index in the full dataset.
    open_price, high_price, low_price, close_price : float
        OHLCV values for bar_index.
    timestamp : pd.Timestamp
    ema21 : float
        EMA(21) computed on 4H close, value at bar_index.
    atr14 : float
        ATR(14) computed on 4H data, value at bar_index.
    daily_sma200_aligned : float
        Daily SMA(200) forward-filled to this 4H bar (D+1 rule).
    btc_daily_close_aligned : float
        Daily BTC close forward-filled to this 4H bar (D+1 rule).
    regime : str
        Regime label for this bar (from BTC daily classifier, D+1 aligned).
    mode : L2SignalMode
        Which decomposition mode to use.
    params : L2Params
        Frozen strategy parameters.

    Returns
    -------
    L2Signal if signal evaluated (fired or rejected).
    None if bar should be skipped (insufficient indicator data).
    """
    def _no_signal(reason: str) -> L2Signal:
        return L2Signal(
            bar_index=bar_index,
            timestamp=timestamp,
            mode=mode,
            entry_price=None,
            stop_price=None,
            target_price=None,
            ema21_at_entry=None,
            atr_at_entry=None,
            regime=regime,
            signal_fired=False,
            filter_rejection_reason=reason,
        )

    def _signal(entry: float, stop: float, target: float, ema: float, atr: float) -> L2Signal:
        return L2Signal(
            bar_index=bar_index,
            timestamp=timestamp,
            mode=mode,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            ema21_at_entry=ema,
            atr_at_entry=atr,
            regime=regime,
            signal_fired=True,
            filter_rejection_reason=None,
        )

    # ---------- RANDOM mode ----------
    # Enters at every bar regardless of conditions.
    # Uses EMA and ATR for stop/target — skip if NaN.
    if mode == L2SignalMode.RANDOM:
        if _is_nan(atr14) or atr14 <= 0:
            return None
        # For RANDOM mode, use close as the "ema" anchor for stop calc
        stop = close_price - params.stop_atr_multiplier * atr14
        target = close_price + params.target_atr_multiplier * atr14
        return _signal(close_price, stop, target, ema21=float("nan"), atr=atr14)

    # ---------- All other modes: require valid EMA and ATR ----------
    if _is_nan(ema21) or _is_nan(atr14) or atr14 <= 0:
        return None

    # ---------- MACRO FILTER (MVS-L2-1) ----------
    # Required for: MACRO_ONLY, MVS_NO_CONFIRM, MVS_FULL
    macro_passes = (
        not _is_nan(daily_sma200_aligned)
        and not _is_nan(btc_daily_close_aligned)
        and btc_daily_close_aligned > daily_sma200_aligned
    )

    if mode == L2SignalMode.MACRO_ONLY:
        if not macro_passes:
            return _no_signal("macro_filter_rejected")
        # Enter at every bar where macro passes — no entry signal check
        stop = ema21 * (1 - params.touch_tolerance) - (params.stop_atr_multiplier * atr14)
        target = close_price + params.target_atr_multiplier * atr14
        return _signal(close_price, stop, target, ema=ema21, atr=atr14)

    # ---------- EMA TOUCH CHECK (MVS-L2-2) ----------
    # Required for: TOUCH_ONLY, MVS_NO_CONFIRM, MVS_FULL
    # Touch: low_price <= ema21 * (1 + touch_tolerance)
    touch_detected = low_price <= ema21 * (1 + params.touch_tolerance)

    if mode == L2SignalMode.TOUCH_ONLY:
        if not touch_detected:
            return _no_signal("no_ema_touch")
        # No macro, no confirmation
        stop = ema21 * (1 - params.touch_tolerance) - (params.stop_atr_multiplier * atr14)
        target = close_price + params.target_atr_multiplier * atr14
        return _signal(close_price, stop, target, ema=ema21, atr=atr14)

    if mode in (L2SignalMode.MVS_NO_CONFIRM, L2SignalMode.MVS_FULL):
        if not macro_passes:
            return _no_signal("macro_filter_rejected")
        if not touch_detected:
            return _no_signal("no_ema_touch")

        # ---------- CONFIRMATION CANDLE (MVS-L2-3) ----------
        # Required for: MVS_FULL only
        # Same-bar: close > open on the touch bar
        if mode == L2SignalMode.MVS_FULL:
            if close_price <= open_price:
                return _no_signal("no_bullish_confirmation")

        # ---------- ENTRY ----------
        # Stop anchored to EMA touch level, not to entry price
        stop = ema21 * (1 - params.touch_tolerance) - (params.stop_atr_multiplier * atr14)
        target = close_price + params.target_atr_multiplier * atr14
        return _signal(close_price, stop, target, ema=ema21, atr=atr14)

    # Should not reach here
    return None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _is_nan(v: float) -> bool:
    """Safe NaN check that works for plain Python floats."""
    return v != v or (isinstance(v, float) and np.isnan(v))
