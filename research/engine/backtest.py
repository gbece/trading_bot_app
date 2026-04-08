"""
Bar-by-bar backtest engine.

Orchestrates all phases (A through D/E) for L2 and S2 strategies.
The engine does NOT know whether it is running L2 or S2 — it calls
strategy_fn() and receives a signal or None.

Processing order per bar (from docs/Phase_2_5_Harness_Spec.md):
  Phase A: State update (record OHLCV)
  Phase B: Open trade management (stop/target check, MAE/MFE update)
  Phase C: Signal generation (only if no open trade)
  Phase D: Trade record update (open new trade if signal fired)

For S2, an additional phase runs before signal generation:
  Phase C-pre: Support level update (bars[0:i-1] only)

Design principles:
  - One open trade at a time (MVS constraint)
  - Stop/target same-bar conflict → stop hit (conservative)
  - All indicator values are pre-computed and passed in
  - Engine does not modify indicator arrays
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from research.config.params import BacktestParams, DetectorAParams, DetectorBParams
from research.accounting.trades import (
    TradeRecord,
    apply_fees_to_trade,
    build_trade_log,
    compute_summary_stats,
)
from research.strategies.l2_mvs import L2Signal, L2SignalMode, evaluate_l2_signal
from research.strategies.s2_mvs import S2Signal, evaluate_s2_signal
from research.detectors.support import (
    SupportLevel,
    detect_support_levels_variant_a,
    detect_support_levels_variant_b,
)
from research.config.params import L2Params, S2Params


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """
    Complete output of a single backtest run.

    trades : list[TradeRecord]
        All closed trades (fees applied).
    open_trade : Optional[TradeRecord]
        Any trade still open at end of data (fees NOT applied).
    signal_log : list[dict]
        Every bar where signal evaluation ran (fired or rejected).
    trade_log : pd.DataFrame
        build_trade_log(trades)
    summary : dict
        compute_summary_stats(trade_log)
    equity_curve : pd.Series
        Cumulative net_R by bar index (NaN for bars with no trade activity).
    run_metadata : dict
        Strategy name, mode, detector variant, run_id, param snapshot.
    """
    trades: list[TradeRecord]
    open_trade: Optional[TradeRecord]
    signal_log: list[dict]
    trade_log: pd.DataFrame
    summary: dict
    equity_curve: pd.Series
    run_metadata: dict


# ---------------------------------------------------------------------------
# L2 backtest runner
# ---------------------------------------------------------------------------

def run_l2_backtest(
    price_df: pd.DataFrame,
    indicators: dict,
    mode: L2SignalMode,
    params: L2Params,
    backtest_params: BacktestParams,
    run_id: str,
) -> BacktestResult:
    """
    Run the L2 EMA Pullback Long backtest for one mode.

    Parameters
    ----------
    price_df : pd.DataFrame
        Full OHLCV DataFrame (validated, aligned). Columns:
        [timestamp, open, high, low, close, volume,
         ema21_4h, atr14_4h, daily_sma200_aligned, btc_daily_close_aligned,
         regime]
    indicators : dict
        Pre-computed indicator series (indexed by DataFrame position):
          'ema21'         : pd.Series (4H EMA21)
          'atr14'         : pd.Series (4H ATR14)
          'daily_sma200'  : pd.Series (daily SMA200, aligned to 4H with D+1)
          'btc_daily_close': pd.Series (daily BTC close, aligned to 4H with D+1)
          'regime'        : pd.Series (regime label strings, aligned to 4H)
    mode : L2SignalMode
    params : L2Params
    backtest_params : BacktestParams
    run_id : str

    Returns
    -------
    BacktestResult
    """
    n = len(price_df)
    warmup = backtest_params.warmup_bars_4h
    slippage_bps = backtest_params.slippage_bps
    fee_rate = backtest_params.fee_rate
    funding_rate = backtest_params.funding_rate_per_settlement
    position_size = backtest_params.position_size

    trades: list[TradeRecord] = []
    signal_log: list[dict] = []
    open_trade: Optional[TradeRecord] = None
    trade_counter = 0

    cumulative_R = np.full(n, np.nan)
    running_net_R = 0.0

    ema21 = indicators["ema21"]
    atr14 = indicators["atr14"]
    daily_sma200 = indicators["daily_sma200"]
    btc_daily_close = indicators["btc_daily_close"]
    regime_series = indicators["regime"]

    for i in range(warmup, n):
        timestamp = price_df["timestamp"].iloc[i]
        open_p = price_df["open"].iloc[i]
        high_p = price_df["high"].iloc[i]
        low_p = price_df["low"].iloc[i]
        close_p = price_df["close"].iloc[i]

        # ── PHASE B: Open trade management ────────────────────────────────
        if open_trade is not None:
            stop = open_trade.stop_price
            target = open_trade.target_price

            # Same-bar conflict: stop hit takes priority (conservative)
            stop_hit = low_p <= stop
            target_hit = high_p >= target

            if stop_hit:
                exit_price = stop
                exit_reason = "stop_hit"
                gross_pnl = (exit_price - open_trade.effective_entry_price) * position_size
                open_trade.exit_bar = i
                open_trade.exit_time = timestamp
                open_trade.exit_price = exit_price
                open_trade.exit_reason = exit_reason
                open_trade.gross_pnl = gross_pnl
                open_trade = apply_fees_to_trade(open_trade, position_size, fee_rate, funding_rate)
                running_net_R += open_trade.net_R
                trades.append(open_trade)
                open_trade = None

            elif target_hit:
                exit_price = target
                exit_reason = "target_hit"
                gross_pnl = (exit_price - open_trade.effective_entry_price) * position_size
                open_trade.exit_bar = i
                open_trade.exit_time = timestamp
                open_trade.exit_price = exit_price
                open_trade.exit_reason = exit_reason
                open_trade.gross_pnl = gross_pnl
                open_trade = apply_fees_to_trade(open_trade, position_size, fee_rate, funding_rate)
                running_net_R += open_trade.net_R
                trades.append(open_trade)
                open_trade = None

            else:
                # MAE/MFE update
                current_mae = open_trade.effective_entry_price - low_p  # long: adverse = low
                current_mfe = high_p - open_trade.effective_entry_price  # long: favorable = high
                open_trade.mae = max(open_trade.mae or 0.0, current_mae)
                open_trade.mfe = max(open_trade.mfe or 0.0, current_mfe)

        cumulative_R[i] = running_net_R

        # Skip signal generation if trade still open
        if open_trade is not None:
            continue

        # ── PHASE C: Signal generation ────────────────────────────────────
        ema21_i = float(ema21.iloc[i]) if not pd.isna(ema21.iloc[i]) else float("nan")
        atr14_i = float(atr14.iloc[i]) if not pd.isna(atr14.iloc[i]) else float("nan")
        sma200_i = float(daily_sma200.iloc[i]) if not pd.isna(daily_sma200.iloc[i]) else float("nan")
        btc_close_i = float(btc_daily_close.iloc[i]) if not pd.isna(btc_daily_close.iloc[i]) else float("nan")
        regime_i = str(regime_series.iloc[i]) if not pd.isna(regime_series.iloc[i]) else "UNDEFINED"

        signal = evaluate_l2_signal(
            bar_index=i,
            open_price=open_p,
            high_price=high_p,
            low_price=low_p,
            close_price=close_p,
            timestamp=timestamp,
            ema21=ema21_i,
            atr14=atr14_i,
            daily_sma200_aligned=sma200_i,
            btc_daily_close_aligned=btc_close_i,
            regime=regime_i,
            mode=mode,
            params=params,
        )

        if signal is None:
            continue  # warmup/NaN — skip

        # Log signal evaluation
        signal_log.append({
            "bar_index": i,
            "timestamp": timestamp,
            "mode": mode.value,
            "signal_fired": signal.signal_fired,
            "rejection_reason": signal.filter_rejection_reason,
            "close": close_p,
            "ema21": ema21_i,
            "regime": regime_i,
        })

        # ── PHASE D: Open new trade ───────────────────────────────────────
        if signal.signal_fired:
            entry = signal.entry_price
            effective_entry = entry * (1 + slippage_bps / 10_000)
            stop_price = signal.stop_price
            target_price = signal.target_price
            stop_dist = abs(effective_entry - stop_price)
            target_dist = abs(target_price - effective_entry)
            planned_R = target_dist / stop_dist if stop_dist > 0 else float("nan")

            trade_counter += 1
            open_trade = TradeRecord(
                trade_id=trade_counter,
                strategy="L2",
                mode=mode.value,
                direction="long",
                detector_variant=None,
                entry_bar=i,
                entry_time=timestamp,
                entry_price=entry,
                effective_entry_price=effective_entry,
                stop_price=stop_price,
                target_price=target_price,
                stop_distance=stop_dist,
                target_distance=target_dist,
                planned_R=planned_R,
                regime=regime_i,
                atr_at_entry=signal.atr_at_entry,
                ema21_at_entry=signal.ema21_at_entry,
                support_level=None,
                level_touch_count=None,
                level_age_bars=None,
                breakdown_volume=None,
                vol_sma20=None,
                vol_ratio=None,
            )

    # End of data: close any open trade at last close
    if open_trade is not None:
        last_i = n - 1
        last_close = price_df["close"].iloc[last_i]
        last_ts = price_df["timestamp"].iloc[last_i]
        gross_pnl = (last_close - open_trade.effective_entry_price) * position_size
        open_trade.exit_bar = last_i
        open_trade.exit_time = last_ts
        open_trade.exit_price = last_close
        open_trade.exit_reason = "end_of_data"
        open_trade.gross_pnl = gross_pnl
        open_trade = apply_fees_to_trade(open_trade, position_size, fee_rate, funding_rate)

    trade_log = build_trade_log(trades)
    summary = compute_summary_stats(trade_log)
    equity_curve = pd.Series(cumulative_R, index=price_df.index, name="cumulative_net_R")

    return BacktestResult(
        trades=trades,
        open_trade=open_trade,
        signal_log=signal_log,
        trade_log=trade_log,
        summary=summary,
        equity_curve=equity_curve,
        run_metadata={
            "strategy": "L2",
            "mode": mode.value,
            "detector_variant": None,
            "run_id": run_id,
            "n_bars": n,
            "warmup_bars": warmup,
        },
    )


# ---------------------------------------------------------------------------
# S2 backtest runner
# ---------------------------------------------------------------------------

def run_s2_backtest(
    price_df: pd.DataFrame,
    indicators: dict,
    params: S2Params,
    backtest_params: BacktestParams,
    detector_params: Any,  # DetectorAParams or DetectorBParams
    detector_variant: str,  # 'A' or 'B'
    run_id: str,
) -> BacktestResult:
    """
    Run the S2 Support Breakdown Short backtest.

    Parameters
    ----------
    price_df : pd.DataFrame
        Full validated OHLCV DataFrame.
    indicators : dict
        Pre-computed indicators:
          'atr14'       : pd.Series (4H ATR14)
          'vol_sma20'   : pd.Series (volume SMA20, current bar excluded)
          'regime'      : pd.Series (regime labels, D+1 aligned)
    params : S2Params
    backtest_params : BacktestParams
    detector_params : DetectorAParams or DetectorBParams
    detector_variant : str ('A' or 'B')
    run_id : str

    Returns
    -------
    BacktestResult
    """
    n = len(price_df)
    warmup = backtest_params.warmup_bars_4h
    slippage_bps = backtest_params.slippage_bps
    fee_rate = backtest_params.fee_rate
    funding_rate = backtest_params.funding_rate_per_settlement
    position_size = backtest_params.position_size

    atr14 = indicators["atr14"]
    vol_sma20 = indicators["vol_sma20"]
    regime_series = indicators["regime"]

    trades: list[TradeRecord] = []
    signal_log: list[dict] = []
    open_trade: Optional[TradeRecord] = None
    trade_counter = 0

    cumulative_R = np.full(n, np.nan)
    running_net_R = 0.0

    for i in range(warmup, n):
        timestamp = price_df["timestamp"].iloc[i]
        high_p = price_df["high"].iloc[i]
        low_p = price_df["low"].iloc[i]
        close_p = price_df["close"].iloc[i]
        volume_i = price_df["volume"].iloc[i]
        open_p = price_df["open"].iloc[i]

        # ── PHASE B: Open trade management (SHORT) ────────────────────────
        if open_trade is not None:
            stop = open_trade.stop_price    # above entry for short
            target = open_trade.target_price  # below entry for short

            # Same-bar conflict → stop hit (conservative)
            stop_hit = high_p >= stop
            target_hit = low_p <= target

            if stop_hit:
                exit_price = stop
                exit_reason = "stop_hit"
                # Short P&L: entry - exit
                gross_pnl = (open_trade.effective_entry_price - exit_price) * position_size
                open_trade.exit_bar = i
                open_trade.exit_time = timestamp
                open_trade.exit_price = exit_price
                open_trade.exit_reason = exit_reason
                open_trade.gross_pnl = gross_pnl
                open_trade = apply_fees_to_trade(open_trade, position_size, fee_rate, funding_rate)
                running_net_R += open_trade.net_R
                trades.append(open_trade)
                open_trade = None

            elif target_hit:
                exit_price = target
                exit_reason = "target_hit"
                gross_pnl = (open_trade.effective_entry_price - exit_price) * position_size
                open_trade.exit_bar = i
                open_trade.exit_time = timestamp
                open_trade.exit_price = exit_price
                open_trade.exit_reason = exit_reason
                open_trade.gross_pnl = gross_pnl
                open_trade = apply_fees_to_trade(open_trade, position_size, fee_rate, funding_rate)
                running_net_R += open_trade.net_R
                trades.append(open_trade)
                open_trade = None

            else:
                # MAE/MFE for short: adverse = up, favorable = down
                current_mae = high_p - open_trade.effective_entry_price
                current_mfe = open_trade.effective_entry_price - low_p
                open_trade.mae = max(open_trade.mae or 0.0, current_mae)
                open_trade.mfe = max(open_trade.mfe or 0.0, current_mfe)

        cumulative_R[i] = running_net_R

        if open_trade is not None:
            continue

        # ── PHASE C-pre: Support level update ────────────────────────────
        # Use bars[0 : i] (i.e., iloc[:i]) — excludes current bar i
        bars_slice = price_df.iloc[:i]
        bar_offset = 0  # bars_slice[0] is always row 0 of price_df

        if detector_variant == "A":
            active_levels = detect_support_levels_variant_a(
                bars_slice=bars_slice,
                params=detector_params,
                bar_offset=bar_offset,
            )
        else:
            active_levels = detect_support_levels_variant_b(
                bars_slice=bars_slice,
                params=detector_params,
                bar_offset=bar_offset,
            )

        # Exclude levels where last_touch_bar == i-1 (too recent — price is at the level now)
        active_levels = [lv for lv in active_levels if lv.last_touch_bar < i - 1]

        # ── PHASE D: Signal generation ────────────────────────────────────
        atr14_i = float(atr14.iloc[i]) if not pd.isna(atr14.iloc[i]) else float("nan")
        vol_sma20_i = float(vol_sma20.iloc[i]) if not pd.isna(vol_sma20.iloc[i]) else float("nan")
        regime_i = str(regime_series.iloc[i]) if not pd.isna(regime_series.iloc[i]) else "UNDEFINED"

        signal = evaluate_s2_signal(
            bar_index=i,
            open_price=open_p,
            high_price=high_p,
            low_price=low_p,
            close_price=close_p,
            volume=volume_i,
            timestamp=timestamp,
            atr14=atr14_i,
            vol_sma20=vol_sma20_i,
            regime=regime_i,
            active_levels=active_levels,
            params=params,
            detector_variant=detector_variant,
        )

        if signal is None:
            continue

        signal_log.append({
            "bar_index": i,
            "timestamp": timestamp,
            "detector_variant": detector_variant,
            "signal_fired": signal.signal_fired,
            "rejection_reason": signal.filter_rejection_reason,
            "n_active_levels": len(active_levels),
            "close": close_p,
            "volume": volume_i,
            "vol_ratio": signal.volume_ratio,
            "regime": regime_i,
        })

        if signal.signal_fired:
            entry = signal.entry_price
            # Short: slippage is adverse downward (effective entry slightly lower = worse fill)
            effective_entry = entry * (1 - slippage_bps / 10_000)
            stop_price = signal.stop_price
            target_price = signal.target_price
            stop_dist = abs(stop_price - effective_entry)    # stop above entry
            target_dist = abs(effective_entry - target_price)  # target below entry
            planned_R = target_dist / stop_dist if stop_dist > 0 else float("nan")

            trade_counter += 1
            open_trade = TradeRecord(
                trade_id=trade_counter,
                strategy="S2",
                mode="MVS_FULL",
                direction="short",
                detector_variant=detector_variant,
                entry_bar=i,
                entry_time=timestamp,
                entry_price=entry,
                effective_entry_price=effective_entry,
                stop_price=stop_price,
                target_price=target_price,
                stop_distance=stop_dist,
                target_distance=target_dist,
                planned_R=planned_R,
                regime=regime_i,
                atr_at_entry=signal.atr_at_entry,
                ema21_at_entry=None,
                support_level=signal.support_level,
                level_touch_count=signal.touch_count,
                level_age_bars=signal.level_age_bars,
                breakdown_volume=volume_i,
                vol_sma20=vol_sma20_i,
                vol_ratio=signal.volume_ratio,
            )

    # End of data: close any open trade at last close
    if open_trade is not None:
        last_i = n - 1
        last_close = price_df["close"].iloc[last_i]
        last_ts = price_df["timestamp"].iloc[last_i]
        gross_pnl = (open_trade.effective_entry_price - last_close) * position_size
        open_trade.exit_bar = last_i
        open_trade.exit_time = last_ts
        open_trade.exit_price = last_close
        open_trade.exit_reason = "end_of_data"
        open_trade.gross_pnl = gross_pnl
        open_trade = apply_fees_to_trade(open_trade, position_size, fee_rate, funding_rate)

    trade_log = build_trade_log(trades)
    summary = compute_summary_stats(trade_log)
    equity_curve = pd.Series(cumulative_R, index=price_df.index, name="cumulative_net_R")

    return BacktestResult(
        trades=trades,
        open_trade=open_trade,
        signal_log=signal_log,
        trade_log=trade_log,
        summary=summary,
        equity_curve=equity_curve,
        run_metadata={
            "strategy": "S2",
            "mode": "MVS_FULL",
            "detector_variant": detector_variant,
            "run_id": run_id,
            "n_bars": n,
            "warmup_bars": warmup,
        },
    )
