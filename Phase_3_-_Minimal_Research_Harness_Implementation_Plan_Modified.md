Phase 3 — Minimal Research Harness Implementation Plan

1. Research Harness Design Principles
These principles govern every decision in this plan. If a proposed file, function, or feature cannot be justified by at least one of these principles, it is not included.
Principle 1 — Falsification over feature completeness.
Every component exists to make it easier to reject the hypothesis, not easier to claim it works. If a component makes the results look better without making the test more rigorous, it does not belong here.
Principle 2 — No hidden state.
Every decision the backtester makes must be traceable to a logged input. If a trade fires, the exact values of every condition that caused it must be recoverable from the trade log. If a signal is rejected, the reason must be recorded.
Principle 3 — Parameter immutability after run start.
Parameters are written to disk before the backtest executes. The backtest reads them from disk. This creates an audit trail and prevents mid-run adjustment. If parameters need to change, a new run is created with a new run ID.
Principle 4 — Minimal surface area.
The harness implements exactly what is needed to test the MVS of L2 and S2, generate all diagnostic outputs defined in Phase 2.5, and apply the research stop criteria. Nothing else. Every additional line of code is a liability — it can hide bugs, introduce complexity, and create the illusion of progress.
Principle 5 — Strict separation of concerns.
Data loading does not compute indicators. Indicator computation does not evaluate signals. Signal evaluation does not manage trades. Trade management does not produce reports. Each layer receives fully formed inputs and produces fully formed outputs. No layer reaches into another layer's responsibilities.
Principle 6 — Test gates are non-negotiable.
No step proceeds until its test gate passes. This is enforced by the implementation order, not by convention. A broken test means a bug exists. The correct response is to fix the bug, not to skip the test.
Principle 7 — Explicit is better than inferred.
Every alignment, every lookahead boundary, every fee calculation is written out explicitly with a comment explaining why it is correct. No behavior is left to pandas defaults or library conventions without verification.
Principle 8 — The code is a record of the research, not just a tool.
Function and variable names must reflect their research meaning. ema_touch_bar is better than signal. macro_filter_passed is better than condition_1. Someone reading the code six months later must be able to reconstruct what hypothesis is being tested.

2. Minimal File Structure
research/
│
├── config/
│   └── params.py                  # All frozen parameters as dataclasses
│
├── data/
│   ├── fetch.py                   # OHLCV fetcher (ccxt, saves to parquet)
│   ├── validate.py                # Data integrity checks (all CHECK-N rules)
│   ├── align.py                   # Daily-4H alignment, regime forward-fill
│   └── raw/                       # Parquet files (gitignored)
│       ├── btc_4h.parquet
│       └── btc_1d.parquet
│
├── indicators/
│   ├── trend.py                   # EMA, SMA, slope
│   ├── volatility.py              # ATR
│   ├── volume.py                  # Volume SMA, relative volume
│   └── regime.py                  # Regime classifier (returns daily labels)
│
├── detectors/
│   └── support.py                 # Variant A and Variant B, shared interface
│
├── strategies/
│   ├── l2_mvs.py                  # L2 bar-by-bar logic, all 5 modes
│   └── s2_mvs.py                  # S2 bar-by-bar logic, both detectors
│
├── engine/
│   └── backtest.py                # Bar-by-bar loop, trade management, logging
│
├── accounting/
│   └── trades.py                  # R-multiple calc, fee model, trade log schema
│
├── diagnostics/
│   ├── attribution.py             # Component attribution report (L2)
│   ├── periods.py                 # Period isolation report (includes buy-and-hold correlation for L2)
│   ├── exits.py                   # Exit structure isolation report (includes Variant F for S2)
│   ├── regimes.py                 # Regime contribution report (6 regimes)
│   ├── outliers.py                # Single-trade sensitivity report
│   ├── walk_forward.py            # [FIX] Walk-forward validation: Method A (rolling) + Method B (expanding)
│   └── portfolio.py               # [FIX] Cross-strategy drawdown correlation (Phase 7)
│
├── baselines/
│   └── random_entry.py            # RANDOM_ALL_BARS and RANDOM_MACRO_MATCHED
│
├── tests/
│   ├── test_data.py               # TEST-DATA-01 through TEST-DATA-06
│   ├── test_indicators.py         # TEST-IND-01 through TEST-IND-05
│   ├── test_l2.py                 # TEST-L2-01 through TEST-L2-07c (includes 07b funding, 07c slippage)
│   ├── test_s2.py                 # TEST-S2-01 through TEST-S2-08
│   ├── test_accounting.py         # Fee, funding cost, R-multiple, log schema tests
│   └── test_detectors.py          # Detector lookahead, overlap metric tests
│
├── runs/
│   └── [run_id]/                  # Created at runtime, one per run
│       ├── params.json            # Frozen copy of all parameters
│       ├── trades_l2.csv          # Trade-by-trade log
│       ├── trades_s2a.csv         # S2 with Variant A detector
│       ├── trades_s2b.csv         # S2 with Variant B detector
│       ├── signals_l2.csv         # All evaluated bars and signal outcomes
│       ├── signals_s2.csv         # All evaluated bars, signal outcomes, level info
│       └── reports/
│           ├── attribution_l2.txt
│           ├── period_isolation_l2.txt
│           ├── buy_and_hold_correlation_l2.txt    # [FIX] Per Phase 2 Section 6
│           ├── exit_isolation_l2.txt
│           ├── exit_isolation_s2.txt               # [FIX] Includes Variant F
│           ├── regime_contribution_l2.txt
│           ├── regime_contribution_s2.txt
│           ├── outlier_sensitivity_l2.txt
│           ├── outlier_sensitivity_s2.txt
│           ├── detector_comparison_s2.txt
│           ├── period_isolation_s2.txt
│           ├── walk_forward_l2.txt                # [FIX] Method A + B results
│           ├── walk_forward_s2.txt                # [FIX] Method A + B results
│           ├── slippage_sensitivity_l2.txt        # [FIX] 0/5/10/15 bps sweep
│           ├── slippage_sensitivity_s2.txt        # [FIX] 0/5/10/15 bps sweep
│           ├── portfolio_correlation.txt           # [FIX] Phase 7 cross-strategy
│           └── research_stop_evaluation.txt
│
├── run_l2.py                      # Entry point: runs L2 research pipeline
├── run_s2.py                      # Entry point: runs S2 research pipeline
└── run_all.py                     # Runs both, generates research stop evaluation
Total files: 30 (excluding generated outputs and raw data).
This is the complete harness. No file exists outside this structure. No file inside this structure serves a purpose not defined in this document.

3. File Responsibilities
Each file has exactly one responsibility. Files that do more than one thing are a design error.
config/params.py
Responsibility: Defines and owns all frozen parameters as Python dataclasses. No parameter exists anywhere else in the codebase. Any file that needs a parameter imports it from here.
Contains:

L2Params dataclass: all L2 MVS parameters with values and justification comments
S2Params dataclass: all S2 MVS parameters with values
DetectorAParams dataclass: Variant A sub-parameters with frozen/sensitivity labels
DetectorBParams dataclass: Variant B sub-parameters with frozen/sensitivity labels
BacktestParams dataclass: fee rate, slippage_bps (default 10), funding_rate_per_settlement (default 0.0002), data range, warmup period, run ID
BaselineParams dataclass: random seed, number of random trials
A freeze() method that serializes all params to a JSON file at a given path
No logic. No computation. Only data definitions.

What it does NOT contain: Any computation, any imports from other harness modules, any conditional logic.
data/fetch.py
Responsibility: Fetches OHLCV data from Binance via ccxt and saves to Parquet. Runs once before research begins. Not called during backtests.
Contains:

fetch_ohlcv(symbol, timeframe, since, until) → saves to data/raw/
Basic retry logic for API failures
Confirmation that saved file matches requested date range

What it does NOT contain: Indicator computation, alignment, validation. Those are separate files.
data/validate.py
Responsibility: Implements all six data integrity checks (CHECK-1 through CHECK-6). Raises descriptive exceptions on failure. Returns a validated DataFrame on success.
Contains:

validate_ohlcv(df, timeframe) → ValidatedOHLCV (a typed wrapper around DataFrame)
One function per check, called sequentially
Detailed error messages that identify the exact row and value causing failure

Contract: If validate_ohlcv returns without raising, the downstream code can assume the data meets all integrity requirements. This is the only validation gate. Nothing else in the harness validates data.
data/align.py
Responsibility: Aligns daily indicator values to 4H bars using strictly point-in-time forward-fill. Implements regime label alignment.
Contains:

align_daily_to_4h(daily_series, four_h_timestamps) → aligned Series
The alignment rule is explicitly: daily value computed through day D is available at 4H bars opening on day D+1 or later. Not D. D+1.
align_regime_labels(daily_labels, four_h_timestamps) → aligned Series
Unit test verification function (not a test file — a callable that verifies alignment logic during data prep)

What it does NOT contain: The indicator or regime computations themselves. It only aligns pre-computed series.
indicators/trend.py
Responsibility: EMA and SMA computation with explicit warmup period handling.
Contains:

compute_ema(series, period) → Series with NaN for warmup bars
compute_sma(series, period) → Series with NaN for warmup bars
compute_ema_slope(ema_series, lookback_bars) → Boolean Series (True if rising)
Explicit documentation of the pandas ewm(adjust=False) convention used and why

Contract: The value at index i is computed from indices 0 through i inclusive. No future data. NaN for the first period - 1 values.
indicators/volatility.py
Responsibility: ATR computation.
Contains:

compute_atr(high, low, close, period) → Series with NaN for warmup bars
Explicit True Range computation (not relying on library magic)
Contract documentation identical to trend.py

indicators/volume.py
Responsibility: Volume SMA and relative volume ratio.
Contains:

compute_volume_sma(volume, period) → Series
compute_relative_volume(volume, sma) → Series (volume / sma)
Critical note: volume_sma.iloc[i] = mean of volume[i-period : i] — does NOT include bar i
This is the most important behavioral specification in this file and must be tested

indicators/regime.py
Responsibility: Regime classification on daily data.
Contains:

compute_regime_labels(btc_daily_df) → Series of regime strings (one per day)
The exact classify_regime function from Phase 2 with all threshold values sourced from config/params.py
ROC_20, VOL_ratio, SMA_200, SMA_50 computations, all using daily data only
A get_regime_at_bar(four_h_timestamp, aligned_regime_series) helper

What it does NOT contain: Any 4H logic. The regime is a daily concept aligned separately by align.py.
detectors/support.py
Responsibility: Implements both Variant A and Variant B support detection algorithms and the detector comparison report generator.
Contains:

class SupportLevel: dataclass with level_price, touch_count, first_touch_bar, last_touch_bar, detector_variant
detect_support_levels_variant_a(bars_slice, params) → list[SupportLevel]
detect_support_levels_variant_b(bars_slice, params) → list[SupportLevel]
compute_detector_overlap(signals_a, signals_b) → overlap metric
Both detectors receive only bars_slice — a slice of the DataFrame ending at i-1. They cannot see bar i.
The bars_slice boundary is enforced by the engine, not the detector. The detector trusts its input.

Critical design note: The detector functions are pure functions. Given the same bars_slice, they always return the same levels. No internal state. This makes them testable in isolation.
strategies/l2_mvs.py
Responsibility: Implements L2 signal generation logic for all five modes. Does NOT manage trades — only produces signals.
Contains:

L2SignalMode enum: RANDOM_ALL_BARS, RANDOM_MACRO_MATCHED, MACRO_ONLY, TOUCH_ONLY, MVS_NO_CONFIRM, MVS_FULL
L2Signal dataclass: bar_index, timestamp, mode, entry_price, stop_price, target_price, regime, signal_reason, filter_rejection_reason
evaluate_l2_signal(bar, indicators, mode, params) → L2Signal | None
Each mode is a clearly labelled branch. No mode shares logic with another mode in a way that makes the branching implicit.
The function receives a single bar's worth of data plus pre-computed indicator values. It does not access the DataFrame directly.

What it does NOT contain: Trade management, stop updates, exit logic, position tracking. The function answers only: "given this bar, should I enter, and if so, at what price?"
strategies/s2_mvs.py
Responsibility: Implements S2 signal generation logic. Consumes pre-computed support levels from the detector. Does not run the detector itself.
Contains:

S2Signal dataclass: bar_index, timestamp, entry_price, stop_price, target_price, support_level, touch_count, level_age_bars, volume_ratio, regime, detector_variant
evaluate_s2_signal(bar, indicators, active_levels, params) → S2Signal | None
Receives active_levels as a pre-computed list from the engine. Does not call the detector.
Multiple level trigger resolution logic (highest touch count, then most recent) is inside this function.

engine/backtest.py
Responsibility: Implements the bar-by-bar loop. Orchestrates all phases (A through E from Phase 2.5). Calls strategies for signals, calls accounting for trade records, records everything.
Contains:

run_backtest(price_df, indicators, strategy_fn, params, run_id) → BacktestResult
BacktestResult dataclass: trades, signal_log, equity_curve, run_metadata
The loop itself: Phase B (open trade management) always before Phase D (signal generation)
Stop/target conflict resolution: same-bar conflict → stop hit
Support level update (for S2) computed at start of each bar from bars[0:i]
The engine does not know whether it is running L2 or S2. It calls strategy_fn(bar, indicators, ...) and receives a signal or None.

What it does NOT contain: Indicator computation, detector logic, report generation, parameter definitions. It is purely the execution loop.
accounting/trades.py
Responsibility: Defines the trade record schema, fee model, and R-multiple calculation. The single source of truth for how performance is measured.
Contains:

TradeRecord dataclass (complete schema defined in Section 9 of this document)
compute_r_multiple(effective_entry, exit, stop, direction) → float
apply_fees(gross_pnl, effective_entry_price, exit_price, position_size, fee_rate) → taker_fee
compute_funding_cost(entry_timestamp, exit_timestamp, entry_price, position_size, funding_rate_per_settlement) → funding_cost
compute_total_fee(taker_fee, funding_cost) → total_fee
compute_r_in_fees(effective_entry_price, stop_price, total_fee) → fee cost expressed in R
build_trade_log(trades: list[TradeRecord]) → pd.DataFrame
compute_summary_stats(trade_log_df) → dict with all metrics from the backtest report format

What it does NOT contain: Any strategy logic, any bar-by-bar processing, any report formatting.
diagnostics/ (seven files)
Each diagnostic file implements one of the diagnostic output types from Phase 2/2.5. Each file takes a BacktestResult and the relevant parameters, produces a formatted text report, and saves it to runs/[run_id]/reports/.
No diagnostic file modifies any data. They are read-only consumers of backtest results.

attribution.py: Component attribution report (L2 only). Requires all 5 mode results to be passed in.
periods.py: Period isolation report. Works for both L2 and S2. [FIX] For L2, includes buy-and-hold correlation column and Pearson correlation per Phase 2 Section 6.
exits.py: Exit structure isolation report. Re-runs backtest with alternative exit parameters — this is the only diagnostic file that calls the engine. [FIX] For S2, includes Variant F (constant-R:R) per Phase 1 mandate.
regimes.py: Regime contribution report. [FIX] Reports on 6 regimes per Phase 2 corrected classifier.
outliers.py: Single-trade sensitivity report.
walk_forward.py: [FIX] Walk-forward validation. Implements both Method A (rolling 6-month windows, 4-month train / 2-month test) and Method B (expanding train set, 6-month non-overlapping test windows per Phase 2 Section 3). Re-runs backtest engine on train/test splits. Produces per-window train PF, test PF, and delta. Reports mean test PF, std dev, and % of windows with test PF > 1.0 for each method. Also runs slippage sensitivity sweep (0/5/10/15 bps) and funding rate sensitivity sweep (0.01/0.02/0.05% per 8H). Both methods required for PROMISING threshold per Phase 2.
portfolio.py: [FIX] Cross-strategy drawdown correlation report. Takes L2 and S2 BacktestResults, overlays equity curves, quantifies correlated drawdowns during TRANSITION regime periods. Only runs after both strategies pass individually (Phase 7 of execution sequence).

baselines/random_entry.py
Responsibility: Implements both random baseline modes. Produces a BacktestResult compatible with all diagnostic outputs.
Contains:

run_random_all_bars(price_df, indicators, params, seed, n_trials) → BacktestResult
run_random_macro_matched(price_df, indicators, params, seed, n_trials) → BacktestResult
Both modes use the same stop/target structure as L2 MVS for direct comparability
Multiple trials with different seeds; result is the median performance across trials (not best trial)
[FIX] Both baselines must apply the same slippage (10 bps) and funding rate cost model (0.02% per 8H) as L2 MVS. Without this, the baseline comparison is invalid — L2 would appear worse simply because it pays more in execution costs.

tests/ (six files)
Each test file maps directly to the unit test plan from Phase 2.5. pytest-based. Every test is self-contained and uses synthetic data constructed within the test. No test reads from data/raw/.
run_l2.py, run_s2.py, run_all.py
Responsibility: Entry points only. They orchestrate the pipeline in order, apply research stop criteria, and exit with an informative message if a stop criterion is triggered. They contain no logic of their own — they call functions from other modules in the correct sequence.

4. Resolved Strategy Definitions
4.1 L2 Confirmation Ambiguity — Resolved
The ambiguity: Phase 2.5 identified that the EMA touch and the confirmation candle can be interpreted in two ways:

Same-bar: Touch detected AND bullish close in the same 4H candle. Entry at that candle's close.
Next-bar: Touch detected in bar i. Entry at bar i+1's close, if bar i+1 closes bullish.

Resolution for MVS primary implementation: Same-bar confirmation.
Justification:
The same-bar interpretation requires fewer parameters (no "pending touch" state, no decision about how many bars to wait for confirmation), produces more trades (more testable), and is stricter about execution timing since the close price is known. It is also the more conservative formulation — it requires the EMA touch and the bullish reversal to co-occur, meaning price must have dipped to the EMA and recovered within the same 4H candle. This is a harder condition to satisfy than next-bar confirmation, which means same-bar signals are a subset of next-bar signals. If same-bar has no edge, next-bar also has no edge (or any apparent next-bar edge is contaminated by signals that would have been rejected under same-bar rules).
The next-bar confirmation is defined as a separate structural variant: L2_VARIANT_NEXTBAR
This is not a sensitivity parameter. It is a different strategy interpretation. It will be run as a separate backtest after MVS results are established. Its results will be compared directly to the MVS results. If L2_VARIANT_NEXTBAR substantially outperforms the MVS, this suggests the timing of confirmation matters and the strategy may be more sensitive to entry price than anticipated. If they perform similarly, the choice between them is immaterial.
Implementation difference:
MVS (same-bar):
  At bar i: evaluate all conditions including close > open.
  If all pass: entry at close[i].

L2_VARIANT_NEXTBAR:
  At bar i: evaluate all conditions EXCEPT close > open.
  If non-confirmation conditions pass: set pending_touch = True.
  At bar i+1: if pending_touch is True AND close[i+1] > open[i+1]:
      entry at close[i+1].
      clear pending_touch.
  If close[i+1] <= open[i+1]: clear pending_touch without entry.
  Pending touch expires after 1 bar (no multi-bar waiting period).
4.2 S2 Entry Mode — Confirmed Single Mode
As established in Phase 2: direct close-of-breakdown-bar entry only. No retest mode. No dual-entry logic. This is not a simplification for the research harness — it is the permanent design choice for MVS. The retest mode, if ever tested, is a separate strategy variant with its own backtest, not an alternative entry within S2 MVS.

5. Baseline Definitions
Baselines must be honest. Their purpose is to determine what the stop/target structure alone produces, what the macro regime filter alone produces, and whether L2's signal logic outperforms these trivial benchmarks.
BASELINE-1: RANDOM_ALL_BARS
Definition: At every bar in the dataset (after warmup), regardless of any market condition, enter a long position with the same stop and target structure as L2 MVS. Position exits when stop or target is hit.
Implementation:

No regime filter. No EMA filter. No confirmation.
Entry at every bar's close.
Stop: close - 1.5 × ATR14
Target: close + 2.0 × ATR14
Only constraint: no concurrent positions (same as MVS).

Purpose: Establishes the "null hypothesis" baseline. If L2 MVS does not materially outperform RANDOM_ALL_BARS, the 2:1 reward-to-risk structure alone is doing the work, not the entry logic.
Multi-trial handling: Since random entry at every bar is deterministic (no randomness required — it enters at every eligible bar), this baseline is deterministic. A single run suffices. The "random" label refers to the lack of selection logic, not to stochastic entry.
Expected result without any edge: With a symmetric market, a 2:1 R target and 1.5× ATR stop implies the strategy needs approximately a 43% win rate to break even (fee-adjusted). This is the mathematical floor. If RANDOM_ALL_BARS achieves a profit factor above 1.0, it is because the fixed ATR-based stop/target structure happens to be well-calibrated to the volatility of the asset — not because any entry logic works.
BASELINE-2: RANDOM_MACRO_MATCHED
Definition: Identical to RANDOM_ALL_BARS, but only enters on bars where the L2 macro filter passes (BTC close > daily SMA200). Same stop and target structure.
Purpose: Isolates the contribution of the macro filter from the EMA touch logic. If RANDOM_MACRO_MATCHED performs as well as L2 MVS FULL, the EMA touch adds no value — the strategy's edge is purely from being long during bull markets with a 2:1 R structure, not from any specific entry signal.
Implementation note: This baseline receives the same pre-computed macro filter results as L2 MVS. It does not recompute the filter. The purpose is comparability, not independence.
Multi-trial handling: Also deterministic — enters at every bar where macro filter passes. No sampling required.
Baseline Comparison Table (template to be filled post-backtest)
BASELINE COMPARISON — L2 EMA PULLBACK
═══════════════════════════════════════════════════════════════════
                      | Trades | Win%  | PF    | Expectancy | Max DD
──────────────────────────────────────────────────────────────────
RANDOM_ALL_BARS       |        |       |       |            |
RANDOM_MACRO_MATCHED  |        |       |       |            |
L2 MACRO_ONLY         |        |       |       |            |
L2 TOUCH_ONLY         |        |       |       |            |
L2 MVS_NO_CONFIRM     |        |       |       |            |
L2 MVS_FULL (primary) |        |       |       |            |
L2_VARIANT_NEXTBAR    |        |       |       |            |
──────────────────────────────────────────────────────────────────

Key comparisons:
MVS_FULL vs RANDOM_ALL_BARS:        ΔPF = [  ]
MVS_FULL vs RANDOM_MACRO_MATCHED:   ΔPF = [  ]
MVS_FULL vs MACRO_ONLY:             ΔPF = [  ]
MVS_FULL vs L2_VARIANT_NEXTBAR:     ΔPF = [  ]

6. Support Detector Parameter Freeze Plan
6.1 Variant A Parameters
ParameterValueStatusRationaletouch_tolerance0.005 (0.5%)FROZENMost critical parameter. Changes the entire set of identified levels. Any post-hoc tuning is direct overfitting.min_touch_count3FROZENThe hypothesis requires a tested level. Fewer than 3 is noise. This is a structural choice, not a tuning variable.min_bounce_atr_multiplier1.0FROZENConfirms support held after each touch. The multiplier is a conceptual floor, not a performance parameter.min_bars_between_touches3FROZENDebounce logic. Prevents adjacent candles from inflating touch count. The exact value (3 vs 4) has minimal impact compared to touch_tolerance.lookback_window60 candlesSENSITIVITY-ELIGIBLECan be tested at 40 and 80 candles as part of the sensitivity sweep. This parameter affects how "recent" the support context is. It does not define the hypothesis — it scopes its temporal window. Acceptable to compare 40/60/80 in the parameter sensitivity report.level_price_calculationmedian of touch lowsFROZENUsing median rather than mean or most recent touch. This is a structural choice that must be consistent across all runs.
Most dangerous Variant A parameter: touch_tolerance.
If this is changed from 0.5% to 0.3%, many clustered levels disappear. If changed to 0.8%, many distinct levels merge. The number of qualifying signals changes by potentially 30–50%. This parameter must never be adjusted after seeing backtest results. It is frozen before the first run.
Second most dangerous: min_touch_count.
Changing from 3 to 2 dramatically increases signal count and almost certainly includes lower-quality levels. This is a structural change to the hypothesis, not a sensitivity test. It is frozen.
6.2 Variant B Parameters
ParameterValueStatusRationalepivot_window5 (2 left, 2 right)FROZENDefines what constitutes a structural low. Standard definition. Changing this changes the entire set of pivots identified. Frozen before any run.lookahead_boundaryj <= i - 3FROZEN — CRITICALThis is not a tuning parameter. It is a correctness constraint. A pivot at bar j requires bars j+1 and j+2 to confirm. Therefore, at bar i, only pivots at j ≤ i-3 are valid. This value is derived from pivot_window, not independently chosen.proximity_pct0.008 (0.8%)FROZENDefines when two pivots are "at the same level." Wider than Variant A's touch tolerance to account for the structural nature of pivots (they may not cluster as tightly as raw lows). Must be frozen before any run.min_pivot_count3FROZENSame rationale as Variant A's min_touch_count.min_bars_between_pivots5FROZENSlightly larger than Variant A's debounce because pivots are defined by a window (rather than a single low), which means adjacent pivots are less likely.lookback_window60 candlesSENSITIVITY-ELIGIBLESame rationale as Variant A. Tested at 40 and 80 only.level_price_calculationlowest pivot in groupFROZENMost conservative choice for a short trade (lowest confirmed touch = closest to actual historical support).
Most dangerous Variant B parameter: pivot_window.
Changing from 5 to 3 (1 left, 1 right) finds many more pivots, most of which are noise. Changing to 7 finds fewer, longer-term structural pivots. The results change dramatically. Frozen.
Second most dangerous: proximity_pct.
At 0.5%, the behavior approaches Variant A's raw-low clustering. At 1.5%, many distinct pivots merge into single levels. Frozen.
Unique Variant B risk: the lookahead boundary.
The j <= i - 3 constraint is derived, not chosen. If implemented as j <= i - 2 (one bar too short), pivots will be included that are not yet confirmed — this is a lookahead bug disguised as a parameter. Unit test TEST-S2-01 exists specifically for this. If this test fails, all Variant B results are invalid.
6.3 Cross-Variant Parameters (Apply to Both)
ParameterValueStatusbreakdown_threshold_pct0.003 (0.3%)FROZENvolume_multiplier1.5FROZENstop_atr_multiplier0.5FROZENtarget_atr_multiplier2.0FROZENmax_concurrent_trades1FROZEN

7. Step-by-Step Implementation Order
Step 1 — Data Acquisition and Validation
Required inputs:

ccxt installed
Exchange API access (read-only, no key needed for historical data on Binance)
Target date range: 2020-01-01 to 2024-12-31 minimum
Two timeframes: 4H and 1D for BTC/USDT **perpetual contract** (per Phase 1 Instrument Type Declaration)

Expected outputs:

data/raw/btc_4h.parquet: validated 4H OHLCV, approximately 8,760 rows for 4 years
data/raw/btc_1d.parquet: validated daily OHLCV, approximately 1,460 rows
Console confirmation: row counts, date ranges, integrity check results

Failure modes:

API rate limiting: add sleep between requests in fetch loop
Missing candles near exchange outages: must be detected by CHECK-3, flagged, not silently skipped
Timestamp timezone issues: all timestamps must be UTC before saving. If exchange returns timezone-naive timestamps, attach UTC explicitly. Never assume.
Parquet write failure: must be caught and reported. Never partially written files.

Tests that must pass before moving on:

TEST-DATA-01 through TEST-DATA-06 all pass on the saved Parquet files
Manual spot check: verify row count, first row, last row, and 3 random rows against exchange web UI


Step 2 — Indicator Computation
Required inputs:

Validated btc_4h.parquet and btc_1d.parquet
config/params.py parameters: EMA period (21), SMA period (200), ATR period (14), volume SMA period (20), EMA slope lookback (3)

Expected outputs:

A single pre-computed indicators DataFrame for 4H data with columns:

ema_21: 4H EMA, NaN for first 20 bars
atr_14: 4H ATR, NaN for first 13 bars
vol_sma_20: Volume SMA, NaN for first 19 bars
ema_slope_positive: Boolean, True if EMA21[i] > EMA21[i-3]
rel_volume: volume / vol_sma_20


A separate indicators DataFrame for daily data:

sma_200_daily: NaN for first 199 daily bars
sma_50_daily: NaN for first 49 daily bars
atr_14_daily: NaN for first 13 daily bars
roc_20_daily: 20-day return, NaN for first 19 bars
vol_ratio_daily: ATR_14_daily / rolling_mean(ATR_14_daily, 60)



Failure modes:

NaN propagation beyond warmup period: if NaN appears at bar 200 when it should be valid, there is a computation error
EMA initialization: if using pandas ewm() with adjust=True vs adjust=False, results will differ. Must match the convention stated in the file docstring. Failure is silent — results are "wrong" but not erroring.
ATR using close-to-close vs high-low-close True Range: must use the three-term True Range definition. Using only high - low is a common error that produces different results in trending markets.

Tests that must pass before moving on:

TEST-IND-01 through TEST-IND-05
Verify EMA21 at a specific known bar against a manually computed value
Verify that vol_sma_20.iloc[i] does not include volume.iloc[i]


Step 3 — Daily-4H Alignment
Required inputs:

4H indicators DataFrame (from Step 2)
Daily indicators DataFrame (from Step 2)
data/align.py with explicit D+1 forward-fill rule

Expected outputs:

A merged 4H DataFrame where each row contains both 4H indicators and the daily indicators forward-filled to that bar using strictly point-in-time alignment:

sma_200_daily_aligned: daily SMA200, aligned to 4H bars, first available on day D+1
regime_label_aligned: daily regime label, aligned similarly



Failure modes:

Off-by-one alignment: most critical failure mode. If the daily value from day D is applied to the first 4H bar OF day D (rather than the first 4H bar of day D+1), every strategy using the macro filter has one day of lookahead built in. This will cause the macro filter to look very slightly better than it is. Must be tested explicitly.
Timezone handling: if daily bars are date-only (no time component) and 4H bars are datetime, the merge logic must handle this explicitly. Do not rely on pandas automatic alignment.
Weekends: crypto trades 24/7. Daily bars are full calendar days. The alignment logic must handle Saturday and Sunday correctly.

Tests that must pass before moving on:

TEST-DATA-04 (alignment timing)
TEST-IND-05 (regime label alignment timing)
Manual verification: pick a specific date. Confirm that the SMA200 value on the 4H bar at that date is the SMA200 from the previous calendar day's close.


Step 4 — Regime Classifier
Required inputs:

Daily indicators DataFrame with all regime variables computed
Regime threshold values from config/params.py

Expected outputs:

Daily Series of regime labels: {'STRONG_BULL', 'WEAK_BULL', 'HIGH_VOL_BULLISH', 'HIGH_VOL_BEARISH', 'BEAR', 'TRANSITION'}
Summary table: number and percentage of days in each regime (6 regimes) over full period
This summary is a sanity check. If STRONG_BULL is 60% of all days, the classifier is likely wrong.

Failure modes:

First-match ordering: the regime classifier uses a specific priority order (STRONG_BULL first, then HIGH_VOL_BULLISH and HIGH_VOL_BEARISH before WEAK_BULL and BEAR, per Phase 2 corrected ordering). If the ordering is changed, regime labels change. The order is defined in config/params.py, not in the classifier logic.
NaN handling: if any regime variable is NaN (during warmup), the classifier must return 'UNDEFINED' rather than misclassifying. All backtests must skip bars with UNDEFINED regime.

Tests that must pass before moving on:

Known-input test: feed a constructed daily DataFrame with known values and verify the regime label matches expectation
Boundary test: feed a bar where price is exactly at SMA_200 * 1.05 (boundary between STRONG_BULL and WEAK_BULL). Verify the correct label is assigned.
Proportion sanity check: over the full period, no single regime should account for more than 50% of days unless there is a specific data explanation.


Step 5 — Support Detectors (S2 Only)
Required inputs:

Validated 4H OHLCV DataFrame
DetectorAParams and DetectorBParams from config/params.py

Expected outputs:

For each detector, a function that accepts (bars_df, current_bar_index, params) → list[SupportLevel]
A test suite that verifies no lookahead (TEST-S2-01)
A synthetic dataset test (TEST-S2-02 and TEST-S2-03 for Variant A; TEST-S2-01 for Variant B)

Failure modes:

Variant B lookahead: pivot detection using bars j through j+2 where j+2 >= i. Must be caught by TEST-S2-01. If this test fails, all Variant B results are contaminated.
Level deduplication failure: if two clusters overlap but are not merged, the same breakdown will generate two signals for adjacent levels on the same bar. Must be caught by TEST-S2-07.
Bounce confirmation: in Variant A, each touch must be followed by a bounce of at least 1× ATR. If the bounce requirement is incorrectly implemented (e.g., looking at bars after the current window boundary), this is a form of lookahead. Implement as: the bounce must complete within min_bars_between_touches bars after the touch, and all those bars must be within [0, i-1].

Tests that must pass before moving on:

TEST-S2-01 (lookahead boundary)
TEST-S2-02 (debounce)
TEST-DETECTORS-01: Variant A with a synthetic DataFrame of 100 bars with a known support level → verify it is detected
TEST-DETECTORS-02: Variant B with same synthetic DataFrame → verify detection and confirm pivot boundary is correct
TEST-DETECTORS-03: TEST-S2-08 overlap metric on synthetic known-overlap signal sets


Step 6 — Trade Accounting Module
Required inputs:

TradeRecord schema definition
Fee rate from BacktestParams

Expected outputs:

All functions in accounting/trades.py callable and tested
A sample trade log in CSV format with known inputs and verified outputs

Failure modes:

Sign error in short trade R-multiple: for a short, profit occurs when exit < entry. compute_r_multiple must handle direction explicitly. A positive R on a short trade means exit was below entry.
Fee applied twice: fees must be applied once per trade (at close), not at both entry and exit separately. The total fee is (entry_price × size + exit_price × size) × fee_rate + funding_cost.
R-multiple and net pnl inconsistency: the R-multiple must be computed from net pnl (after ALL fees including funding), not gross pnl. If fee cost is not expressed in R, the apparent expectancy will be too high.
[FIX] Funding cost computed incorrectly: the number of funding settlements must use floor(), not round(). A trade held for 7.9 hours crosses 0 settlements (floor(7.9/8) = 0), not 1.
[FIX] Slippage direction error: long slippage is positive (worse fill = higher price), short slippage is negative (worse fill = lower price). If the sign is wrong, slippage artificially helps instead of hurting.

Tests that must pass before moving on:

TEST-ACCOUNTING-01: Known trade inputs → verify gross_pnl, taker_fee, funding_cost, total_fee, net_pnl, R-multiple
TEST-ACCOUNTING-02: Short trade with positive R → verify sign is correct
TEST-ACCOUNTING-03: Fee expressed in R is consistent with net_pnl / stop_distance
TEST-L2-07 (fee application end-to-end)
TEST-L2-07b (funding cost calculation — per Phase 2.5)
TEST-L2-07c (slippage application — per Phase 2.5)


Step 7 — Backtest Engine
Required inputs:

Aligned 4H DataFrame with all pre-computed indicators
A strategy function (signal generator) from strategies/
Parameters from config/params.py
Run ID (timestamp string)

Expected outputs:

BacktestResult dataclass containing:

trades: list[TradeRecord]
signal_log: DataFrame with one row per bar evaluated (whether signal fired or not, and why)
equity_curve: Series indexed by timestamp
run_metadata: dict with run_id, strategy name, parameter hash, data date range



Failure modes:

Phase ordering violation: if signal generation runs before open trade management, a trade could fire on a bar where a stop should have already been hit. The phase order (B before D) must be enforced structurally, not by convention.
Signal log incompleteness: if only trades are logged (not rejections), the signal log cannot be used to diagnose the macro filter, EMA touch rejection rates, or volume filter rejection rates. Every evaluated bar must produce a log entry, including bars where no signal fired and the reason.
Equity curve construction: the equity curve must reflect the PnL at the bar of trade exit, not at the bar of trade entry. Trades that are still open at the end of the period should be marked-to-market at the last bar's close for the equity curve, but flagged as open in the trade log.

Tests that must pass before moving on:

TEST-L2-05 (no concurrent trades)
TEST-L2-06 (same-bar stop/target conflict → stop wins)
TEST-S2-05 and TEST-S2-06 (short trade stop/target direction)
Lookahead verification procedure from Phase 2.5 Section 7.3 on a 50-bar synthetic dataset
End-to-end test: run engine on 100-bar synthetic dataset with known outcome → verify trade log matches expected


Step 8 — Strategy Runners
Required inputs:

All prior components complete and tested
run_l2.py and run_s2.py entry points

Expected outputs:

For L2: five BacktestResult objects (one per mode) plus two baseline results
For S2: two BacktestResult objects (one per detector variant)
All results written to runs/[run_id]/
params.json written before any result file

Failure modes:

params.json not written before backtest: must be a hard error, not a warning. If the parameter file cannot be written, execution must halt. Results without provenance are untrusted.
Run ID collision: if two runs start within the same second (same timestamp string), outputs overwrite each other. Use a UUID suffix if needed.
Missing warmup period guard: if a strategy fires on bar 5 when warmup requires 1200 bars, the results are invalid. Must be enforced in the engine, not assumed by the strategy.

Tests that must pass before moving on:

params.json exists and is readable before any result file is created (verified by inspection, not a pytest test)
All five L2 modes produce non-empty trade logs on the full dataset
Both S2 detectors produce non-empty trade logs on the full dataset


Step 9 — Diagnostic Outputs, Walk-Forward Validation, and Research Stop Evaluation
Required inputs:

All BacktestResult objects from Step 8
diagnostics/ module
Research stop criteria from Phase 2.5

Expected outputs:

All diagnostic reports for L2 (attribution, period isolation with buy-and-hold, exit isolation, regime contribution, outlier sensitivity)
Detector comparison report and applicable diagnostic reports for S2 (exit isolation with Variant F, regime contribution, period isolation, outlier sensitivity)
Walk-forward validation reports for both L2 and S2 using BOTH methods:
  - Method A (rolling): 6-month windows, 4-month train / 2-month test
  - Method B (expanding): expanding train set, fixed 6-month test, advancing in 6-month non-overlapping increments
  Both methods must pass for PROMISING per Phase 2 thresholds.
Slippage sensitivity sweep (0, 5, 10, 15 bps) for both strategies
Funding rate sensitivity sweep (0.01%, 0.02%, 0.05% per 8H) for both strategies
research_stop_evaluation.txt with explicit pass/fail for each stop criterion

Failure modes:

Diagnostic reports generated before research stop is evaluated: if stop criteria are checked after reading diagnostic outputs, there is a risk of motivated continuation ("the period isolation looks interesting, let me not stop"). The stop criteria must be applied to the raw summary statistics from the BacktestResult, not from the formatted diagnostic reports.
Exit isolation re-running engine with different parameters: the exits.py diagnostic must use the same entry signals as the MVS run. It re-runs only the exit logic. If it accidentally re-generates signals with the alternative exit parameters, it is testing a different strategy, not isolating the exit contribution.


8. Test Gates Between Steps
Step 1 complete gate:
  ✓ TEST-DATA-01 through TEST-DATA-06 pass
  ✓ Row counts and date ranges manually verified
  → Proceed to Step 2

Step 2 complete gate:
  ✓ TEST-IND-01 through TEST-IND-05 pass
  ✓ EMA and ATR spot-check values verified manually
  → Proceed to Step 3

Step 3 complete gate:
  ✓ TEST-DATA-04 passes (alignment timing)
  ✓ TEST-IND-05 passes (regime label alignment)
  ✓ Manual date-specific alignment verification
  → Proceed to Step 4

Step 4 complete gate:
  ✓ Known-input regime classification test passes
  ✓ Boundary condition test passes
  ✓ Regime proportion sanity check passes
  → Proceed to Step 5 (S2) or Step 6 (L2)

Step 5 complete gate (S2 only):
  ✓ TEST-S2-01 through TEST-S2-03 pass
  ✓ TEST-DETECTORS-01 through TEST-DETECTORS-03 pass
  ✓ TEST-S2-08 passes
  → Proceed to Step 6

Step 6 complete gate:
  ✓ TEST-ACCOUNTING-01 through TEST-ACCOUNTING-03 pass
  ✓ TEST-L2-07, TEST-L2-07b, TEST-L2-07c pass
  ✓ Funding cost manually verified on one sample trade
  ✓ Slippage direction verified for both long and short
  → Proceed to Step 7

Step 7 complete gate:
  ✓ TEST-L2-01 through TEST-L2-07c pass (includes 07b funding, 07c slippage)
  ✓ TEST-S2-04 through TEST-S2-07 pass
  ✓ Lookahead verification procedure on synthetic data passes
  ✓ End-to-end engine test on 100-bar synthetic data passes
  ✓ MAE/MFE tracking verified: sample trade shows correct max adverse/favorable excursion
  → Proceed to Step 8

Step 8 complete gate:
  ✓ params.json exists and is intact before any result file
  ✓ All mode trade logs are non-empty
  → Proceed to Step 9

Step 9 complete gate:
  ✓ All diagnostic reports generated without error
  ✓ Walk-forward validation completed: both Method A and Method B for L2 and S2
  ✓ Slippage sensitivity sweep completed for both strategies
  ✓ research_stop_evaluation.txt contains explicit pass/fail for each criterion
     (including STOP-L2-4 and STOP-S2-5 which reference walk-forward results)
  ✓ If any STOP criterion triggers: halt. Document the reason. Do not proceed.
  → If all STOP criteria pass: proceed to ESS specification and implementation

9. Trade Accounting Rules
These rules define the exact computation for every performance metric produced by the harness. No metric is computed in more than one place. All metrics trace back to these definitions.
9.1 TradeRecord Schema
TradeRecord:
  trade_id:           int         # Sequential, reset per run
  strategy:           str         # 'L2_MVS', 'L2_NEXTBAR', 'S2_MVSA', 'S2_MVSB', etc.
  direction:          str         # 'LONG' or 'SHORT'
  entry_bar_index:    int         # Bar index in the DataFrame
  entry_timestamp:    datetime    # UTC
  entry_price:        float       # Close of entry bar (raw signal price)
  effective_entry_price: float    # [FIX] entry_price adjusted for slippage. 
                                  # Long: entry_price × (1 + slippage_bps/10000)
                                  # Short: entry_price × (1 - slippage_bps/10000)
                                  # Used for all P&L and R-multiple calculations.
  stop_price:         float       # Set at entry, fixed unless trailing stop is active
  target_price:       float       # Set at entry, fixed
  stop_distance:      float       # abs(effective_entry_price - stop_price)
  target_distance:    float       # abs(target_price - effective_entry_price)
  planned_r_ratio:    float       # target_distance / stop_distance (should be ~2.0 for L2, ~4.0 for S2)
  exit_bar_index:     int | None  # None if trade still open at end of period
  exit_timestamp:     datetime | None
  exit_price:         float | None
  exit_reason:        str | None  # 'STOP_HIT', 'TARGET_HIT', 'OPEN_AT_END'
  gross_pnl:          float | None  # (exit_price - effective_entry_price) × direction_sign
  fee_entry:          float | None  # effective_entry_price × fee_rate × notional_units
  fee_exit:           float | None  # exit_price × fee_rate × notional_units
  funding_cost:       float | None  # [FIX] floor(holding_hours/8) × funding_rate × entry_price
  total_fee:          float | None  # fee_entry + fee_exit + funding_cost
  net_pnl:            float | None  # gross_pnl - total_fee
  r_multiple_gross:   float | None  # gross_pnl / stop_distance
  r_multiple_net:     float | None  # net_pnl / stop_distance  [USE THIS, not gross]
  regime:             str         # Regime label at entry bar (one of 6 regimes)
  mode:               str         # L2 mode or detector variant
  mae:                float | None  # [FIX] Maximum Adverse Excursion (from bar highs/lows)
                                    # Long: max(effective_entry - bar_low) during trade
                                    # Short: max(bar_high - effective_entry) during trade
  mfe:                float | None  # [FIX] Maximum Favorable Excursion
                                    # Long: max(bar_high - effective_entry) during trade
                                    # Short: max(effective_entry - bar_low) during trade
  
  # L2-specific fields
  ema_21_at_entry:    float | None
  atr_14_at_entry:    float | None
  daily_sma200_at_entry: float | None
  macro_filter_passed: bool | None
  touch_confirmed:    bool | None
  
  # S2-specific fields
  support_level_price:    float | None
  level_touch_count:      int | None
  level_age_bars:         int | None
  level_first_touch_bar:  int | None
  volume_ratio_at_entry:  float | None
  detector_variant:       str | None   # 'A' or 'B'
9.2 Fee Model
CONVENTION:
  fee_rate = 0.0005  (0.05% per side, Binance taker fee)
  funding_rate_per_settlement = 0.0002  (0.02% per 8H, from Phase 1 params)
  
  The research harness trades 1 unit of notional for simplicity.
  position_size = 1.0  (normalized)
  
  Taker fees:
  fee_entry = entry_price × position_size × fee_rate
  fee_exit  = exit_price  × position_size × fee_rate
  total_taker_fee = fee_entry + fee_exit
  
  [FIX — Funding rate cost added per Phase 1/2.5 mandate]
  Funding cost:
  holding_duration_hours = (exit_timestamp - entry_timestamp).total_seconds() / 3600
  funding_settlements_crossed = floor(holding_duration_hours / 8)
  funding_cost = funding_settlements_crossed × funding_rate_per_settlement × entry_price × position_size
  
  Total fee:
  total_fee = total_taker_fee + funding_cost
  
  For a long trade:
    gross_pnl = (exit_price - entry_price) × position_size
    net_pnl   = gross_pnl - total_fee
  
  For a short trade:
    gross_pnl = (entry_price - exit_price) × position_size
    net_pnl   = gross_pnl - total_fee
  
  Fee in R units:
    fee_in_r = total_fee / stop_distance
    
  NOTE: For typical L2/S2 trades with stop distances of 2–5% of price,
  the round-trip taker fee of ~0.10% represents approximately 0.02–0.05R.
  Funding cost adds 0.01–0.04R per trade depending on holding duration.
  Combined fee drag is small but non-negligible over many trades.
  All fees are applied consistently to every trade including baseline trades.
  
  Sensitivity sweeps required (per Phase 2 report format):
  - Slippage: 0, 5, 10, 15 bps
  - Funding rate: 0.01%, 0.02%, 0.05% per 8H
9.3 R-Multiple Calculation
CONVENTION:
  All R-multiples are computed NET of fees.
  All distances use effective_entry_price (slippage-adjusted), not raw entry_price.
  
  For a long trade:
    r_multiple_net = net_pnl / stop_distance
    
    Where stop_distance = effective_entry_price - stop_price (always positive for long)
  
  For a short trade:
    r_multiple_net = net_pnl / stop_distance
    
    Where stop_distance = stop_price - effective_entry_price (always positive for short)
  
  An R-multiple of +1.0 means the trade made exactly 1× the risk.
  An R-multiple of -1.0 means the trade lost exactly 1× the risk (a full stop-out).
  An R-multiple between -1.0 and 0.0 is possible if:
    - trade is closed for a partial loss (time exit in ESS, or breakeven trailing in ESS)
    - fees alone are greater than the stop distance (near-zero stop distance trades)
  
  R-multiples below -1.0 are possible if:
    - Gap occurs through stop price (next bar opens beyond stop)
    - In this case, exit price = open of the gap bar, and R < -1.0 is recorded accurately
    - This must not be clipped or capped. Gaps are real.
9.4 Summary Statistics Computation
From the list of net R-multiples [r1, r2, ..., rN]:

  win_count      = count(r > 0)
  loss_count     = count(r <= 0)
  win_rate       = win_count / N
  
  avg_win_r      = mean(r for r > 0)
  avg_loss_r     = mean(abs(r) for r <= 0)
  
  profit_factor  = sum(r for r > 0) / abs(sum(r for r <= 0))
                   [If no losses: profit_factor = inf — flag this]
                   [If no wins: profit_factor = 0]
  
  expectancy     = mean([r1, r2, ..., rN])  (mean net R per trade)
  
  total_r        = sum([r1, r2, ..., rN])
  
  max_drawdown:
    Compute running cumulative R series.
    For each point, compute drawdown from peak.
    max_drawdown = max absolute drawdown in R terms
    max_drawdown_pct = max_drawdown / peak_equity (if equity curve is used)
  
  sharpe_r:
    annualized_r   = expectancy × (trades_per_year)
    r_std          = std([r1, ..., rN])
    sharpe_r       = annualized_r / (r_std × sqrt(trades_per_year))
    [Using R-based Sharpe, not dollar-based, for regime-independence]
  
  longest_losing_streak:
    Scan r series. Count consecutive r <= 0 values.
    Return maximum count.
  
  avg_trade_duration:
    mean(exit_bar_index - entry_bar_index) × bar_duration_hours

10. Readiness Criteria Before First Backtest
The following checklist must be completed and signed off — not assumed. Every item is verifiable.
DATA READINESS
─────────────────────────────────────────────────────────
□ btc_4h.parquet loaded and CHECK-1 through CHECK-6 all pass
□ btc_1d.parquet loaded and CHECK-1 through CHECK-6 all pass
□ Row count verified: 4H >= 8,500 rows, daily >= 1,400 rows
□ Date range confirmed: starts no later than 2020-01-01
□ No gaps larger than 2 consecutive candles in 4H data
□ Timezone: all timestamps are UTC and timezone-aware

INDICATOR READINESS
─────────────────────────────────────────────────────────
□ EMA21 has NaN for first 20 bars. Correct value at bar 21.
□ ATR14 has NaN for first 13 bars.
□ Volume SMA20 confirmed to exclude current bar
□ Daily SMA200 aligned with D+1 rule verified on specific date
□ Regime labels forward-filled correctly. No UNDEFINED beyond warmup.
□ Regime classifier produces 6 labels: {STRONG_BULL, WEAK_BULL, HIGH_VOL_BULLISH, HIGH_VOL_BEARISH, BEAR, TRANSITION}
□ No NaN values in any indicator column beyond warmup period

PARAMETER READINESS
─────────────────────────────────────────────────────────
□ params.py contains all parameters with values
□ All FROZEN parameters documented with freeze justification
□ All SENSITIVITY-ELIGIBLE parameters documented with allowed range
□ slippage_bps = 10 present in BacktestParams
□ funding_rate_per_settlement = 0.0002 present in BacktestParams
□ params.json written to runs/ directory
□ params.json is human-readable and contains every parameter

TEST GATE READINESS
─────────────────────────────────────────────────────────
□ pytest: all tests in tests/ pass with 0 failures, 0 errors
□ Lookahead verification procedure passed on 100-bar synthetic dataset
□ Support detector Variant B TEST-S2-01 explicitly confirmed
□ Fee calculation manually verified on one sample trade (taker + funding)
□ Slippage direction verified: long entry > close, short entry < close
□ Funding cost verified: floor(holding_hours/8) × rate × price
□ MAE/MFE tracking verified on one sample trade

WALK-FORWARD VALIDATION READINESS
─────────────────────────────────────────────────────────
□ walk_forward.py implements Method A (rolling 6-month windows, 4-month train / 2-month test)
□ walk_forward.py implements Method B (expanding train, 6-month non-overlapping test windows)
□ Method B window advancement verified: train grows by 6 months each step, test windows don't overlap
□ Walk-forward re-runs use frozen parameters from params.json (no parameter changes between windows)
□ Slippage sensitivity sweep implemented (0, 5, 10, 15 bps)
□ Funding rate sensitivity sweep implemented (0.01%, 0.02%, 0.05% per 8H)
□ Both methods produce output format matching Phase 2 Section 3 template

RESEARCH STOP CRITERIA READINESS
─────────────────────────────────────────────────────────
□ All research stop criteria from Phase 2.5 documented in 
  research_stop_evaluation.txt template (pre-populated with 
  criteria, awaiting results to fill in pass/fail)
□ Team agreement: if any STOP criterion triggers, development halts.
  This agreement must exist before the first run, not after.

SCOPE BOUNDARY CONFIRMATION
─────────────────────────────────────────────────────────
□ No live trading code exists anywhere in the repository
□ No paper trading code exists
□ No exchange execution code exists
□ No dashboard or notification code exists
□ No ESS (enhanced spec) code exists
□ Only MVS logic is implemented in strategies/

This plan is complete. No code has been written yet. All design decisions are resolved, all parameters are frozen, all test gates are defined, and all research stop criteria are documented.
On your command, the implementation will proceed file by file in the exact order defined in Step 7, starting with config/params.py. Each file will be complete and tested before the next file is written.