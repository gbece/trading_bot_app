"""
Walk-forward validation.

Implements both methods per docs/Phase_2_Strategy_Spec.md Section 3:

Method A — Rolling windows:
  4-month train / 2-month test windows, rolling forward.
  Each window is independent (no expanding history).

Method B — Expanding windows:
  Expanding train set, fixed 6-month test periods.
  Train always starts at data start; test advances by 6 months.

Both methods required for PROMISING threshold.
Also runs slippage sensitivity sweep (0, 5, 10, 15 bps).

Produces:
  walk_forward_[strategy].txt
  slippage_sensitivity_[strategy].txt
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.config.params import BacktestParams, L2Params, S2Params
from research.engine.backtest import BacktestResult, run_l2_backtest, run_s2_backtest
from research.strategies.l2_mvs import L2SignalMode


def generate_walk_forward_report(
    price_df: pd.DataFrame,
    indicators: dict,
    strategy: str,
    params: Any,
    backtest_params: BacktestParams,
    run_id: str,
    output_dir: Path,
    detector_params: Any = None,
    detector_variant: str = "A",
) -> str:
    """
    Generate walk-forward validation report for L2 or S2.

    Parameters
    ----------
    price_df : pd.DataFrame
    indicators : dict
    strategy : str
        'L2' or 'S2'
    params : L2Params or S2Params
    backtest_params : BacktestParams
    run_id : str
    output_dir : Path
    detector_params : DetectorAParams or DetectorBParams (S2 only)
    detector_variant : str (S2 only)

    Returns
    -------
    str: formatted report text.
    """
    lines = []
    lines.append(f"WALK-FORWARD VALIDATION REPORT — {strategy}")
    lines.append("=" * 60)
    lines.append("")

    timestamps = price_df["timestamp"]
    data_start = timestamps.min()
    data_end = timestamps.max()

    def run_on_slice(df_slice: pd.DataFrame) -> dict:
        """Run backtest on a price_df slice, recomputing indicator slice."""
        if len(df_slice) < backtest_params.warmup_bars_4h + 30:
            return {"n_trades": 0, "profit_factor": float("nan")}

        # Slice indicators to match df_slice
        idx = df_slice.index
        ind_slice = {k: v.loc[idx] if hasattr(v, "loc") else v for k, v in indicators.items()}

        # Reset index for sliced data to be positional
        df_reset = df_slice.reset_index(drop=True)
        ind_reset = {k: v.reset_index(drop=True) for k, v in ind_slice.items()}

        try:
            if strategy == "L2":
                result = run_l2_backtest(
                    price_df=df_reset,
                    indicators=ind_reset,
                    mode=L2SignalMode.MVS_FULL,
                    params=params,
                    backtest_params=backtest_params,
                    run_id=run_id + "_wf",
                )
            else:
                result = run_s2_backtest(
                    price_df=df_reset,
                    indicators=ind_reset,
                    params=params,
                    backtest_params=backtest_params,
                    detector_params=detector_params,
                    detector_variant=detector_variant,
                    run_id=run_id + "_wf",
                )
            return result.summary
        except Exception:
            return {"n_trades": 0, "profit_factor": float("nan")}

    # ── Method A: Rolling windows (4-month train / 2-month test) ──────────
    lines.append("METHOD A — Rolling Windows (4-month train / 2-month test)")
    lines.append("─" * 60)

    train_months = 4
    test_months = 2
    window_months = train_months + test_months

    method_a_windows = _build_rolling_windows(data_start, data_end, train_months, test_months)

    if not method_a_windows:
        lines.append("Insufficient data for rolling window validation.")
    else:
        lines.append(f"{'Period':<35} {'Tr_N':>5} {'Tr_PF':>7} {'Te_N':>5} {'Te_PF':>7} {'Delta':>7}")
        lines.append("-" * 68)

        test_pfs = []
        for (train_start, train_end, test_start, test_end) in method_a_windows:
            train_mask = (timestamps >= train_start) & (timestamps < train_end)
            test_mask = (timestamps >= test_start) & (timestamps < test_end)

            train_df = price_df[train_mask]
            test_df = price_df[test_mask]

            train_stats = run_on_slice(train_df)
            test_stats = run_on_slice(test_df)

            tr_n = train_stats.get("n_trades", 0)
            te_n = test_stats.get("n_trades", 0)
            tr_pf = train_stats.get("profit_factor", float("nan"))
            te_pf = test_stats.get("profit_factor", float("nan"))

            delta = tr_pf - te_pf if not np.isnan(tr_pf) and not np.isnan(te_pf) else float("nan")

            period_str = f"{train_start.strftime('%Y-%m')}→{test_end.strftime('%Y-%m')}"
            tr_pf_str = f"{tr_pf:.3f}" if not np.isnan(tr_pf) else "n/a"
            te_pf_str = f"{te_pf:.3f}" if not np.isnan(te_pf) else "n/a"
            delta_str = f"{delta:+.3f}" if not np.isnan(delta) else "n/a"

            lines.append(f"  {period_str:<33} {tr_n:>5} {tr_pf_str:>7} {te_n:>5} {te_pf_str:>7} {delta_str:>7}")

            if not np.isnan(te_pf):
                test_pfs.append(te_pf)

        lines.append("")
        if test_pfs:
            mean_pf = float(np.mean(test_pfs))
            std_pf = float(np.std(test_pfs))
            pct_above_1 = sum(1 for p in test_pfs if p > 1.0) / len(test_pfs) * 100
            lines.append(f"Method A summary:")
            lines.append(f"  Mean test PF:           {mean_pf:.3f}")
            lines.append(f"  Std dev of test PF:     {std_pf:.3f}")
            lines.append(f"  % windows with PF > 1.0: {pct_above_1:.1f}%")
            if mean_pf >= 1.15 and pct_above_1 >= 60:
                lines.append(f"  → PROMISING threshold met (mean PF ≥ 1.15, ≥60% windows > 1.0)")
            elif mean_pf >= 0.95:
                lines.append(f"  → INCONCLUSIVE (mean PF {mean_pf:.3f}, between 0.95–1.15)")
            else:
                lines.append(f"  → REJECT (mean PF < 0.95)")

    lines.append("")

    # ── Method B: Expanding windows ──────────────────────────────────────
    lines.append("METHOD B — Expanding Windows (6-month test, expanding train)")
    lines.append("─" * 60)

    method_b_windows = _build_expanding_windows(data_start, data_end, test_months=6)

    if not method_b_windows:
        lines.append("Insufficient data for expanding window validation.")
    else:
        lines.append(f"{'Train period':<25} {'Test period':<20} {'Tr_N':>5} {'Tr_PF':>7} {'Te_N':>5} {'Te_PF':>7}")
        lines.append("-" * 72)

        test_pfs_b = []
        for (train_start, train_end, test_start, test_end) in method_b_windows:
            train_mask = (timestamps >= train_start) & (timestamps < train_end)
            test_mask = (timestamps >= test_start) & (timestamps < test_end)

            train_df = price_df[train_mask]
            test_df = price_df[test_mask]

            train_stats = run_on_slice(train_df)
            test_stats = run_on_slice(test_df)

            tr_n = train_stats.get("n_trades", 0)
            te_n = test_stats.get("n_trades", 0)
            tr_pf = train_stats.get("profit_factor", float("nan"))
            te_pf = test_stats.get("profit_factor", float("nan"))

            train_str = f"{train_start.strftime('%Y-%m')} → {train_end.strftime('%Y-%m')}"
            test_str = f"{test_start.strftime('%Y-%m')} → {test_end.strftime('%Y-%m')}"
            tr_pf_str = f"{tr_pf:.3f}" if not np.isnan(tr_pf) else "n/a"
            te_pf_str = f"{te_pf:.3f}" if not np.isnan(te_pf) else "n/a"

            lines.append(f"  {train_str:<23} {test_str:<20} {tr_n:>5} {tr_pf_str:>7} {te_n:>5} {te_pf_str:>7}")

            if not np.isnan(te_pf):
                test_pfs_b.append(te_pf)

        lines.append("")
        if test_pfs_b:
            mean_pf_b = float(np.mean(test_pfs_b))
            std_pf_b = float(np.std(test_pfs_b))
            pct_above_b = sum(1 for p in test_pfs_b if p > 1.0) / len(test_pfs_b) * 100
            lines.append(f"Method B summary:")
            lines.append(f"  Mean test PF:           {mean_pf_b:.3f}")
            lines.append(f"  Std dev of test PF:     {std_pf_b:.3f}")
            lines.append(f"  % windows with PF > 1.0: {pct_above_b:.1f}%")
            if mean_pf_b >= 1.15 and pct_above_b >= 60:
                lines.append(f"  → PROMISING threshold met")
            elif mean_pf_b >= 0.95:
                lines.append(f"  → INCONCLUSIVE")
            else:
                lines.append(f"  → REJECT")

    text = "\n".join(lines)
    _write_report(output_dir, f"walk_forward_{strategy.lower()}.txt", text)

    # ── Slippage sensitivity sweep ────────────────────────────────────────
    slippage_text = _generate_slippage_sweep(
        price_df, indicators, strategy, params, backtest_params, run_id,
        detector_params, detector_variant
    )
    _write_report(output_dir, f"slippage_sensitivity_{strategy.lower()}.txt", slippage_text)

    return text


def _generate_slippage_sweep(
    price_df, indicators, strategy, params, backtest_params, run_id,
    detector_params, detector_variant
) -> str:
    """Run slippage sensitivity sweep (0, 5, 10, 15 bps)."""
    lines = []
    lines.append(f"SLIPPAGE SENSITIVITY REPORT — {strategy}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Tests whether the edge survives realistic execution costs.")
    lines.append("")

    lines.append(f"{'Slippage':>10} {'Trades':>7} {'Win%':>7} {'PF':>8} {'E(R)':>9}")
    lines.append("-" * 46)

    for bps in [0, 5, 10, 15]:
        bp_params = BacktestParams(
            fee_rate=backtest_params.fee_rate,
            slippage_bps=bps,
            funding_rate_per_settlement=backtest_params.funding_rate_per_settlement,
            data_start=backtest_params.data_start,
            data_end=backtest_params.data_end,
            warmup_bars_4h=backtest_params.warmup_bars_4h,
            position_size=backtest_params.position_size,
            random_seed=backtest_params.random_seed,
        )
        try:
            if strategy == "L2":
                result = run_l2_backtest(
                    price_df=price_df,
                    indicators=indicators,
                    mode=L2SignalMode.MVS_FULL,
                    params=params,
                    backtest_params=bp_params,
                    run_id=f"{run_id}_slip{bps}",
                )
            else:
                result = run_s2_backtest(
                    price_df=price_df,
                    indicators=indicators,
                    params=params,
                    backtest_params=bp_params,
                    detector_params=detector_params,
                    detector_variant=detector_variant,
                    run_id=f"{run_id}_slip{bps}",
                )

            s = result.summary
            n = s.get("n_trades", 0)
            wr = s.get("win_rate", float("nan"))
            pf = s.get("profit_factor", float("nan"))
            exp_r = s.get("expectancy_R", float("nan"))

            wr_str = f"{wr*100:.1f}%" if not np.isnan(wr) else "n/a"
            pf_str = f"{pf:.3f}" if not np.isnan(pf) else "n/a"
            exp_str = f"{exp_r:.3f}R" if not np.isnan(exp_r) else "n/a"

            warn = ""
            if not np.isnan(pf):
                if pf < 1.0 and bps <= 10:
                    warn = " ← CRITICAL: edge consumed by costs"
                elif pf < 1.0 and bps == 15:
                    warn = " ← WARNING: not tradeable at 15bps"

            lines.append(f"  {bps:>8}bps {n:>7} {wr_str:>7} {pf_str:>8} {exp_str:>9}{warn}")
        except Exception as e:
            lines.append(f"  {bps:>8}bps ERROR: {e}")

    lines.append("")
    lines.append("INTERPRETATION:")
    lines.append("If PF < 1.0 at 15 bps: Strategy not tradeable under realistic execution.")
    lines.append("If PF < 1.0 at 10 bps: Edge entirely consumed by costs. CRITICAL FAILURE.")

    return "\n".join(lines)


def _build_rolling_windows(
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
    train_months: int,
    test_months: int,
) -> list:
    """Build rolling (train_start, train_end, test_start, test_end) tuples."""
    windows = []
    current = data_start

    while True:
        train_end = _add_months(current, train_months)
        test_start = train_end
        test_end = _add_months(test_start, test_months)

        if test_end > data_end:
            break

        windows.append((current, train_end, test_start, test_end))
        current = _add_months(current, test_months)  # slide by test period

    return windows


def _build_expanding_windows(
    data_start: pd.Timestamp,
    data_end: pd.Timestamp,
    test_months: int,
) -> list:
    """Build expanding (train_start, train_end, test_start, test_end) tuples."""
    windows = []
    # First test window starts after initial 12 months of data for training
    initial_train = _add_months(data_start, 12)
    test_start = initial_train

    while True:
        test_end = _add_months(test_start, test_months)
        if test_end > data_end:
            break

        windows.append((data_start, test_start, test_start, test_end))
        test_start = test_end

    return windows


def _add_months(dt: pd.Timestamp, months: int) -> pd.Timestamp:
    """Add months to a Timestamp."""
    month = dt.month + months
    year = dt.year
    while month > 12:
        month -= 12
        year += 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def _write_report(output_dir: Path, filename: str, text: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / filename).write_text(text)
