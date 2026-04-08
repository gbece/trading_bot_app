"""
Cross-strategy drawdown correlation report.

Only runs after BOTH L2 and S2 pass individually (Phase 7).

Overlays L2 and S2 equity curves, computes correlated drawdowns,
identifies periods where both strategies lose simultaneously.

Produces: portfolio_correlation.txt
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.engine.backtest import BacktestResult


def generate_portfolio_report(
    l2_result: BacktestResult,
    s2_result: BacktestResult,
    output_dir: Path,
) -> str:
    """
    Generate cross-strategy drawdown correlation report.

    Parameters
    ----------
    l2_result : BacktestResult
    s2_result : BacktestResult
    output_dir : Path

    Returns
    -------
    str: formatted report text.
    """
    lines = []
    lines.append("CROSS-STRATEGY PORTFOLIO CORRELATION REPORT")
    lines.append("=" * 60)
    lines.append("")

    l2_log = l2_result.trade_log
    s2_log = s2_result.trade_log

    if l2_log.empty or s2_log.empty:
        lines.append("Insufficient trade data for portfolio analysis.")
        text = "\n".join(lines)
        _write_report(output_dir, "portfolio_correlation.txt", text)
        return text

    # Align equity curves
    l2_curve = l2_result.equity_curve.dropna()
    s2_curve = s2_result.equity_curve.dropna()

    # Daily R-return from equity curves
    l2_daily = l2_curve.resample("D").last().ffill()
    s2_daily = s2_curve.resample("D").last().ffill()

    # Compute correlation on overlapping period
    common_idx = l2_daily.index.intersection(s2_daily.index)
    if len(common_idx) < 30:
        lines.append("Insufficient overlapping data for correlation analysis.")
        text = "\n".join(lines)
        _write_report(output_dir, "portfolio_correlation.txt", text)
        return text

    l2_ret = l2_daily.loc[common_idx].diff().dropna()
    s2_ret = s2_daily.loc[common_idx].diff().dropna()

    if len(l2_ret) > 1 and len(s2_ret) > 1:
        corr = float(np.corrcoef(l2_ret.values, s2_ret.values)[0, 1])
    else:
        corr = float("nan")

    lines.append(f"Equity curve correlation (L2 vs S2 daily R): {corr:.3f}")
    lines.append("")

    if not np.isnan(corr):
        if corr > 0.5:
            lines.append("  WARNING: High positive correlation between L2 and S2.")
            lines.append("  Both strategies lose simultaneously in market stress events.")
            lines.append("  Running both does not meaningfully diversify risk.")
        elif corr < -0.1:
            lines.append("  GOOD: Negative correlation — strategies offset each other.")
        else:
            lines.append("  OK: Low correlation — strategies provide some diversification.")

    lines.append("")
    lines.append("REGIME-CONDITIONAL ANALYSIS")
    lines.append("─" * 40)

    # Tag L2 trades by regime and find simultaneous drawdown periods
    if "regime" in l2_log.columns and "regime" in s2_log.columns:
        transition_l2 = l2_log[l2_log["regime"] == "TRANSITION"]["net_R"].mean()
        transition_s2 = s2_log[s2_log["regime"] == "TRANSITION"]["net_R"].mean()
        lines.append(f"L2 expectancy in TRANSITION regime:  {transition_l2:.3f}R" if not np.isnan(transition_l2) else "L2 TRANSITION: no trades")
        lines.append(f"S2 expectancy in TRANSITION regime:  {transition_s2:.3f}R" if not np.isnan(transition_s2) else "S2 TRANSITION: no trades")
        lines.append("")
        lines.append("  TRANSITION periods are highest correlation-risk for multi-strategy portfolios.")
        lines.append("  Both strategies may degrade simultaneously during regime uncertainty.")

    lines.append("")
    lines.append("PORTFOLIO SUMMARY")
    lines.append("─" * 40)
    l2_total_R = l2_log["net_R"].sum() if "net_R" in l2_log.columns else float("nan")
    s2_total_R = s2_log["net_R"].sum() if "net_R" in s2_log.columns else float("nan")
    combined = (l2_total_R + s2_total_R) if not np.isnan(l2_total_R) and not np.isnan(s2_total_R) else float("nan")

    lines.append(f"L2 total net R:       {l2_total_R:.2f}R" if not np.isnan(l2_total_R) else "L2 total net R: n/a")
    lines.append(f"S2 total net R:       {s2_total_R:.2f}R" if not np.isnan(s2_total_R) else "S2 total net R: n/a")
    lines.append(f"Combined net R:       {combined:.2f}R" if not np.isnan(combined) else "Combined net R: n/a")
    lines.append("")
    lines.append("Note: Combined R assumes equal position sizing for L2 and S2.")
    lines.append("Actual capital allocation should reflect relative confidence in each strategy.")

    text = "\n".join(lines)
    _write_report(output_dir, "portfolio_correlation.txt", text)
    return text


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
