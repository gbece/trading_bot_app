"""
Single-trade sensitivity (outlier) report.

Tests how robust the aggregate performance is to individual outlier trades.

Method: Remove the best N trades and the worst N trades one at a time,
report PF and expectancy after each removal.

If performance collapses after removing 1-2 trades, the edge is not genuine —
it depends on a handful of exceptional outcomes.

Produces: outlier_sensitivity_[strategy].txt
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.engine.backtest import BacktestResult


def generate_outlier_report(
    result: BacktestResult,
    strategy_name: str,
    output_dir: Path,
    n_remove: int = 5,
) -> str:
    """
    Generate the single-trade sensitivity report.

    Parameters
    ----------
    result : BacktestResult
    strategy_name : str
    output_dir : Path
    n_remove : int
        How many top/bottom trades to progressively remove (default 5).

    Returns
    -------
    str: formatted report text.
    """
    log = result.trade_log
    lines = []

    lines.append(f"OUTLIER SENSITIVITY REPORT — {strategy_name}")
    lines.append("=" * 60)
    lines.append("")

    if log.empty or "net_R" not in log.columns:
        lines.append("No trades found.")
        text = "\n".join(lines)
        _write_report(output_dir, f"outlier_sensitivity_{strategy_name.lower()}.txt", text)
        return text

    base_stats = _compute_stats(log)
    lines.append(f"BASELINE (all {base_stats['n']} trades):")
    lines.append(f"  Profit factor:  {_fmt(base_stats['pf'])}")
    lines.append(f"  Expectancy (R): {_fmt(base_stats['exp_r'])}R")
    lines.append(f"  Win rate:       {_fmt_pct(base_stats['win_rate'])}")
    lines.append("")

    # Remove top N winning trades progressively
    lines.append("REMOVING BEST TRADES (by net_R):")
    lines.append(f"{'Removed':>8} {'N_left':>8} {'PF':>8} {'E(R)':>9} {'Win%':>7}")
    lines.append("-" * 46)

    sorted_log = log.sort_values("net_R", ascending=False).reset_index(drop=True)
    for k in range(1, min(n_remove + 1, len(log))):
        subset = sorted_log.iloc[k:]
        s = _compute_stats(subset)
        lines.append(
            f"  {k:>6} {s['n']:>8} {_fmt(s['pf']):>8} {_fmt(s['exp_r'])+'R':>9} {_fmt_pct(s['win_rate']):>7}"
        )

    lines.append("")

    # Remove worst N losing trades progressively
    lines.append("REMOVING WORST TRADES (by net_R):")
    lines.append(f"{'Removed':>8} {'N_left':>8} {'PF':>8} {'E(R)':>9} {'Win%':>7}")
    lines.append("-" * 46)

    sorted_asc = log.sort_values("net_R", ascending=True).reset_index(drop=True)
    for k in range(1, min(n_remove + 1, len(log))):
        subset = sorted_asc.iloc[k:]
        s = _compute_stats(subset)
        lines.append(
            f"  {k:>6} {s['n']:>8} {_fmt(s['pf']):>8} {_fmt(s['exp_r'])+'R':>9} {_fmt_pct(s['win_rate']):>7}"
        )

    lines.append("")
    lines.append("─" * 60)
    lines.append("INTERPRETATION:")
    lines.append("If PF collapses after removing 1-2 best trades: edge is outlier-driven. REJECT.")
    lines.append("If PF improves dramatically after removing 1-2 worst: beware of tail-risk.")
    lines.append("Robust strategy: modest sensitivity to removing individual trades.")

    text = "\n".join(lines)
    _write_report(output_dir, f"outlier_sensitivity_{strategy_name.lower()}.txt", text)
    return text


def _compute_stats(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {"n": 0, "pf": float("nan"), "exp_r": float("nan"), "win_rate": float("nan")}
    wins = df[df["net_R"] > 0]
    losses = df[df["net_R"] <= 0]
    gw = wins["net_R"].sum() if len(wins) > 0 else 0.0
    gl = abs(losses["net_R"].sum()) if len(losses) > 0 else 0.0
    pf = gw / gl if gl > 0 else float("nan")
    exp_r = df["net_R"].mean()
    win_rate = len(wins) / n if n > 0 else float("nan")
    return {"n": n, "pf": pf, "exp_r": exp_r, "win_rate": win_rate}


def _fmt(v: float) -> str:
    return f"{v:.3f}" if not np.isnan(v) else "n/a"


def _fmt_pct(v: float) -> str:
    return f"{v*100:.1f}%" if not np.isnan(v) else "n/a"


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
