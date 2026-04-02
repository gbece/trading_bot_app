Phase 2.5 — Research Harness Specification

1. Research Harness Goals
The purpose of this harness is falsification, not optimization. Every design decision must serve one of the following goals and no others:
Goal 1 — Test whether the core hypothesis has edge.
The MVS contains the minimum rules needed to express the hypothesis. If the MVS has no edge, the hypothesis is rejected. The harness must make rejection easy to see, not hard to find.
Goal 2 — Decompose where apparent edge comes from.
A profitable backtest is not evidence of edge. It is a starting point for asking: which component produced the profit? Is it the entry logic, the exit logic, the regime filter, or a single exceptional period? The harness must answer this question with structured outputs, not manual inspection.
Goal 3 — Detect lookahead bias before it contaminates results.
Lookahead bias is the most common reason a backtest shows edge that does not exist. The harness must be designed so that lookahead is structurally impossible, not merely avoided by convention.
Goal 4 — Produce results that can be compared across variants.
The two support detection algorithms for S2 and the MVS/ESS comparison for L2 require a harness that produces consistent, comparable outputs. Every run must use the same performance reporting format.
Goal 5 — Establish a research record.
Every parameter, every design decision, and every result must be logged before the next run begins. The harness must enforce this by writing a parameter snapshot to disk before executing any backtest. If the parameter snapshot cannot be recovered, the results cannot be trusted.
What this harness explicitly does not do:

No live or paper trading integration
No exchange API connectivity
No order management
No position sizing beyond fixed fractional (for R calculation only)
No production logging infrastructure
No web interface or dashboard
No alerting or notification system
No multi-asset portfolio logic
No concurrent position management

This harness runs on historical OHLCV data stored as local CSV or Parquet files. It produces CSV and JSON outputs. That is its entire scope.

2. MVS-Only Test Scope
The harness implements exactly two strategies in their MVS form. Nothing else is implemented until both MVS backtests are complete and evaluated against the PROMISING/INCONCLUSIVE/REJECT thresholds defined in Phase 2.
In scope for this harness:
ItemIn ScopeNotesL2 MVS backtestYes4 rules only as definedS2 MVS backtestYes4 rules only plus 2 detection variantsL2 ESS backtestNoOnly after MVS is PROMISINGS2 ESS backtestNoOnly after MVS is PROMISINGComponent decompositionYesRegime filter, entry logic, exit logic attributionWalk-forward validationYesBoth Method A (rolling) and Method B (expanding) required for PROMISING thresholdParameter sensitivity sweepYes±20% of fixed parameters + slippage sweep (0/5/10/15 bps) + funding rate sweep (0.01/0.02/0.05%)Optimization / grid searchNoExplicitly forbidden in this harnessMulti-asset testingNoBTC/USDT only in v1 researchAltcoin validationNoDeferred to post-PROMISING confirmationExecution simulationMinimal-plusClose-of-bar entry with slippage adjustment (10 bps) and funding rate cost model (0.02% per 8H settlement). Not a full execution simulator — no order book modeling, no partial fills.
Scope boundary enforcement:
The harness directory structure must reflect this scope. If a file does not belong to the above scope, it must not exist in the research harness directory. This is not pedantry — scope creep in a research harness is how production architecture gets built on an unvalidated foundation.

3. Data Requirements
3.1 Required Input Data
For L2 (EMA Pullback Long):
ColumnTimeframeTypeRequired forNotestimestamp4Hdatetime (UTC, timezone-aware)All calculationsMust be exchange time. No local timezone conversion.open4Hfloat64Confirmation candle checkhigh4Hfloat64Stop managementlow4Hfloat64EMA touch detectionclose4Hfloat64All calculationsvolume4Hfloat64ESS only — not used in MVSInclude in dataset for forward compatibilitytimestamp1Ddatetime (UTC)Macro filterMust be aligned separatelyclose1Dfloat64200 SMA calculation
For S2 (Support Breakdown Short):
ColumnTimeframeTypeRequired forNotestimestamp4Hdatetime (UTC, timezone-aware)All calculationsopen4Hfloat64Entry price referencehigh4Hfloat64Stop management, touch detection upper boundlow4Hfloat64Touch detection primary signalclose4Hfloat64Breakdown confirmation, entry pricevolume4Hfloat64Volume confirmation filterCore rule in MVStimestamp1Ddatetime (UTC)Regime classificationclose1Dfloat64BTC regime SMA calculationshigh1Dfloat64BTC regime ATRlow1Dfloat64BTC regime ATR
Data source specification:

Exchange: Binance — **BTC/USDT perpetual contract** (per Phase 1 Instrument Type Declaration). Spot data must not be used. Perpetual and spot candles differ during funding settlement periods and high-leverage liquidation events.
Source method: ccxt historical OHLCV fetch, saved to local Parquet files
Minimum history required: 2020-01-01 to present (captures 2020 COVID crash, 2021 bull, 2022 bear, 2023 recovery, 2024 bull)
Maximum gap allowed: 1 missing candle per 24H period. More than this requires data quality review before backtesting.
Data must be fetched once and frozen for the research period. No live data updates during research. If data is refreshed, all prior results are invalidated and must be re-run.

3.2 Preprocessing Steps
These steps are executed once before any strategy logic runs. They are not part of the bar-by-bar loop.
Step 1 — Data integrity checks (fail fast):
CHECK-1: No duplicate timestamps
CHECK-2: No gaps larger than 2 consecutive candles (8H on 4H data)
CHECK-3: No OHLC integrity violations (high >= low, high >= open, high >= close, 
          low <= open, low <= close)
CHECK-4: No zero or negative volume candles (flag and remove)
CHECK-5: No price values that deviate by more than 50% from the prior candle 
          (likely data error — log and investigate before proceeding)
CHECK-6: Timestamp monotonicity (each timestamp strictly greater than prior)
If any check fails, the harness must raise an exception and halt. It must not silently continue with corrupted data.
Step 2 — Daily and 4H alignment:
The daily SMA used in L2's macro filter must be aligned to each 4H candle by forward-filling the daily value. Specifically: the daily SMA value available at 4H candle with timestamp T is computed from all daily candles with close timestamp strictly before T's calendar date. A daily candle from 2024-01-15 is not available to a 4H candle opening at 2024-01-15 00:00 UTC — it is available from 2024-01-16 00:00 UTC onward. This alignment must be explicitly implemented and tested.
Step 3 — Indicator pre-computation:
All indicators are computed on the full dataset before the bar-by-bar loop begins. This is an efficiency choice, but it requires careful handling:

EMA must be computed using a standard recursive formula with a proper warmup period. The first period - 1 values are NaN and must not be used in signal evaluation.
ATR must similarly have a warmup period of at least 14 bars.
SMA(200) on daily data requires at least 200 daily bars of history before any signal can fire.
All indicator values for bar N must be computed from bars 0 through N only. If using pandas, this means using .shift() correctly — the indicator value at index N is aligned to bar N, meaning it was computed from data up to and including bar N. The signal evaluation then uses indicator.iloc[i] at bar i, which is the value available after bar i closes.

Step 4 — Regime labeling:
Run the regime classification function on the full daily dataset and produce a daily regime label series. Forward-fill to 4H granularity using the same alignment rule as Step 2.
Step 5 — Parameter snapshot:
Before any strategy logic runs, write a JSON file to research/runs/[run_id]/params.json containing every parameter value used in the run. The run_id is a timestamp string (e.g., 20240115_143022). This file must be written before the backtest executes and must not be modified afterward. If it cannot be written, halt execution.

4. L2 Bar-by-Bar Evaluation Spec
4.1 Component Decomposition Structure
Before defining the bar-by-bar logic, the decomposition framework must be established. The harness must be capable of running L2 in the following modes, each of which isolates a different component:
ModeWhat is activePurposeMODE_RANDOMNo filters, random entry at any bar, same stop/targetEstablishes baseline — what does the exit structure alone produce?MODE_MACRO_ONLYMacro filter only, enter at every bar where filter passesMeasures how much edge the regime selector creates by itselfMODE_TOUCH_ONLYEMA touch condition only, no macro filter, no confirmationIsolates the entry signal from the macro contextMODE_MVS_NO_CONFIRMMacro + touch, no confirmation candleMeasures confirmation candle's marginal contributionMODE_MVS_FULLFull MVS as specifiedThe strategy as intended
Every mode uses identical stop/target logic and identical trade logging. The difference in performance across modes reveals which components actually contribute edge. This is the most important diagnostic the harness produces.
Decomposition hypothesis to be tested explicitly:

If MODE_MVS_FULL materially outperforms MODE_TOUCH_ONLY, the macro filter adds value
If MODE_MVS_NO_CONFIRM and MODE_MVS_FULL perform similarly, the confirmation candle adds no measurable edge and should be reconsidered
If MODE_MACRO_ONLY performs as well as MODE_MVS_FULL, the EMA touch logic adds no value over simply trading the bull-market period

4.2 Bar-by-Bar Processing Order
The following sequence is executed for every bar in the dataset, in this exact order. No step may reference data from a bar index higher than the current bar index.
BAR LOOP — executed for bar index i from warmup_period to len(data)-1:

─── PHASE A: STATE UPDATE (no signals, no decisions) ───────────────────

A1. Mark current bar as:
    - timestamp    = data['timestamp'].iloc[i]
    - open_price   = data['open'].iloc[i]
    - high_price   = data['high'].iloc[i]
    - low_price    = data['low'].iloc[i]
    - close_price  = data['close'].iloc[i]
    
    NOTE: high and low are used in stop management (Phase C).
    They represent the range of bar i, which is fully formed at bar 
    close. This is correct because entries are at bar close and 
    stop checks happen at the NEXT bar's high/low.
    
    CORRECTION: For stop management, high and low of bar i are used 
    to check if a stop was hit DURING bar i. Since entries happen at 
    the close of the prior bar (i-1), bar i is the first bar where 
    the stop can be hit. This is the correct sequence.

─── PHASE B: OPEN TRADE MANAGEMENT (before signal generation) ──────────

B1. If there is an open trade:
    
    B1a. CHECK STOP HIT:
         If low_price <= stop_price:
             Exit trade at stop_price.
             Log exit: reason='stop_hit', exit_bar=i, exit_price=stop_price
             Close trade record.
             Set open_trade = None.
             GOTO Phase D (no signal generation this bar — trade just closed)
    
    B1b. CHECK TARGET HIT:
         If high_price >= target_price:
             Exit trade at target_price.
             Log exit: reason='target_hit', exit_bar=i, exit_price=target_price
             Close trade record.
             Set open_trade = None.
             GOTO Phase D
    
    B1c. Neither stop nor target hit:
         Trade remains open.
         [FIX: Update MAE/MFE for open trade]
         current_mae = effective_entry_price - low_price
         current_mfe = high_price - effective_entry_price
         trade.mae = max(trade.mae or 0, current_mae)
         trade.mfe = max(trade.mfe or 0, current_mfe)
         Continue to Phase D.
         (No signal generation when a trade is already open — 
          MVS allows at most 1 concurrent trade)
    
    NOTE ON STOP/TARGET PRIORITY:
    If both stop and target are hit within the same bar (high >= target 
    AND low <= stop), assume STOP HIT. This is the conservative assumption.
    A favorable same-bar assumption here would be a form of lookahead.

─── PHASE C: SIGNAL GENERATION (only if no open trade) ─────────────────

C1. MACRO FILTER CHECK (MVS-L2-1):
    daily_sma200  = daily_sma200_aligned.iloc[i]
    btc_close_d   = btc_daily_close_aligned.iloc[i]
    
    If daily_sma200 is NaN: skip bar (insufficient history)
    If btc_close_d <= daily_sma200: 
        signal_eligible = False
        Record: bar_i, reason='macro_filter_rejected'
        GOTO Phase D
    
C2. EMA TOUCH CHECK (MVS-L2-2):
    ema21 = ema21_4h.iloc[i]
    
    If ema21 is NaN: skip bar
    If low_price > ema21 * 1.003:
        signal_eligible = False
        GOTO Phase D
    
    touch_detected = True
    touch_bar = i
    touch_ema_value = ema21

C3. CONFIRMATION CANDLE CHECK (MVS-L2-3):
    This check is applied at bar i, which IS the confirmation candle.
    The touch is detected at bar i (the current bar's low touched EMA).
    The bullish close check is also on bar i.
    
    IMPORTANT DESIGN DECISION:
    Touch detection and confirmation are evaluated on the SAME bar.
    The entry fires at the CLOSE of bar i.
    This means we require: low <= EMA21 * 1.003 AND close > open
    in the same 4H candle.
    
    Alternative interpretation (touch on bar i, confirm on bar i+1):
    This would require carrying forward a "pending touch" state across 
    bars, which introduces the question of how many bars to wait for 
    confirmation. The same-bar interpretation is simpler and less 
    parameter-dependent.
    
    Document this choice in params.json. Test both in sensitivity 
    analysis (not optimization — simply compare the two approaches
    as a structural variant, not a tuned parameter).
    
    If close_price <= open_price:
        signal_eligible = False
        GOTO Phase D
    
C4. ENTRY SIGNAL CONFIRMED:
    entry_price = close_price  (market order at bar close)
    effective_entry_price = close_price * (1 + slippage_bps / 10000)
                  [FIX: slippage-adjusted price. entry_price is used for 
                   signal analysis; effective_entry_price is used for 
                   P&L, R-multiple, and stop_distance calculations.
                   slippage_bps = 10 from params.]
    atr14       = atr14_4h.iloc[i]
    stop_price  = ema21 * (1 - 0.003) - (1.5 * atr14)
                  [stop is 1.5× ATR below the EMA touch level,
                   not below entry — this is correct, entry may be 
                   above EMA at close]
    
    CLARIFICATION ON STOP ANCHOR:
    The stop is anchored to the EMA value at the touch, not the entry 
    price. This matters because if price closes above the EMA after 
    touching it, the entry price is above the EMA and the stop distance 
    is larger than if anchored to entry. This is the intended behavior —
    the stop protects against the EMA touch being a false support.
    
    target_price = entry_price + (2.0 * atr14)

─── PHASE D: TRADE RECORD UPDATE ───────────────────────────────────────

D1. If a new entry was triggered in Phase C:
    Create trade record:
    {
        'trade_id':      sequential_id,
        'entry_bar':     i,
        'entry_time':    timestamp,
        'entry_price':   entry_price,
        'effective_entry_price': entry_price * (1 + slippage_bps / 10000),
                         [FIX: slippage-adjusted price for P&L accounting]
        'stop_price':    stop_price,
        'target_price':  target_price,
        'stop_distance': effective_entry_price - stop_price,
        'target_distance': target_price - effective_entry_price,
        'planned_R':     target_distance / stop_distance,
        'regime':        regime_label at bar i,
        'ema21_at_entry': ema21,
        'atr_at_entry':  atr14,
        'fees_applied':  False,  [fees applied at exit]
        'mae':           None,   [FIX: updated bar-by-bar during trade — 
                                  max(effective_entry_price - low) across all bars while open]
        'mfe':           None    [FIX: updated bar-by-bar during trade — 
                                  max(high - effective_entry_price) across all bars while open]
    }

D2. End of bar i. Advance to bar i+1.

─── FEE MODEL ──────────────────────────────────────────────────────────

Applied at exit only (for simplicity in research harness):
    fee_per_side = 0.05%  (Binance taker fee, conservative)
    total_taker_fee = entry_price * fee_rate + exit_price * fee_rate
    
    [FIX — Funding rate cost added per Phase 1 mandate]
    funding_rate_per_settlement = 0.0002  (0.02% per 8H, from Phase 1 params)
    holding_duration_hours = (exit_timestamp - entry_timestamp).total_seconds() / 3600
    funding_settlements_crossed = floor(holding_duration_hours / 8)
    funding_cost = funding_settlements_crossed * funding_rate_per_settlement * entry_price
    
    total_fee    = total_taker_fee + funding_cost
    net_pnl      = gross_pnl - total_fee
    
    In R terms:
    fee_in_R = total_fee / (entry_price - stop_price)
    net_R    = gross_R - fee_in_R
    
    NOTE: The funding rate is applied as a flat cost regardless of 
    actual funding direction (conservative assumption per Phase 1). 
    Sensitivity sweep at 0.01%, 0.02%, 0.05% per 8H is required 
    in the parameter sensitivity report.
4.3 L2 Warmup Period
Minimum bars required before any signal can fire:

EMA21 on 4H: 21 bars (but practically 63 bars for stability)
ATR14 on 4H: 14 bars
Daily SMA200: 200 daily bars = approximately 1200 4H bars

Effective warmup: 1200 4H bars (approximately 200 trading days)
No signal may fire before bar index 1200. Any backtest on less than 18 months of data is not valid for L2.

5. S2 Bar-by-Bar Evaluation Spec
5.1 Bar-by-Bar Processing Order
The following sequence is executed for every bar in the dataset.
BAR LOOP — executed for bar index i from warmup_period to len(data)-1:

─── PHASE A: STATE UPDATE ──────────────────────────────────────────────

A1. (Same as L2 Phase A — record OHLCV for current bar)

─── PHASE B: OPEN TRADE MANAGEMENT ────────────────────────────────────

B1. If there is an open trade:

    B1a. CHECK STOP HIT:
         If high_price >= stop_price:  [SHORT trade — stop is ABOVE entry]
             Exit trade at stop_price.
             Log exit: reason='stop_hit'
             Set open_trade = None
             GOTO Phase D
    
    B1b. CHECK TARGET HIT:
         If low_price <= target_price:  [SHORT trade — target is BELOW entry]
             Exit trade at target_price.
             Log exit: reason='target_hit'
             Set open_trade = None
             GOTO Phase D
    
    B1c. CHECK TIME EXIT (MVS-S2-9 is ESS — not in MVS):
         In MVS, no time exit. Trades run until stop or target.
         NOTE: This means the MVS will hold losing trades longer 
         than the ESS. This is intentional — it tests the core 
         hypothesis without the time exit crutch.
    
    B1d. SAME-BAR CONFLICT (high >= stop AND low <= target):
         Assume STOP HIT. Conservative.
    
    B1e. [FIX: MAE/MFE UPDATE — if trade still open after B1a-B1d]
         If trade is still open:
         current_mae = high_price - effective_entry_price  [SHORT: adverse = price going UP]
         current_mfe = effective_entry_price - low_price   [SHORT: favorable = price going DOWN]
         trade.mae = max(trade.mae or 0, current_mae)
         trade.mfe = max(trade.mfe or 0, current_mfe)

─── PHASE C: SUPPORT LEVEL UPDATE ─────────────────────────────────────

CRITICAL: Support level detection must be updated BEFORE signal 
evaluation, and must only use data from bars 0 through i-1.
Bar i's OHLCV is NOT yet available when support levels are computed.

This means: at bar i, the support detection algorithm scans bars
[max(0, i - lookback), i-1] only.

C1. Run support detection algorithm (see Section 6) on 
    bars [i - lookback_window, i-1].
    
    This produces: active_support_levels = list of (level_price, touch_count, 
                                                      first_touch_bar, last_touch_bar)
    
    Discard any level where last_touch_bar == i-1 (too recent — 
    the most recent touch is the current candle's prior bar, 
    meaning price is currently near the level, not breaking it).

─── PHASE D: SIGNAL GENERATION ─────────────────────────────────────────

D1. For each active support level:

    D1a. CHECK BREAKDOWN (MVS-S2-2):
         breakdown_threshold = level_price * (1 - 0.003)
         If close_price >= breakdown_threshold: no breakdown, skip level.
         
         breakdown_confirmed = (close_price < breakdown_threshold)
    
    D1b. CHECK VOLUME (MVS-S2-3):
         vol_sma20 = volume_sma20.iloc[i]
         [NOTE: volume_sma20 at bar i = mean(volume[i-20:i])
          It does NOT include bar i's volume.]
         
         If volume.iloc[i] < 1.5 * vol_sma20: no volume confirm, skip level.
    
    D1c. ENTRY SIGNAL CONFIRMED:
         If already have an open trade: skip (max 1 concurrent trade).
         
         entry_price  = close_price
         atr14        = atr14_4h.iloc[i]
         stop_price   = level_price + (0.5 * atr14)
                        [stop is 0.5× ATR ABOVE the broken support level]
         target_price = entry_price - (2.0 * atr14)
                        [target is 2× ATR BELOW entry]
         
         If multiple support levels trigger simultaneously: 
         take the one with the highest touch count.
         If still tied: take the most recently formed level.
         Log the conflict for later review.

─── PHASE E: TRADE RECORD UPDATE ───────────────────────────────────────

E1. If new entry triggered:
    Create trade record:
    {
        'trade_id':          sequential_id,
        'entry_bar':         i,
        'entry_time':        timestamp,
        'entry_price':       entry_price,
        'effective_entry_price': entry_price * (1 - slippage_bps / 10000),
                             [FIX: slippage for shorts is adverse downward]
        'stop_price':        stop_price,
        'target_price':      target_price,
        'stop_distance':     stop_price - effective_entry_price,
                             [FIX: for shorts, stop is ABOVE entry, so stop - entry > 0]
        'target_distance':   effective_entry_price - target_price,
                             [FIX: for shorts, target is BELOW entry, so entry - target > 0]
        'planned_R':         (effective_entry_price - target_price) / (stop_price - effective_entry_price),
        'support_level':     level_price,
        'level_touch_count': touch_count,
        'level_age_bars':    i - first_touch_bar,
        'breakdown_volume':  volume.iloc[i],
        'vol_sma20':         vol_sma20,
        'vol_ratio':         volume.iloc[i] / vol_sma20,
        'regime':            regime_label at bar i,
        'detector_variant':  'A' or 'B',
        'atr_at_entry':      atr14,
        'fees_applied':      False,
        'mae':               None,   [FIX: max(high - effective_entry_price) across bars while open]
        'mfe':               None    [FIX: max(effective_entry_price - low) across bars while open]
    }

E2. End of bar i. Advance to bar i+1.

─── FEE MODEL ──────────────────────────────────────────────────────────

Same as L2: 0.05% taker fee per side + funding rate cost (0.02% per 8H settlement crossed), applied at exit, expressed in R. For short trades, the funding cost formula is identical but note that in reality shorts may receive funding when rates are positive (longs paying shorts). The flat cost assumption is conservative per Phase 1.
5.2 S2 Warmup Period

ATR14 on 4H: 14 bars
Volume SMA20 on 4H: 20 bars
Support detection lookback: 60 bars
Regime classification (200 SMA on daily): 200 daily bars ≈ 1200 4H bars

Effective warmup: 1200 4H bars, same as L2.

6. Support Detection Variants for S2
The support detection algorithm is the single highest-risk component in S2. Different implementations will produce materially different signal sets. This is not a minor implementation detail — it is a research question. Two variants must be implemented and run in parallel, and the detector-dependence of results must be measured explicitly.

Variant A — Fixed-Tolerance Price Clustering
Philosophy: A support level is a price zone where the market has repeatedly rejected downward moves. The zone is defined by proximity tolerance applied to candle lows.
Algorithm:
INPUT: bars[i - lookback : i-1]  (strictly prior to current bar)
PARAMETERS:
    touch_tolerance    = 0.005   (0.5% — two lows within 0.5% of each other 
                                  are "at the same level")
    min_touch_count    = 3
    min_bounce_atr     = 1.0     (each touch must be followed by at least 
                                  1.0× ATR upward move to confirm support held)
    min_bars_between_touches = 3  (debounce — prevents counting adjacent candles 
                                   as separate touches)
    lookback_window    = 60       (candles)

ALGORITHM:

1. Extract all low prices from bars[i-60 : i-1].

2. For each low L in this set:
   a. Compute "zone_center" as L.
   b. Collect all lows within [zone_center * (1 - touch_tolerance), 
                                zone_center * (1 + touch_tolerance)].
   c. If this cluster has fewer than min_touch_count members: skip.
   
3. For each candidate cluster:
   a. Sort touches by bar index.
   b. Apply debounce: remove any touch that occurs within 
      min_bars_between_touches bars of the prior touch.
   c. Re-check: after debounce, if touch count < min_touch_count: discard.
   d. For each touch at bar j: verify that the highest close between 
      bar j and bar j+min_bars_between_touches is at least 
      1.0× ATR(14)[j] above the touch low. 
      If this condition fails for a touch, remove that touch from the count.
      Re-check touch count.
   
4. Deduplicate overlapping clusters:
   If two cluster centers are within touch_tolerance of each other,
   merge them into the one with higher touch count.

5. Return all surviving clusters as active support levels.
   Level price = median of touch lows in the cluster.
Known weaknesses of Variant A:

The touch_tolerance parameter (0.5%) is the most critical free parameter. Levels detected depend heavily on this value. It is fixed before backtesting and not tuned.
Price zones that form at different absolute price levels have the same tolerance in percentage terms, which is appropriate, but the 0.5% value itself is a choice without rigorous theoretical basis.
In trending markets, the lookback window may include touches from a prior price range that no longer represent active support.


Variant B — Pivot Low Structural Detection
Philosophy: A support level is a pivot low — a candle whose low is the lowest in a local neighborhood — that has been confirmed multiple times. This is structurally different from Variant A: it identifies distinct price pivots rather than clustered price zones.
Algorithm:
INPUT: bars[i - lookback : i-1]
PARAMETERS:
    pivot_window       = 5    (a pivot low is a candle whose low is the lowest 
                               of the 5 candles centered on it — 2 left, 2 right)
    proximity_pct      = 0.008  (0.8% — two pivots within 0.8% of each other 
                                  are considered "at the same level")
    min_pivot_count    = 3
    min_bars_between_pivots = 5
    lookback_window    = 60

ALGORITHM:

1. Identify all pivot lows in bars[i-60 : i-1]:
   A pivot low at bar j is defined as:
   low[j] = min(low[j-2], low[j-1], low[j], low[j+1], low[j+2])
   
   LOOKAHEAD CONCERN:
   This definition requires bars j+1 and j+2 to be known at the time 
   of evaluating bar j. This means a pivot at bar j is only CONFIRMED
   at bar j+2, not at bar j.
   
   CORRECT IMPLEMENTATION:
   At current bar i, a pivot low at bar j is valid only if j <= i-3.
   This ensures both right-side confirmation bars are available.
   
   This is the most important lookahead boundary in Variant B.
   Unit test required (see Section 8).

2. Group nearby pivots:
   For each pivot P, find all other pivots within proximity_pct.
   Group them into a level.
   Apply the same debounce logic as Variant A (min 5 bars between pivots).
   Require min_pivot_count pivots in the group.

3. For each valid level group:
   Level price = lowest pivot in the group (most conservative — 
                 actual support is at the lowest confirmed touch).

4. Return all surviving levels.
Key structural difference between A and B:

Variant A uses raw low prices and clusters by proximity
Variant B uses confirmed structural pivots and clusters by proximity
Variant B has a larger inherent lag (j <= i-3 requirement) which reduces false levels at the cost of slightly delayed detection
Variant B is less sensitive to a single candle wick penetrating a zone
Variant A will generally detect more levels; Variant B will detect fewer but potentially more significant ones


Measuring Detector-Dependence
The following outputs must be produced to quantify how much S2's performance depends on which detector is used:
DETECTOR COMPARISON REPORT

1. SIGNAL SET OVERLAP ANALYSIS
   ─────────────────────────────
   Total signals from Variant A:          [N_A]
   Total signals from Variant B:          [N_B]
   Signals in common (same bar, same level ± 0.5%): [N_shared]
   Overlap rate:                          N_shared / max(N_A, N_B) = [%]
   
   Signals unique to Variant A:           [N_A - N_shared]
   Signals unique to Variant B:           [N_B - N_shared]
   
   INTERPRETATION:
   If overlap < 50%, the two detectors are finding fundamentally 
   different signals. Neither can be trusted as "the correct" 
   detector without further validation. Flag for review.
   If overlap > 70%, the detectors are largely equivalent and 
   the choice between them is secondary.

2. PERFORMANCE COMPARISON
   ─────────────────────────
   [Full performance table from Section 2 of backtest report format,
    shown side by side for Variant A and Variant B]

3. REGIME-CONDITIONAL DETECTOR BEHAVIOR
   ─────────────────────────────────────
   For each regime {STRONG_BULL, WEAK_BULL, HIGH_VOL_BULLISH, 
                    HIGH_VOL_BEARISH, BEAR, TRANSITION}:
   [N signals from A | N signals from B | Win rate A | Win rate B]

4. DETECTOR STABILITY ASSESSMENT
   ─────────────────────────────────
   If Profit Factor A - Profit Factor B > 0.30:
       Flag: DETECTOR-DEPENDENT RESULT
       Interpretation: The strategy's apparent edge is substantially 
       determined by which support detection algorithm is used.
       This means the edge is in the detector parameters, not in 
       the breakdown hypothesis. Do not proceed.
   
   If |Profit Factor A - Profit Factor B| <= 0.15:
       Flag: DETECTOR-STABLE RESULT
       Interpretation: The core hypothesis shows consistent behavior 
       regardless of detection methodology. This is meaningful.
   
   If difference is between 0.15 and 0.30:
       Flag: MODERATELY DETECTOR-DEPENDENT
       Interpret with caution. Use the more conservative result 
       (lower profit factor) as the strategy's true expected performance.

7. No-Lookahead Rules
These are structural rules that govern the entire harness. Violations are bugs, not edge cases.
7.1 The Fundamental Rule
At bar index i, the only data accessible to any calculation is data.iloc[0:i+1]. Nothing after index i may be accessed for any purpose — signal generation, indicator calculation, or stop management.
7.2 Specific Lookahead Vectors to Eliminate
Vector 1 — Indicator alignment off-by-one.
When computing indicators with pandas and then merging with price data, the default behavior of pd.DataFrame.rolling().mean() computes the value AT bar i using bars up to and including bar i. This is CORRECT for use in signal evaluation at bar i (the indicator is available after bar i closes). The error occurs when the indicator series is shifted incorrectly. Define the convention once and state it explicitly:
CONVENTION: indicator.iloc[i] represents the indicator value 
computed from data[0:i+1], available to trading logic after 
bar i closes. Entry at bar i close is therefore based on 
indicator.iloc[i]. This is correct. No shift required.

THE DANGEROUS ANTI-PATTERN:
Using indicator.iloc[i+1] for an entry decision at bar i 
is lookahead. This can occur accidentally if a "confirmation" 
candle is evaluated one bar early.
Vector 2 — EMA calculation at bar 0.
EMA is recursive: EMA[0] = close[0], EMA[i] = close[i] * k + EMA[i-1] * (1 - k) where k = 2/(period+1). The first period - 1 values are unreliable due to initialization. They must be marked as NaN and excluded from signal evaluation. Using pandas ewm() with adjust=False is correct. Using adjust=True introduces a different initialization that assigns different weights to early bars — this is not wrong but must be consistent. State the method, do not allow both.
Vector 3 — Pivot low detection in Variant B.
As explicitly noted in Section 6, a pivot low at bar j requires confirmation from bars j+1 and j+2. Therefore, at current bar i, only pivots at bars j <= i-3 are valid. This must be enforced in code with an assertion, not just a convention.
Vector 4 — Regime label assignment.
The daily regime label for day D is computed from daily closes up to and including day D. It is not available to a 4H candle that opens on day D before the daily close. It is available to any 4H candle that opens on day D+1 or later. Therefore, regime labels must be forward-filled starting from the following calendar day, not from the computation day.
Vector 5 — Same-bar stop and target evaluation.
When evaluating stops and targets within bar i, using bar i's high and low is correct — they represent the full range of the bar, and since entry was at bar i-1's close, bar i is the first bar where the stop can be hit. However, the ENTRY PRICE for a trade entered at bar i's close is the close of bar i, which is available at the end of bar i. The stop and target are set at bar i's close and first tested at bar i+1. This means: the bar-by-bar loop must process stop/target management BEFORE signal generation for the current bar, as specified in Phase B of both strategy specs above.
Vector 6 — Support level recalculation.
In S2, support levels are recomputed at every bar using only prior bars. The act of recalculating levels must not "discover" the current bar's low as a potential support touch. The support scanner must explicitly exclude bar i when running at bar i.
Vector 7 — ATR in stop calculation.
ATR at bar i is computed from bars 0 through i. This is the ATR available at bar i's close and is therefore correctly used for stop calculation when entering at bar i's close. No shift needed. However, if ATR is used for TRAILING stops on subsequent bars (ESS only), the ATR at bar j (the current management bar) should be used, not the ATR at the entry bar. This distinction matters and must be documented clearly.
7.3 Lookahead Verification Procedure
Before trusting any backtest result, the following verification must be run:
VERIFICATION TEST: FUTURE-BLIND RECONSTRUCTION

1. Run the backtest normally. Record all trade entry bars.

2. For each trade, extract the exact slice of data that was 
   "visible" at the entry bar: data.iloc[0 : entry_bar + 1]

3. Re-run only the signal generation logic for that trade using 
   only this slice. Confirm that:
   a. The same signal fires
   b. The same indicator values are produced
   c. The same stop and target are calculated

4. If any trade produces a different result in the slice-based 
   re-run, there is a lookahead bug. Halt and debug before 
   trusting any results.

8. Unit Test Plan
These tests must pass before any backtest result is trusted. They are not optional. A failing test means a bug exists, not that the test is wrong.
8.1 Data Integrity Tests
TEST-DATA-01: OHLC CONSISTENCY
Input: DataFrame with one row where high < close (invalid)
Expected: IntegrityError raised, execution halted
Must pass before: any indicator computation

TEST-DATA-02: DUPLICATE TIMESTAMP DETECTION
Input: DataFrame with two rows having identical timestamps
Expected: IntegrityError raised
Must pass before: any processing

TEST-DATA-03: GAP DETECTION
Input: 4H DataFrame with a 16H gap (missing 3 consecutive candles)
Expected: GapWarning raised with specific gap location
Must pass before: any backtest run on that dataset

TEST-DATA-04: DAILY-4H ALIGNMENT
Input: Daily close series and 4H timestamp series
Expected: For a 4H bar opening at 2024-01-15 00:00 UTC,
          the aligned daily value is the SMA computed 
          through 2024-01-14 close, NOT 2024-01-15 close
Must pass before: L2 macro filter is used
8.2 Indicator Computation Tests
TEST-IND-01: EMA WARMUP
Input: 30-bar price series, EMA period 21
Expected: ema.iloc[0:20] are all NaN, ema.iloc[20] is not NaN
Must pass before: EMA touch detection is used

TEST-IND-02: EMA CORRECTNESS
Input: Price series [100, 102, 101, 103, 105] with period 3
Expected: Manually computed EMA values (k = 0.5)
Must pass before: any EMA-based signal is trusted

TEST-IND-03: ATR WARMUP
Input: 20-bar OHLC series, ATR period 14
Expected: atr.iloc[0:13] are NaN, atr.iloc[13] is not NaN
Must pass before: ATR-based stops are calculated

TEST-IND-04: VOLUME SMA EXCLUDES CURRENT BAR
Input: Volume series, compute SMA20 at bar i=25
Expected: SMA is mean of volume[5:25], NOT mean of volume[5:26]
This test verifies the rolling calculation window boundary.
Must pass before: S2 volume filter is used

TEST-IND-05: REGIME LABEL FORWARD FILL TIMING
Input: Daily regime series, 4H timestamp series
Expected: 4H bar at 2024-01-15 02:00 UTC carries the regime 
          label computed from 2024-01-14 daily close,
          NOT from 2024-01-15 daily close
Must pass before: regime-conditional reporting is produced
8.3 L2-Specific Tests
TEST-L2-01: EMA TOUCH DETECTION BOUNDARY
Input: 4H bar with low = EMA21 * 1.0025 (within 0.3% tolerance)
Expected: touch_detected = True
Input: 4H bar with low = EMA21 * 1.0035 (outside 0.3% tolerance)
Expected: touch_detected = False
Must pass before: any L2 signal is generated

TEST-L2-02: CONFIRMATION CANDLE REQUIREMENT
Input: Bar where low touches EMA (trigger) but close < open
Expected: No entry signal generated
Must pass before: L2 MVS is backtested

TEST-L2-03: STOP ANCHORING
Input: Entry bar where EMA21 = 100.0, ATR14 = 2.0, close = 102.0
Expected: stop_price = 100.0 * 0.997 - (1.5 * 2.0) = 99.70 - 3.0 = 96.70
          [NOT 102.0 - 3.0 = 99.0 — stop is NOT anchored to entry]
Must pass before: any L2 stop calculation is trusted

TEST-L2-04: MACRO FILTER BLOCKS TRADES IN DOWNTREND
Input: Sequence of 250 daily bars trending down, then EMA touch on 4H
Expected: Zero trades generated (macro filter blocks all)
Must pass before: L2 regime analysis is interpreted

TEST-L2-05: NO CONCURRENT TRADES
Input: Two consecutive EMA touch bars with bullish confirmation
Expected: Second signal is skipped because first trade is open
Must pass before: any multi-trade backtest is trusted

TEST-L2-06: SAME-BAR STOP-AND-TARGET CONFLICT
Input: Trade open, next bar has high >= target AND low <= stop
Expected: Exit recorded as STOP_HIT, not TARGET_HIT
Must pass before: any profitability claims are made

TEST-L2-07: FEE APPLICATION
Input: Trade with entry=100, exit=104, fee_rate=0.0005
Expected: gross_pnl = 4.0, total_taker_fee = (100 * 0.0005) + (104 * 0.0005) = 0.102
          net_pnl = 4.0 - 0.102 = 3.898
Must pass before: profit factor or expectancy is reported

TEST-L2-07b: FUNDING RATE COST CALCULATION
Input: Trade with entry_time=2024-01-15 00:00 UTC, exit_time=2024-01-16 08:00 UTC
       (holding duration = 32 hours), funding_rate_per_settlement = 0.0002,
       entry_price = 100.0
Expected: funding_settlements_crossed = floor(32 / 8) = 4
          funding_cost = 4 * 0.0002 * 100.0 = 0.08
          total_fee = taker_fee + funding_cost
Must pass before: any net_pnl or R-multiple is reported

TEST-L2-07c: SLIPPAGE APPLICATION (LONG)
Input: close_price = 100.0, slippage_bps = 10
Expected: effective_entry_price = 100.0 * (1 + 10/10000) = 100.10
          stop_distance computed from effective_entry_price, not close_price
Must pass before: any R-multiple calculation is trusted
8.4 S2-Specific Tests
TEST-S2-01: SUPPORT DETECTION LOOKAHEAD (VARIANT B CRITICAL)
Input: Price series of length 100. Run detector at bar i=50.
Expected: No pivot at bar j=49 is returned (requires j+2 = 51 > 50)
          Pivots at j <= 47 may be returned.
Must pass before: Variant B is used in any backtest

TEST-S2-02: TOUCH DEBOUNCE
Input: Three consecutive lows of [100.1, 99.9, 100.0] 
       (three bars in a row near the 100.0 level)
Expected: Counts as 1 touch, not 3 (debounce applied)
Must pass before: touch count is used as filter

TEST-S2-03: BREAKDOWN REQUIRES BODY CLOSE
Input: Bar with low = 99.5 (below level 100.0) but close = 100.3
Expected: No breakdown signal (close is above level)
Must pass before: any S2 breakdown signal is generated

TEST-S2-04: VOLUME COMPARISON EXCLUDES CURRENT BAR
Input: Volume series [100, 110, 90, 120, ...] at bar i=25
       volume_sma20 computed at bar i should use bars 5 through 24
Expected: current bar (25) volume is NOT included in the SMA
Must pass before: volume filter is trusted

TEST-S2-05: SHORT STOP DIRECTION
Input: Short entry at 100.0, support level at 101.0, ATR = 1.0
Expected: stop_price = 101.0 + (0.5 * 1.0) = 101.5  [ABOVE entry for short]
          target_price = 100.0 - (2.0 * 1.0) = 98.0  [BELOW entry for short]
Must pass before: any stop or target calculation is trusted

TEST-S2-06: SHORT STOP HIT CONDITION
Input: Short trade with stop at 103.0. Current bar high = 103.5.
Expected: Trade exits at 103.0 (stop hit, HIGH exceeds stop for short)
Input: Current bar high = 102.9.
Expected: Trade remains open.
Must pass before: any short trade management is trusted

TEST-S2-07: MULTIPLE SIMULTANEOUS LEVEL TRIGGERS
Input: Two support levels trigger breakdown on the same bar
Expected: One trade entered, at the level with highest touch count.
          If tied, use most recent level.
          Both signals logged, only one acted upon.
Must pass before: multi-level datasets are backtested

TEST-S2-08: DETECTOR COMPARISON PRODUCES CORRECT OVERLAP METRIC
Input: Two synthetic signal sets with known overlap
Expected: Overlap metric equals manually computed value
Must pass before: detector comparison report is interpreted

9. Diagnostic Output Requirements
The following outputs must be produced for every complete backtest run. Their purpose is to diagnose the source of apparent edge — or the absence of it.
9.1 Output 1 — Component Attribution Report (L2 only)
Run all five modes defined in Section 4.1 and produce the following table:
COMPONENT ATTRIBUTION — L2 EMA PULLBACK
═══════════════════════════════════════════════════════════
                     | Trades | Win% | PF   | Expectancy | Max DD
─────────────────────────────────────────────────────────────────
MODE_RANDOM          | [N]    | [%]  | [x]  | [R]        | [%]
MODE_MACRO_ONLY      | [N]    | [%]  | [x]  | [R]        | [%]
MODE_TOUCH_ONLY      | [N]    | [%]  | [x]  | [R]        | [%]
MODE_MVS_NO_CONFIRM  | [N]    | [%]  | [x]  | [R]        | [%]
MODE_MVS_FULL        | [N]    | [%]  | [x]  | [R]        | [%]
─────────────────────────────────────────────────────────────────

Incremental contribution analysis:
  Macro filter adds:       PF(MODE_MACRO_ONLY) - PF(MODE_RANDOM)     = [Δ]
  EMA touch adds:          PF(MODE_MVS_NO_CONFIRM) - PF(MODE_MACRO_ONLY) = [Δ]  
  Confirmation adds:       PF(MODE_MVS_FULL) - PF(MODE_MVS_NO_CONFIRM)  = [Δ]

INTERPRETATION FLAGS:
  If PF(MODE_MACRO_ONLY) > PF(MODE_MVS_FULL):
      WARNING: Adding the EMA touch filter HURTS performance.
      The edge is regime selection, not entry logic.
      
  If PF(MODE_MVS_FULL) - PF(MODE_RANDOM) < 0.15:
      WARNING: Strategy barely outperforms random entry with 
      same stop/target. Edge may be entirely in exit structure.
9.2 Output 2 — Period Isolation Report
This identifies whether performance is driven by one exceptional period.
PERIOD ISOLATION ANALYSIS
══════════════════════════════════════════════════════
Full period PF: [x]

Rolling 6-month periods (non-overlapping):
  Period          | Trades | PF    | Regime composition | BTC B&H Return
  ────────────────────────────────────────────────────────────────────────
  2020-01 to 06   | [N]    | [x]   | [% each regime]    | [%]
  2020-07 to 12   | [N]    | [x]   | [% each regime]    | [%]
  2021-01 to 06   | [N]    | [x]   | [% each regime]    | [%]
  ... etc.

[FIX — Buy-and-hold correlation added per Phase 2 Section 6]
Buy-and-hold correlation (L2 only):
  Pearson correlation (period PF, BTC period return): [r]
  If r > 0.80: WARNING — strategy performance is correlated with 
  underlying trend. Entry signal may not add value over regime beta.

Flag: If any single 6-month period accounts for more than 
      40% of total net R across all periods:
      CONCENTRATION WARNING — results may be period-dependent.

Flag: If the strategy is profitable in fewer than 50% of 
      6-month periods:
      INCONSISTENCY WARNING — edge is episodic, not systematic.

Worst single period: [period, PF, trades]
Best single period:  [period, PF, trades]
PF without best period: [x]  ← Critical diagnostic
9.3 Output 3 — Exit Structure Isolation Report
This diagnoses whether the apparent edge is in the entry or the exit structure.
EXIT STRUCTURE ISOLATION ANALYSIS
═══════════════════════════════════════════════════════
Using MVS_FULL entry signals with alternative exits:

Exit variant A (original):     stop 1.5× ATR, target 2.0× ATR
Exit variant B (tight):        stop 1.0× ATR, target 1.5× ATR
Exit variant C (wide):         stop 2.0× ATR, target 3.0× ATR
Exit variant D (time exit 12H): exit after 3 candles regardless
Exit variant E (hold 5 days):  exit after 30 candles regardless

[FIX — Variant F added per Phase 1 mandate, S2 only]
Exit variant F (constant-R:R): stop 1.0× ATR, target 4.0× ATR
  Purpose: Tests whether S2's edge is in the signal or in the stop 
  calibration. Variant F maintains approximately the same R:R ratio 
  as S2's primary configuration (0.5× stop / 2.0× target ≈ 4:1) 
  but at double the absolute distance. If Variant F performs similarly 
  to S2's primary config, the signal has genuine edge regardless of 
  stop tightness. If Variant F performs significantly worse, the 
  tight stop is the source of apparent edge (through favorable 
  selection of which breakdowns happen to not retrace).
  This variant is applied to S2 signals only — it is not meaningful 
  for L2 where the stop anchor (EMA) is structural, not distance-based.

  Exit Variant | Trades | Win%  | PF    | Expectancy
  ──────────────────────────────────────────────────
  A (original) | [N]    | [%]   | [x]   | [R]
  B (tight)    | [N]    | [%]   | [x]   | [R]
  C (wide)     | [N]    | [%]   | [x]   | [R]
  D (time 12H) | [N]    | [%]   | [x]   | [R]
  E (hold 5d)  | [N]    | [%]   | [x]   | [R]
  F (const-R:R)| [N]    | [%]   | [x]   | [R]  [S2 only]

INTERPRETATION:
  If performance is highly consistent across exit variants A, B, C:
      The entry logic has genuine edge that persists regardless 
      of exit structure. This is the strongest possible evidence.
      
  If performance varies dramatically across exit variants:
      The edge is in the exit parameter choice, not the entry logic.
      This is a significant red flag for overfitting.
      
  If variant D (random time exit) or E (hold 5 days) performs 
  similarly to variant A:
      The stop/target structure is not contributing value. 
      The edge may come from trend momentum alone 
      (buy in uptrend, hold, it goes up).
9.4 Output 4 — Regime Contribution Report
REGIME CONTRIBUTION ANALYSIS
═══════════════════════════════════════════════════════
[Use the standard regime performance table from Phase 2 report format]

Additional diagnostic:
  Net R contributed by regime:
    STRONG_BULL:      [total R from all trades in this regime]
    WEAK_BULL:        [total R]
    HIGH_VOL_BULLISH: [total R]
    HIGH_VOL_BEARISH: [total R]
    BEAR:             [total R]
    TRANSITION:       [total R]

  Cumulative R curve by regime (separate equity curve for each)

  Flag: If a strategy's total positive R is entirely explained 
        by one regime, it is a regime-timing strategy, not an 
        entry-signal strategy. This is not necessarily disqualifying 
        but it changes what the strategy requires to work in live 
        trading: it requires accurate regime identification in real time,
        which is not the same as having it computed cleanly on historical data.
9.5 Output 5 — Single-Trade Sensitivity Report
SINGLE-TRADE IMPACT ANALYSIS
═══════════════════════════════════════════════════════
Total net R across all trades: [X]

Top 5 individual trades by R contribution:
  Trade ID | Date | R multiple | % of total net R | Regime
  ─────────────────────────────────────────────────────────
  [...]

Bottom 5 individual trades by R contribution:
  [...]

Metric: Remove top 3 trades. New total R = [X']. New PF = [y].
  If PF drops below 1.0 after removing top 3 trades:
      WARNING: Results are driven by outlier trades.
      This is a fragile edge, not a systematic edge.
      
Longest winning streak:  [N trades, total R]
Longest losing streak:   [N trades, total R]

10. Research Stop Criteria
These are the conditions under which further development effort on a strategy is not justified. They are defined now, before any backtest is run. They cannot be renegotiated after results are seen.
10.1 L2 Research Stop Criteria
Immediate research stop — do not proceed to ESS, do not test more assets, do not adjust parameters:
STOP-L2-1: MVS profit factor < 1.10 on full period
           Rationale: At < 1.10, adding filters that reduce trade count 
           cannot realistically push the strategy to a useful profit factor.
           The math does not support it.

STOP-L2-2: MVS produces fewer than 35 trades over the full data period
           Rationale: Insufficient statistical basis. Any result — positive 
           or negative — is noise at this sample size.

STOP-L2-3: Component attribution shows that MODE_MACRO_ONLY performs 
           within 0.10 PF of MODE_MVS_FULL
           Rationale: The EMA touch signal is not adding meaningful value.
           The strategy would be equivalent to "be long when BTC is in 
           a bull market." This is not a tradeable strategy — it is 
           regime selection with entry at any price.

STOP-L2-4: Walk-forward test PF is below 0.90 in more than 60% of windows
           in EITHER Method A (rolling) OR Method B (expanding)
           Rationale: The strategy deteriorates significantly out of sample.
           This indicates in-sample overfitting that survives even the 
           minimal parameterization of the MVS. If either validation 
           method shows this level of degradation, the strategy is suspect.
           Both methods must be run per Phase 2 PROMISING requirements.

STOP-L2-5: Period isolation shows that removing the single best 6-month 
           period causes PF to drop below 1.05
           Rationale: The entire apparent edge is explained by one period.
           This is not a systematic strategy.

STOP-L2-6: Exit structure isolation shows that exit variants A, B, and C 
           produce PF values spanning more than 0.60 PF units
           (e.g., PF ranges from 0.90 to 1.50 across exit variants)
           Rationale: The strategy's profitability is fragile to exit 
           parameter choice. It has no real entry edge — only a lucky 
           stop/target configuration.
Conditional pause — do not proceed to full implementation, but may investigate specific issue:
PAUSE-L2-1: MVS PF between 1.10 and 1.25, walk-forward mostly positive
            Action: Test on ETH data. If ETH shows similar results, 
            revisit. If ETH shows significantly different results, 
            the BTC result may be asset-specific and unreliable.

PAUSE-L2-2: Component attribution shows confirmation candle adds 
            negative marginal value
            Action: Investigate whether removing the confirmation 
            requirement (going back to pure EMA touch entry) improves 
            results. This is NOT optimizing — it is testing whether 
            a filter that was expected to help is actually hurting.
            Document and report both results.
10.2 S2 Research Stop Criteria
STOP-S2-1: MVS profit factor < 1.05 on full period
           Rationale: Short strategies face structural headwinds. 
           The threshold is lower than L2's but still meaningful.
           Below 1.05, fees alone make the strategy untenable.

STOP-S2-2: Detector comparison shows PF difference > 0.30 between 
           Variant A and Variant B
           Rationale: If performance is this sensitive to the support 
           detection algorithm, the strategy does not have a stable edge.
           It has an algorithm-fitting artifact. Do not proceed.

STOP-S2-3: MVS produces fewer than 25 trades on the full period
           Rationale: Even lower threshold than L2 because shorter 
           holding periods mean more data is needed for confidence. 
           25 trades is not statistically meaningful.

STOP-S2-4: MVS shows negative expectancy in both BEAR and HIGH_VOL_BEARISH regimes
           Rationale: S2 is a short strategy. If it cannot make money 
           in any bearish environment (neither trending bear nor volatile 
           bear), it has no business case. This is a hard requirement.
           Note: negative expectancy in only ONE of the two bearish 
           regimes is not an automatic stop — it triggers PAUSE-S2-3 
           (see below) for investigation.

STOP-S2-5: Walk-forward test PF < 0.85 in more than 60% of windows
           in EITHER Method A (rolling) OR Method B (expanding)
           Rationale: Same logic as L2 STOP-4. Slightly more lenient 
           threshold due to lower expected S2 PF in aggregate.
           Both methods must be run per Phase 2 PROMISING requirements.

STOP-S2-6: The 2022 bear market period accounts for more than 60% of 
           total net R across the full period
           Rationale: This would mean S2 is a "works in a severe bear 
           market" strategy. Such strategies are only useful when you 
           can time the bear market in advance — which you cannot do 
           systematically. It does not have general edge.

STOP-S2-7: Period isolation shows PF below 1.0 when 2022 data is 
           excluded entirely
           Rationale: Confirms the bear-market concentration problem 
           described in STOP-S2-6. Hard stop.

STOP-S2-8: Exit structure isolation shows Variant F (constant-R:R, 
           1.0× ATR stop / 4.0× ATR target) PF below 0.80 while 
           primary config (0.5× ATR stop / 2.0× ATR target) PF is 
           above 1.20
           Rationale: If doubling the absolute stop/target distance 
           while maintaining the same R:R ratio causes PF to collapse, 
           the strategy's edge is in the tight stop calibration — not 
           in the breakdown signal. The tight stop selects which 
           breakdowns "survive" (those that happen to not retrace), 
           creating an illusion of signal quality. This is the most 
           dangerous form of exit-parameter overfitting because it 
           looks like entry edge but is actually stop-distance fitting.
           Hard stop — do not proceed with S2 in any form.

Conditional pause for S2:
PAUSE-S2-1: Detector overlap below 50% but both detectors show PF > 1.10
            Action: Investigate which regime each detector performs in.
            If Variant A works in bear markets and Variant B works in 
            transitional markets, they may be complementary rather than 
            competing. Do not assume one is correct — study the difference.

PAUSE-S2-2: Good aggregate PF but high max drawdown (> 25%)
            Action: Analyze losing streak clustering. If losses cluster 
            in specific regime transitions, the ESS time-exit and EMA 
            context filter may help. Do not add filters to improve 
            aggregate PF — add them to reduce regime-specific drawdowns.

PAUSE-S2-3: Negative expectancy in ONE of BEAR or HIGH_VOL_BEARISH 
            (but not both — both triggers STOP-S2-4)
            Action: Investigate why the strategy works in one bearish 
            sub-regime but not the other. If it works in HIGH_VOL_BEARISH 
            but not BEAR, the edge may depend on panic/liquidation dynamics 
            (volatile breakdowns) rather than structural supply shifts 
            (trending breakdowns). If it works in BEAR but not 
            HIGH_VOL_BEARISH, the strategy may be vulnerable to extreme 
            volatility whipsaws. Document which sub-regime fails and why.

Summary: Research Harness Execution Sequence
Before writing a single line of strategy or backtest code, this is the complete ordered checklist:
PHASE 0 — BEFORE ANY CODE
□ Fix all parameters for L2 MVS and S2 MVS. Write them to params_v1.json.
□ Do not open backtest result files until this document is complete.

PHASE 1 — DATA INFRASTRUCTURE
□ Implement data fetcher (ccxt) for BTC/USDT perpetual with output to Parquet
□ Implement all CHECK-1 through CHECK-6 data integrity validations
□ Implement daily-4H alignment with unit test TEST-DATA-04
□ Implement regime classifier (6 regimes per Phase 2 corrected ordering)

PHASE 2 — INDICATOR LIBRARY
□ Implement EMA with warmup. Pass TEST-IND-01, TEST-IND-02.
□ Implement ATR with warmup. Pass TEST-IND-03.
□ Implement volume SMA with correct window. Pass TEST-IND-04.
□ Implement regime forward-fill. Pass TEST-IND-05.

PHASE 3 — SUPPORT DETECTION (S2)
□ Implement Variant A. Pass TEST-S2-01 through TEST-S2-03.
□ Implement Variant B. Pass TEST-S2-01 (lookahead boundary).
□ Implement detector comparison report.

PHASE 4 — BACKTEST ENGINE
□ Implement bar-by-bar loop with explicit phase ordering.
□ Implement slippage adjustment (effective_entry_price) in trade record creation.
□ Implement funding rate cost calculation in fee model.
□ Implement MAE/MFE tracking during open trade management (Phase B).
□ Implement lookahead verification procedure.
□ Pass all unit tests (including TEST-L2-07b for funding cost) before running any full backtest.

PHASE 5 — BACKTEST EXECUTION
□ Run L2 MVS in all 5 modes. Generate component attribution report.
□ Run S2 MVS with both detectors. Generate detector comparison report.
□ Run walk-forward validation: both Method A (rolling) and Method B (expanding).
□ Run slippage sensitivity sweep (0, 5, 10, 15 bps) for both strategies.
□ Apply research stop criteria before proceeding.

PHASE 6 — DIAGNOSTIC OUTPUTS
□ Generate all diagnostic output types for each passing strategy.
□ Generate buy-and-hold correlation report (L2 only, per Phase 2 Section 6).
□ Generate Exit Structure Isolation including Variant F for S2.
□ Evaluate against PROMISING/INCONCLUSIVE/REJECT thresholds (both walk-forward methods must pass).
□ Document findings before any code is written for ESS or production.

PHASE 7 — CROSS-STRATEGY DIAGNOSTICS (after both L2 and S2 pass individually)
□ Generate Portfolio Correlation Diagnostic: overlay L2 and S2 equity curves.
□ Quantify correlated drawdowns during TRANSITION regime periods.
□ If >30% of combined max drawdown occurs in TRANSITION, flag for review (threshold is preliminary per Phase 1).
□ Document cross-strategy findings before combined paper trading begins.

Ready to proceed to Phase 3 (Python research harness implementation) on your command, strictly scoped to what was defined in this specification.