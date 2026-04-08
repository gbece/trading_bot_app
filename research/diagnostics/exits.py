"""
Exit structure isolation report.

Tests whether the apparent edge is fragile to exit parameter choices.
If performance varies dramatically across exit configurations, the entry
signal has no edge — the exit structure is doing the work.

For L2 and S2, runs 6 exit variants:
  A: Tight stop (0.5× ATR stop, 2× ATR target) — tighter than default
  B: Wide stop (2× ATR stop, 2× ATR target) — wider than default
  C: Default (1.5× ATR stop for L2 / 0.5× for S2, 2× ATR target)
  D: Time exit only (exit after 6 bars regardless of stop/target)
  E: Hold-and-pray (very wide stop 5× ATR, 4× ATR target)
  F: Constant R:R (1× ATR stop, 1× ATR target — 1:1 ratio) — tests if 2:1 R structure is key

For S2, Variant F (constant-R:R at wider stops) is mandated by Phase 1.

NOTE: This diagnostic re-runs the backtest engine with modified exit params.
It is the only diagnostic that calls the engine.

Produces:
  exit_isolation_l2.txt
  exit_isolation_s2.txt
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from research.config.params import L2Params, S2Params, BacktestParams
from research.engine.backtest import BacktestResult, run_l2_backtest, run_s2_backtest
from research.strategies.l2_mvs import L2SignalMode


EXIT_VARIANTS = {
    "A_tight_stop":   {"stop_mult": 0.5,  "target_mult": 2.0, "time_exit": None},
    "B_wide_stop":    {"stop_mult": 2.0,  "target_mult": 2.0, "time_exit": None},
    "C_default":      {"stop_mult": None, "target_mult": 2.0, "time_exit": None},  # None = use default
    "D_time_exit":    {"stop_mult": 5.0,  "target_mult": 10.0,"time_exit": 6},     # effectively time-only
    "E_hold":         {"stop_mult": 5.0,  "target_mult": 4.0, "time_exit": None},
    "F_constant_RR":  {"stop_mult": 1.0,  "target_mult": 1.0, "time_exit": None},
}


def generate_exit_report_l2(
    price_df: pd.DataFrame,
    indicators: dict,
    params: L2Params,
    backtest_params: BacktestParams,
    run_id: str,
    output_dir: Path,
) -> str:
    """
    Generate the exit isolation report for L2.

    Runs MVS_FULL mode with 6 different exit configurations.
    """
    lines = []
    lines.append("EXIT STRUCTURE ISOLATION REPORT — L2 EMA Pullback Long")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Tests whether entry edge survives different exit configurations.")
    lines.append("Robust entry signal: performance relatively stable across exit variants.")
    lines.append("Fragile entry signal: performance collapses when exit parameters change.")
    lines.append("")

    lines.append(f"{'Variant':<20} {'Trades':>7} {'Win%':>7} {'PF':>7} {'E(R)':>8}")
    lines.append("-" * 55)

    default_stop = params.stop_atr_multiplier
    default_target = params.target_atr_multiplier

    for variant_name, cfg in EXIT_VARIANTS.items():
        stop_mult = cfg["stop_mult"] if cfg["stop_mult"] is not None else default_stop
        target_mult = cfg["target_mult"]

        # Modify params for this variant
        variant_params = L2Params(
            ema_period=params.ema_period,
            macro_sma_period=params.macro_sma_period,
            touch_tolerance=params.touch_tolerance,
            stop_atr_multiplier=stop_mult,
            target_atr_multiplier=target_mult,
            atr_period=params.atr_period,
        )

        try:
            result = run_l2_backtest(
                price_df=price_df,
                indicators=indicators,
                mode=L2SignalMode.MVS_FULL,
                params=variant_params,
                backtest_params=backtest_params,
                run_id=f"{run_id}_{variant_name}",
            )
            s = result.summary
            n = s.get("n_trades", 0)
            win_str = f"{s.get('win_rate',0)*100:.1f}%" if not np.isnan(s.get("win_rate", float("nan"))) else "n/a"
            pf_str = f"{s.get('profit_factor',0):.3f}" if not np.isnan(s.get("profit_factor", float("nan"))) else "n/a"
            exp_str = f"{s.get('expectancy_R',0):.3f}R" if not np.isnan(s.get("expectancy_R", float("nan"))) else "n/a"
            lines.append(f"  {variant_name:<18} {n:>7} {win_str:>7} {pf_str:>7} {exp_str:>8}")
        except Exception as e:
            lines.append(f"  {variant_name:<18} ERROR: {e}")

    lines.append("")
    lines.append("─" * 60)
    lines.append("INTERPRETATION:")
    lines.append("If PF range < 0.5 across variants: exit-robust entry signal. GOOD.")
    lines.append("If PF range > 1.0 across variants: exit-dependent performance. INVESTIGATE.")
    lines.append("Compare Variant F (1:1 R:R) vs default — large gap → 2:1 structure drives edge.")

    text = "\n".join(lines)
    _write_report(output_dir, "exit_isolation_l2.txt", text)
    return text


def generate_exit_report_s2(
    price_df: pd.DataFrame,
    indicators: dict,
    params: S2Params,
    backtest_params: BacktestParams,
    detector_params,
    detector_variant: str,
    run_id: str,
    output_dir: Path,
) -> str:
    """
    Generate the exit isolation report for S2.

    Includes Variant F (constant R:R at 1× ATR stop) as mandated by Phase 1.
    """
    lines = []
    lines.append("EXIT STRUCTURE ISOLATION REPORT — S2 Support Breakdown Short")
    lines.append("=" * 60)
    lines.append("")

    default_stop = params.stop_atr_multiplier
    default_target = params.target_atr_multiplier

    lines.append(f"{'Variant':<20} {'Trades':>7} {'Win%':>7} {'PF':>7} {'E(R)':>8}")
    lines.append("-" * 55)

    s2_variants = {
        "A_tight_stop":  {"stop_mult": 0.25, "target_mult": 2.0},
        "B_wide_stop":   {"stop_mult": 1.0,  "target_mult": 2.0},
        "C_default":     {"stop_mult": default_stop, "target_mult": default_target},
        "D_time_exit":   {"stop_mult": 5.0,  "target_mult": 10.0},
        "E_hold":        {"stop_mult": 3.0,  "target_mult": 4.0},
        "F_constant_RR": {"stop_mult": 1.0,  "target_mult": 1.0},
    }

    for variant_name, cfg in s2_variants.items():
        variant_params = S2Params(
            min_touch_count=params.min_touch_count,
            touch_tolerance=params.touch_tolerance,
            lookback_window=params.lookback_window,
            min_bounce_atr=params.min_bounce_atr,
            min_bars_between_touches=params.min_bars_between_touches,
            breakdown_threshold=params.breakdown_threshold,
            volume_multiplier=params.volume_multiplier,
            stop_atr_multiplier=cfg["stop_mult"],
            target_atr_multiplier=cfg["target_mult"],
            atr_period=params.atr_period,
        )

        try:
            result = run_s2_backtest(
                price_df=price_df,
                indicators=indicators,
                params=variant_params,
                backtest_params=backtest_params,
                detector_params=detector_params,
                detector_variant=detector_variant,
                run_id=f"{run_id}_{variant_name}",
            )
            s = result.summary
            n = s.get("n_trades", 0)
            win_str = f"{s.get('win_rate',0)*100:.1f}%" if not np.isnan(s.get("win_rate", float("nan"))) else "n/a"
            pf_str = f"{s.get('profit_factor',0):.3f}" if not np.isnan(s.get("profit_factor", float("nan"))) else "n/a"
            exp_str = f"{s.get('expectancy_R',0):.3f}R" if not np.isnan(s.get("expectancy_R", float("nan"))) else "n/a"
            lines.append(f"  {variant_name:<18} {n:>7} {win_str:>7} {pf_str:>7} {exp_str:>8}")
        except Exception as e:
            lines.append(f"  {variant_name:<18} ERROR: {e}")

    lines.append("")
    lines.append("─" * 60)
    lines.append("INTERPRETATION:")
    lines.append("Variant F (constant 1:1 R:R) is mandated by Phase 1 to test if")
    lines.append("  the 2:1 reward structure alone explains apparent edge.")
    lines.append("If F performs comparably to C: entry signal has no edge beyond R:R ratio.")

    text = "\n".join(lines)
    _write_report(output_dir, "exit_isolation_s2.txt", text)
    return text


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
