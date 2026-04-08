# Project Status Report — Crypto Trading Research System

**Report date:** 2026-04-07
**Repository:** `https://github.com/gbece/trading_bot_app.git`
**Branch:** `master` (1 commit ahead of `origin/master`)

---

## 1. Project Status Summary

| Attribute | Value |
|-----------|-------|
| Project name | Crypto Trading Research & Execution System |
| Author | Gonzalo — Uruguay |
| Started | March 2026 |
| Language | Python 3.11+ |
| Current phase | Phase 3 (Implementation) — partially complete |
| Next milestone | Complete Round 3 (diagnostics + entry points), then Phase 4 (research execution) |
| Blockers | 6 untracked files at risk of loss; missing `requirements.txt`; `run_s2.py` has a runtime bug |

**Bottom line:** The research harness core (data pipeline, indicators, detectors, strategies, backtest engine, accounting) is implemented and tested. The diagnostic layer and entry-point scripts exist locally but are not committed. The project cannot proceed to Phase 4 (actual research runs) until the untracked work is committed, the `run_s2.py` bug is fixed, and baseline execution is wired into `run_l2.py`.

---

## 2. Phase Completion Tracker

| Phase | Title | Status | Notes |
|-------|-------|--------|-------|
| 1 | Evaluation Layer | **Complete** | 6 hypotheses scored; L2 and S2 selected |
| 2 | Strategy Specification | **Complete** | Formal rules, regime classifier, thresholds defined |
| 2.5 | Research Harness Specification | **Complete** | Bar-by-bar logic, test plan, diagnostic formats specified |
| 3 | Implementation Plan | **In progress** | Rounds 1-2 committed; Round 3 written but untracked |
| 4 | Research Execution | **Not started** | Blocked on Phase 3 completion |
| 5 | Execution Layer | **Not started** | Conditional on Phase 4 producing PROMISING verdict |

---

## 3. Implementation Progress vs Phase 3 Plan

Phase 3 defines a 13-step implementation order with test gates. Here is the actual status:

### Round 1 (committed — `ff99d2c`)

| Step | Component | Status | Gate |
|------|-----------|--------|------|
| 1 | Data acquisition and validation (`data/fetch.py`, `validate.py`) | Done | TEST-DATA-01 to -06 pass |
| 2 | Indicator computation (`indicators/*.py`) | Done | TEST-IND-01 to -05 pass |
| 3 | Daily-4H alignment (`data/align.py`) | Done | Alignment timing verified |
| 4 | Regime classifier (`indicators/regime.py`) | Done | `classify_regime` tested; `compute_regime_labels` gap |

### Round 2 (committed — `9a1ccf4`)

| Step | Component | Status | Gate |
|------|-----------|--------|------|
| 5 | Support detectors (`detectors/support.py`) | Done | TEST-S2-01 to -03 pass |
| 6 | Trade accounting (`accounting/trades.py`) | Done | Fee/R-multiple tests pass; `apply_fees_to_trade` untested |
| 7 | Backtest engine (`engine/backtest.py`) | Done | No direct tests; exercised via strategy tests |
| 8 | Strategy runners (`strategies/l2_mvs.py`, `s2_mvs.py`) | Done | All mode tests pass |
| — | Baselines (`baselines/random_entry.py`) | Done | Code exists but not wired into run scripts |

### Round 3 (untracked — at risk)

| Step | Component | Status | Gate |
|------|-----------|--------|------|
| 9a | Diagnostics: attribution, regimes, periods, outliers, exits | Written, **untracked** | No tests |
| 9b | Walk-forward validation | Written, **untracked** | No tests |
| 9c | Portfolio correlation | **Missing** | `diagnostics/portfolio.py` exists in `run_all.py` imports but as a separate untracked file |
| 9d | Entry points: `run_l2.py`, `run_s2.py`, `run_all.py` | Written, **untracked** | `run_s2.py` has runtime bug |
| 9e | Research stop evaluation | Written (in run scripts) | Thresholds duplicated; not centralized |

### Phase 3 deliverables not yet produced

| Deliverable | Status |
|-------------|--------|
| `runs/` directory structure | Not created (expected at Phase 4 runtime) |
| `params.json` snapshot | Not created (expected at Phase 4 runtime) |
| All diagnostic reports | Not created (expected at Phase 4 runtime) |
| `research_stop_evaluation.txt` | Not created (expected at Phase 4 runtime) |

---

## 4. Git History

| Hash | Message | Round |
|------|---------|-------|
| `231343a` | Initial commit: project docs and specifications | Docs |
| `068f62d` | Clean up: remove duplicate files from root, keep only in docs/ | Docs |
| `e3d6edd` | Merge pull request #1 from gbece/main | Merge |
| `ff99d2c` | Round 1: data pipeline + indicators + tests | Round 1 |
| `9a1ccf4` | Round 2: backtest engine, strategies, detectors, accounting, baselines | Round 2 |

**Development pace:** 5 commits over approximately 2-3 weeks. Two substantive implementation pushes (Rounds 1 and 2). The local working tree has Round 3 work that has not been committed.

**Unpushed:** `master` is 1 commit ahead of `origin/master` (commit `9a1ccf4`).

**Untracked files (9 total):**

```
research/diagnostics/attribution.py
research/diagnostics/exits.py
research/diagnostics/outliers.py
research/diagnostics/periods.py
research/diagnostics/regimes.py
research/diagnostics/walk_forward.py
research/run_l2.py
research/run_s2.py
research/run_all.py
```

---

## 5. Test Health

| Metric | Value |
|--------|-------|
| Total tests | 125 |
| Passing | 125 |
| Failing | 0 |
| Errors | 0 |
| Runtime | 1.82 seconds |
| Last run | Verified 2026-04-07 |

### Coverage by area

| Area | Tests | Assessment |
|------|-------|------------|
| Data validation (CHECK-1 to -6) | 20 | Strong |
| Daily-4H alignment (D+1 rule) | 4 | Strong |
| Indicators (EMA, SMA, ATR, volume) | 22 | Strong |
| Regime classifier | 7 | Partial — `classify_regime` only |
| Support detectors (lookahead, debounce) | 17 | Strong |
| L2 strategy (all 5 modes) | 18 | Strong |
| S2 strategy (signal rules, edges) | 17 | Strong |
| Trade accounting (fees, R-multiples) | 20 | Good — `apply_fees_to_trade` gap |
| Backtest engine | 0 | **Gap** |
| Baselines | 0 | **Gap** |
| Diagnostics | 0 | **Gap** |
| Entry points | 0 | **Gap** |

---

## 6. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R-1 | Untracked diagnostic/run files lost before commit | Medium | High | **Commit immediately.** This is the top priority action. |
| R-2 | `run_s2.py` crashes on first research run | High | Medium | Fix the f-string formatting bug in `_evaluate_research_stops` before any Phase 4 work. |
| R-3 | Baselines never run, invalidating L2 attribution | High | High | Wire `run_random_all_bars` and `run_random_macro_matched` into `run_l2.py`. Without baselines, the component attribution diagnostic has no null-hypothesis reference. |
| R-4 | Dependency version mismatch on fresh clone | Medium | Medium | Create `requirements.txt` with version bounds. |
| R-5 | Backtest engine has no direct tests | Low | High | Add an end-to-end synthetic test for `run_l2_backtest` and `run_s2_backtest`. Currently only exercised through strategy-level tests. |
| R-6 | Regime classifier thresholds drift from spec | Low | Medium | Move hardcoded thresholds from `regime.py` to `config/params.py`. |
| R-7 | Phase 5 deployment approach is undecided | Low | Low | Reconcile README (custom bot) vs Phase 5 doc (Freqtrade) before Phase 5 begins. Not blocking for Phase 4. |

---

## 7. Recommended Next Steps (Prioritized)

### Priority 1 — Unblock Phase 4

1. **Commit all untracked files.** `git add research/diagnostics/ research/run_*.py && git commit`. This is non-negotiable — 1,800 LOC of work is at risk.
2. **Push to origin.** `master` is 1 commit ahead; push Rounds 2 and 3 together.
3. **Fix the `run_s2.py` f-string bug** so research runs don't crash.
4. **Wire baseline execution in `run_l2.py`** — import calls exist but are dead code.
5. **Create `requirements.txt`** for reproducible installs.

### Priority 2 — Strengthen test coverage

6. Add a direct test for `apply_fees_to_trade` (test accounting gap).
7. Add a test for `compute_regime_labels` (indicator gap).
8. Add an end-to-end engine test on synthetic data (engine gap).
9. Implement the missing TEST-S2-08 (engine same-bar stop/target for shorts).

### Priority 3 — Code hygiene

10. Clean up unused imports across all files.
11. Centralize research verdict thresholds (currently duplicated in 3 scripts).
12. Move regime classifier magic numbers to `config/params.py`.
13. Add `.pytest_cache/` to `.gitignore`.
14. Create `diagnostics/portfolio.py` if not already present as an untracked file.

### Priority 4 — Infrastructure

15. Set up GitHub Actions CI (run `pytest` on push).
16. Add a linting step (ruff or flake8).
17. Write `docs/Phase_4_Research_Execution.md`.
18. Reconcile Phase 5 deployment documentation.

---

## 8. Appendix: File Inventory

### Production code

| File | LOC |
|------|-----|
| `research/config/params.py` | 125 |
| `research/data/fetch.py` | 224 |
| `research/data/validate.py` | 223 |
| `research/data/align.py` | 96 |
| `research/indicators/trend.py` | 98 |
| `research/indicators/volatility.py` | 53 |
| `research/indicators/volume.py` | 63 |
| `research/indicators/regime.py` | 134 |
| `research/detectors/support.py` | 409 |
| `research/strategies/l2_mvs.py` | 233 |
| `research/strategies/s2_mvs.py` | 202 |
| `research/engine/backtest.py` | 548 |
| `research/accounting/trades.py` | 409 |
| `research/baselines/random_entry.py` | 111 |
| `research/diagnostics/attribution.py` | 168 |
| `research/diagnostics/exits.py` | 204 |
| `research/diagnostics/outliers.py` | 130 |
| `research/diagnostics/periods.py` | 208 |
| `research/diagnostics/regimes.py` | 171 |
| `research/diagnostics/walk_forward.py` | — |
| **Production total** | **~3,809** |

### Test code

| File | LOC |
|------|-----|
| `research/tests/test_data.py` | 206 |
| `research/tests/test_indicators.py` | 394 |
| `research/tests/test_detectors.py` | 315 |
| `research/tests/test_l2.py` | 292 |
| `research/tests/test_s2.py` | 261 |
| `research/tests/test_accounting.py` | 237 |
| **Test total** | **2,259** (37% of codebase) |

### Documentation

| File | Description |
|------|-------------|
| `README.md` | Project overview, vision, roadmap |
| `docs/Phase_1_Evaluation.md` | Strategy hypothesis scoring |
| `docs/Phase_2_Strategy_Spec.md` | Formal strategy rules and thresholds |
| `docs/Phase_2_5_Harness_Spec.md` | Backtesting engine specification |
| `docs/Phase_3_Implementation.md` | File-by-file implementation plan |
| `docs/Phase_5_Deployment.md` | Deployment guide (Freqtrade/Pi) |

---

*End of report.*
