"""
L2 Research Pipeline — Entry Point

Runs the complete L2 EMA Pullback Long research pipeline:
  1. Load and validate data
  2. Compute indicators
  3. Run all 5 component decomposition modes
  4. Run random baselines
  5. Generate all diagnostic reports
  6. Apply research stop criteria
  7. Print verdict: PROMISING / INCONCLUSIVE / REJECT

Usage:
    python research/run_l2.py
    python research/run_l2.py --data-dir research/data/raw --run-id my_run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# ── Config ─────────────────────────────────────────────────────────────────
from research.config.params import (
    L2Params, BacktestParams, DetectorAParams, DetectorBParams,
    freeze_all,
)

# ── Data ───────────────────────────────────────────────────────────────────
from research.data.validate import validate_ohlcv
from research.data.align import align_daily_to_4h, align_regime_labels

# ── Indicators ─────────────────────────────────────────────────────────────
from research.indicators.trend import compute_ema, compute_sma
from research.indicators.volatility import compute_atr
from research.indicators.volume import compute_volume_sma, compute_relative_volume
from research.indicators.regime import compute_regime_labels

# ── Engine ─────────────────────────────────────────────────────────────────
from research.engine.backtest import run_l2_backtest, BacktestResult
from research.strategies.l2_mvs import L2SignalMode
from research.baselines.random_entry import run_random_all_bars, run_random_macro_matched

# ── Diagnostics ────────────────────────────────────────────────────────────
from research.diagnostics.attribution import generate_attribution_report
from research.diagnostics.regimes import generate_regime_report
from research.diagnostics.periods import generate_period_report
from research.diagnostics.outliers import generate_outlier_report
from research.diagnostics.walk_forward import generate_walk_forward_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).parent / "runs"
RAW_DIR = Path(__file__).parent / "data" / "raw"


def main(args=None):
    parser = argparse.ArgumentParser(description="Run L2 research pipeline")
    parser.add_argument("--data-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--skip-walk-forward", action="store_true",
                        help="Skip walk-forward (faster, for debugging)")
    opts = parser.parse_args(args)

    run_id = opts.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / f"{run_id}_L2"
    reports_dir = run_dir / "reports"
    run_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    params = L2Params()
    backtest_params = BacktestParams()

    # ── Step 1: Parameter snapshot ─────────────────────────────────────────
    logger.info("Writing parameter snapshot...")
    params_json = freeze_all()
    (run_dir / "params.json").write_text(params_json)
    logger.info("params.json written. Parameters are now frozen for this run.")

    # ── Step 2: Load data ───────────────────────────────────────────────────
    logger.info("Loading data...")
    btc_4h_path = opts.data_dir / "BTCUSDT_4h.parquet"
    btc_1d_path = opts.data_dir / "BTCUSDT_1d.parquet"

    if not btc_4h_path.exists() or not btc_1d_path.exists():
        logger.error(
            f"Data files not found in {opts.data_dir}. "
            f"Run `python -m research.data.fetch` first."
        )
        sys.exit(1)

    df_4h_raw = pd.read_parquet(btc_4h_path)
    df_1d_raw = pd.read_parquet(btc_1d_path)

    # ── Step 3: Validate ────────────────────────────────────────────────────
    logger.info("Validating 4H data...")
    validated_4h = validate_ohlcv(df_4h_raw, symbol="BTC/USDT", timeframe="4h")
    logger.info("Validating 1D data...")
    validated_1d = validate_ohlcv(df_1d_raw, symbol="BTC/USDT", timeframe="1d")
    df_4h = validated_4h.df
    df_1d = validated_1d.df

    logger.info(f"4H bars: {len(df_4h)}, 1D bars: {len(df_1d)}")

    # ── Step 4: Compute indicators ──────────────────────────────────────────
    logger.info("Computing indicators...")

    # 4H indicators
    ema21_4h = compute_ema(df_4h["close"], period=params.ema_period)
    atr14_4h = compute_atr(df_4h["high"], df_4h["low"], df_4h["close"], period=params.atr_period)
    vol_sma20_4h = compute_volume_sma(df_4h["volume"], period=params.volume_sma_period)

    # Daily indicators
    sma200_1d = compute_sma(df_1d["close"], period=params.macro_sma_period)
    regime_labels_1d = compute_regime_labels(df_1d["close"], df_1d["high"], df_1d["low"])

    # Align daily → 4H (D+1 rule)
    ts_4h = df_4h["timestamp"]
    daily_sma200_aligned = align_daily_to_4h(
        pd.Series(sma200_1d.values, index=df_1d["timestamp"]),
        ts_4h
    )
    btc_daily_close_aligned = align_daily_to_4h(
        pd.Series(df_1d["close"].values, index=df_1d["timestamp"]),
        ts_4h
    )
    regime_aligned = align_regime_labels(
        pd.Series(regime_labels_1d.values, index=df_1d["timestamp"]),
        ts_4h
    )

    indicators = {
        "ema21": ema21_4h,
        "atr14": atr14_4h,
        "vol_sma20": vol_sma20_4h,
        "daily_sma200": daily_sma200_aligned,
        "btc_daily_close": btc_daily_close_aligned,
        "regime": regime_aligned,
    }

    # ── Step 5: Run all L2 modes ────────────────────────────────────────────
    logger.info("Running L2 component decomposition (5 modes)...")
    mode_results: dict[str, BacktestResult] = {}

    for mode in L2SignalMode:
        logger.info(f"  Running mode: {mode.value}")
        result = run_l2_backtest(
            price_df=df_4h,
            indicators=indicators,
            mode=mode,
            params=params,
            backtest_params=backtest_params,
            run_id=run_id,
        )
        mode_results[mode.value] = result
        logger.info(f"    Trades: {result.summary.get('n_trades',0)}, PF: {result.summary.get('profit_factor', float('nan')):.3f}")

        # Save trade log
        if not result.trade_log.empty:
            result.trade_log.to_csv(run_dir / f"trades_l2_{mode.value.lower()}.csv", index=False)
        pd.DataFrame(result.signal_log).to_csv(run_dir / f"signals_l2_{mode.value.lower()}.csv", index=False)

    mvs_result = mode_results["MVS_FULL"]

    # ── Step 6: Generate diagnostic reports ────────────────────────────────
    logger.info("Generating diagnostic reports...")

    # Component attribution
    generate_attribution_report(mode_results, reports_dir)
    logger.info("  attribution_l2.txt written")

    # Regime contribution
    generate_regime_report(mvs_result, "L2_MVS_FULL", reports_dir)
    logger.info("  regime_contribution_l2_mvs_full.txt written")

    # Period isolation + buy-and-hold
    generate_period_report(
        mvs_result, df_4h, "L2_MVS_FULL", reports_dir, is_l2=True
    )
    logger.info("  period_isolation_l2.txt written")

    # Outlier sensitivity
    generate_outlier_report(mvs_result, "L2_MVS_FULL", reports_dir)
    logger.info("  outlier_sensitivity_l2_mvs_full.txt written")

    # Walk-forward + slippage
    if not opts.skip_walk_forward:
        logger.info("  Running walk-forward validation (this may take a while)...")
        generate_walk_forward_report(
            price_df=df_4h,
            indicators=indicators,
            strategy="L2",
            params=params,
            backtest_params=backtest_params,
            run_id=run_id,
            output_dir=reports_dir,
        )
        logger.info("  walk_forward_l2.txt + slippage_sensitivity_l2.txt written")
    else:
        logger.info("  Walk-forward skipped (--skip-walk-forward)")

    # ── Step 7: Research stop criteria ─────────────────────────────────────
    logger.info("Evaluating research stop criteria...")
    verdict, stop_report = _evaluate_research_stops(mvs_result, params)
    (reports_dir / "research_stop_evaluation.txt").write_text(stop_report)

    # ── Step 8: Print verdict ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"L2 RESEARCH VERDICT: {verdict}")
    print("=" * 60)
    s = mvs_result.summary
    print(f"  Total trades:     {s.get('n_trades', 0)}")
    print(f"  Profit factor:    {s.get('profit_factor', float('nan')):.3f}")
    print(f"  Win rate:         {s.get('win_rate', float('nan'))*100:.1f}%")
    print(f"  Expectancy (R):   {s.get('expectancy_R', float('nan')):.3f}R")
    print(f"  Max drawdown (R): {s.get('max_drawdown_R', float('nan')):.2f}R")
    print(f"\n  Reports written to: {reports_dir}")
    print(f"  Run ID: {run_id}")

    if verdict == "REJECT":
        logger.warning("VERDICT: REJECT — L2 does not show genuine edge. Do not proceed to execution.")
        return 1
    elif verdict == "INCONCLUSIVE":
        logger.warning("VERDICT: INCONCLUSIVE — Results neither confirm nor reject the hypothesis.")
        return 2
    else:
        logger.info("VERDICT: PROMISING — L2 shows genuine edge. Proceed to cross-validation.")
        return 0


def _evaluate_research_stops(result: BacktestResult, params: L2Params) -> tuple:
    """
    Apply research stop criteria per Phase 2 Section 4 thresholds.

    Returns (verdict, report_text).
    Verdict: 'PROMISING', 'INCONCLUSIVE', or 'REJECT'
    """
    s = result.summary
    n = s.get("n_trades", 0)
    pf = s.get("profit_factor", float("nan"))
    win_rate = s.get("win_rate", float("nan"))
    max_dd = s.get("max_drawdown_R", float("nan"))

    lines = []
    lines.append("RESEARCH STOP CRITERIA EVALUATION — L2")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Thresholds defined in Phase 2 before any backtest was run.")
    lines.append("")

    def check(condition: bool, label: str, value: str, threshold: str, impact: str) -> bool:
        status = "PASS" if condition else "FAIL"
        lines.append(f"  [{status}] {label}")
        lines.append(f"         Value: {value} | Threshold: {threshold}")
        lines.append(f"         Impact: {impact}")
        lines.append("")
        return condition

    # REJECT criteria
    reject_flags = []

    reject_flags.append(not check(
        n >= 30,
        "Minimum sample size", f"N={n}", "N ≥ 30",
        "REJECT if N < 30 — statistically meaningless"
    ))
    reject_flags.append(not check(
        not np.isnan(pf) and pf >= 1.05,
        "Profit factor floor", f"PF={pf:.3f}" if not np.isnan(pf) else "n/a", "PF ≥ 1.05",
        "REJECT if PF < 1.05 — no measurable edge"
    ))
    reject_flags.append(not check(
        not np.isnan(win_rate) and win_rate >= 0.40,
        "Win rate floor", f"WR={win_rate*100:.1f}%" if not np.isnan(win_rate) else "n/a", "WR ≥ 40%",
        "REJECT if win rate < 40% — excessive losers"
    ))
    reject_flags.append(not check(
        not np.isnan(max_dd) and max_dd <= 30,
        "Max drawdown ceiling", f"DD={max_dd:.1f}R" if not np.isnan(max_dd) else "n/a", "DD ≤ 30R",
        "REJECT if max drawdown > 30R — unacceptable risk"
    ))

    # PROMISING criteria (all must pass)
    promising_flags = []

    promising_flags.append(check(
        n >= 50,
        "Minimum trades for PROMISING", f"N={n}", "N ≥ 50",
        "PROMISING requires ≥50 trades"
    ))
    promising_flags.append(check(
        not np.isnan(pf) and pf >= 1.30,
        "Profit factor PROMISING", f"PF={pf:.3f}" if not np.isnan(pf) else "n/a", "PF ≥ 1.30",
        "PROMISING requires PF ≥ 1.30"
    ))
    promising_flags.append(check(
        not np.isnan(win_rate) and win_rate >= 0.48,
        "Win rate PROMISING", f"WR={win_rate*100:.1f}%" if not np.isnan(win_rate) else "n/a", "WR ≥ 48%",
        "PROMISING requires win rate ≥ 48%"
    ))
    promising_flags.append(check(
        not np.isnan(max_dd) and max_dd <= 20,
        "Max drawdown PROMISING", f"DD={max_dd:.1f}R" if not np.isnan(max_dd) else "n/a", "DD ≤ 20R",
        "PROMISING requires max drawdown ≤ 20R"
    ))

    lines.append("─" * 60)
    if any(reject_flags):
        verdict = "REJECT"
        lines.append("VERDICT: REJECT")
        lines.append("  One or more hard reject criteria failed.")
        lines.append("  Do not proceed. The core hypothesis has no edge.")
    elif all(promising_flags):
        verdict = "PROMISING"
        lines.append("VERDICT: PROMISING")
        lines.append("  All promising criteria met (pending walk-forward validation).")
        lines.append("  Proceed to cross-asset validation.")
    else:
        verdict = "INCONCLUSIVE"
        lines.append("VERDICT: INCONCLUSIVE")
        lines.append("  Reject criteria passed but PROMISING criteria not fully met.")
        lines.append("  Results do not clearly confirm or reject the hypothesis.")

    return verdict, "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
