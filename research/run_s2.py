"""
S2 Research Pipeline — Entry Point

Runs the complete S2 Support Breakdown Short research pipeline:
  1. Load and validate data
  2. Compute indicators
  3. Run S2 with Variant A and Variant B detectors
  4. Generate all diagnostic reports
  5. Generate detector comparison report
  6. Apply research stop criteria
  7. Print verdict

Usage:
    python research/run_s2.py
    python research/run_s2.py --data-dir research/data/raw --run-id my_run
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

from research.config.params import (
    S2Params, BacktestParams, DetectorAParams, DetectorBParams,
    freeze_all,
)
from research.data.validate import validate_ohlcv
from research.data.align import align_daily_to_4h, align_regime_labels
from research.indicators.trend import compute_sma
from research.indicators.volatility import compute_atr
from research.indicators.volume import compute_volume_sma
from research.indicators.regime import compute_regime_labels
from research.engine.backtest import run_s2_backtest, BacktestResult
from research.detectors.support import compute_detector_overlap
from research.diagnostics.regimes import generate_regime_report
from research.diagnostics.periods import generate_period_report
from research.diagnostics.outliers import generate_outlier_report
from research.diagnostics.walk_forward import generate_walk_forward_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).parent / "runs"
RAW_DIR = Path(__file__).parent / "data" / "raw"


def main(args=None):
    parser = argparse.ArgumentParser(description="Run S2 research pipeline")
    parser.add_argument("--data-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--skip-walk-forward", action="store_true")
    opts = parser.parse_args(args)

    run_id = opts.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / f"{run_id}_S2"
    reports_dir = run_dir / "reports"
    run_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    params = S2Params()
    backtest_params = BacktestParams()
    detector_a_params = DetectorAParams()
    detector_b_params = DetectorBParams()

    # ── Parameter snapshot ──────────────────────────────────────────────────
    (run_dir / "params.json").write_text(freeze_all())
    logger.info("params.json written.")

    # ── Load data ───────────────────────────────────────────────────────────
    btc_4h_path = opts.data_dir / "BTCUSDT_4h.parquet"
    btc_1d_path = opts.data_dir / "BTCUSDT_1d.parquet"

    if not btc_4h_path.exists() or not btc_1d_path.exists():
        logger.error(f"Data files not found in {opts.data_dir}. Run `python -m research.data.fetch` first.")
        sys.exit(1)

    df_4h = validate_ohlcv(pd.read_parquet(btc_4h_path), "BTC/USDT", "4h").df
    df_1d = validate_ohlcv(pd.read_parquet(btc_1d_path), "BTC/USDT", "1d").df

    logger.info(f"4H bars: {len(df_4h)}, 1D bars: {len(df_1d)}")

    # ── Compute indicators ──────────────────────────────────────────────────
    atr14_4h = compute_atr(df_4h["high"], df_4h["low"], df_4h["close"], period=params.atr_period)
    vol_sma20_4h = compute_volume_sma(df_4h["volume"], period=20)

    regime_labels_1d = compute_regime_labels(df_1d["close"], df_1d["high"], df_1d["low"])
    regime_aligned = align_regime_labels(
        pd.Series(regime_labels_1d.values, index=df_1d["timestamp"]),
        df_4h["timestamp"]
    )

    indicators = {
        "atr14": atr14_4h,
        "vol_sma20": vol_sma20_4h,
        "regime": regime_aligned,
    }

    # ── Run S2 Variant A ────────────────────────────────────────────────────
    logger.info("Running S2 — Variant A (price clustering)...")
    result_a = run_s2_backtest(
        price_df=df_4h,
        indicators=indicators,
        params=params,
        backtest_params=backtest_params,
        detector_params=detector_a_params,
        detector_variant="A",
        run_id=run_id,
    )
    logger.info(f"  Trades: {result_a.summary.get('n_trades',0)}, PF: {result_a.summary.get('profit_factor', float('nan')):.3f}")

    if not result_a.trade_log.empty:
        result_a.trade_log.to_csv(run_dir / "trades_s2a.csv", index=False)
    pd.DataFrame(result_a.signal_log).to_csv(run_dir / "signals_s2a.csv", index=False)

    # ── Run S2 Variant B ────────────────────────────────────────────────────
    logger.info("Running S2 — Variant B (pivot lows)...")
    result_b = run_s2_backtest(
        price_df=df_4h,
        indicators=indicators,
        params=params,
        backtest_params=backtest_params,
        detector_params=detector_b_params,
        detector_variant="B",
        run_id=run_id,
    )
    logger.info(f"  Trades: {result_b.summary.get('n_trades',0)}, PF: {result_b.summary.get('profit_factor', float('nan')):.3f}")

    if not result_b.trade_log.empty:
        result_b.trade_log.to_csv(run_dir / "trades_s2b.csv", index=False)
    pd.DataFrame(result_b.signal_log).to_csv(run_dir / "signals_s2b.csv", index=False)

    # ── Diagnostic reports ──────────────────────────────────────────────────
    logger.info("Generating diagnostic reports...")

    generate_regime_report(result_a, "S2_VARIANT_A", reports_dir)
    generate_regime_report(result_b, "S2_VARIANT_B", reports_dir)
    generate_period_report(result_a, df_4h, "S2_VARIANT_A", reports_dir, is_l2=False)
    generate_period_report(result_b, df_4h, "S2_VARIANT_B", reports_dir, is_l2=False)
    generate_outlier_report(result_a, "S2_VARIANT_A", reports_dir)
    generate_outlier_report(result_b, "S2_VARIANT_B", reports_dir)

    if not opts.skip_walk_forward:
        logger.info("  Running walk-forward for Variant A...")
        generate_walk_forward_report(
            df_4h, indicators, "S2", params, backtest_params, run_id, reports_dir,
            detector_params=detector_a_params, detector_variant="A",
        )

    # ── Detector comparison report ──────────────────────────────────────────
    _write_detector_comparison(result_a, result_b, reports_dir)
    logger.info("  detector_comparison_s2.txt written")

    # ── Verdict ─────────────────────────────────────────────────────────────
    verdict_a, stop_a = _evaluate_research_stops(result_a, "Variant A")
    verdict_b, stop_b = _evaluate_research_stops(result_b, "Variant B")
    (reports_dir / "research_stop_evaluation.txt").write_text(stop_a + "\n\n" + stop_b)

    # Use the conservative result (lower PF)
    pf_a = result_a.summary.get("profit_factor", 0.0) or 0.0
    pf_b = result_b.summary.get("profit_factor", 0.0) or 0.0
    conservative_verdict = verdict_a if pf_a <= pf_b else verdict_b

    print("\n" + "=" * 60)
    print(f"S2 RESEARCH VERDICT: {conservative_verdict}")
    print(f"  (Variant A: {verdict_a}, Variant B: {verdict_b})")
    print("=" * 60)
    _print_summary("Variant A", result_a)
    _print_summary("Variant B", result_b)
    print(f"\n  Reports written to: {reports_dir}")

    return 0 if conservative_verdict == "PROMISING" else 1


def _write_detector_comparison(result_a: BacktestResult, result_b: BacktestResult, output_dir: Path) -> None:
    lines = []
    lines.append("DETECTOR COMPARISON REPORT — S2")
    lines.append("=" * 60)
    lines.append("")

    # Signal overlap
    bars_a = [s["bar_index"] for s in result_a.signal_log if s.get("signal_fired")]
    bars_b = [s["bar_index"] for s in result_b.signal_log if s.get("signal_fired")]
    overlap = compute_detector_overlap(bars_a, bars_b)

    lines.append("1. SIGNAL SET OVERLAP ANALYSIS")
    lines.append("─" * 40)
    lines.append(f"  Total signals Variant A: {len(bars_a)}")
    lines.append(f"  Total signals Variant B: {len(bars_b)}")
    lines.append(f"  Overlap (Jaccard):       {overlap:.3f}" if not (overlap != overlap) else "  Overlap: n/a")

    if not (overlap != overlap):
        if overlap < 0.50:
            lines.append("  *** WARNING: Overlap < 50% — detectors find fundamentally different signals. ***")
        elif overlap > 0.70:
            lines.append("  OK: Overlap > 70% — detectors largely equivalent.")

    lines.append("")
    lines.append("2. PERFORMANCE COMPARISON")
    lines.append("─" * 40)
    for name, result in [("Variant A", result_a), ("Variant B", result_b)]:
        s = result.summary
        pf = s.get("profit_factor", float("nan"))
        wr = s.get("win_rate", float("nan"))
        exp_r = s.get("expectancy_R", float("nan"))
        n = s.get("n_trades", 0)
        lines.append(f"  {name}: N={n}, PF={pf:.3f}, WR={wr*100:.1f}%, E(R)={exp_r:.3f}R"
                     if not any(np.isnan(v) for v in [pf, wr, exp_r]) else f"  {name}: N={n}, insufficient data")

    lines.append("")
    lines.append("4. DETECTOR STABILITY ASSESSMENT")
    lines.append("─" * 40)
    pf_a = result_a.summary.get("profit_factor", float("nan"))
    pf_b = result_b.summary.get("profit_factor", float("nan"))
    if not (np.isnan(pf_a) or np.isnan(pf_b)):
        diff = abs(pf_a - pf_b)
        lines.append(f"  |PF_A - PF_B| = {diff:.3f}")
        if diff > 0.30:
            lines.append("  *** DETECTOR-DEPENDENT RESULT: Edge determined by detection algorithm, not hypothesis. ***")
        elif diff > 0.15:
            lines.append("  MODERATELY DETECTOR-DEPENDENT: Use conservative (lower PF) result.")
        else:
            lines.append("  DETECTOR-STABLE: Consistent behavior across detection methods.")

    (output_dir / "detector_comparison_s2.txt").write_text("\n".join(lines))


def _evaluate_research_stops(result: BacktestResult, variant_name: str) -> tuple:
    s = result.summary
    n = s.get("n_trades", 0)
    pf = s.get("profit_factor", float("nan"))
    wr = s.get("win_rate", float("nan"))
    max_dd = s.get("max_drawdown_R", float("nan"))

    lines = [f"RESEARCH STOP CRITERIA — S2 {variant_name}", "=" * 50, ""]

    reject = any([
        n < 30,
        np.isnan(pf) or pf < 1.05,
        np.isnan(wr) or wr < 0.40,
        np.isnan(max_dd) or max_dd > 30,
    ])

    promising = all([
        n >= 50,
        not np.isnan(pf) and pf >= 1.30,
        not np.isnan(wr) and wr >= 0.48,
        not np.isnan(max_dd) and max_dd <= 20,
    ])

    if reject:
        verdict = "REJECT"
    elif promising:
        verdict = "PROMISING"
    else:
        verdict = "INCONCLUSIVE"

    lines.append(f"N={n}, PF={pf:.3f if not np.isnan(pf) else 'n/a'}, WR={wr*100:.1f if not np.isnan(wr) else 'n/a'}%, DD={max_dd:.1f if not np.isnan(max_dd) else 'n/a'}R")
    lines.append(f"VERDICT: {verdict}")

    return verdict, "\n".join(lines)


def _print_summary(name: str, result: BacktestResult) -> None:
    s = result.summary
    pf = s.get("profit_factor", float("nan"))
    wr = s.get("win_rate", float("nan"))
    n = s.get("n_trades", 0)
    pf_str = f"{pf:.3f}" if not np.isnan(pf) else "n/a"
    wr_str = f"{wr*100:.1f}%" if not np.isnan(wr) else "n/a"
    print(f"  {name}: trades={n}, PF={pf_str}, WR={wr_str}")


if __name__ == "__main__":
    sys.exit(main())
