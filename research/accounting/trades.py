"""
Trade record schema, fee model, and R-multiple calculation.

This is the single source of truth for how performance is measured.
All P&L, fee, and R calculations flow through this module.

Fee model (from docs/Phase_2_5_Harness_Spec.md Section 4):
  - Taker fee: 0.05% per side (Binance perpetual)
  - Funding rate: 0.02% per 8H settlement crossed (flat cost, conservative)
  - Slippage: 10 bps applied at entry (effective_entry_price)
  - All fees applied at exit only (for simplicity)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# TradeRecord
# ---------------------------------------------------------------------------

@dataclass
class TradeRecord:
    """
    Complete trade record. Created at entry, updated at exit and during hold.

    Fields marked [EXIT] are filled when the trade closes.
    Fields marked [LIVE] are updated bar-by-bar while open.
    """
    # Identity
    trade_id: int
    strategy: str                    # 'L2' or 'S2'
    mode: str                        # e.g. 'MVS_FULL', 'MACRO_ONLY', etc.
    direction: str                   # 'long' or 'short'
    detector_variant: Optional[str]  # 'A', 'B', or None (for L2)

    # Entry
    entry_bar: int
    entry_time: pd.Timestamp
    entry_price: float               # Signal price (close of entry bar)
    effective_entry_price: float     # Slippage-adjusted price used for P&L
    stop_price: float
    target_price: float
    stop_distance: float             # abs(effective_entry_price - stop_price)
    target_distance: float           # abs(target_price - effective_entry_price)
    planned_R: float                 # target_distance / stop_distance

    # Context at entry
    regime: str
    atr_at_entry: float
    ema21_at_entry: Optional[float]  # L2 only
    support_level: Optional[float]   # S2 only
    level_touch_count: Optional[int] # S2 only
    level_age_bars: Optional[int]    # S2 only
    breakdown_volume: Optional[float]# S2 only
    vol_sma20: Optional[float]       # S2 only
    vol_ratio: Optional[float]       # S2 only

    # Exit [EXIT]
    exit_bar: Optional[int] = None
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # 'stop_hit', 'target_hit', 'end_of_data'

    # P&L [EXIT]
    gross_pnl: Optional[float] = None
    taker_fee: Optional[float] = None
    funding_cost: Optional[float] = None
    total_fee: Optional[float] = None
    net_pnl: Optional[float] = None

    # R-multiples [EXIT]
    gross_R: Optional[float] = None
    fee_in_R: Optional[float] = None
    net_R: Optional[float] = None

    # MAE/MFE [LIVE]
    mae: Optional[float] = None  # Maximum Adverse Excursion
    mfe: Optional[float] = None  # Maximum Favorable Excursion

    fees_applied: bool = False


# ---------------------------------------------------------------------------
# Fee model
# ---------------------------------------------------------------------------

def compute_taker_fee(
    entry_price: float,
    exit_price: float,
    position_size: float,
    fee_rate: float,
) -> float:
    """
    Taker fee: fee_rate per side on both entry and exit.

    fee = (entry_price + exit_price) * position_size * fee_rate

    Parameters
    ----------
    entry_price : float
        Entry price (signal price, before slippage).
    exit_price : float
        Exit price (stop or target).
    position_size : float
        Normalized position size (default 1.0 in research harness).
    fee_rate : float
        Fee per side (0.0005 for 0.05%).

    Returns
    -------
    float: total taker fee (always positive).
    """
    return (entry_price + exit_price) * position_size * fee_rate


def compute_funding_cost(
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
    position_size: float,
    funding_rate_per_settlement: float,
) -> float:
    """
    Funding cost: flat cost per 8H settlement crossed (conservative assumption).

    funding_settlements = floor(holding_hours / 8)
    funding_cost = settlements * rate * entry_price * position_size

    Parameters
    ----------
    entry_time, exit_time : pd.Timestamp
        UTC timestamps.
    entry_price : float
    position_size : float
    funding_rate_per_settlement : float
        Rate per 8H (0.0002 for 0.02%).

    Returns
    -------
    float: total funding cost (always non-negative).
    """
    holding_seconds = (exit_time - entry_time).total_seconds()
    holding_hours = holding_seconds / 3600.0
    settlements = math.floor(holding_hours / 8.0)
    return settlements * funding_rate_per_settlement * entry_price * position_size


def compute_total_fee(taker_fee: float, funding_cost: float) -> float:
    """Sum of taker and funding costs."""
    return taker_fee + funding_cost


def compute_r_multiple(
    effective_entry: float,
    exit_price: float,
    stop_price: float,
    direction: str,
) -> float:
    """
    Gross R-multiple: how many R did this trade make or lose?

    For longs:  R = (exit - entry) / (entry - stop)
    For shorts: R = (entry - exit) / (stop - entry)

    Parameters
    ----------
    effective_entry : float
        Slippage-adjusted entry price.
    exit_price : float
    stop_price : float
    direction : str
        'long' or 'short'

    Returns
    -------
    float: R-multiple. Positive = profit. Negative = loss.
    """
    stop_distance = abs(effective_entry - stop_price)
    if stop_distance == 0:
        return 0.0

    if direction == "long":
        return (exit_price - effective_entry) / stop_distance
    else:  # short
        return (effective_entry - exit_price) / stop_distance


def compute_r_in_fees(
    effective_entry_price: float,
    stop_price: float,
    total_fee: float,
) -> float:
    """
    Express total fee cost as a fraction of 1R (the stop distance).

    fee_in_R = total_fee / stop_distance

    Parameters
    ----------
    effective_entry_price : float
    stop_price : float
    total_fee : float

    Returns
    -------
    float: fee cost in R units. Positive = fee reduces profit.
    """
    stop_distance = abs(effective_entry_price - stop_price)
    if stop_distance == 0:
        return 0.0
    return total_fee / stop_distance


def apply_fees_to_trade(
    trade: TradeRecord,
    position_size: float,
    fee_rate: float,
    funding_rate_per_settlement: float,
) -> TradeRecord:
    """
    Apply the complete fee model to a closed trade.
    Fills in: taker_fee, funding_cost, total_fee, net_pnl, fee_in_R, net_R.

    Must only be called on trades with exit_price, exit_time, and gross_pnl set.

    Parameters
    ----------
    trade : TradeRecord
        Must have exit_price, exit_time, gross_pnl set.
    position_size : float
    fee_rate : float
    funding_rate_per_settlement : float

    Returns
    -------
    TradeRecord with fee fields filled in.
    """
    assert trade.exit_price is not None, "exit_price must be set before applying fees"
    assert trade.exit_time is not None, "exit_time must be set before applying fees"
    assert trade.gross_pnl is not None, "gross_pnl must be set before applying fees"

    taker = compute_taker_fee(
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        position_size=position_size,
        fee_rate=fee_rate,
    )
    funding = compute_funding_cost(
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        entry_price=trade.entry_price,
        position_size=position_size,
        funding_rate_per_settlement=funding_rate_per_settlement,
    )
    total = compute_total_fee(taker, funding)

    trade.taker_fee = taker
    trade.funding_cost = funding
    trade.total_fee = total
    trade.net_pnl = trade.gross_pnl - total

    # R-multiples
    trade.gross_R = compute_r_multiple(
        effective_entry=trade.effective_entry_price,
        exit_price=trade.exit_price,
        stop_price=trade.stop_price,
        direction=trade.direction,
    )
    trade.fee_in_R = compute_r_in_fees(
        effective_entry_price=trade.effective_entry_price,
        stop_price=trade.stop_price,
        total_fee=total,
    )
    trade.net_R = trade.gross_R - trade.fee_in_R
    trade.fees_applied = True
    return trade


# ---------------------------------------------------------------------------
# Trade log and summary statistics
# ---------------------------------------------------------------------------

def build_trade_log(trades: list[TradeRecord]) -> pd.DataFrame:
    """
    Convert a list of TradeRecord objects to a DataFrame.

    Each row is one closed trade. Columns match TradeRecord fields.

    Parameters
    ----------
    trades : list[TradeRecord]
        Closed trades (exit_price set).

    Returns
    -------
    pd.DataFrame
    """
    if not trades:
        return pd.DataFrame()

    rows = [asdict(t) for t in trades]
    df = pd.DataFrame(rows)
    return df


def compute_summary_stats(trade_log: pd.DataFrame) -> dict:
    """
    Compute aggregate performance statistics from a trade log DataFrame.

    Returns a dict with all metrics used in the backtest report format.

    Parameters
    ----------
    trade_log : pd.DataFrame
        Output of build_trade_log().

    Returns
    -------
    dict with keys:
        n_trades, n_wins, n_losses, win_rate,
        profit_factor, expectancy_R,
        avg_win_R, avg_loss_R,
        max_drawdown_R, max_consecutive_losses,
        gross_R_total, net_R_total,
        avg_net_R, std_net_R,
        total_fees_R
    """
    if trade_log.empty or "net_R" not in trade_log.columns:
        return {
            "n_trades": 0,
            "n_wins": 0,
            "n_losses": 0,
            "win_rate": float("nan"),
            "profit_factor": float("nan"),
            "expectancy_R": float("nan"),
            "avg_win_R": float("nan"),
            "avg_loss_R": float("nan"),
            "max_drawdown_R": float("nan"),
            "max_consecutive_losses": 0,
            "gross_R_total": float("nan"),
            "net_R_total": float("nan"),
            "avg_net_R": float("nan"),
            "std_net_R": float("nan"),
            "total_fees_R": float("nan"),
        }

    closed = trade_log.dropna(subset=["net_R"])
    n = len(closed)
    wins = closed[closed["net_R"] > 0]
    losses = closed[closed["net_R"] <= 0]

    n_wins = len(wins)
    n_losses = len(losses)
    win_rate = n_wins / n if n > 0 else float("nan")

    gross_win_R = wins["net_R"].sum() if n_wins > 0 else 0.0
    gross_loss_R = abs(losses["net_R"].sum()) if n_losses > 0 else 0.0
    profit_factor = gross_win_R / gross_loss_R if gross_loss_R > 0 else float("nan")

    avg_win_R = wins["net_R"].mean() if n_wins > 0 else float("nan")
    avg_loss_R = losses["net_R"].mean() if n_losses > 0 else float("nan")
    expectancy_R = closed["net_R"].mean() if n > 0 else float("nan")

    # Drawdown in R-space
    cumulative_R = closed["net_R"].cumsum()
    running_max = cumulative_R.cummax()
    drawdown = running_max - cumulative_R
    max_drawdown_R = drawdown.max() if n > 0 else float("nan")

    # Max consecutive losses
    max_consec_losses = 0
    consec = 0
    for r in closed["net_R"]:
        if r <= 0:
            consec += 1
            max_consec_losses = max(max_consec_losses, consec)
        else:
            consec = 0

    gross_R_total = closed["gross_R"].sum() if "gross_R" in closed.columns else float("nan")
    net_R_total = closed["net_R"].sum()
    avg_net_R = closed["net_R"].mean()
    std_net_R = closed["net_R"].std()
    total_fees_R = closed["fee_in_R"].sum() if "fee_in_R" in closed.columns else float("nan")

    return {
        "n_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy_R": expectancy_R,
        "avg_win_R": avg_win_R,
        "avg_loss_R": avg_loss_R,
        "max_drawdown_R": max_drawdown_R,
        "max_consecutive_losses": max_consec_losses,
        "gross_R_total": gross_R_total,
        "net_R_total": net_R_total,
        "avg_net_R": avg_net_R,
        "std_net_R": std_net_R,
        "total_fees_R": total_fees_R,
    }
