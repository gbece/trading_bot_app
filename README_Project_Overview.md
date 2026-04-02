# Crypto Trading Research & Execution System

## Project Overview

**Author:** Gonzalo — Uruguay
**Started:** March 2026
**Status:** Design complete, implementation pending

---

## What This Is

This is a complete system for researching, validating, and executing cryptocurrency trading strategies. It is designed around one principle: **never risk capital on a strategy that hasn't been rigorously tested for genuine statistical edge.**

The system has two layers:

**Research layer** — An offline backtesting harness that takes a trading hypothesis, runs it against 4+ years of historical data, decomposes where the apparent edge comes from, tests whether it survives out-of-sample validation, and produces a verdict: PROMISING, INCONCLUSIVE, or REJECT. If the verdict is REJECT, nothing gets built. The research layer has no connection to any exchange and no ability to place orders. It exists to prevent you from trading strategies that don't work.

**Execution layer** — A minimal live trading engine that takes validated strategies and runs them in real-time on Binance across a whitelist of validated pairs. It reads candles, computes indicators, evaluates signals, places orders, manages positions (with aggregate exposure limits), enforces kill criteria, and reports via Telegram. It only gets built for strategies that pass the research layer. It is deliberately simple because the hard work (signal logic, risk management rules, regime classification) is already validated in the research layer.

The two layers share the same strategy logic, the same parameters, and the same regime classifier. The execution layer is the research harness with a Binance connection and a 4-hour heartbeat.

---

## Why Not Freqtrade

This system was originally planned to run on Freqtrade. The decision to build a custom system instead was made for these reasons:

**What Freqtrade gave us:** A quick start with 4 bots running within days. A web UI. Telegram integration out of the box. Community support.

**What Freqtrade cost us:** ARM64 runtime crashes on futures that we couldn't fix. Opaque internals — when something breaks in Freqtrade's async stack, you're debugging someone else's framework, not your strategy. Dependency on their ccxt version, their aiohttp version, their release cycle. 90% of Freqtrade's features (hyperopt, multi-pair scanning, FreqUI, pairlist handlers, advanced order types) are irrelevant for a system that trades one pair on 4H candles with one position at a time.

**What we actually need for execution:** Read a 4H candle from Binance every 4 hours. Compute 3 indicators (EMA, ATR, SMA). Evaluate 3 entry conditions. Place a market order. Set a stop and target. Check every 4 hours if either was hit. Send a Telegram message. That's ~500 lines of Python, not a framework.

**The tradeoff:** We lose Freqtrade's built-in backtester and FreqUI. But our research harness is a better backtester (it has component decomposition, regime segmentation, walk-forward validation, and exit isolation that Freqtrade doesn't). And a dashboard can be built later if needed — it's a nice-to-have, not a requirement.

---

## The Two Strategies Being Tested

### L2 — EMA Pullback Long

**Hypothesis:** In a confirmed uptrend (BTC above daily 200 SMA), price pulling back to the 4H 21 EMA and closing bullish has positive expectancy on the subsequent move.

**Mechanics:** When price dips to a rising moving average in a bull market and bounces within a single 4H candle, that's institutional dip-buying meeting dynamic support. The stop is anchored to the EMA (structural), not to the entry price (arbitrary). The target is 2× ATR — a fixed mechanical exit.

**Why this might work:** EMA pullbacks in uptrends have a genuine mechanical basis — trend-following capital accumulates at predictable levels. The macro filter (200 SMA) prevents trading this pattern in bear markets where it fails. Multi-pair operation increases trade frequency — a pullback to EMA21 might fire on ETH while BTC is flat, capturing opportunities across the market.

**Why this might not work:** The entire edge might be "being long crypto during bull markets" with a complex entry mechanism that adds no value over buying at any random point. The research harness is specifically designed to test this by comparing the strategy against random entries in the same regime windows. Additionally, altcoins are more volatile and less liquid than BTC — the same strategy may behave differently on each pair.

### S2 — Support Breakdown Short

**Hypothesis:** When a clearly established horizontal support level (touched 3+ times on 4H) breaks down on a high-volume candle close, price tends to continue lower.

**Mechanics:** Support levels are where buyers have repeatedly stepped in. When that level breaks with volume, the buyers who were defending it become sellers (stop-outs), creating a cascade. The strategy enters short at the breakdown candle close with a tight stop above the broken level.

**Why this might work:** Stop cascades below support are a real market microstructure phenomenon. Volume confirmation filters out thin/fake breakdowns.

**Why this might not work:** The tight stop (0.5× ATR) may be the source of apparent edge rather than the signal itself — it selects which breakdowns happen to not retrace, not which breakdowns are genuine. The research harness tests this with a constant-R:R variant at wider stops.

---

## How the Research Works

The research harness is not a simple backtester. It's a falsification framework. Its job is to make it easy to REJECT a strategy, not easy to CONFIRM it.

### What makes it different from a normal backtest

**Component decomposition.** L2 is run in 5 modes: random entry, macro filter only, EMA touch only, touch + macro (no confirmation), and full MVS. By comparing performance across modes, you can see whether the edge comes from the entry signal, the regime filter, or just the stop/target structure. If "macro filter only" performs as well as the full strategy, the EMA touch adds no value — you're just trading the bull market.

**Two support detectors.** S2 is run with two completely different algorithms for detecting support levels. If performance varies dramatically between them, the edge is in the detection algorithm's parameters, not in the breakdown hypothesis. That's a red flag for overfitting.

**Exit structure isolation.** The same entry signals are tested with 6 different exit configurations (tight stops, wide stops, time exits, hold-and-pray, and a constant-R:R variant). If performance is fragile to exit choice, there's no genuine entry edge.

**Walk-forward validation.** Two methods — rolling windows and expanding windows — test whether the strategy works out of sample, not just in-sample. Both must pass for PROMISING.

**Regime segmentation.** Every trade is tagged with one of 6 market regimes. If a strategy only works in one regime, it's a regime-timing strategy, not an entry-signal strategy. That requires perfect regime identification in real time, which is much harder than it looks on historical data.

**Research stop criteria.** Pre-defined conditions that halt further development. If the core hypothesis fails, no amount of filter-adding can rescue it. These are defined before any backtest runs and cannot be changed after seeing results.

### What the harness produces

For each strategy: a complete diagnostic package including aggregate performance, performance by regime, walk-forward results, component attribution, period isolation, exit isolation, outlier sensitivity, and a buy-and-hold correlation check. Plus a binary verdict: PROMISING or not.

### Cross-asset validation

The research follows a tiered approach:

**Tier 1 — Primary validation on BTC/USDT.** BTC is the most liquid, most data-rich crypto asset. If the strategy has no edge on BTC, it won't have edge on alts (which are noisier, thinner, and more manipulated). All Phase 2/2.5 thresholds (PROMISING/REJECT) are evaluated on BTC first.

**Tier 2 — Cross-validation on major pairs.** If BTC passes PROMISING, the same strategy (same parameters, no re-optimization) is tested on ETH/USDT, SOL/USDT, and 3-5 other high-volume perpetual pairs. This is NOT optimization — parameters are frozen from the BTC run. It answers: is the edge asset-specific or structural?

**Tier 3 — Whitelist construction.** A pair is added to the execution whitelist ONLY if it independently shows PF > 1.10 with the frozen BTC parameters. Pairs that fail are excluded. This prevents the illusion of diversification — trading 10 pairs where 7 lose money dilutes the edge from the 3 that work.

**What stays constant across all pairs:** Strategy parameters, regime classifier (always BTC-anchored), fee model, slippage assumptions. **What varies:** The OHLCV data. Nothing else. If you re-optimize parameters per pair, you've overfitted to each asset's history.

---

## How the Execution Works (if strategies pass)

The execution layer is built ONLY for strategies that receive a PROMISING verdict. It consists of:

**A candle reader** that fetches the latest 4H candles from Binance for all whitelisted pairs every 4 hours via ccxt.

**An indicator engine** — identical to the research harness. Same EMA, ATR, SMA computations, same regime classifier (BTC-anchored for all pairs), same parameters.

**A signal evaluator** — identical to the research harness. Same entry conditions, same same-bar confirmation logic. Evaluates each whitelisted pair independently.

**An order manager** that places market orders on Binance when a signal fires. Sets stop-loss and take-profit orders. Tracks open positions across all pairs.

**A position manager** that enforces aggregate risk limits:
- Maximum 2-3 simultaneous open positions (total, not per pair)
- No new position if it would create correlated exposure: if the 30-day correlation between the new pair and any existing open position pair exceeds 0.85, the signal is skipped
- Capital allocation: each position uses a fixed stake amount, total exposure never exceeds available capital
- If L2 has a long open on ETH and another L2 signal fires on SOL, the position manager checks correlation before allowing the second trade

**A kill monitor** that evaluates hard kill criteria every cycle: drawdown limits, consecutive loss streaks, profit factor degradation, regime overrides, funding rate extremes. Kill criteria are evaluated on the aggregate portfolio (all pairs combined), not per pair individually. If any criterion triggers, the system stops ALL trading and sends a Telegram alert. Manual review required before resuming.

**A Telegram reporter** that sends trade notifications, daily summaries, and kill alerts.

The execution layer runs as a single Python process with a 4-hour loop. No web framework, no database beyond a JSON trade log, no UI. It scans all whitelisted pairs each cycle, evaluates signals, manages positions with aggregate limits, and enforces kill protection.

---

## Infrastructure

### Development (your PC)

The research harness runs here. It needs Python 3.11+, pandas, numpy, ccxt (for data fetching only), and pytest. No exchange credentials needed — it works on downloaded historical data.

### Production (Raspberry Pi 4)

The execution layer runs here. It needs Python 3.11+, ccxt (for live trading), and network access to Binance. It runs as a systemd service with auto-restart.

**Existing infrastructure on the Pi:**
- Freqtrade bots v1 (stable, spot) and v2 (functional, spot) — these can continue running independently
- Freqtrade bots v3/v4 (futures, blocked by ARM64 runtime) — suspended
- telegram_claude, claude_advisor, health_check, trade_learner — existing monitoring scripts
- Config scheme: base + private file separation for secrets
- `.env` for script credentials

The new execution layer coexists with the existing Freqtrade bots. Different ports, different processes, different strategies, different timeframes (4H vs 5m). No conflict.

### GitHub

Single repository with this structure:

```
crypto-research/
│
├── README.md                      ← You are here
│
├── research/                      ← Research harness (runs on PC only)
│   ├── config/
│   ├── data/
│   │   └── raw/                   ← Per-pair Parquet files:
│   │       ├── BTCUSDT_4h.parquet
│   │       ├── BTCUSDT_1d.parquet
│   │       ├── ETHUSDT_4h.parquet ← Added in Tier 2 cross-validation
│   │       ├── ETHUSDT_1d.parquet
│   │       └── ...
│   ├── indicators/
│   ├── detectors/
│   ├── strategies/
│   ├── engine/
│   ├── accounting/
│   ├── diagnostics/
│   ├── baselines/
│   ├── tests/
│   ├── runs/                      ← Backtest results (committed as research record)
│   │   ├── [run_id]_BTCUSDT/     ← Tier 1: primary validation
│   │   ├── [run_id]_ETHUSDT/     ← Tier 2: cross-validation
│   │   ├── [run_id]_SOLUSDT/     ← Tier 2: cross-validation
│   │   └── whitelist_report.txt  ← Which pairs passed, which failed
│   ├── run_l2.py
│   ├── run_s2.py
│   └── run_all.py
│
├── execution/                     ← Live trading engine (runs on Pi)
│   ├── config/
│   │   ├── settings.py            ← Operational parameters + whitelist (committed)
│   │   └── secrets.example.py     ← Template for secrets (committed)
│   ├── core/
│   │   ├── candle_reader.py       ← Binance candle fetcher (all whitelisted pairs)
│   │   ├── indicators.py          ← Same computations as research/
│   │   ├── regime.py              ← Same classifier as research/ (BTC-anchored)
│   │   ├── signals.py             ← Same signal logic as research/
│   │   ├── order_manager.py       ← Binance order placement
│   │   └── position_manager.py    ← Aggregate exposure limits + correlation check
│   ├── monitoring/
│   │   ├── kill_monitor.py        ← Kill criteria (aggregate portfolio)
│   │   ├── telegram_bot.py        ← Notifications and alerts
│   │   └── health_check.py        ← Process health monitoring
│   ├── logs/                      ← Trade logs, signal logs (gitignored)
│   ├── main.py                    ← Entry point: 4-hour loop over all pairs
│   └── requirements.txt
│
├── docs/                          ← All specification documents
│   ├── Phase_1_Evaluation.md
│   ├── Phase_2_Strategy_Spec.md
│   ├── Phase_2_5_Harness_Spec.md
│   ├── Phase_3_Implementation.md
│   └── Phase_5_Deployment.md
│
├── .gitignore                     ← secrets, .env, raw data, __pycache__
└── LICENSE
```

**What goes to GitHub:** All source code, all documentation, backtest results (as research record), config templates. **What never goes to GitHub:** API keys, Telegram tokens, `.env`, private config files, raw OHLCV data files (too large, easily re-downloaded).

---

## Project Phases

The project is organized into phases. Each phase is a self-contained document with its own scope. They are designed to be tackled one at a time, in order.

### Phase 1 — Evaluation Layer
**Status:** Complete
**What it does:** Evaluates 6 strategy hypotheses (3 long, 3 short) across 6 criteria each. Produces scores, selects the two best (L2 and S2), rejects the rest with documented reasoning. Identifies ghost edges — ways each strategy could appear profitable without genuine edge.
**Key output:** L2 selected as long strategy. S2 selected as short strategy. S1 rejected (insufficient sample size). L3 rejected (execution sensitivity too high).

### Phase 2 — Strategy Specification
**Status:** Complete
**What it does:** Defines the exact rules for L2 and S2, both in Minimal Viable Spec (MVS — 4 rules, no filters) and Enhanced Spec (ESS — additional filters tested only if MVS passes). Defines the 6-regime classifier. Defines performance thresholds (PROMISING/INCONCLUSIVE/REJECT). Defines hard kill criteria for live trading.
**Key output:** Frozen parameter values. Pre-defined success/failure thresholds. Kill criteria.

### Phase 2.5 — Research Harness Specification
**Status:** Complete
**What it does:** Specifies the bar-by-bar backtesting logic, lookahead prevention rules, support detection algorithms (2 variants), fee model (taker + funding rate + slippage), unit test plan (30+ tests), diagnostic output formats (7 types), and research stop criteria.
**Key output:** Complete specification for the backtesting engine. Every computation defined to the level of "which index of which array."

### Phase 3 — Implementation Plan
**Status:** Complete
**What it does:** Translates Phase 2.5 into a file-by-file, function-by-function implementation plan with 13 steps, test gates between each step, and readiness checklists.
**Key output:** Exact file structure. Exact implementation order. Exact test gate criteria.

### Phase 4 — Research Execution
**Status:** Not started
**What it does:** Actually implement and run the research harness. Fetch data, run backtests, generate diagnostics, evaluate against thresholds, produce PROMISING/REJECT verdict.
**Key output:** The verdict. All diagnostic reports committed to GitHub as research record.

### Phase 5 — Execution Layer (conditional)
**Status:** Not started. Only proceeds if Phase 4 produces PROMISING.
**What it does:** Build the minimal live trading engine. Candle reader, signal evaluator, order manager, kill monitor, Telegram integration. Deploy to Raspberry Pi.
**Key output:** A running bot that executes validated strategies with kill protection.

---

## How to Use This with Claude Code

### Round 1 — Data Pipeline

Tell Claude Code to implement:
- `research/config/params.py` — all frozen parameters
- `research/data/fetch.py` — download BTC/USDT perp 4H + 1D from Binance
- `research/data/validate.py` — all 6 data integrity checks
- `research/data/align.py` — daily-to-4H alignment with D+1 rule
- `research/indicators/` — EMA, SMA, ATR, volume SMA, regime classifier
- `research/tests/test_data.py` and `research/tests/test_indicators.py`

**Verify:** Data downloads correctly. All CHECK-1 through CHECK-6 pass. Indicators match manually computed values. Regime classifier produces 6 labels in correct proportions. Daily alignment uses D+1 rule.

**Push to GitHub.** This is a checkpoint.

### Round 2 — Backtest Engine

Tell Claude Code to implement:
- `research/detectors/support.py` — Variant A and Variant B
- `research/strategies/l2_mvs.py` — 5 modes
- `research/strategies/s2_mvs.py` — both detectors
- `research/engine/backtest.py` — bar-by-bar loop
- `research/accounting/trades.py` — TradeRecord, fees, R-multiples
- `research/baselines/random_entry.py`
- All remaining tests

**Verify:** Unit tests pass. Trade logs are non-empty. Stop/target math is correct for both long and short. Fee model includes taker + funding + slippage. MAE/MFE tracking works. Lookahead verification passes.

**Push to GitHub.** Second checkpoint.

### Round 3 — Diagnostics & Verdict (BTC)

Tell Claude Code to implement:
- `research/diagnostics/` — all 7 diagnostic files
- `research/run_l2.py`, `research/run_s2.py`, `research/run_all.py`
- Walk-forward validation (Method A + Method B)
- Sensitivity sweeps (slippage, funding rate)

**Run everything on BTC/USDT.** Evaluate against PROMISING thresholds and research stop criteria.

**Push results to GitHub.** This is the Tier 1 research record.

**If REJECT:** Stop. The strategies don't have edge on the cleanest asset in crypto. Multi-pair won't save them.

### Round 3b — Cross-Asset Validation (if BTC is PROMISING)

Tell Claude Code to:
- Download 4H + 1D data for ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, and 3-4 other high-volume perpetual pairs
- Run the SAME harness with the SAME frozen parameters (no re-optimization) on each pair
- For each pair, report: total trades, PF, win rate, max drawdown
- A pair passes cross-validation if PF > 1.10 with frozen BTC parameters
- Generate `whitelist_report.txt`: which pairs passed, which failed, recommended whitelist

**Push results to GitHub.** This is the Tier 2 research record.

**The whitelist is the final output.** Only pairs that pass are included in the execution layer.

### Round 4 — Execution Layer (only if PROMISING + whitelist built)

Tell Claude Code to implement:
- `execution/` — the live trading engine
- Candle reader (fetches all whitelisted pairs each cycle)
- Indicator engine, signal evaluator (per pair, same logic as harness)
- Order manager (Binance placement, stop/target management)
- Position manager (max 2-3 simultaneous positions, correlation check, capital allocation)
- Kill monitor (aggregate portfolio evaluation)
- Telegram reporter
- systemd service file

**Push to GitHub.** Pull on the Pi. Configure secrets (API keys, Telegram token — never in the repo). Start dry_run with the validated whitelist.

The execution layer settings file includes the whitelist:
```python
# execution/config/settings.py
WHITELIST = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"]  # from Tier 2 validation
MAX_OPEN_POSITIONS = 2
CORRELATION_THRESHOLD = 0.85  # skip signal if correlated with existing position
STAKE_AMOUNT = 20  # USDT per position
```

---

## What Success Looks Like

**If the research says REJECT on BTC:** Success. You spent zero real capital on strategies that don't work. The framework is reusable — test different hypotheses with the same infrastructure.

**If BTC is PROMISING but most altcoins fail cross-validation:** Partial success. You have a validated BTC-only (or BTC+ETH) strategy. The whitelist is small, but the edge is confirmed. Trade fewer pairs with higher confidence.

**If BTC is PROMISING and 4+ pairs pass cross-validation:** Full success. You have a validated multi-pair strategy with a researched whitelist, running on infrastructure you fully control, with a complete research record documenting why you believe each pair has edge.

**If research says PROMISING but dry-run diverges:** The harness revealed something about execution reality (slippage, timing, exchange behavior, pair-specific liquidity) that backtesting couldn't capture. Investigate before risking capital. Remove pairs where dry-run diverges significantly.

In all cases, you have a GitHub repository with a complete, documented research and trading system that you can extend, share, or audit at any point.

---

## Constraints and Honest Limitations

**Capital is small.** $405 USDT means each trade risks ~$3-5. At this scale, fees (taker + funding) consume a meaningful percentage of each trade's P&L. The research harness models this explicitly — if slippage sensitivity shows the edge disappears at 15 bps, the strategy isn't tradeable at this scale. With multi-pair execution and max 2-3 simultaneous positions, the capital is spread thin — each position might use $20-30, leaving little margin for drawdowns.

**Hardware is limited.** The Raspberry Pi 4 with 4GB RAM can run the execution layer comfortably (it's a 4-hour loop scanning a whitelist of pairs), but running the full research harness on it would be slow. Research runs on your PC.

**Correlation risk in multi-pair.** In crypto, when BTC drops, most altcoins drop harder. Having 3 long positions open in 3 different altcoins during a sudden selloff is NOT diversification — it's concentrated exposure to a single event. The position manager's correlation check (0.85 threshold) mitigates this, but doesn't eliminate it. In a true panic (March 2020, May 2021, November 2022), correlations go to 1.0 and all positions lose simultaneously. The kill criteria (aggregate drawdown limit) are the last line of defense.

**Altcoin data quality varies.** BTC/USDT has clean, continuous 4H data from 2020 onward. Smaller altcoins may have gaps, delistings, low-liquidity periods, or structural breaks (token upgrades, chain splits). The data validation layer (CHECK-1 through CHECK-6) catches some of this, but pairs with poor data quality should be excluded from the whitelist rather than fixed with interpolation.

**Two strategies.** L2 and S2 are the only strategies in v1. If both are rejected, the framework can test new hypotheses, but the strategies themselves would need to be re-designed from Phase 1.

**This is not financial advice.** This is a research and engineering project. The system is designed to be honest about whether strategies work — that honesty might tell you they don't.

---

*This document is the entry point. Read this first. Then read the phases in order. Then implement with Claude Code, one round at a time.*
