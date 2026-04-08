"""
Period isolation report.

Splits the backtest into 6-month periods and reports performance per period.
For L2, also computes BTC buy-and-hold return per period and Pearson correlation.

Produces:
  - period_isolation_[strategy].txt
  - buy_and_hold_correlation_l2.txt (L2 only)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.engine.backtest import BacktestResult


def generate_period_report(
    result: BacktestResult,
    price_df: pd.DataFrame,
    strategy_name: str,
    output_dir: Path,
    is_l2: bool = False,
) -> str:
    """
    Generate the period isolation report.

    Parameters
    ----------
    result : BacktestResult
    price_df : pd.DataFrame
        Full OHLCV DataFrame with 'timestamp' and 'close' columns.
    strategy_name : str
    output_dir : Path
    is_l2 : bool
        If True, also compute BTC buy-and-hold comparison (Section 6 of spec).

    Returns
    -------
    str: formatted report text.
    """
    log = result.trade_log
    lines = []

    lines.append(f"PERIOD ISOLATION REPORT — {strategy_name}")
    lines.append("=" * 60)
    lines.append("")

    if log.empty or "net_R" not in log.columns or "entry_time" not in log.columns:
        lines.append("No trades found.")
        text = "\n".join(lines)
        _write_report(output_dir, f"period_isolation_{strategy_name.lower()}.txt", text)
        return text

    log = log.copy()
    log["entry_time"] = pd.to_datetime(log["entry_time"], utc=True)

    # Build 6-month periods from min entry_time
    start = log["entry_time"].min().normalize().replace(day=1)
    end = log["entry_time"].max()

    periods = _build_6m_periods(start, end)

    period_rows = []
    for (p_start, p_end) in periods:
        mask = (log["entry_time"] >= p_start) & (log["entry_time"] < p_end)
        subset = log[mask]

        n = len(subset)
        if n == 0:
            period_rows.append({
                "period": f"{p_start.strftime('%Y-%m')} to {(p_end - pd.Timedelta(days=1)).strftime('%Y-%m')}",
                "n": 0,
                "win_rate": float("nan"),
                "profit_factor": float("nan"),
                "expectancy_R": float("nan"),
                "net_R_total": float("nan"),
                "p_start": p_start,
                "p_end": p_end,
            })
            continue

        wins = subset[subset["net_R"] > 0]
        losses = subset[subset["net_R"] <= 0]
        win_rate = len(wins) / n if n > 0 else float("nan")
        gross_win = wins["net_R"].sum() if len(wins) > 0 else 0.0
        gross_loss = abs(losses["net_R"].sum()) if len(losses) > 0 else 0.0
        pf = gross_win / gross_loss if gross_loss > 0 else float("nan")
        exp_r = subset["net_R"].mean()
        net_r_total = subset["net_R"].sum()

        period_rows.append({
            "period": f"{p_start.strftime('%Y-%m')} to {(p_end - pd.Timedelta(days=1)).strftime('%Y-%m')}",
            "n": n,
            "win_rate": win_rate,
            "profit_factor": pf,
            "expectancy_R": exp_r,
            "net_R_total": net_r_total,
            "p_start": p_start,
            "p_end": p_end,
        })

    # Table
    lines.append(f"{'Period':<22} {'N':>5} {'Win%':>7} {'PF':>7} {'E(R)':>8} {'Total_R':>9}")
    lines.append("-" * 62)
    for r in period_rows:
        win_str = f"{r['win_rate']*100:.1f}%" if not np.isnan(r.get("win_rate", float("nan"))) else "n/a"
        pf_str = f"{r['profit_factor']:.3f}" if not np.isnan(r.get("profit_factor", float("nan"))) else "n/a"
        exp_str = f"{r['expectancy_R']:.3f}R" if not np.isnan(r.get("expectancy_R", float("nan"))) else "n/a"
        total_str = f"{r['net_R_total']:.2f}R" if not np.isnan(r.get("net_R_total", float("nan"))) else "n/a"
        lines.append(f"  {r['period']:<20} {r['n']:>5} {win_str:>7} {pf_str:>7} {exp_str:>8} {total_str:>9}")

    lines.append("")

    # L2: Buy-and-hold comparison
    if is_l2 and not price_df.empty:
        bah_lines = _compute_bah_comparison(period_rows, price_df, lines)
        lines.extend(bah_lines)
        # Write separate file
        bah_text = "\n".join(bah_lines)
        _write_report(output_dir, "buy_and_hold_correlation_l2.txt", bah_text)

    text = "\n".join(lines)
    _write_report(output_dir, f"period_isolation_{strategy_name.lower()}.txt", text)
    return text


def _compute_bah_comparison(period_rows: list, price_df: pd.DataFrame, existing_lines: list) -> list:
    """Compute BTC buy-and-hold comparison for L2 (Section 6)."""
    lines = []
    lines.append("=" * 60)
    lines.append("SECTION 6: BUY-AND-HOLD COMPARISON (L2 only)")
    lines.append("─" * 60)

    price_df = price_df.copy()
    price_df["timestamp"] = pd.to_datetime(price_df["timestamp"], utc=True)

    l2_pf_values = []
    btc_returns = []

    lines.append(f"{'Period':<22} {'L2_PF':>7} {'L2_E(R)':>9} {'BTC_Ret%':>9}")
    lines.append("-" * 55)

    for r in period_rows:
        p_start = r["p_start"]
        p_end = r["p_end"]

        btc_mask = (price_df["timestamp"] >= p_start) & (price_df["timestamp"] < p_end)
        btc_period = price_df[btc_mask]

        if len(btc_period) < 2:
            btc_ret = float("nan")
        else:
            btc_ret = (btc_period["close"].iloc[-1] / btc_period["close"].iloc[0] - 1) * 100

        pf_str = f"{r['profit_factor']:.3f}" if not np.isnan(r.get("profit_factor", float("nan"))) else "n/a"
        exp_str = f"{r['expectancy_R']:.3f}" if not np.isnan(r.get("expectancy_R", float("nan"))) else "n/a"
        btc_str = f"{btc_ret:.1f}%" if not np.isnan(btc_ret) else "n/a"

        lines.append(f"  {r['period']:<20} {pf_str:>7} {exp_str:>9} {btc_str:>9}")

        if not np.isnan(r.get("profit_factor", float("nan"))) and not np.isnan(btc_ret):
            l2_pf_values.append(r["profit_factor"])
            btc_returns.append(btc_ret)

    lines.append("")

    if len(l2_pf_values) >= 3:
        corr = float(np.corrcoef(l2_pf_values, btc_returns)[0, 1])
        lines.append(f"Pearson correlation (L2 period PF, BTC return): r = {corr:.3f}")
        if corr > 0.80:
            lines.append("  *** WARNING: r > 0.80 — Strategy performance strongly correlated with BTC trend.")
            lines.append("      L2's entry signal may not add value over regime beta exposure.")
        elif corr > 0.60:
            lines.append("  NOTE: Moderate correlation with BTC trend. Expected for a trend-following strategy.")
        else:
            lines.append("  OK: Correlation moderate/low — entry signal may provide independent selectivity.")
    else:
        lines.append("Insufficient data for Pearson correlation (need ≥3 complete periods).")

    return lines


def _build_6m_periods(start: pd.Timestamp, end: pd.Timestamp) -> list:
    """Build list of (p_start, p_end) covering start to end in 6-month increments."""
    periods = []
    current = start
    while current < end:
        # 6 months forward
        month = current.month + 6
        year = current.year
        if month > 12:
            month -= 12
            year += 1
        next_ = current.replace(year=year, month=month)
        periods.append((current, next_))
        current = next_
    return periods


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
