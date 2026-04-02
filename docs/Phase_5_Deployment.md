# Phase 5 — Complete Implementation & Deployment Guide

## For Claude Code: Research Harness → Freqtrade Integration

**Target operator:** Gonzalo — Uruguay
**Target hardware:** Development PC (research) → Raspberry Pi 4 (production)
**Date:** April 2026

---

## 1. What This Document Is

This is the implementation guide for a two-stage crypto trading system:

**Stage 1 — Research Harness (runs on development PC)**
A Python backtesting framework that tests whether two trading strategies (L2 and S2) have genuine statistical edge. It produces a PROMISING/INCONCLUSIVE/REJECT verdict. If the verdict is REJECT, nothing gets deployed. If PROMISING, proceed to Stage 2.

**Stage 2 — Freqtrade Deployment (runs on Raspberry Pi 4)**
Translation of the validated strategies into Freqtrade IStrategy classes, integrated into an existing multi-bot infrastructure with proper config separation, systemd services, and monitoring.

**This document is authoritative for implementation.** The design specifications are in Phase 1–4 documents. This document tells you HOW to build it, WHERE it runs, and in WHAT order.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT PC                                │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              RESEARCH HARNESS (Stage 1)                    │  │
│  │                                                            │  │
│  │  data/ → indicators/ → detectors/ → strategies/ → engine/ │  │
│  │       → accounting/ → diagnostics/ → walk_forward/        │  │
│  │                                                            │  │
│  │  INPUT:  BTC/USDT perp OHLCV (4H + 1D), 2020–2024        │  │
│  │  OUTPUT: PROMISING / INCONCLUSIVE / REJECT                 │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                    │
│                    IF PROMISING                                  │
│                             │                                    │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │         FREQTRADE STRATEGY TRANSLATION (Stage 2a)          │  │
│  │                                                            │  │
│  │  L2_EMA_Pullback.py  — IStrategy class                    │  │
│  │  S2_Support_Breakdown.py — IStrategy class                 │  │
│  │  Freqtrade backtesting validation                          │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                         SCP / TRANSFER
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                    RASPBERRY PI 4                                 │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │            EXISTING FREQTRADE INFRASTRUCTURE               │  │
│  │                                                            │  │
│  │  v1 (ConservadoraBB)     — :8080 — spot    — STABLE       │  │
│  │  v2 (ConservadoraBB_v2)  — :8081 — spot    — FUNCTIONAL   │  │
│  │  v3 (ShortExplorerBB)    — :8082 — futures — BLOCKED      │  │
│  │  v4 (MomentumShortBB)    — :8083 — futures — BLOCKED      │  │
│  │                                                            │  │
│  │  NEW (after validation):                                   │  │
│  │  L2 (EMA_Pullback)       — :8084 — futures — dry_run      │  │
│  │  S2 (Support_Breakdown)  — :8085 — futures — dry_run      │  │
│  │                                                            │  │
│  │  Scripts: telegram_claude, claude_advisor, health_check,   │  │
│  │           trade_learner, weekly_report, kill_monitor (NEW) │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Config scheme: base + private (per bot)                         │
│  Runtime: Docker (after migration) or native                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Pre-Requisites Before Any Code

### On the Development PC

```
Python 3.11+ (3.13 is fine)
pip install pandas numpy ccxt pyarrow pytest
```

No other dependencies. The research harness is deliberately minimal.

### On the Raspberry Pi (existing)

```
Freqtrade 2026.2 stable (already installed)
Python 3.13 in virtualenv
Existing config scheme: base + private
Existing services: freqtrade.service (v1), freqtrade_v2-v4.service
```

### Data Source

```
Exchange: Binance
Symbol: BTC/USDT perpetual contract
Timeframes: 4H and 1D
Date range: 2020-01-01 to present
Fetch method: ccxt (no API key needed for historical OHLCV on Binance)
```

---

## 4. Stage 1 — Research Harness Implementation

### 4.1 Directory Structure

Create this exact structure on the development PC:

```
research/
│
├── config/
│   └── params.py                  # All frozen parameters as dataclasses
│
├── data/
│   ├── fetch.py                   # OHLCV fetcher (ccxt → parquet)
│   ├── validate.py                # Data integrity checks (CHECK-1 through CHECK-6)
│   ├── align.py                   # Daily-4H alignment, regime forward-fill
│   └── raw/                       # Parquet files (gitignored)
│       ├── btc_4h.parquet
│       └── btc_1d.parquet
│
├── indicators/
│   ├── trend.py                   # EMA, SMA, slope
│   ├── volatility.py              # ATR
│   ├── volume.py                  # Volume SMA, relative volume
│   └── regime.py                  # Regime classifier (6 regimes)
│
├── detectors/
│   └── support.py                 # Variant A and Variant B, shared interface
│
├── strategies/
│   ├── l2_mvs.py                  # L2 signal generation, all 5 modes
│   └── s2_mvs.py                  # S2 signal generation, both detectors
│
├── engine/
│   └── backtest.py                # Bar-by-bar loop, trade management, logging
│
├── accounting/
│   └── trades.py                  # TradeRecord, fee model (taker + funding), R-multiple
│
├── diagnostics/
│   ├── attribution.py             # Component attribution (L2)
│   ├── periods.py                 # Period isolation + buy-and-hold correlation
│   ├── exits.py                   # Exit structure isolation (includes Variant F for S2)
│   ├── regimes.py                 # Regime contribution (6 regimes)
│   ├── outliers.py                # Single-trade sensitivity
│   ├── walk_forward.py            # Method A (rolling) + Method B (expanding)
│   └── portfolio.py               # Cross-strategy drawdown correlation
│
├── baselines/
│   └── random_entry.py            # RANDOM_ALL_BARS and RANDOM_MACRO_MATCHED
│
├── tests/
│   ├── test_data.py               # TEST-DATA-01 through TEST-DATA-06
│   ├── test_indicators.py         # TEST-IND-01 through TEST-IND-05
│   ├── test_l2.py                 # TEST-L2-01 through TEST-L2-07c
│   ├── test_s2.py                 # TEST-S2-01 through TEST-S2-08
│   ├── test_accounting.py         # Fee, funding, R-multiple, slippage tests
│   └── test_detectors.py          # Detector lookahead, overlap metric tests
│
├── runs/                          # Created at runtime, one folder per run
│   └── [run_id]/
│       ├── params.json
│       ├── trades_l2.csv
│       ├── trades_s2a.csv
│       ├── trades_s2b.csv
│       ├── signals_l2.csv
│       ├── signals_s2.csv
│       └── reports/
│           ├── attribution_l2.txt
│           ├── period_isolation_l2.txt
│           ├── buy_and_hold_correlation_l2.txt
│           ├── exit_isolation_l2.txt
│           ├── exit_isolation_s2.txt
│           ├── regime_contribution_l2.txt
│           ├── regime_contribution_s2.txt
│           ├── outlier_sensitivity_l2.txt
│           ├── outlier_sensitivity_s2.txt
│           ├── detector_comparison_s2.txt
│           ├── period_isolation_s2.txt
│           ├── walk_forward_l2.txt
│           ├── walk_forward_s2.txt
│           ├── slippage_sensitivity_l2.txt
│           ├── slippage_sensitivity_s2.txt
│           ├── portfolio_correlation.txt
│           └── research_stop_evaluation.txt
│
├── run_l2.py                      # Entry point: runs L2 research pipeline
├── run_s2.py                      # Entry point: runs S2 research pipeline
└── run_all.py                     # Runs both, generates research stop evaluation
```

Total: 30 source files.

### 4.2 Frozen Parameters

All parameters must be defined in `config/params.py` as Python dataclasses and written to `params.json` before any backtest executes.

#### L2Params

```python
@dataclass(frozen=True)
class L2Params:
    # Core MVS
    ema_period: int = 21                    # FROZEN
    macro_sma_period: int = 200             # FROZEN (daily)
    touch_tolerance: float = 0.003          # FROZEN (0.3%)
    stop_atr_multiplier: float = 1.5        # FROZEN
    target_atr_multiplier: float = 2.0      # FROZEN
    atr_period: int = 14                    # FROZEN
    
    # ESS (not used until MVS is PROMISING)
    rsi_period: int = 14                    # FROZEN
    rsi_lower: int = 30                     # FROZEN
    rsi_upper: int = 52                     # FROZEN
    ema_slope_lookback: int = 3             # FROZEN
    prior_move_atr_multiplier: float = 2.5  # FROZEN
    volume_sma_period: int = 20             # FROZEN
    pullback_candles: int = 3               # FROZEN
    
    # Trailing (ESS only)
    breakeven_atr_trigger: float = 1.0      # FROZEN
    trailing_atr_distance: float = 1.5      # FROZEN
```

#### S2Params

```python
@dataclass(frozen=True)
class S2Params:
    # Core MVS
    min_touch_count: int = 3                # FROZEN
    touch_tolerance: float = 0.005          # FROZEN (0.5%)
    lookback_window: int = 60               # SENSITIVITY-ELIGIBLE (test 40, 60, 80)
    min_bounce_atr: float = 1.0             # FROZEN
    min_bars_between_touches: int = 3       # FROZEN
    breakdown_threshold: float = 0.003      # FROZEN (0.3%)
    volume_multiplier: float = 1.5          # FROZEN
    stop_atr_multiplier: float = 0.5        # FROZEN
    target_atr_multiplier: float = 2.0      # FROZEN
    atr_period: int = 14                    # FROZEN
    max_concurrent_trades: int = 1          # FROZEN
    
    # ESS (not used until MVS is PROMISING)
    ema50_context_lookback: int = 10        # FROZEN
    sma200_floor_atr: float = 3.0           # FROZEN
    support_age_min: int = 10               # FROZEN
    low_vol_percentile: float = 0.20        # FROZEN
    time_exit_candles: int = 6              # FROZEN
```

#### DetectorAParams / DetectorBParams

```python
@dataclass(frozen=True)
class DetectorAParams:
    touch_tolerance: float = 0.005          # FROZEN
    min_touch_count: int = 3                # FROZEN
    min_bounce_atr: float = 1.0             # FROZEN
    min_bars_between_touches: int = 3       # FROZEN
    lookback_window: int = 60               # SENSITIVITY-ELIGIBLE
    level_price_calc: str = "median"        # FROZEN

@dataclass(frozen=True)
class DetectorBParams:
    pivot_window: int = 5                   # FROZEN (2 left, 2 right)
    lookahead_boundary: int = 3             # FROZEN — CRITICAL (derived from pivot_window)
    proximity_pct: float = 0.008            # FROZEN
    min_pivot_count: int = 3                # FROZEN
    min_bars_between_pivots: int = 5        # FROZEN
    lookback_window: int = 60               # SENSITIVITY-ELIGIBLE
    level_price_calc: str = "lowest"        # FROZEN
```

#### BacktestParams

```python
@dataclass(frozen=True)
class BacktestParams:
    fee_rate: float = 0.0005                # 0.05% per side (Binance taker)
    slippage_bps: int = 10                  # 10 basis points
    funding_rate_per_settlement: float = 0.0002  # 0.02% per 8H
    data_start: str = "2020-01-01"
    data_end: str = "2024-12-31"
    warmup_bars_4h: int = 1200              # ~200 days for SMA200 daily
    position_size: float = 1.0              # Normalized
    random_seed: int = 42
```

### 4.3 Regime Classifier

Six regimes, applied in this exact priority order (first match wins):

```python
def classify_regime(btc_close, SMA_200, SMA_50, ROC_20, VOL_ratio):
    
    # 1. STRONG_BULL — trending up, low volatility
    if (btc_close > SMA_200 * 1.05 and 
        btc_close > SMA_50 and 
        ROC_20 > 0.10 and 
        VOL_ratio < 1.5):
        return "STRONG_BULL"
    
    # 2. HIGH_VOL_BULLISH — volatile spike, price above SMA200
    #    MUST be before WEAK_BULL to capture euphoric volatility
    if VOL_ratio >= 2.0 and btc_close > SMA_200:
        return "HIGH_VOL_BULLISH"
    
    # 3. HIGH_VOL_BEARISH — volatile crash, price below SMA200
    #    MUST be before BEAR to capture panic crashes
    if VOL_ratio >= 2.0 and btc_close <= SMA_200:
        return "HIGH_VOL_BEARISH"
    
    # 4. WEAK_BULL — above SMA200, moderate momentum
    if btc_close > SMA_200 and ROC_20 > -0.05:
        return "WEAK_BULL"
    
    # 5. BEAR — below SMA200, negative momentum
    if btc_close < SMA_200 and ROC_20 < -0.05:
        return "BEAR"
    
    # 6. TRANSITION — everything else
    return "TRANSITION"
```

Variables:
- `SMA_200` = SMA(daily close, 200)
- `SMA_50` = SMA(daily close, 50)
- `ROC_20` = (close - close[20]) / close[20]
- `VOL_ratio` = ATR(14, daily) / SMA(ATR(14, daily), 60)

### 4.4 L2 Strategy Logic (MVS)

**Core hypothesis:** In a confirmed uptrend, price pulling back to the 21 EMA on 4H and closing bullish has positive expectancy.

**Same-bar confirmation:** Touch and bullish close evaluated on the SAME candle.

```
ENTRY CONDITIONS (all must be true on bar i):
  1. daily_close > SMA_200_daily          [macro filter]
  2. bar_low <= EMA21 * 1.003             [EMA touch]
  3. bar_close > bar_open                 [bullish close — same bar]

ENTRY PRICE:
  entry_price = bar_close
  effective_entry_price = bar_close * (1 + slippage_bps / 10000)

STOP:
  stop_price = EMA21_value * (1 - 0.003) - (1.5 * ATR14)
  NOTE: Stop anchored to EMA, NOT to entry price.

TARGET:
  target_price = entry_price + (2.0 * ATR14)

EXIT PRIORITY (next bar onward):
  If bar_low <= stop_price AND bar_high >= target_price → STOP HIT (conservative)
  If bar_low <= stop_price → STOP HIT
  If bar_high >= target_price → TARGET HIT
  
MAX CONCURRENT TRADES: 1
```

**5 decomposition modes:**

| Mode | What's Active | Purpose |
|---|---|---|
| MODE_RANDOM | No filters, enter every bar | Baseline — exit structure only |
| MODE_MACRO_ONLY | Macro filter only, enter every qualifying bar | Regime selector value |
| MODE_TOUCH_ONLY | EMA touch only, no macro, no confirm | Entry signal isolation |
| MODE_MVS_NO_CONFIRM | Macro + touch, no bullish close | Confirmation value |
| MODE_MVS_FULL | All 3 conditions | The strategy as designed |

### 4.5 S2 Strategy Logic (MVS)

**Core hypothesis:** When a support level (3+ touches on 4H) breaks with high volume, price continues lower.

```
SUPPORT DETECTION (run at bar i using bars [i-60, i-1] ONLY):
  Two variants implemented in parallel — see Phase 2.5 Section 6.
  
ENTRY CONDITIONS (all must be true on bar i):
  1. Active support level exists (3+ touches, debounced)
  2. bar_close < level_price * (1 - 0.003)    [breakdown confirmed]
  3. bar_volume > 1.5 * volume_sma20           [volume confirmation]
     NOTE: volume_sma20 at bar i = mean(volume[i-20 : i]) — excludes bar i

ENTRY PRICE:
  entry_price = bar_close
  effective_entry_price = bar_close * (1 - slippage_bps / 10000)
  NOTE: Short slippage is adverse DOWNWARD.

STOP:
  stop_price = level_price + (0.5 * ATR14)    [ABOVE level for short]

TARGET:
  target_price = entry_price - (2.0 * ATR14)  [BELOW entry for short]

EXIT PRIORITY (next bar onward):
  If bar_high >= stop_price AND bar_low <= target_price → STOP HIT
  If bar_high >= stop_price → STOP HIT
  If bar_low <= target_price → TARGET HIT

MULTIPLE LEVEL CONFLICT: Take highest touch count, then most recent.
MAX CONCURRENT TRADES: 1
```

### 4.6 Fee Model

Applied at exit for every trade (including baselines):

```python
# Taker fees
fee_entry = effective_entry_price * position_size * fee_rate
fee_exit  = exit_price * position_size * fee_rate
total_taker_fee = fee_entry + fee_exit

# Funding rate
holding_hours = (exit_timestamp - entry_timestamp).total_seconds() / 3600
funding_settlements = floor(holding_hours / 8)
funding_cost = funding_settlements * funding_rate_per_settlement * entry_price * position_size

# Total
total_fee = total_taker_fee + funding_cost
net_pnl = gross_pnl - total_fee

# R-multiple (always net)
stop_distance = abs(effective_entry_price - stop_price)
r_multiple_net = net_pnl / stop_distance
```

### 4.7 TradeRecord Schema

Every trade produces a record with these fields:

```python
@dataclass
class TradeRecord:
    trade_id: int
    strategy: str           # 'L2_MVS', 'S2_MVSA', 'S2_MVSB', etc.
    direction: str          # 'LONG' or 'SHORT'
    entry_bar_index: int
    entry_timestamp: datetime
    entry_price: float      # Raw close price (for signal analysis)
    effective_entry_price: float  # Slippage-adjusted (for P&L)
    stop_price: float
    target_price: float
    stop_distance: float
    target_distance: float
    planned_r_ratio: float
    exit_bar_index: int | None
    exit_timestamp: datetime | None
    exit_price: float | None
    exit_reason: str | None  # 'STOP_HIT', 'TARGET_HIT', 'OPEN_AT_END'
    gross_pnl: float | None
    fee_entry: float | None
    fee_exit: float | None
    funding_cost: float | None
    total_fee: float | None
    net_pnl: float | None
    r_multiple_gross: float | None
    r_multiple_net: float | None
    regime: str              # One of 6 regime labels
    mode: str
    mae: float | None        # Max Adverse Excursion (from bar highs/lows)
    mfe: float | None        # Max Favorable Excursion
    # L2-specific
    ema_21_at_entry: float | None
    atr_14_at_entry: float | None
    daily_sma200_at_entry: float | None
    # S2-specific
    support_level_price: float | None
    level_touch_count: int | None
    level_age_bars: int | None
    volume_ratio_at_entry: float | None
    detector_variant: str | None
```

### 4.8 Implementation Order

Follow this exact sequence. Each step has a test gate that must pass before proceeding.

```
STEP 1 — config/params.py
  Define all dataclasses. Implement freeze() → JSON serialization.
  TEST GATE: params.json is writable and human-readable.

STEP 2 — data/fetch.py
  Fetch BTC/USDT perpetual 4H and 1D from Binance via ccxt.
  Save to data/raw/ as Parquet.
  TEST GATE: TEST-DATA-01 through TEST-DATA-06 pass.

STEP 3 — data/validate.py
  Implement CHECK-1 (no duplicate timestamps) through CHECK-6 (monotonicity).
  Raise on failure. Return ValidatedOHLCV on success.
  TEST GATE: All checks pass on saved data.

STEP 4 — indicators/trend.py, volatility.py, volume.py
  EMA(21), SMA(200), ATR(14), Volume SMA(20), EMA slope.
  Convention: indicator.iloc[i] = computed from data[0:i+1].
  NaN for warmup bars.
  TEST GATE: TEST-IND-01 through TEST-IND-05 pass.

STEP 5 — data/align.py
  Align daily indicators to 4H using D+1 rule.
  Daily value from day D available at 4H bars opening on D+1, NOT D.
  TEST GATE: TEST-DATA-04, TEST-IND-05 pass.

STEP 6 — indicators/regime.py
  Implement classify_regime() with 6 regimes in corrected ordering.
  Forward-fill to 4H using same D+1 rule.
  TEST GATE: Known-input test, boundary test, proportion sanity check.

STEP 7 — detectors/support.py (S2 only)
  Implement Variant A (fixed-tolerance clustering) and Variant B (pivot low).
  Pure functions: given bars_slice, return list[SupportLevel].
  CRITICAL: Variant B lookahead boundary j <= i-3 enforced with assertion.
  TEST GATE: TEST-S2-01 through TEST-S2-03, TEST-DETECTORS-01 through 03.

STEP 8 — accounting/trades.py
  TradeRecord dataclass, compute_r_multiple(), apply_fees(),
  compute_funding_cost(), build_trade_log(), compute_summary_stats().
  TEST GATE: TEST-ACCOUNTING-01 through 03, TEST-L2-07, 07b, 07c.

STEP 9 — engine/backtest.py
  Bar-by-bar loop: Phase B (trade management + MAE/MFE update) →
  Phase C (signal generation) → Phase D (trade record).
  Strategy-agnostic: receives strategy_fn, returns BacktestResult.
  TEST GATE: TEST-L2-05, 06, TEST-S2-05 through 07. Lookahead verification.

STEP 10 — strategies/l2_mvs.py, s2_mvs.py
  Signal generation only. No trade management.
  L2: 5 modes (RANDOM through MVS_FULL).
  S2: consumes pre-computed support levels.
  TEST GATE: All L2/S2 unit tests pass. Non-empty trade logs on full data.

STEP 11 — baselines/random_entry.py
  RANDOM_ALL_BARS and RANDOM_MACRO_MATCHED.
  Same stop/target/slippage/funding as L2 MVS.
  TEST GATE: Produces valid BacktestResult.

STEP 12 — diagnostics/ (all 7 files)
  attribution.py, periods.py, exits.py, regimes.py, outliers.py,
  walk_forward.py, portfolio.py.
  Each produces a formatted text report.
  TEST GATE: All reports generate without error.

STEP 13 — run_l2.py, run_s2.py, run_all.py
  Entry points. Write params.json BEFORE any backtest.
  Apply research stop criteria BEFORE reading diagnostic reports.
  TEST GATE: Full pipeline completes. research_stop_evaluation.txt populated.
```

### 4.9 Performance Thresholds (pre-defined, non-negotiable)

#### L2 — PROMISING

```
Total trades ≥ 50
AND profit factor ≥ 1.30
AND win rate ≥ 48%
AND max drawdown ≤ 20%
AND at least 4 of 6 regimes show positive expectancy
AND walk-forward test PF ≥ 1.15 (both Method A AND B)
AND walk-forward test PF > 1.0 in ≥ 60% of windows (both methods)
```

#### S2 — PROMISING

```
Total trades ≥ 40
AND profit factor ≥ 1.25
AND win rate ≥ 44%
AND max drawdown ≤ 25%
AND positive expectancy in BEAR and HIGH_VOL_BEARISH regimes
AND walk-forward test PF ≥ 1.10 (both Method A AND B)
AND walk-forward test PF > 1.0 in ≥ 55% of windows (both methods)
```

#### Research Stop Criteria (immediate halt)

```
STOP-L2-1: MVS PF < 1.10
STOP-L2-2: < 35 trades
STOP-L2-3: MODE_MACRO_ONLY within 0.10 PF of MODE_MVS_FULL
STOP-L2-4: Walk-forward test PF < 0.90 in >60% windows (either method)
STOP-L2-5: Removing best 6-month period drops PF below 1.05
STOP-L2-6: Exit variants A/B/C span > 0.60 PF

STOP-S2-1: MVS PF < 1.05
STOP-S2-2: Detector PF difference > 0.30
STOP-S2-3: < 25 trades
STOP-S2-4: Negative expectancy in BOTH BEAR and HIGH_VOL_BEARISH
STOP-S2-5: Walk-forward test PF < 0.85 in >60% windows (either method)
STOP-S2-6: 2022 accounts for >60% of total net R
STOP-S2-7: PF < 1.0 when 2022 excluded
STOP-S2-8: Variant F PF < 0.80 while primary PF > 1.20
```

**If ANY stop criterion triggers, development halts. Do not proceed to Stage 2.**

---

## 5. Stage 2 — Freqtrade Strategy Translation

**This section is ONLY executed if Stage 1 produces a PROMISING verdict.**

### 5.1 L2 as Freqtrade IStrategy

File: `user_data/strategies/L2_EMA_Pullback.py`

```python
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.persistence import Trade
import talib.abstract as ta
import pandas as pd
from datetime import datetime

class L2_EMA_Pullback(IStrategy):
    """
    L2 — EMA Pullback Long (MVS)
    
    Hypothesis: In a confirmed uptrend (price > daily SMA200),
    price pulling back to the 4H EMA21 and closing bullish
    has positive expectancy.
    
    Validated by research harness run [RUN_ID].
    DO NOT modify parameters without re-running validation.
    """
    
    INTERFACE_VERSION = 3
    
    # Timeframe
    timeframe = '4h'
    
    # Can short = False (L2 is long only)
    can_short = False
    
    # ROI — disabled, using fixed ATR target
    minimal_roi = {"0": 100}  # effectively disabled
    
    # Stoploss — disabled, using custom_stoploss
    stoploss = -0.99  # safety net only
    use_custom_stoploss = True
    
    # Trailing — disabled in MVS, handled by custom logic in ESS
    trailing_stop = False
    
    # Parameters (from validated research harness)
    ema_period = 21
    atr_period = 14
    touch_tolerance = 0.003
    stop_atr_mult = 1.5
    target_atr_mult = 2.0
    
    # Process only new candles
    process_only_new_candles = True
    
    # Number of candles needed
    startup_candle_count = 250  # enough for daily SMA200 alignment
    
    def informative_pairs(self):
        """Need daily BTC data for macro filter."""
        return [("BTC/USDT:USDT", "1d")]
    
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict):
        # 4H indicators
        dataframe['ema21'] = ta.EMA(dataframe, timeperiod=self.ema_period)
        dataframe['atr14'] = ta.ATR(dataframe, timeperiod=self.atr_period)
        
        # Daily SMA200 via informative pair
        # (merged by Freqtrade's informative pair mechanism)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict):
        """
        Same-bar confirmation: touch EMA AND close bullish in same candle.
        """
        dataframe.loc[
            (
                # Macro filter: price above daily SMA200
                (dataframe['daily_sma200'] < dataframe['close']) &
                
                # EMA touch: low within 0.3% of EMA21
                (dataframe['low'] <= dataframe['ema21'] * (1 + self.touch_tolerance)) &
                
                # Bullish close (same bar)
                (dataframe['close'] > dataframe['open']) &
                
                # Indicators valid (past warmup)
                (dataframe['ema21'].notna()) &
                (dataframe['atr14'].notna())
            ),
            'enter_long'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict):
        # Exits handled by custom_stoploss and custom_exit
        return dataframe
    
    def custom_stoploss(self, pair: str, trade: Trade, 
                        current_time: datetime, current_rate: float,
                        current_profit: float, after_fill: bool,
                        **kwargs) -> float:
        """
        Stop anchored to EMA value at entry, NOT to entry price.
        Returns relative stoploss as negative fraction.
        """
        # Retrieve EMA and ATR at entry from custom_info or trade tags
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        # Find the entry candle
        entry_candle = dataframe.loc[
            dataframe['date'] == trade.open_date_utc
        ]
        
        if entry_candle.empty:
            return -0.99  # safety fallback
        
        ema_at_entry = entry_candle['ema21'].values[0]
        atr_at_entry = entry_candle['atr14'].values[0]
        
        # Stop = EMA * (1 - tolerance) - 1.5 * ATR
        stop_price = ema_at_entry * (1 - self.touch_tolerance) - (self.stop_atr_mult * atr_at_entry)
        
        # Convert to relative stoploss
        stoploss = (stop_price / trade.open_rate) - 1.0
        
        return stoploss
    
    def custom_exit(self, pair: str, trade: Trade,
                    current_time: datetime, current_rate: float,
                    current_profit: float, **kwargs):
        """
        Fixed ATR target exit.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        entry_candle = dataframe.loc[
            dataframe['date'] == trade.open_date_utc
        ]
        
        if entry_candle.empty:
            return None
        
        atr_at_entry = entry_candle['atr14'].values[0]
        target_price = trade.open_rate + (self.target_atr_mult * atr_at_entry)
        
        if current_rate >= target_price:
            return "target_hit"
        
        return None
```

**IMPORTANT NOTE:** This is a structural skeleton. The actual implementation must handle:
- `merge_informative_pair` for daily SMA200 alignment (with proper fill method)
- Edge cases where entry candle lookup fails
- The exact alignment rule: daily data from day D available at 4H bars on D+1

### 5.2 S2 as Freqtrade IStrategy

File: `user_data/strategies/S2_Support_Breakdown.py`

S2 is more complex because Freqtrade doesn't natively support "support level detection" as an indicator. The support detection logic must be implemented inside `populate_indicators()`.

Key implementation challenges:
- Support levels must be detected from a rolling window of prior bars only (no lookahead)
- The detection must run on every candle (computationally heavier)
- Volume SMA must exclude current bar
- Multiple level conflict resolution (highest touch count)

This strategy requires `can_short = True` and `trading_mode = futures` in config.

### 5.3 Freqtrade Backtesting Validation

After translating to IStrategy, run Freqtrade's built-in backtester to verify the translation produces similar results to the research harness:

```bash
freqtrade backtesting \
  --strategy L2_EMA_Pullback \
  --timeframe 4h \
  --timerange 20200101-20241231 \
  --config user_data/config_l2.json \
  --config user_data/config_l2.private.json
```

Compare:
- Total trade count (should be within ±10% of harness)
- Profit factor (should be within ±0.15 of harness)
- Win rate (should be within ±3% of harness)

Large discrepancies indicate a translation error.

---

## 6. Stage 2b — Raspberry Pi Deployment

### 6.1 New Config Files

Following the existing base + private scheme:

#### config_l2.json (base — operational)

```json
{
    "bot_name": "L2_EMA_Pullback",
    "trading_mode": "futures",
    "margin_mode": "isolated",
    "max_open_trades": 1,
    "stake_currency": "USDT",
    "stake_amount": 20,
    "available_capital": 100,
    "dry_run": true,
    "dry_run_wallet": 100,
    "timeframe": "4h",
    "exchange": {
        "name": "binance",
        "pair_whitelist": ["BTC/USDT:USDT"],
        "pair_blacklist": []
    },
    "entry_pricing": {
        "price_side": "other",
        "use_order_book": true,
        "order_book_top": 1
    },
    "exit_pricing": {
        "price_side": "other",
        "use_order_book": true,
        "order_book_top": 1
    },
    "api_server": {
        "enabled": true,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8084,
        "verbosity": "error"
    },
    "db_url": "sqlite:///user_data/tradesv3_l2.sqlite",
    "logfile": "user_data/logs/freqtrade_l2.log",
    "internals": {
        "process_throttle_secs": 5
    }
}
```

#### config_l2.private.json (secrets)

```json
{
    "exchange": {
        "key": "YOUR_BINANCE_API_KEY",
        "secret": "YOUR_BINANCE_API_SECRET"
    },
    "telegram": {
        "enabled": true,
        "token": "YOUR_L2_BOT_TOKEN",
        "chat_id": "YOUR_CHAT_ID"
    },
    "api_server": {
        "username": "gonzalo",
        "password": "GENERATE_UNIQUE_PASSWORD",
        "jwt_secret_key": "GENERATE_UNIQUE_JWT",
        "ws_token": "GENERATE_UNIQUE_WS_TOKEN"
    }
}
```

**Same pattern for S2** with `config_s2.json` + `config_s2.private.json`, port 8085, `can_short = true` in strategy.

### 6.2 New Systemd Services

#### freqtrade_l2.service

```ini
[Unit]
Description=Freqtrade L2 EMA Pullback
After=network-online.target

[Service]
Type=simple
User=gonzalo
WorkingDirectory=/home/gonzalo/freqtrade
ExecStart=/home/gonzalo/freqtrade/.venv/bin/freqtrade trade \
    --config user_data/config_l2.json \
    --config user_data/config_l2.private.json \
    --strategy L2_EMA_Pullback
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Same pattern for `freqtrade_s2.service` with S2 config and strategy.

### 6.3 Kill Criteria Monitor

New script: `user_data/kill_monitor.py`

This script runs every 15 minutes (cron) and evaluates the hard kill criteria from Phase 2:

```python
"""
Kill criteria monitor for L2 and S2.
Reads trade history from each bot's API and evaluates:

L2 kills:
  KILL-L2-1: Equity drawdown > 15%
  KILL-L2-2: 8 consecutive losses
  KILL-L2-3: Rolling 30-trade PF < 0.80
  KILL-L2-4: Data quality (missing candles, ATR deviation)
  KILL-L2-5: BTC below SMA200 for 5 consecutive days

S2 kills:
  KILL-S2-1: Equity drawdown > 20%
  KILL-S2-2: 7 consecutive losses
  KILL-S2-3: Rolling 25-trade PF < 0.75
  KILL-S2-4: STRONG_BULL or HIGH_VOL_BULLISH for 10/5 consecutive days
  KILL-S2-5: Funding rate > 0.05% for 5 consecutive 8H periods
  KILL-S2-6: Data quality

If any criterion triggers:
  1. Pause the bot via API (/api/v1/forcesell or /api/v1/stop)
  2. Send Telegram alert
  3. Log the reason
  4. Do NOT auto-resume — manual review required
"""
```

Secrets for this script come from `.env` (existing pattern):

```bash
# .env
L2_API_URL=http://127.0.0.1:8084
L2_API_USER=gonzalo
L2_API_PASS=...
S2_API_URL=http://127.0.0.1:8085
S2_API_USER=gonzalo
S2_API_PASS=...
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### 6.4 Integration with Existing Scripts

#### claude_advisor.py — Add L2/S2

The advisor already queries all bots. Add L2/S2 to the bot list:

```python
BOTS = {
    "v1": {"url": "http://127.0.0.1:8080", "type": "long", "timeframe": "5m"},
    "v2": {"url": "http://127.0.0.1:8081", "type": "long", "timeframe": "5m"},
    "v3": {"url": "http://127.0.0.1:8082", "type": "short", "timeframe": "5m"},
    "v4": {"url": "http://127.0.0.1:8083", "type": "short", "timeframe": "5m"},
    "l2": {"url": "http://127.0.0.1:8084", "type": "long", "timeframe": "4h"},
    "s2": {"url": "http://127.0.0.1:8085", "type": "short", "timeframe": "4h"},
}
```

L2/S2 decision logic follows the same pattern as v1-v4 but with awareness that 4H strategies trade less frequently and have wider stops.

#### health_check.py — Add L2/S2

Add ports 8084/8085 to the health check rotation.

#### trade_learner.py — Add L2/S2

Add `trade_memory_l2.json` and `trade_memory_s2.json`. Claude's analysis for 4H trades should consider regime context (which regime was the trade in?) since this information is available from the kill monitor.

### 6.5 Updated System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Raspberry Pi 4                      │
│                                                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │ Bot v1  │ │ Bot v2  │ │ Bot L2  │ │ Bot S2  │  │
│  │ :8080   │ │ :8081   │ │ :8084   │ │ :8085   │  │
│  │ BB Long │ │ BB Long+│ │EMA Pull │ │Sup Break│  │
│  │  5min   │ │  5min   │ │  4hour  │ │  4hour  │  │
│  │  spot   │ │  spot   │ │ futures │ │ futures │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘  │
│       └────────────┴──────────┴────────────┘       │
│                        │                            │
│    ┌───────────────────┼───────────────────┐       │
│    │                   │                   │       │
│  ┌─▼──────────┐ ┌─────▼─────┐ ┌──────────▼──┐   │
│  │claude_adv. │ │trade_learn│ │kill_monitor │   │
│  │ every hour │ │ every 30m │ │ every 15min │   │
│  └────────────┘ └───────────┘ └─────────────┘   │
│                                                    │
│  ┌────────────────────────────────────────────┐   │
│  │         telegram_claude (24/7)              │   │
│  └────────────────────────────────────────────┘   │
│                                                    │
│  v3/v4: suspended until Docker migration           │
└────────────────────────────────────────────────────┘
```

### 6.6 Port Allocation

| Service | Strategy | Port | Mode | Timeframe |
|---|---|---|---|---|
| freqtrade.service | ConservadoraBB (v1) | 8080 | spot | 5m |
| freqtrade_v2.service | ConservadoraBB_v2 (v2) | 8081 | spot | 5m |
| freqtrade_v3.service | ShortExplorerBB (v3) | 8082 | futures | 5m |
| freqtrade_v4.service | MomentumShortBB (v4) | 8083 | futures | 5m |
| freqtrade_l2.service | L2_EMA_Pullback | 8084 | futures | 4h |
| freqtrade_s2.service | S2_Support_Breakdown | 8085 | futures | 4h |

v3/v4 remain suspended until Docker migration resolves ARM64 runtime issues.
L2/S2 on futures face the same Docker dependency — deploy only after Docker migration.

### 6.7 Crontab Update

```cron
# Existing
0 * * * *    .venv/bin/python user_data/claude_advisor.py
*/30 * * * * .venv/bin/python user_data/trade_learner.py
*/15 * * * * .venv/bin/python user_data/health_check.py
0 9 * * *    .venv/bin/python user_data/weekly_report.py

# New
*/15 * * * * .venv/bin/python user_data/kill_monitor.py
```

---

## 7. Docker Migration (Required for Futures Bots)

The existing v3/v4 bots are blocked by ARM64 runtime issues with async/ccxt/futures. L2 and S2 being futures bots will face the same problem.

### Recommended Approach

```bash
# On the Raspberry Pi
docker pull freqtradeorg/freqtrade:stable

# Run L2 as Docker container
docker run -d \
  --name freqtrade_l2 \
  -v /home/gonzalo/freqtrade/user_data:/freqtrade/user_data \
  -p 8084:8084 \
  freqtradeorg/freqtrade:stable \
  trade \
  --config user_data/config_l2.json \
  --config user_data/config_l2.private.json \
  --strategy L2_EMA_Pullback
```

Docker resolves the ARM64 runtime issue because the container provides a known-good Python + ccxt + aiohttp stack that's tested on ARM64.

Consider using `docker-compose.yml` to manage all futures bots:

```yaml
version: '3'
services:
  freqtrade_l2:
    image: freqtradeorg/freqtrade:stable
    volumes:
      - ./user_data:/freqtrade/user_data
    ports:
      - "8084:8084"
    command: >
      trade
      --config user_data/config_l2.json
      --config user_data/config_l2.private.json
      --strategy L2_EMA_Pullback
    restart: always

  freqtrade_s2:
    image: freqtradeorg/freqtrade:stable
    volumes:
      - ./user_data:/freqtrade/user_data
    ports:
      - "8085:8085"
    command: >
      trade
      --config user_data/config_s2.json
      --config user_data/config_s2.private.json
      --strategy S2_Support_Breakdown
    restart: always
```

---

## 8. Decision Points and Safeguards

### What Blocks Stage 2

Stage 2 does NOT proceed if:
- L2 MVS is REJECT or INCONCLUSIVE
- S2 MVS is REJECT or INCONCLUSIVE
- Any research stop criterion triggers
- Freqtrade backtesting shows >15% PF discrepancy vs harness

### What Blocks Deployment to Pi

Deployment does NOT proceed if:
- Docker is not set up on the Pi (for futures bots)
- Config base/private files are not created
- Kill monitor is not implemented
- Freqtrade dry_run backtesting not validated

### What Blocks Live Trading

Live trading does NOT proceed if:
- Less than 30 dry-run trades on the Pi
- Dry-run performance deviates >25% from backtest
- Any kill criterion has triggered during dry-run
- Capital allocation plan not defined (separate from v1/v2 capital)

---

## 9. Summary: What Claude Code Needs to Do

### On the Development PC (Stage 1)

1. Create the `research/` directory with all 30 files
2. Fetch historical data from Binance (BTC/USDT perp, 4H + 1D, 2020-2024)
3. Implement all components following Steps 1-13 in Section 4.8
4. Run all unit tests (every test must pass before proceeding)
5. Run full backtests: L2 (5 modes + 2 baselines) and S2 (2 detectors)
6. Run walk-forward validation (Method A + B for both strategies)
7. Run sensitivity sweeps (slippage + funding rate)
8. Generate all diagnostic reports
9. Evaluate research stop criteria
10. Produce PROMISING/INCONCLUSIVE/REJECT verdict

### If PROMISING (Stage 2)

11. Translate L2 and S2 to Freqtrade IStrategy classes
12. Run Freqtrade backtesting to validate translation
13. Create config_l2.json, config_l2.private.json, config_s2.json, config_s2.private.json
14. Create systemd service files
15. Create kill_monitor.py
16. Update claude_advisor.py, health_check.py, trade_learner.py
17. Create docker-compose.yml for futures bots

### Transfer to Raspberry Pi

18. SCP strategy files, configs, services, scripts to the Pi
19. Set up Docker (if not already done)
20. Start dry_run
21. Monitor for 2+ weeks before any live capital decision

---

## 10. File Reference: What Goes Where on the Pi

```
/home/gonzalo/freqtrade/
├── user_data/
│   ├── strategies/
│   │   ├── ConservadoraBB.py          # existing v1
│   │   ├── ConservadoraBB_v2.py       # existing v2
│   │   ├── ShortExplorerBB.py         # existing v3 (suspended)
│   │   ├── MomentumShortBB.py         # existing v4 (suspended)
│   │   ├── L2_EMA_Pullback.py         # NEW — from research harness
│   │   └── S2_Support_Breakdown.py    # NEW — from research harness
│   ├── config.json                    # v1 base
│   ├── config_v1.private.json         # v1 secrets
│   ├── config_v2.json                 # v2 base
│   ├── config_v2.private.json         # v2 secrets
│   ├── config_v3.json                 # v3 base (suspended)
│   ├── config_v3.private.json         # v3 secrets
│   ├── config_v4.json                 # v4 base (suspended)
│   ├── config_v4.private.json         # v4 secrets
│   ├── config_l2.json                 # NEW — L2 base
│   ├── config_l2.private.json         # NEW — L2 secrets
│   ├── config_s2.json                 # NEW — S2 base
│   ├── config_s2.private.json         # NEW — S2 secrets
│   ├── logs/
│   │   ├── freqtrade.log             # v1
│   │   ├── freqtrade_v2.log          # v2
│   │   ├── freqtrade_l2.log          # NEW
│   │   └── freqtrade_s2.log          # NEW
│   ├── tradesv3.sqlite               # v1
│   ├── tradesv3_v2.sqlite            # v2
│   ├── tradesv3_l2.sqlite            # NEW
│   ├── tradesv3_s2.sqlite            # NEW
│   ├── trade_memory_v1.json
│   ├── trade_memory_v2.json
│   ├── trade_memory_l2.json          # NEW
│   ├── trade_memory_s2.json          # NEW
│   ├── claude_advisor.py             # UPDATED — add L2/S2 bots
│   ├── trade_learner.py              # UPDATED — add L2/S2
│   ├── health_check.py               # UPDATED — add ports 8084/8085
│   ├── kill_monitor.py               # NEW — kill criteria for L2/S2
│   ├── telegram_claude.py            # existing
│   ├── weekly_report.py              # UPDATED — add L2/S2
│   └── .env                          # UPDATED — add L2/S2 credentials
├── docker-compose.yml                # NEW — for futures bots
└── .venv/                            # existing virtualenv
```

---

*This document is complete. Implementation proceeds file by file, test by test, in the exact order defined. No step is skipped. No parameter is changed after backtesting begins.*
