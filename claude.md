# Claude — Project Context & Coding Conventions

This file gives you everything you need to work effectively on this codebase. Read it before making any changes.

---

## What This Project Is

A **Python research harness** that tests whether two cryptocurrency trading strategies have genuine statistical edge on historical BTC/USDT perpetual data. The core principle is **falsification over confirmation** — the system is designed to make it easy to REJECT a strategy, not easy to confirm it.

There are two strategies under evaluation:

- **L2 (EMA Pullback Long)** — In a confirmed uptrend (BTC above daily 200 SMA), price pulling back to the 4H 21 EMA and closing bullish has positive expectancy. Tested in 5 modes: RANDOM, MACRO_ONLY, TOUCH_ONLY, MVS_NO_CONFIRM, MVS_FULL.
- **S2 (Support Breakdown Short)** — When a horizontal support level (3+ touches) breaks down on high volume, price continues lower. Tested with two independent support detection algorithms (Variant A and Variant B).

The system produces a verdict: **PROMISING**, **INCONCLUSIVE**, or **REJECT**. If REJECT, nothing further gets built. If PROMISING, a minimal live execution layer is built separately.

---

## Architecture

All research code lives under `research/`. The execution layer (`execution/`) does not exist yet and will only be built if strategies pass.

### Module map

| Module | Responsibility | Key exports |
|--------|---------------|-------------|
| `config/params.py` | All frozen parameters as dataclasses | `L2Params`, `S2Params`, `DetectorAParams`, `DetectorBParams`, `BacktestParams`, `freeze()` |
| `data/fetch.py` | Download OHLCV from Binance via ccxt, save to Parquet | `fetch_pair()`, `save_pair()`, `load_pair()` |
| `data/validate.py` | 6 integrity checks (CHECK-1 to CHECK-6) | `validate_ohlcv()` → `ValidatedOHLCV` |
| `data/align.py` | Daily-to-4H alignment using D+1 forward-fill | `align_daily_to_4h()`, `align_regime_labels()` |
| `indicators/trend.py` | EMA, SMA, EMA slope | `compute_ema()`, `compute_sma()`, `compute_ema_slope()` |
| `indicators/volatility.py` | ATR (three-term True Range) | `compute_atr()` |
| `indicators/volume.py` | Volume SMA (excludes current bar), relative volume | `compute_volume_sma()`, `compute_relative_volume()` |
| `indicators/regime.py` | 6-regime daily classifier | `classify_regime()`, `compute_regime_labels()` |
| `detectors/support.py` | Two support-level detection algorithms | `detect_support_levels_variant_a()`, `detect_support_levels_variant_b()`, `SupportLevel` |
| `strategies/l2_mvs.py` | L2 signal generation for all 5 modes | `evaluate_l2_signal()`, `L2SignalMode`, `L2Signal` |
| `strategies/s2_mvs.py` | S2 signal generation | `evaluate_s2_signal()`, `S2Signal` |
| `engine/backtest.py` | Bar-by-bar loop, trade management | `run_l2_backtest()`, `run_s2_backtest()`, `BacktestResult` |
| `accounting/trades.py` | Fee model, R-multiples, trade log, summary stats | `TradeRecord`, `apply_fees_to_trade()`, `compute_summary_stats()` |
| `baselines/random_entry.py` | Null-hypothesis random-entry baselines | `run_random_all_bars()`, `run_random_macro_matched()` |
| `diagnostics/*.py` | 6 diagnostic report generators (read-only consumers of BacktestResult) | `generate_*_report()` functions |

### Data flow

```
OHLCV (Binance) → fetch.py → Parquet files
                                    ↓
                              validate.py (CHECK-1 to CHECK-6)
                                    ↓
                              align.py (D+1 rule)
                                    ↓
                           indicators/*.py (EMA, ATR, SMA, regime)
                                    ↓
                    ┌───────────────┴───────────────┐
                    │                               │
           detectors/support.py              (L2 uses indicators directly)
                    │                               │
           strategies/s2_mvs.py         strategies/l2_mvs.py
                    │                               │
                    └───────────────┬───────────────┘
                                    ↓
                          engine/backtest.py (bar-by-bar loop)
                                    ↓
                         accounting/trades.py (fees, R-multiples)
                                    ↓
                          diagnostics/*.py (reports)
```

### Current project state

- **Phases 1-2.5**: Complete (design and specification)
- **Phase 3 (implementation)**: Rounds 1-2 committed; Round 3 (diagnostics, entry points) written but untracked
- **Phase 4 (research execution)**: Not started — blocked on committing Round 3 and fixing bugs
- **Phase 5 (live execution)**: Not started — conditional on Phase 4 PROMISING verdict

---

## How to Run Things

### Tests

```bash
cd /Users/agustinbecerra/trading_bot_app
python3 -m pytest research/tests/ -q
```

All 125 tests should pass. If any fail, stop and fix before proceeding.

### Fetch data

```bash
python3 -m research.data.fetch
```

Downloads BTC/USDT perpetual 4H + 1D OHLCV from Binance to `research/data/raw/`. No API keys required (public data).

### Run research (once Phase 4 is ready)

```bash
python3 -m research.run_l2
python3 -m research.run_s2
python3 -m research.run_all
```

---

## Coding Rules

These rules are extracted from the Phase 3 specification and observed codebase patterns. Follow them for all changes.

### The 8 Design Principles

1. **Falsification over feature completeness.** Every component exists to make it easier to reject the hypothesis. If a component makes results look better without making the test more rigorous, it does not belong.

2. **No hidden state.** Every decision the backtester makes must be traceable to a logged input. If a trade fires, the exact values of every condition must be recoverable from the trade log.

3. **Parameter immutability after run start.** Parameters are written to disk via `freeze()` before the backtest executes. The backtest reads them. No mid-run adjustment.

4. **Minimal surface area.** The harness implements exactly what is needed to test the MVS of L2 and S2. Every additional line of code is a liability.

5. **Strict separation of concerns.** Data loading does not compute indicators. Indicator computation does not evaluate signals. Signal evaluation does not manage trades. Trade management does not produce reports. Each layer receives fully formed inputs and produces fully formed outputs.

6. **Test gates are non-negotiable.** No step proceeds until its test gate passes. A broken test means a bug exists — fix the bug, don't skip the test.

7. **Explicit is better than inferred.** Every alignment, lookahead boundary, and fee calculation is written out explicitly. No behavior is left to pandas defaults or library conventions without verification.

8. **The code is a record of the research.** Function and variable names must reflect their research meaning.

### Naming Conventions

Use names that describe the research concept, not generic programming terms:

| Good | Bad |
|------|-----|
| `ema_touch_bar` | `signal` |
| `macro_filter_passed` | `condition_1` |
| `breakdown_confirmed` | `flag` |
| `stop_distance` | `dist` |
| `r_multiple_net` | `result` |
| `funding_settlements_crossed` | `count` |

### Style Patterns

These patterns are used consistently across the codebase. Follow them:

- **`from __future__ import annotations`** at the top of every module
- **Module-level docstring** describing the file's single responsibility
- **Section banners** (comment blocks) to separate logical sections within files
- **Frozen dataclasses** for all parameter containers and signal/trade records
- **Type hints** on all public function signatures (use `Optional[X]` or `X | None`)
- **`raise ValueError`** with descriptive messages for input validation
- **Return `None`** (not raise) when a strategy evaluates a bar and finds no signal

### Parameter Rules

- **All parameters live in `config/params.py`.** No parameter exists anywhere else.
- Parameters are either **FROZEN** (never changed after initial definition) or **SENSITIVITY-ELIGIBLE** (can be tested at specific alternative values documented in Phase 3).
- If you need a new parameter, add it to the appropriate dataclass in `config/params.py` with a freeze justification comment.
- Never change a FROZEN parameter after seeing backtest results.

### Lookahead Prevention (Critical)

This is the most important correctness constraint in the entire codebase:

- **D+1 rule**: A daily indicator value computed through day D is available to 4H bars starting on day D+1, never day D. The `align.py` module enforces this.
- **Detector boundary**: Support detectors receive `bars[0:i]` — they cannot see bar `i`. The engine enforces the slice, not the detector.
- **Pivot lookahead (Variant B)**: A pivot at bar `j` requires bars `j+1` and `j+2` to confirm. Therefore at bar `i`, only pivots at `j <= i-3` are valid. This is derived from `pivot_window`, not independently chosen.
- **Volume SMA**: `vol_sma_20.iloc[i]` must NOT include `volume.iloc[i]`. The SMA is shifted to exclude the current bar.
- **Regime labels**: Forward-filled using the D+1 rule. A regime change on day D is not visible until day D+1's 4H bars.

If you touch alignment, detector, or indicator code, verify the lookahead boundary with a test.

### Test Conventions

- All tests use **synthetic data constructed within the test**. No test reads from `data/raw/`.
- Tests are organized by module: `test_data.py` for data/, `test_indicators.py` for indicators/, etc.
- Use **exact assertions** with tight tolerances (`abs(actual - expected) < 1e-9`) for numerical checks.
- Each test maps to a **test ID** from the Phase 2.5 spec (e.g., TEST-DATA-01, TEST-IND-03, TEST-L2-05).
- Run `pytest` after every change. If a test breaks, fix it before moving on.

### What NOT to Do

- **No live trading code in `research/`.** The research harness has no connection to any exchange and no ability to place orders.
- **No ESS (Enhanced Spec) logic in MVS files.** The current strategies implement only the Minimal Viable Spec. ESS filters are a separate phase.
- **No optimization or grid search.** Parameters are frozen. The harness tests specific hypotheses, not parameter spaces.
- **No pandas default reliance.** If a computation depends on pandas behavior (e.g., `ewm(adjust=True)` vs `adjust=False`), document which convention is used and verify it with a test.
- **No broad `except Exception`.** If you must catch exceptions, catch specific types and log the error. Never silently swallow failures.
- **No imports you don't use.** Clean up unused imports when you see them.
- **No comments that just narrate the code.** Comments should explain *why*, not *what*. The code itself should make the *what* obvious through good naming.

### Fee Model Reference

Every trade (including baselines) uses this fee model:

```
taker_fee = entry_price * fee_rate + exit_price * fee_rate  (fee_rate = 0.0005)
funding_cost = floor(holding_hours / 8) * funding_rate * entry_price  (funding_rate = 0.0002)
total_fee = taker_fee + funding_cost
net_pnl = gross_pnl - total_fee
r_multiple_net = net_pnl / stop_distance  (always use net, not gross)
```

Slippage is applied to the entry price:
- Long: `effective_entry = close * (1 + slippage_bps / 10000)`
- Short: `effective_entry = close * (1 - slippage_bps / 10000)`

### The 6 Market Regimes

The regime classifier produces one of these labels per day (priority order):

1. `STRONG_BULL` — price > SMA200 * 1.05, ROC20 > 10%, vol_ratio < 1.5
2. `HIGH_VOL_BULLISH` — price > SMA200, vol_ratio >= 1.5
3. `HIGH_VOL_BEARISH` — price <= SMA200, vol_ratio >= 2.0
4. `WEAK_BULL` — price > SMA200 (does not qualify as STRONG_BULL or HIGH_VOL)
5. `BEAR` — price <= SMA200, ROC20 < -5%
6. `TRANSITION` — everything else (catch-all)

Priority matters: a bar matching both STRONG_BULL and HIGH_VOL_BULLISH is classified as STRONG_BULL. `UNDEFINED` is returned during warmup (NaN indicators).

---

## Key Files to Read First

If you're getting oriented, read these in order:

1. `README.md` — project vision and full roadmap
2. `docs/Phase_2_Strategy_Spec.md` — the exact strategy rules
3. `docs/Phase_2_5_Harness_Spec.md` — how the backtester works
4. `research/config/params.py` — all frozen parameters
5. `research/engine/backtest.py` — the core bar-by-bar loop
6. `AUDIT.md` — known issues and recommendations
