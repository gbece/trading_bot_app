"""
Regime contribution report.

Produces: regime_contribution_[strategy].txt

For each of the 6 regimes, reports:
  - trade count (% of total)
  - win rate
  - profit factor
  - expectancy (R)
  - contribution to total PnL (%)
  - max drawdown within regime
  - avg R-multiple
  - flag if N < 15

Used for both L2 and S2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.engine.backtest import BacktestResult

REGIMES = [
    "STRONG_BULL",
    "WEAK_BULL",
    "HIGH_VOL_BULLISH",
    "HIGH_VOL_BEARISH",
    "BEAR",
    "TRANSITION",
]


def generate_regime_report(
    result: BacktestResult,
    strategy_name: str,
    output_dir: Path,
) -> str:
    """
    Generate the regime contribution report.

    Parameters
    ----------
    result : BacktestResult
    strategy_name : str
        e.g. 'L2_MVS_FULL', 'S2_VARIANT_A'
    output_dir : Path
        Directory where reports are saved.

    Returns
    -------
    str: formatted report text.
    """
    log = result.trade_log
    lines = []

    lines.append(f"REGIME CONTRIBUTION REPORT — {strategy_name}")
    lines.append("=" * 60)
    lines.append("")

    if log.empty or "net_R" not in log.columns:
        lines.append("No trades found. Cannot produce regime report.")
        text = "\n".join(lines)
        _write_report(output_dir, f"regime_contribution_{strategy_name.lower()}.txt", text)
        return text

    total_n = len(log)
    total_net_pnl = log["net_R"].sum()

    lines.append(f"Total trades across all regimes: {total_n}")
    lines.append("")

    regime_results = []

    for regime in REGIMES:
        subset = log[log["regime"] == regime] if "regime" in log.columns else pd.DataFrame()

        if subset.empty:
            regime_results.append({
                "regime": regime,
                "n": 0,
                "pct": 0.0,
                "win_rate": float("nan"),
                "profit_factor": float("nan"),
                "expectancy_R": float("nan"),
                "pnl_contribution_pct": 0.0,
                "max_drawdown_R": float("nan"),
                "avg_R": float("nan"),
                "low_sample": True,
            })
            continue

        n = len(subset)
        pct = n / total_n * 100 if total_n > 0 else 0.0
        wins = subset[subset["net_R"] > 0]
        losses = subset[subset["net_R"] <= 0]
        win_rate = len(wins) / n * 100 if n > 0 else float("nan")

        gross_win = wins["net_R"].sum() if len(wins) > 0 else 0.0
        gross_loss = abs(losses["net_R"].sum()) if len(losses) > 0 else 0.0
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("nan")
        expectancy_R = subset["net_R"].mean()
        avg_R = subset["net_R"].mean()

        # Contribution to total PnL
        regime_pnl = subset["net_R"].sum()
        pnl_contribution_pct = regime_pnl / total_net_pnl * 100 if total_net_pnl != 0 else float("nan")

        # Max drawdown within regime
        cum_R = subset["net_R"].cumsum()
        running_max = cum_R.cummax()
        drawdown = (running_max - cum_R)
        max_dd = drawdown.max() if n > 0 else float("nan")

        regime_results.append({
            "regime": regime,
            "n": n,
            "pct": pct,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy_R": expectancy_R,
            "pnl_contribution_pct": pnl_contribution_pct,
            "max_drawdown_R": max_dd,
            "avg_R": avg_R,
            "low_sample": n < 15,
        })

    for r in regime_results:
        lines.append(f"Regime: {r['regime']}")
        lines.append("─" * 40)

        if r["n"] == 0:
            lines.append("  No trades in this regime.")
        else:
            lines.append(f"  Trades in regime:         {r['n']} ({r['pct']:.1f}% of total)")
            lines.append(f"  Win rate:                 {r['win_rate']:.1f}%")
            pf_str = f"{r['profit_factor']:.3f}" if not np.isnan(r["profit_factor"]) else "n/a (no losses)"
            lines.append(f"  Profit factor:            {pf_str}")
            lines.append(f"  Expectancy:               {r['expectancy_R']:.3f}R")
            contrib_str = f"{r['pnl_contribution_pct']:.1f}%" if not np.isnan(r["pnl_contribution_pct"]) else "n/a"
            lines.append(f"  Contribution to total PnL: {contrib_str}")
            dd_str = f"{r['max_drawdown_R']:.2f}R" if not np.isnan(r["max_drawdown_R"]) else "n/a"
            lines.append(f"  Max drawdown in regime:   {dd_str}")
            lines.append(f"  Avg R-multiple:           {r['avg_R']:.3f}R")
            if r["low_sample"]:
                lines.append(f"  *** WARNING: N < 15 — statistically insufficient ***")

        lines.append("")

    # Summary: which regimes are positive?
    positive_regimes = [r for r in regime_results if not np.isnan(r["expectancy_R"]) and r["expectancy_R"] > 0]
    lines.append("─" * 60)
    lines.append(f"Positive expectancy regimes: {len(positive_regimes)} of {len(REGIMES)}")
    lines.append(f"  {[r['regime'] for r in positive_regimes]}")
    if len(positive_regimes) >= 4:
        lines.append("  → PROMISING threshold met (≥4 of 6 regimes positive)")
    else:
        lines.append(f"  → PROMISING requires 4 of 6. Currently {len(positive_regimes)}.")

    text = "\n".join(lines)
    _write_report(output_dir, f"regime_contribution_{strategy_name.lower()}.txt", text)
    return text


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
