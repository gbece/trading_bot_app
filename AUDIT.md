# Codebase Audit — Crypto Trading Research Harness

**Audit date:** 2026-04-07
**Scope:** All files under `/trading_bot_app/` (research harness, documentation, configuration)
**Auditor:** Automated deep inspection via Claude

---

## 1. Executive Summary

This is a Python research harness for validating two cryptocurrency trading strategies (L2 EMA Pullback Long, S2 Support Breakdown Short) against historical BTC/USDT perpetual data. The codebase is well-structured and follows a clear separation-of-concerns architecture. All 125 unit tests pass. However, several issues require attention before Phase 4 (research execution) can begin: six diagnostic modules are untracked in git, three entry-point scripts are missing, dependencies are not pinned, and test coverage has meaningful gaps in the backtest engine, diagnostics, and data-fetching layers.

**Overall health: Solid foundation with gaps that block the next phase.**

| Metric | Value |
|--------|-------|
| Total Python files | 35 |
| Production LOC | 3,809 |
| Test LOC | 2,259 |
| Total LOC | 6,068 |
| Tests | 125 passing (1.82s) |
| Git commits | 5 |
| Untracked files at risk | 6 |
| Critical/high issues | 5 |
| Medium issues | 7 |
| Low issues | 5 |

---

## 2. Architecture Overview

```
research/
├── config/params.py          Frozen dataclass parameters (125 LOC)
├── data/
│   ├── fetch.py              OHLCV download via ccxt (224 LOC)
│   ├── validate.py           6 integrity checks (223 LOC)
│   └── align.py              Daily-to-4H D+1 alignment (96 LOC)
├── indicators/
│   ├── trend.py              EMA, SMA, slope (98 LOC)
│   ├── volatility.py         ATR (53 LOC)
│   ├── volume.py             Volume SMA, relative volume (63 LOC)
│   └── regime.py             6-regime classifier (134 LOC)
├── detectors/
│   └── support.py            Variant A + B detection (409 LOC)
├── strategies/
│   ├── l2_mvs.py             L2 signal generation, 5 modes (233 LOC)
│   └── s2_mvs.py             S2 signal generation (202 LOC)
├── engine/
│   └── backtest.py           Bar-by-bar loop (548 LOC)
├── accounting/
│   └── trades.py             Fee model, R-multiples (409 LOC)
├── baselines/
│   └── random_entry.py       Null-hypothesis baselines (111 LOC)
├── diagnostics/
│   ├── attribution.py        Component attribution — L2 (168 LOC) [UNTRACKED]
│   ├── exits.py              Exit structure isolation (204 LOC) [UNTRACKED]
│   ├── outliers.py           Single-trade sensitivity (130 LOC) [UNTRACKED]
│   ├── periods.py            Period isolation + buy-and-hold (208 LOC) [UNTRACKED]
│   ├── regimes.py            Regime contribution (171 LOC) [UNTRACKED]
│   └── walk_forward.py       Walk-forward + slippage sweep [UNTRACKED]
├── tests/
│   ├── test_data.py          (206 LOC)
│   ├── test_indicators.py    (394 LOC)
│   ├── test_detectors.py     (315 LOC)
│   ├── test_l2.py            (292 LOC)
│   ├── test_s2.py            (261 LOC)
│   └── test_accounting.py    (237 LOC)
├── run_l2.py                 L2 pipeline entry point [UNTRACKED]
├── run_s2.py                 S2 pipeline entry point [UNTRACKED]
└── run_all.py                Combined entry point [UNTRACKED]
```

**Data flow:**

```
fetch.py → validate.py → align.py
                              ↓
                     indicators/*.py
                              ↓
              ┌───────────────┴───────────────┐
              │                               │
     detectors/support.py              (L2 path)
              │                               │
     strategies/s2_mvs.py         strategies/l2_mvs.py
              │                               │
              └───────────────┬───────────────┘
                              ↓
                    engine/backtest.py
                              ↓
                   accounting/trades.py
                              ↓
                    diagnostics/*.py
```

---

## 3. Code Quality Assessment (per module)

### 3.1 `config/params.py`

**Quality: Good.** Clean frozen dataclasses. All parameters documented with freeze rationale. `freeze()` serializes to JSON for audit trails.

- No issues found.

### 3.2 `data/fetch.py`

**Quality: Acceptable with minor issues.**

- Unused import: `os`
- Hardcoded symbols, timeframes, date ranges, and retry parameters (intentional for single-use fetcher)
- Good retry logic with exponential backoff for API failures
- Skips existing files silently — could mask stale data
- No test coverage

### 3.3 `data/validate.py`

**Quality: Good.**

- Unused import: `numpy`
- All 6 CHECK functions raise descriptive `ValueError` with specific row/value context
- `ValidatedOHLCV` wrapper enforces the validation gate pattern
- Spike detection and zero-volume handling are well-documented

### 3.4 `data/align.py`

**Quality: Excellent.**

- Clean, minimal, well-typed
- D+1 rule implemented explicitly with `pd.Timedelta(days=1)`
- `TypeError` raised on invalid index type
- No issues found

### 3.5 `indicators/trend.py`, `volatility.py`, `volume.py`

**Quality: Excellent.**

- Full type hints, `ValueError` on invalid periods
- EMA warmup convention documented and enforced (first `period-1` values set to NaN)
- ATR uses three-term True Range (not just high-low)
- Volume SMA correctly excludes current bar via `.shift(1)` windowing

### 3.6 `indicators/regime.py`

**Quality: Acceptable with concerns.**

- All regime thresholds are hardcoded magic numbers (`1.05`, `0.10`, `1.5`, `2.0`, `-0.05`, etc.) rather than sourced from `config/params.py` — violates the "single source of parameters" principle
- NaN check uses `v != v` idiom instead of `np.isnan()` — works for Python floats but fragile for numpy scalar edge cases
- `compute_regime_labels` is untested (only `classify_regime` has tests)
- SMA periods (`200`, `50`), ROC period (`20`), ATR period (`14`), ATR SMA window (`60`) are all inline literals

### 3.7 `detectors/support.py`

**Quality: Good.**

- Unused import: `Optional`
- Both Variant A and Variant B are pure functions — good for testability
- Hardcoded ATR proxy window (`14`) in Variant A's `_rolling_mean(hl_ranges, 14)`
- Pivot definition in Variant B may double-count equal lows (known ambiguity, documented)
- Overlap metric (`compute_detector_overlap`) is well-defined

### 3.8 `strategies/l2_mvs.py`

**Quality: Excellent.**

- Strong type hints, clear mode branching
- Each mode is an explicit branch — no hidden shared logic
- `RANDOM` mode intentionally passes `NaN` for EMA anchor
- Returns `None` for warmup/invalid bars — clean contract

### 3.9 `strategies/s2_mvs.py`

**Quality: Good.**

- `open_price` and `high_price` parameters are accepted but unused in the function body — reserved for future use but creates a misleading signature
- Otherwise clean, params-driven, well-typed

### 3.10 `engine/backtest.py`

**Quality: Acceptable with unused imports.**

- Unused imports: `uuid`, `field`, `Callable`, `DetectorAParams`, `DetectorBParams`
- `detector_params` typed as `Any` — loses type safety
- Phase ordering (B before D) is structurally enforced — correct
- Same-bar stop/target conflict correctly resolves to stop — per spec
- Signal log includes rejection reasons — good for diagnostics
- No test coverage for the engine module itself

### 3.11 `accounting/trades.py`

**Quality: Good with minor issues.**

- Unused imports: `numpy`, `field`
- `direction` handling uses `else: # short` — any non-`"LONG"` value silently treated as short
- `apply_fees_to_trade` uses `assert` for preconditions (correct for research code but no direct test)
- `compute_summary_stats` returns untyped `dict`
- `max_consecutive_losses` counts breakeven (`r <= 0`) as losses — documented but could surprise

### 3.12 `baselines/random_entry.py`

**Quality: Acceptable.**

- Unused import: `numpy`
- Delegates to `run_l2_backtest` with `RANDOM` and `MACRO_ONLY` modes — clean reuse
- No test coverage

### 3.13 `diagnostics/` (6 untracked files)

**Quality: Mixed.**

| File | Notes |
|------|-------|
| `attribution.py` | Unused import: `Optional`. Hardcoded PF delta thresholds. Otherwise clean. |
| `exits.py` | Unused imports: `replace`, `Callable`. `default_target` variable assigned but never used. `detector_params` untyped. |
| `periods.py` | Unused import: `Optional`. Dead parameter `existing_lines` in `_compute_bah_comparison`. Duplicated calendar logic with `walk_forward.py`. |
| `regimes.py` | Clean. No issues. |
| `outliers.py` | Clean. Good progressive-removal logic. |
| `walk_forward.py` | Unused imports: `BacktestResult`, `L2Params`, `S2Params`. Unused variable `window_months`. Bare `except Exception` swallows errors silently in `run_on_slice` — can mask bugs. |

### 3.14 Entry-point scripts (`run_l2.py`, `run_s2.py`, `run_all.py`)

**Quality: Acceptable with bugs.**

| File | Issues |
|------|--------|
| `run_l2.py` | Unused imports: `json`, `DetectorAParams`, `DetectorBParams`, `compute_relative_volume`, baseline imports (`run_random_all_bars`, `run_random_macro_matched`). Docstring promises baseline runs but they are never called. `params` argument in `_evaluate_research_stops` is unused — thresholds are hardcoded instead. |
| `run_s2.py` | Unused import: `compute_sma`. **Likely runtime bug**: f-string format specs in `_evaluate_research_stops` use inline conditionals incorrectly (e.g., `{pf:.3f if not np.isnan(pf) else 'n/a'}`) — this will raise `ValueError` at runtime. |
| `run_all.py` | `generate_portfolio_report` always uses S2 Variant A, not the conservative variant used for the S2 verdict — inconsistency. Research verdict thresholds are duplicated across all three scripts. |

---

## 4. Test Coverage Matrix

| Module | Test file | Coverage | Gaps |
|--------|-----------|----------|------|
| `config/params.py` | (indirect) | Partial | No direct tests for `freeze()` or `freeze_all()` |
| `data/fetch.py` | None | **None** | No tests at all |
| `data/validate.py` | `test_data.py` | Good | `check_no_zero_volume`, `check_no_price_spikes`, `check_timestamp_monotonicity` are imported but untested |
| `data/align.py` | `test_data.py`, `test_indicators.py` | Good | Covered via D+1 alignment tests |
| `indicators/trend.py` | `test_indicators.py` | Good | EMA, SMA, slope all tested |
| `indicators/volatility.py` | `test_indicators.py` | Good | ATR warmup and correctness tested |
| `indicators/volume.py` | `test_indicators.py` | Good | Current-bar exclusion explicitly tested |
| `indicators/regime.py` | `test_indicators.py` | **Partial** | `classify_regime` tested; `compute_regime_labels` untested |
| `detectors/support.py` | `test_detectors.py` | Good | Lookahead, debounce, overlap all tested |
| `strategies/l2_mvs.py` | `test_l2.py` | Good | All 5 modes tested |
| `strategies/s2_mvs.py` | `test_s2.py` | Good | Signal rules and edge cases tested |
| `engine/backtest.py` | None | **None** | No direct tests; exercised indirectly via strategy tests |
| `accounting/trades.py` | `test_accounting.py` | **Partial** | `apply_fees_to_trade` and `compute_total_fee` imported but never called in tests |
| `baselines/random_entry.py` | None | **None** | No tests |
| `diagnostics/*.py` | None | **None** | No tests for any diagnostic module |
| `run_*.py` | None | **None** | No tests for entry points |

### Test documentation drift

| File | Promised test IDs | Missing |
|------|-------------------|---------|
| `test_l2.py` | TEST-L2-07a (fee model), TEST-L2-07b (funding) | Not implemented — fee tests live in `test_accounting.py` under different IDs |
| `test_s2.py` | TEST-S2-08 (engine same-bar stop/target) | Not implemented |

### Unused imports in test files

| File | Unused imports |
|------|----------------|
| `test_accounting.py` | `math`, `pytest`, `compute_total_fee`, `apply_fees_to_trade` |
| `test_indicators.py` | `compute_regime_labels` |
| `test_data.py` | `check_no_zero_volume`, `check_no_price_spikes`, `check_timestamp_monotonicity` |
| `test_detectors.py` | `pytest`, `SupportLevel` |
| `test_l2.py` | `math`, `pytest`, `numpy`, `BacktestParams` |
| `test_s2.py` | `pytest`, `numpy` |

### Weak assertions

- `test_accounting.py::test_profit_factor_all_wins`: asserts `np.isnan(pf) or pf > 100` — very loose
- `test_s2.py::TestMultipleLevelConflict`: tolerance `abs(...) < 1.0` is broad enough to pass for the wrong support level if prices are close
- `test_indicators.py::test_volume_sma_nan_for_first_period_bars`: docstring contradicts assertion about the first-valid index (off-by-one in prose)

---

## 5. Security Review

| Area | Finding | Severity |
|------|---------|----------|
| API keys / secrets | No hardcoded secrets. `.env` is gitignored. `fetch.py` uses public Binance endpoints (no keys required). | None |
| Code injection | No `eval()`, `exec()`, `subprocess`, or shell invocations. | None |
| File path safety | Diagnostic modules write to caller-controlled `output_dir` paths. Only a concern if paths originate from untrusted input (not applicable in research context). | Low |
| Dependency supply chain | No `requirements.txt` — no pinned versions, no hash verification. | Medium |
| Data integrity | Validated via 6 CHECK functions before use. No raw data committed to repo. | Good |

**Verdict: No security vulnerabilities in the current research-only codebase.**

---

## 6. Dependency Audit

### Required dependencies (documented in README and Phase 5)

| Package | Required version | Pinned? | Used by |
|---------|-----------------|---------|---------|
| Python | 3.11+ | No | All |
| pandas | Any | **No** | All modules |
| numpy | Any | **No** | Indicators, accounting, strategies, diagnostics |
| ccxt | Any | **No** | `data/fetch.py` only |
| pyarrow | Any | **No** | Parquet I/O (implicit via pandas) |
| pytest | Any | **No** | `tests/` |

### Missing dependency management files

- No `requirements.txt`
- No `pyproject.toml`
- No `setup.py` or `setup.cfg`
- No `Pipfile` or `poetry.lock`
- No `conda` environment file

### Risk

Without pinned versions, a `pip install` on a new machine could pull incompatible versions. Pandas 3.x introduces breaking changes to datetime handling that could affect the alignment module. The `ccxt` library updates frequently with exchange-specific changes.

---

## 7. Documentation Completeness

| Document | Status | Notes |
|----------|--------|-------|
| `README.md` | Complete | Comprehensive project overview, vision, roadmap, phase descriptions |
| `docs/Phase_1_Evaluation.md` | Complete | Strategy scoring and selection |
| `docs/Phase_2_Strategy_Spec.md` | Complete | Formal L2/S2 rules, regime classifier, thresholds |
| `docs/Phase_2_5_Harness_Spec.md` | Complete | Backtesting logic, test plan, diagnostic formats |
| `docs/Phase_3_Implementation.md` | Complete | File-by-file plan, test gates, trade accounting rules |
| `docs/Phase_4_*.md` | **Missing** | Only described in README; no standalone spec |
| `docs/Phase_5_Deployment.md` | Complete but inconsistent | Prescribes Freqtrade deployment; README describes custom Python bot |

### Documentation inconsistency

Phase 5 and the README describe two different deployment approaches:
- **Phase 5**: Freqtrade on Raspberry Pi with ports 8084/8085
- **README**: Custom minimal Python execution layer (`execution/main.py`)

These need to be reconciled before Phase 5 begins.

---

## 8. Issues by Severity

### CRITICAL / HIGH

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| H-1 | 6 diagnostic files + 3 run scripts are **untracked** in git | `research/diagnostics/`, `research/run_*.py` | Work can be permanently lost; `git clean` or accidental deletion destroys ~1,800 LOC |
| H-2 | No `requirements.txt` or dependency pinning | Project root | Fresh installs may break; reproducibility not guaranteed |
| H-3 | Missing entry-point scripts in committed code | `run_l2.py`, `run_s2.py`, `run_all.py` | Phase 4 cannot execute from a clean clone |
| H-4 | Missing `diagnostics/portfolio.py` per Phase 3 plan | `research/diagnostics/` | Cross-strategy correlation diagnostic is unavailable for full research run |
| H-5 | Likely runtime bug in `run_s2.py` | `_evaluate_research_stops` f-string formatting | Will crash when generating the research stop summary |

### MEDIUM

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| M-1 | Unused imports across 15+ files | See Section 3 | Code noise; may confuse contributors; linter warnings |
| M-2 | Test documentation drift (TEST-L2-07a/07b, TEST-S2-08) | `test_l2.py`, `test_s2.py` | Promised tests don't exist; creates false confidence in coverage |
| M-3 | `apply_fees_to_trade` has no direct test | `test_accounting.py` | Key accounting function exercised only indirectly |
| M-4 | `compute_regime_labels` untested | `indicators/regime.py` | Full pipeline from daily data to regime labels is unverified |
| M-5 | Regime classifier thresholds hardcoded as magic numbers | `indicators/regime.py` | Violates single-source-of-parameters principle from Phase 3 |
| M-6 | `run_l2.py` imports but never calls baseline functions | `run_l2.py` | Baselines are part of the research protocol but not wired in |
| M-7 | Research verdict thresholds duplicated across 3 scripts | `run_l2.py`, `run_s2.py`, `run_all.py` | Drift risk; changing a threshold in one file but not another produces inconsistent verdicts |

### LOW

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| L-1 | No CI/CD pipeline | Project-wide | Tests must be run manually; no automated quality gate |
| L-2 | No linting configuration | Project-wide | Style issues accumulate without automated checks |
| L-3 | No pre-commit hooks | `.git/hooks/` | No enforcement before commits |
| L-4 | `.pytest_cache/` not gitignored | `.gitignore` | Cache directory could be accidentally committed |
| L-5 | Dead variables and parameters | `exits.py` (`default_target`), `periods.py` (`existing_lines`), `walk_forward.py` (`window_months`) | Minor code smell |

---

## 9. Recommendations

### Immediate (before Phase 4)

1. **Git-add the untracked files.** Run `git add research/diagnostics/ research/run_*.py` and commit. This is the single highest-priority action.
2. **Create `requirements.txt`** with pinned versions:
   ```
   pandas>=2.0,<3.0
   numpy>=1.24,<2.0
   ccxt>=4.0
   pyarrow>=14.0
   pytest>=7.0
   ```
3. **Fix the `run_s2.py` f-string bug** in `_evaluate_research_stops` before any research run.
4. **Wire baseline calls in `run_l2.py`** — the random baselines are imported but never executed.
5. **Centralize research verdict thresholds** into `config/params.py` or a new `config/thresholds.py`.

### Short-term (during Phase 4)

6. Add tests for `engine/backtest.py` — at minimum an end-to-end test on synthetic data.
7. Add a direct test for `apply_fees_to_trade`.
8. Add a test for `compute_regime_labels` (full pipeline, not just `classify_regime`).
9. Clean up unused imports across all files.
10. Move regime classifier thresholds to `config/params.py`.

### Medium-term

11. Implement `diagnostics/portfolio.py` for cross-strategy drawdown correlation.
12. Add `.pytest_cache/` to `.gitignore`.
13. Create a `Phase_4_Research_Execution.md` specification document.
14. Reconcile Phase 5 / README deployment approach.
15. Set up a minimal CI pipeline (GitHub Actions running `pytest`).

---

*End of audit.*
