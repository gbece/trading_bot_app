"""
Random entry baselines for L2 component attribution.

BASELINE-1: RANDOM_ALL_BARS
  Enter at every bar (after warmup), no regime filter, no EMA filter.
  Same stop/target structure as L2 MVS.
  Deterministic: enters at every eligible bar. A single run suffices.

BASELINE-2: RANDOM_MACRO_MATCHED
  Identical to RANDOM_ALL_BARS, but only enters on bars where the
  L2 macro filter passes (BTC close > daily SMA200).

Both baselines apply the same slippage (10 bps) and funding rate model (0.02% per 8H)
as L2 MVS. Without this, the comparison is invalid.

Both produce BacktestResult objects compatible with all diagnostic outputs.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from research.config.params import L2Params, BacktestParams
from research.engine.backtest import BacktestResult, run_l2_backtest
from research.strategies.l2_mvs import L2SignalMode


def run_random_all_bars(
    price_df: pd.DataFrame,
    indicators: dict,
    params: L2Params,
    backtest_params: BacktestParams,
    run_id: str,
) -> BacktestResult:
    """
    Run RANDOM_ALL_BARS baseline.

    Enters at every bar after warmup regardless of any market condition.
    Uses same stop/target structure as L2 MVS:
      stop   = close - stop_atr_multiplier * ATR14
      target = close + target_atr_multiplier * ATR14

    No regime filter. No EMA filter. No confirmation candle.

    Parameters
    ----------
    price_df : pd.DataFrame
        Full validated OHLCV DataFrame.
    indicators : dict
        Must contain: 'ema21', 'atr14', 'daily_sma200', 'btc_daily_close', 'regime'.
    params : L2Params
    backtest_params : BacktestParams
    run_id : str

    Returns
    -------
    BacktestResult with mode='RANDOM'.
    """
    result = run_l2_backtest(
        price_df=price_df,
        indicators=indicators,
        mode=L2SignalMode.RANDOM,
        params=params,
        backtest_params=backtest_params,
        run_id=run_id,
    )
    result.run_metadata["baseline"] = "RANDOM_ALL_BARS"
    return result


def run_random_macro_matched(
    price_df: pd.DataFrame,
    indicators: dict,
    params: L2Params,
    backtest_params: BacktestParams,
    run_id: str,
) -> BacktestResult:
    """
    Run RANDOM_MACRO_MATCHED baseline.

    Enters at every bar where the L2 macro filter passes
    (BTC close > daily SMA200), same stop/target structure.
    No EMA filter. No confirmation.

    Purpose: isolates macro filter contribution.
    If this performs as well as L2 MVS FULL, the EMA touch adds no value.

    Parameters
    ----------
    price_df : pd.DataFrame
    indicators : dict
        Must contain: 'ema21', 'atr14', 'daily_sma200', 'btc_daily_close', 'regime'.
    params : L2Params
    backtest_params : BacktestParams
    run_id : str

    Returns
    -------
    BacktestResult with mode='MACRO_ONLY'.
    """
    result = run_l2_backtest(
        price_df=price_df,
        indicators=indicators,
        mode=L2SignalMode.MACRO_ONLY,
        params=params,
        backtest_params=backtest_params,
        run_id=run_id,
    )
    result.run_metadata["baseline"] = "RANDOM_MACRO_MATCHED"
    return result
