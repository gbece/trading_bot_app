"""
Component attribution report for L2.

Requires all 5 mode BacktestResults to be passed in:
  RANDOM, MACRO_ONLY, TOUCH_ONLY, MVS_NO_CONFIRM, MVS_FULL

Produces: attribution_l2.txt

Purpose: Show which components of the L2 strategy actually contribute edge.
If MACRO_ONLY performs as well as MVS_FULL, the EMA touch adds nothing.
If RANDOM performs comparably, the stop/target structure is doing all the work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

from research.engine.backtest import BacktestResult


MODES_IN_ORDER = [
    "RANDOM",
    "MACRO_ONLY",
    "TOUCH_ONLY",
    "MVS_NO_CONFIRM",
    "MVS_FULL",
]


def generate_attribution_report(
    mode_results: dict[str, BacktestResult],
    output_dir: Path,
) -> str:
    """
    Generate the L2 component attribution report.

    Parameters
    ----------
    mode_results : dict[str, BacktestResult]
        Keys are mode names (e.g. 'RANDOM', 'MVS_FULL').
        All 5 modes should be present for a complete report.
    output_dir : Path
        Directory where the report is saved.

    Returns
    -------
    str: formatted report text.
    """
    lines = []
    lines.append("COMPONENT ATTRIBUTION REPORT — L2 EMA Pullback Long")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Purpose: Decompose where L2's apparent edge comes from.")
    lines.append("Each mode isolates a different component of the strategy.")
    lines.append("")

    # Table header
    lines.append(f"{'Mode':<20} {'Trades':>7} {'Win%':>7} {'PF':>7} {'E(R)':>8} {'MaxDD_R':>9}")
    lines.append("-" * 62)

    rows = {}
    for mode in MODES_IN_ORDER:
        result = mode_results.get(mode)
        if result is None:
            lines.append(f"  {mode:<18} {'NOT RUN':>7}")
            continue

        s = result.summary
        n = s.get("n_trades", 0)
        win_rate = s.get("win_rate", float("nan"))
        pf = s.get("profit_factor", float("nan"))
        exp_r = s.get("expectancy_R", float("nan"))
        max_dd = s.get("max_drawdown_R", float("nan"))

        win_str = f"{win_rate*100:.1f}%" if not np.isnan(win_rate) else "n/a"
        pf_str = f"{pf:.3f}" if not np.isnan(pf) else "n/a"
        exp_str = f"{exp_r:.3f}R" if not np.isnan(exp_r) else "n/a"
        dd_str = f"{max_dd:.2f}R" if not np.isnan(max_dd) else "n/a"

        lines.append(f"  {mode:<18} {n:>7} {win_str:>7} {pf_str:>7} {exp_str:>8} {dd_str:>9}")
        rows[mode] = s

    lines.append("")
    lines.append("=" * 60)
    lines.append("COMPONENT ATTRIBUTION ANALYSIS")
    lines.append("─" * 60)

    # Hypothesis 1: Does macro filter add value?
    mvs_pf = rows.get("MVS_FULL", {}).get("profit_factor", float("nan"))
    touch_pf = rows.get("TOUCH_ONLY", {}).get("profit_factor", float("nan"))
    if not np.isnan(mvs_pf) and not np.isnan(touch_pf):
        delta = mvs_pf - touch_pf
        lines.append(f"\nHypothesis 1: Does the macro filter (SMA200) add value?")
        lines.append(f"  MVS_FULL PF:    {mvs_pf:.3f}")
        lines.append(f"  TOUCH_ONLY PF:  {touch_pf:.3f}")
        lines.append(f"  Delta (MVS - TOUCH_ONLY): {delta:+.3f}")
        if delta > 0.10:
            lines.append("  → YES: Macro filter adds material edge (+0.10 PF)")
        elif delta > 0.0:
            lines.append("  → MARGINAL: Macro filter adds slight edge")
        else:
            lines.append("  → NO: Macro filter does not improve performance over touch-only")

    # Hypothesis 2: Does EMA touch add value over just trading the bull market?
    macro_pf = rows.get("MACRO_ONLY", {}).get("profit_factor", float("nan"))
    if not np.isnan(mvs_pf) and not np.isnan(macro_pf):
        delta = mvs_pf - macro_pf
        lines.append(f"\nHypothesis 2: Does EMA touch add value over MACRO_ONLY?")
        lines.append(f"  MVS_FULL PF:    {mvs_pf:.3f}")
        lines.append(f"  MACRO_ONLY PF:  {macro_pf:.3f}")
        lines.append(f"  Delta (MVS - MACRO): {delta:+.3f}")
        if delta > 0.10:
            lines.append("  → YES: EMA touch provides genuine entry selectivity")
        elif abs(delta) <= 0.10:
            lines.append("  → INCONCLUSIVE: EMA touch adds little over undifferentiated bull-market exposure")
        else:
            lines.append("  → NO: EMA touch actually HURTS performance vs MACRO_ONLY")

    # Hypothesis 3: Does confirmation candle add value?
    no_confirm_pf = rows.get("MVS_NO_CONFIRM", {}).get("profit_factor", float("nan"))
    if not np.isnan(mvs_pf) and not np.isnan(no_confirm_pf):
        delta = mvs_pf - no_confirm_pf
        lines.append(f"\nHypothesis 3: Does the confirmation candle add value?")
        lines.append(f"  MVS_FULL PF:       {mvs_pf:.3f}")
        lines.append(f"  MVS_NO_CONFIRM PF: {no_confirm_pf:.3f}")
        lines.append(f"  Delta (FULL - NO_CONFIRM): {delta:+.3f}")
        if abs(delta) <= 0.05:
            lines.append("  → MARGINAL: Confirmation candle adds negligible edge (within 0.05 PF)")
        elif delta > 0.05:
            lines.append("  → YES: Confirmation candle adds measurable value")
        else:
            lines.append("  → NO: Skipping confirmation produces better results")

    # Hypothesis 4: Is the stop/target structure doing the work?
    random_pf = rows.get("RANDOM", {}).get("profit_factor", float("nan"))
    if not np.isnan(mvs_pf) and not np.isnan(random_pf):
        delta = mvs_pf - random_pf
        lines.append(f"\nHypothesis 4: Does MVS outperform random entry (same stop/target)?")
        lines.append(f"  MVS_FULL PF: {mvs_pf:.3f}")
        lines.append(f"  RANDOM PF:   {random_pf:.3f}")
        lines.append(f"  Delta (MVS - RANDOM): {delta:+.3f}")
        if delta > 0.15:
            lines.append("  → YES: Strategy provides meaningful selectivity over random entry")
        elif delta > 0.0:
            lines.append("  → MARGINAL: Small improvement over random — may be noise")
        else:
            lines.append("  → NO: Random entry performs as well or better. Stop/target structure is doing the work, not the signal.")

    lines.append("")
    lines.append("─" * 60)
    lines.append("VERDICT GUIDANCE")
    lines.append("─" * 60)
    lines.append("If RANDOM ≈ MVS_FULL: Edge is in the exit structure, not the signal. REJECT signal logic.")
    lines.append("If MACRO_ONLY ≈ MVS_FULL: Edge is in bull-market exposure, not the EMA touch. REVIEW.")
    lines.append("If TOUCH_ONLY ≈ MVS_FULL: Macro filter adds no value. Simplify or reconsider.")
    lines.append("If MVS_FULL materially outperforms all others: Genuine entry signal edge. PROCEED.")

    text = "\n".join(lines)
    _write_report(output_dir, "attribution_l2.txt", text)
    return text


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
