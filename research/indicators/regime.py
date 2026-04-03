"""
Six-regime market classifier (BTC anchor).

Regime ordering is CRITICAL — first match wins (from docs/Phase_5_Deployment.md Section 4.3):
  1. STRONG_BULL
  2. HIGH_VOL_BULLISH  ← MUST be before WEAK_BULL
  3. HIGH_VOL_BEARISH  ← MUST be before BEAR
  4. WEAK_BULL
  5. BEAR
  6. TRANSITION        (catch-all)

Any NaN input → 'UNDEFINED'.

Variables:
  SMA_200  = SMA(daily close, 200)
  SMA_50   = SMA(daily close, 50)
  ROC_20   = (close - close[20]) / close[20]
  VOL_ratio = ATR(14, daily) / SMA(ATR(14, daily), 60)

BTC is the regime anchor — all pairs use BTC's regime labels.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.indicators.trend import compute_sma
from research.indicators.volatility import compute_atr


# ---------------------------------------------------------------------------
# Single-bar classification
# ---------------------------------------------------------------------------

def classify_regime(
    btc_close: float,
    sma_200: float,
    sma_50: float,
    roc_20: float,
    vol_ratio: float,
) -> str:
    """
    Classify a single bar into one of 6 regimes.

    Returns 'UNDEFINED' if any input is NaN.
    """
    if any(
        v != v  # NaN check (works for floats, avoids numpy import dependency here)
        for v in [btc_close, sma_200, sma_50, roc_20, vol_ratio]
    ):
        return "UNDEFINED"

    # 1. STRONG_BULL — trending up, low volatility
    if (
        btc_close > sma_200 * 1.05
        and btc_close > sma_50
        and roc_20 > 0.10
        and vol_ratio < 1.5
    ):
        return "STRONG_BULL"

    # 2. HIGH_VOL_BULLISH — volatile spike, price above SMA200
    #    MUST be before WEAK_BULL to capture euphoric volatility
    if vol_ratio >= 2.0 and btc_close > sma_200:
        return "HIGH_VOL_BULLISH"

    # 3. HIGH_VOL_BEARISH — volatile crash, price below SMA200
    #    MUST be before BEAR to capture panic crashes
    if vol_ratio >= 2.0 and btc_close <= sma_200:
        return "HIGH_VOL_BEARISH"

    # 4. WEAK_BULL — above SMA200, moderate momentum
    if btc_close > sma_200 and roc_20 > -0.05:
        return "WEAK_BULL"

    # 5. BEAR — below SMA200, negative momentum
    if btc_close < sma_200 and roc_20 < -0.05:
        return "BEAR"

    # 6. TRANSITION — everything else
    return "TRANSITION"


# ---------------------------------------------------------------------------
# Full-series regime computation
# ---------------------------------------------------------------------------

def compute_regime_labels(
    daily_close: pd.Series,
    daily_high: pd.Series,
    daily_low: pd.Series,
) -> pd.Series:
    """
    Compute daily regime labels for the full BTC daily series.

    Parameters
    ----------
    daily_close : pd.Series
        Daily BTC close prices (UTC DatetimeIndex).
    daily_high : pd.Series
        Daily BTC high prices.
    daily_low : pd.Series
        Daily BTC low prices.

    Returns
    -------
    pd.Series of str regime labels, indexed like daily_close.
    Values: 'STRONG_BULL', 'HIGH_VOL_BULLISH', 'HIGH_VOL_BEARISH',
            'WEAK_BULL', 'BEAR', 'TRANSITION', 'UNDEFINED'
    """
    sma_200 = compute_sma(daily_close, 200)
    sma_50 = compute_sma(daily_close, 50)

    # ROC_20 = (close - close[20]) / close[20]
    roc_20 = (daily_close - daily_close.shift(20)) / daily_close.shift(20)

    # VOL_ratio = ATR(14) / SMA(ATR(14), 60)
    atr_14 = compute_atr(daily_high, daily_low, daily_close, 14)
    atr_sma_60 = compute_sma(atr_14, 60)
    vol_ratio = atr_14 / atr_sma_60.replace(0, np.nan)

    labels = []
    for i in range(len(daily_close)):
        label = classify_regime(
            btc_close=daily_close.iloc[i],
            sma_200=sma_200.iloc[i],
            sma_50=sma_50.iloc[i],
            roc_20=roc_20.iloc[i],
            vol_ratio=vol_ratio.iloc[i],
        )
        labels.append(label)

    return pd.Series(labels, index=daily_close.index, name="regime")
