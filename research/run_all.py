"""
Full Research Pipeline — Entry Point

Runs L2 and S2 pipelines in sequence, applies research stop criteria,
and if both pass, generates the cross-strategy portfolio correlation report.

Usage:
    python research/run_all.py
    python research/run_all.py --run-id 20240115_143022 --skip-walk-forward
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
    L2Params, S2Params, BacktestParams, DetectorAParams, DetectorBParams,
    freeze_all,
)
from research.data.validate import validate_ohlcv
from research.data.align import align_daily_to_4h, align_regime_labels
from research.indicators.trend import compute_ema, compute_sma
from research.indicators.volatility import compute_atr
from research.indicators.volume import compute_volume_sma
from research.indicators.regime import compute_regime_labels
from research.engine.backtest import run_l2_backtest, run_s2_backtest
from research.strategies.l2_mvs import L2SignalMode
from research.diagnostics.attribution import generate_attribution_report
from research.diagnostics.regimes import generate_regime_report
from research.diagnostics.periods import generate_period_report
from research.diagnostics.outliers import generate_outlier_report
from research.diagnostics.walk_forward import generate_walk_forward_report
from research.diagnostics.portfolio import generate_portfolio_report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).parent / "runs"
RAW_DIR = Path(__file__).parent / "data" / "raw"


def main(args=None):
    parser = argparse.ArgumentParser(description="Run full research pipeline (L2 + S2)")
    parser.add_argument("--data-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--skip-walk-forward", action="store_true")
    opts = parser.parse_args(args)

    run_id = opts.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    reports_dir = run_dir / "reports"
    run_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Params ──────────────────────────────────────────────────────────────
    l2_params = L2Params()
    s2_params = S2Params()
    backtest_params = BacktestParams()
    det_a = DetectorAParams()
    det_b = DetectorBParams()

    # Freeze ALL params before any backtest executes
    (run_dir / "params.json").write_text(freeze_all())
    logger.info(f"Parameters frozen. Run ID: {run_id}")

    # ── Load & validate data ─────────────────────────────────────────────────
    btc_4h_path = opts.data_dir / "BTCUSDT_4h.parquet"
    btc_1d_path = opts.data_dir / "BTCUSDT_1d.parquet"

    if not btc_4h_path.exists() or not btc_1d_path.exists():
        logger.error(f"Data files not found in {opts.data_dir}. Run `python -m research.data.fetch` first.")
        sys.exit(1)

    df_4h = validate_ohlcv(pd.read_parquet(btc_4h_path), "BTC/USDT", "4h").df
    df_1d = validate_ohlcv(pd.read_parquet(btc_1d_path), "BTC/USDT", "1d").df
    logger.info(f"Data loaded: {len(df_4h)} 4H bars, {len(df_1d)} 1D bars")

    # ── Compute shared indicators ────────────────────────────────────────────
    ema21_4h = compute_ema(df_4h["close"], period=l2_params.ema_period)
    atr14_4h = compute_atr(df_4h["high"], df_4h["low"], df_4h["close"], period=l2_params.atr_period)
    vol_sma20_4h = compute_volume_sma(df_4h["volume"], period=20)
    sma200_1d = compute_sma(df_1d["close"], period=l2_params.macro_sma_period)
    regime_labels_1d = compute_regime_labels(df_1d["close"], df_1d["high"], df_1d["low"])

    regime_aligned = align_regime_labels(
        pd.Series(regime_labels_1d.values, index=df_1d["timestamp"]),
        df_4h["timestamp"]
    )
    daily_sma200_aligned = align_daily_to_4h(
        pd.Series(sma200_1d.values, index=df_1d["timestamp"]),
        df_4h["timestamp"]
    )
    btc_daily_close_aligned = align_daily_to_4h(
        pd.Series(df_1d["close"].values, index=df_1d["timestamp"]),
        df_4h["timestamp"]
    )

    l2_indicators = {
        "ema21": ema21_4h,
        "atr14": atr14_4h,
        "vol_sma20": vol_sma20_4h,
        "daily_sma200": daily_sma200_aligned,
        "btc_daily_close": btc_daily_close_aligned,
        "regime": regime_aligned,
    }
    s2_indicators = {
        "atr14": atr14_4h,
        "vol_sma20": vol_sma20_4h,
        "regime": regime_aligned,
    }

    # ════════════════════════════════════════════════════════════════════════
    # L2 PIPELINE
    # ════════════════════════════════════════════════════════════════════════
    logger.info("=== L2 PIPELINE ===")
    l2_run_dir = run_dir / "L2"
    l2_reports = l2_run_dir / "reports"
    l2_run_dir.mkdir(parents=True, exist_ok=True)
    l2_reports.mkdir(parents=True, exist_ok=True)

    # Run all 5 modes
    l2_mode_results = {}
    for mode in L2SignalMode:
        logger.info(f"  L2 mode: {mode.value}")
        result = run_l2_backtest(
            df_4h, l2_indicators, mode, l2_params, backtest_params, run_id
        )
        l2_mode_results[mode.value] = result
        if not result.trade_log.empty:
            result.trade_log.to_csv(l2_run_dir / f"trades_l2_{mode.value.lower()}.csv", index=False)

    l2_mvs = l2_mode_results["MVS_FULL"]

    generate_attribution_report(l2_mode_results, l2_reports)
    generate_regime_report(l2_mvs, "L2_MVS_FULL", l2_reports)
    generate_period_report(l2_mvs, df_4h, "L2_MVS_FULL", l2_reports, is_l2=True)
    generate_outlier_report(l2_mvs, "L2_MVS_FULL", l2_reports)

    if not opts.skip_walk_forward:
        logger.info("  L2 walk-forward...")
        generate_walk_forward_report(
            df_4h, l2_indicators, "L2", l2_params, backtest_params,
            run_id, l2_reports
        )

    l2_verdict = _evaluate_verdict(l2_mvs)
    (l2_reports / "research_stop_evaluation.txt").write_text(l2_verdict[1])
    logger.info(f"L2 verdict: {l2_verdict[0]}")

    # ════════════════════════════════════════════════════════════════════════
    # S2 PIPELINE
    # ════════════════════════════════════════════════════════════════════════
    logger.info("=== S2 PIPELINE ===")
    s2_run_dir = run_dir / "S2"
    s2_reports = s2_run_dir / "reports"
    s2_run_dir.mkdir(parents=True, exist_ok=True)
    s2_reports.mkdir(parents=True, exist_ok=True)

    logger.info("  S2 Variant A...")
    result_s2a = run_s2_backtest(
        df_4h, s2_indicators, s2_params, backtest_params, det_a, "A", run_id
    )
    if not result_s2a.trade_log.empty:
        result_s2a.trade_log.to_csv(s2_run_dir / "trades_s2a.csv", index=False)

    logger.info("  S2 Variant B...")
    result_s2b = run_s2_backtest(
        df_4h, s2_indicators, s2_params, backtest_params, det_b, "B", run_id
    )
    if not result_s2b.trade_log.empty:
        result_s2b.trade_log.to_csv(s2_run_dir / "trades_s2b.csv", index=False)

    generate_regime_report(result_s2a, "S2_VARIANT_A", s2_reports)
    generate_regime_report(result_s2b, "S2_VARIANT_B", s2_reports)
    generate_period_report(result_s2a, df_4h, "S2_VARIANT_A", s2_reports)
    generate_outlier_report(result_s2a, "S2_VARIANT_A", s2_reports)

    if not opts.skip_walk_forward:
        logger.info("  S2 walk-forward...")
        generate_walk_forward_report(
            df_4h, s2_indicators, "S2", s2_params, backtest_params, run_id, s2_reports,
            detector_params=det_a, detector_variant="A"
        )

    # Conservative S2 verdict: use lower PF variant
    pf_a = result_s2a.summary.get("profit_factor", 0) or 0
    pf_b = result_s2b.summary.get("profit_factor", 0) or 0
    s2_conservative = result_s2a if pf_a <= pf_b else result_s2b
    s2_verdict = _evaluate_verdict(s2_conservative)
    (s2_reports / "research_stop_evaluation.txt").write_text(s2_verdict[1])
    logger.info(f"S2 verdict: {s2_verdict[0]}")

    # ════════════════════════════════════════════════════════════════════════
    # PORTFOLIO CORRELATION (if both pass)
    # ════════════════════════════════════════════════════════════════════════
    if l2_verdict[0] == "PROMISING" and s2_verdict[0] == "PROMISING":
        logger.info("Both strategies PROMISING — generating portfolio correlation report...")
        generate_portfolio_report(l2_mvs, result_s2a, reports_dir)
    else:
        logger.info("Not all strategies PROMISING — skipping portfolio report.")

    # ── Final summary ────────────────────────────────────────────────────────
    _print_final_summary(run_id, l2_verdict[0], l2_mvs, s2_verdict[0], s2_conservative)

    return 0 if l2_verdict[0] == "PROMISING" and s2_verdict[0] == "PROMISING" else 1


def _evaluate_verdict(result) -> tuple:
    s = result.summary
    n = s.get("n_trades", 0)
    pf = s.get("profit_factor", float("nan"))
    wr = s.get("win_rate", float("nan"))
    max_dd = s.get("max_drawdown_R", float("nan"))

    lines = ["RESEARCH VERDICT", "=" * 40, f"N={n}", f"PF={pf:.3f}" if not np.isnan(pf) else "PF=n/a"]

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

    lines.append(f"VERDICT: {verdict}")
    return verdict, "\n".join(lines)


def _print_final_summary(run_id, l2_verdict, l2_result, s2_verdict, s2_result):
    print("\n" + "=" * 60)
    print("FULL RESEARCH PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Run ID: {run_id}")
    print(f"  L2 verdict: {l2_verdict}")
    _print_stats("  L2", l2_result)
    print(f"  S2 verdict: {s2_verdict}")
    _print_stats("  S2", s2_result)
    print("=" * 60)

    if l2_verdict == "PROMISING" and s2_verdict == "PROMISING":
        print("\n>>> BOTH STRATEGIES PROMISING — Proceed to cross-asset validation (Tier 2) <<<")
    elif l2_verdict == "PROMISING":
        print("\n>>> L2 PROMISING, S2 not. Consider L2-only deployment after cross-validation. <<<")
    elif s2_verdict == "PROMISING":
        print("\n>>> S2 PROMISING, L2 not. Consider S2-only after cross-validation. <<<")
    else:
        print("\n>>> NO STRATEGY PROMISING — Do not proceed to live trading. <<<")


def _print_stats(prefix, result):
    s = result.summary
    pf = s.get("profit_factor", float("nan"))
    wr = s.get("win_rate", float("nan"))
    n = s.get("n_trades", 0)
    pf_str = f"{pf:.3f}" if not np.isnan(pf) else "n/a"
    wr_str = f"{wr*100:.1f}%" if not np.isnan(wr) else "n/a"
    print(f"{prefix}: trades={n}, PF={pf_str}, WR={wr_str}")


if __name__ == "__main__":
    sys.exit(main())
