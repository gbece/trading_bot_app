# Phase 2 — Strict Strategy Specification & Research Framework

> **[MODIFICACIÓN — Instrument Type Alignment]** All specifications in this document apply to **BTC/USDT perpetual contracts on Binance**, as declared in Phase 1's Instrument Type Declaration. Historical OHLCV data must be sourced from the perpetual contract, not spot. This is binding for v1.

---

## Part 1: L2 — EMA Pullback Long

### Minimal Viable Strategy Spec (MVS)

The MVS tests the core hypothesis with the absolute minimum number of rules. If the core hypothesis has no edge, additional filters cannot create it. If the MVS shows no edge, the strategy is rejected entirely regardless of how many filters are added.

**Core hypothesis in one sentence:**
In a confirmed uptrend, price pulling back to the 21 EMA on the 4H chart and then producing a bullish close has positive expectancy on the subsequent move.

**MVS Rules — 4 rules only:**

```
MVS-L2-1: Price on 4H is above the 200-period SMA on the daily chart at signal time.

MVS-L2-2: The current 4H candle low touches or crosses the 21 EMA (low <= EMA21 * 1.003).

MVS-L2-3: The current 4H candle closes bullish (close > open). Touch detection 
           (MVS-L2-2) and confirmation are evaluated on the SAME bar — the candle 
           must both touch the EMA and close bullish. Entry fires at this bar's close.
           (Design resolution documented in Phase 2.5 Section 4.1; L2_VARIANT_NEXTBAR 
           tests the alternative next-bar interpretation as a separate structural variant.)

MVS-L2-4: Entry at close of confirmation candle. Stop at 1.5× ATR(14) below EMA21 
           at entry time. Exit at 2× ATR(14) above entry price (fixed ratio TP, 
           no structural target in MVS).
           
           [MODIFICACIÓN — Slippage note] For accounting purposes, effective entry 
           price = close_price × (1 + slippage_bps / 10000) where slippage_bps = 10.
           Signal evaluation uses raw close_price; P&L and R-multiple use 
           effective_entry_price. Funding rate cost is computed at exit based on 
           holding duration. See Phase 1 parameter freeze table for values.
```

That is the entire MVS. No volume filter. No RSI. No prior move magnitude check. No declining volume requirement. Just: uptrend confirmed, price touches key dynamic support, bullish close follows, enter with mechanical stop and target.

**Why this is sufficient to test the core hypothesis:**
If buying EMA21 pullbacks in uptrends has no edge at all, the MVS will show it. If it does have edge, the enhanced spec layers in filters to improve signal quality. Starting with the MVS prevents the filters from masking the absence of a real core edge.

### Enhanced Strategy Spec (ESS)

The ESS adds filters on top of the MVS. Each filter must justify its existence against the cost it imposes (reduced trade count, added parameterization, added codability risk).

**ESS Rules — all MVS rules plus the following:**

```
ESS-L2-5: RSI(14) on the 4H is between 30 and 52 at the time of the EMA touch candle.

ESS-L2-6: Volume on the pullback candles (last 3 candles before confirmation) is below 
           the 20-period 4H volume average (avg of last 3 pullback candle volumes < SMA_vol_20).

ESS-L2-7: The prior upward move from the last swing low to the last swing high must be 
           >= 2.5× ATR(14) in magnitude, measured at signal time.

ESS-L2-8: The 4H 21 EMA must have a positive slope: EMA21[0] > EMA21[3] 
           (current EMA value greater than EMA value 3 candles ago).

ESS-L2-9: Trailing stop: once price has moved 1× ATR(14) above entry price, move stop to 
           entry price (breakeven). Thereafter trail at 1.5× ATR below the highest close 
           since entry.
```

**What was considered and deliberately excluded from ESS:**

- **ADX filter:** adds a second trend-strength measurement on top of the EMA slope check (ESS-L2-8). That is redundant. Two trend filters measuring similar things add parameter count without adding information. Excluded.
- **Time-of-day filter:** would reduce sample size further and introduce session-selection bias. Excluded.
- **Funding rate filter:** relevant as a signal filter for perpetuals but adds a data pipeline dependency that should not be in v1 ESS. Excluded as a **signal filter**. **[MODIFICACIÓN — Clarification]** Note: funding rate is modeled as a **cost** in the fee structure (per Phase 1 mandate), not excluded as a cost. The exclusion here refers only to using funding rate as an entry/exit signal condition.
- **Volatility spike filter (ATR percentile):** adds complexity and the ATR-based stop already adjusts for volatility implicitly. Excluded unless walk-forward results specifically show underperformance during high-volatility entries.

### Rule Classification Table — L2

| Rule | Description | Classification | Justification |
|---|---|---|---|
| MVS-L2-1 | Daily 200 SMA bull filter | Core hypothesis rule | The hypothesis is explicitly "in an uptrend." Without this, you are buying dips in downtrends, which is a different (and worse) hypothesis entirely. |
| MVS-L2-2 | 4H price touches 21 EMA | Core hypothesis rule | This IS the hypothesis. The EMA touch is the signal. Removing this removes the strategy. |
| MVS-L2-3 | Confirmation candle bullish close | Anti-noise filter | Prevents entering on an EMA touch that continues downward. Minimal cost: reduces entries on candles that would immediately stop out. Justified. |
| MVS-L2-4 | Fixed ATR stop and target | Risk control rule | Non-negotiable in any systematic strategy. The specific multipliers (1.5× stop, 2× TP) are the only fragile element here — they must be fixed before backtesting. |
| ESS-L2-5 | RSI 30–52 at touch | Anti-noise filter | Intended to exclude EMA touches that occur during deeper corrections (RSI < 30) or overbought continuation moves (RSI > 52). Risk: the specific band is empirically derived and unfixed — see overfitting risk column in matrix below. |
| ESS-L2-6 | Declining volume on pullback | Anti-noise filter | Distinguishes distribution pullbacks (high volume selling) from consolidation pullbacks (low volume). Justified in theory. Risk: 20-period average includes candles from different sessions, diluting the signal. |
| ESS-L2-7 | Prior move >= 2.5× ATR | Anti-noise filter | Ensures the pullback follows a real move, not a micro-wiggle at the EMA. Prevents entries in choppy flat markets where the EMA is being touched constantly. Borderline necessary — without it, the strategy trades noise around the EMA in ranging conditions. |
| ESS-L2-8 | EMA slope positive | Anti-noise filter | Ensures the dynamic support is actually dynamic and rising. A flat or declining EMA means the "uptrend" momentum is weakening. This is a legitimate filter but partially redundant with the 200 SMA filter. Borderline — keep for v1 but monitor whether it adds marginal value. |
| ESS-L2-9 | Trailing stop to breakeven then trail | Risk control rule | Mechanically sound. Protects open profits once established without requiring a structural judgment. The trailing distance (1.5× ATR) must be fixed and not optimized. |

**Rules considered and rejected (not in MVS or ESS):**

| Rejected Rule | Reason for Rejection |
|---|---|
| ADX > 25 filter | Redundant with EMA slope (ESS-L2-8) and 200 SMA (MVS-L2-1). Third trend measurement on top of two existing ones adds overfitting risk without adding new information type. |
| Candle body size minimum | Pattern-matching filter with no causal grounding. Would reduce sample size with no mechanistic justification. Likely overfitting risk. |
| Time-of-day filter | Session bias. Would artificially improve backtest performance by excluding certain periods. Not justified without tick data and session volume analysis. |
| Multiple timeframe RSI alignment | Indicator duplication. RSI on two timeframes introduces correlated noise, not independent confirmation. |
| Min volume on confirmation candle | Volume on a single candle is too noisy to filter reliably. The confirmation candle volume filter was removed — only the pullback volume matters for the hypothesis. |

### Research Matrix — L2

| Rule | Purpose | Codability Risk | Overfitting Risk | Effect on Trade Count | Effect on Win Rate | Effect on Avg R | Keep for v1? |
|---|---|---|---|---|---|---|---|
| MVS-L2-1 (200 SMA daily) | Macro regime filter — only trade in uptrends | Low. Binary: price > SMA(200). Deterministic. | Medium. SMA(200) is standard but selecting this period over SMA(150) or SMA(100) is a choice. The specific number was not tested; it is a convention. | High reduction. Removes ~40–50% of calendar time depending on asset. | High positive expected effect. Removes most bear market losses by construction. | Moderate positive. Trades in uptrends have structurally better R due to trend momentum. | Yes |
| MVS-L2-2 (EMA21 touch) | Core signal entry trigger | Low-Medium. "Touch" tolerance (0.003 = 0.3%) is a parameter. Different tolerances produce meaningfully different signal sets. | Medium. Touch tolerance is a free parameter. Must be fixed. | Primary signal driver. Loosening tolerance increases trades; tightening reduces. | Neutral to slightly positive. Tighter touch = higher quality entry; fewer entries. | Positive with tighter tolerance. | Yes |
| MVS-L2-3 (Confirmation candle) | Prevent entries on continued downward momentum | Low. close > open is unambiguous. | Low. This is a binary condition with no tunable parameters. | Low reduction (~15–20%). Only removes immediately bearish continuation candles. | Moderate positive. Filters out entries that would hit stops quickly. | Slight positive. Stops out fewer trades at maximum loss. | Yes |
| MVS-L2-4 (ATR stop + TP) | Risk control — define trade boundaries | Low. ATR calculation is standard. | High. The 1.5× stop and 2× TP multipliers are the two most performance-sensitive parameters in the entire strategy. Must be fixed before any backtest run. | N/A (affects R, not trade count). | Significant effect. Different TP ratios produce very different apparent win rates. | Directly determined by these multipliers. This is the most impactful parameter pair. | Yes, but fix multipliers before running |
| ESS-L2-5 (RSI 30–52) | Remove deep corrections and overbought entries | Low-Medium. RSI calculation is standard; the band boundaries are parameters. | High. Both the lower (30) and upper (52) bounds are free parameters. The band was not derived from a theoretical argument — it was estimated intuitively. If swept against backtest results, this is direct overfitting. | Moderate reduction (~20–30%). Removes entries during momentum extremes. | Unclear without testing. The intuitive case is positive, but the specific bounds are uncertain. | Unclear. May improve by removing mean-reversion false entries. | Conditional. Include in ESS backtest only. Compare ESS vs MVS performance directly. |
| ESS-L2-6 (Declining pullback volume) | Distinguish healthy pullbacks from distribution | Medium. Requires consistent definition of "pullback candles" — the 3 candles before confirmation is a parameter (could be 2 or 4). | Medium. The 20-period average and the "last 3 candles" rule are both parameters. The direction of the effect is theoretically justified but the implementation details are fragile. | Low-moderate reduction (~10–20%). | Small positive expected. Removes highest-risk entries. | Small positive expected. | Conditional. Test ESS with and without this rule. Keep only if statistically meaningful improvement on out-of-sample. |
| ESS-L2-7 (Prior move >= 2.5× ATR) | Require real trend move before pullback | Medium. "Prior move" requires defining swing low identification algorithm. That algorithm has its own parameters. | Medium. The 2.5× multiplier is arbitrary. However, having some minimum is necessary to prevent flat-market noise entries. This is a necessary filter with an uncertain threshold. | Moderate reduction (~15–25%). Most impactful in ranging markets. | Positive in ranging periods, neutral in trending periods. | Moderate positive in choppy conditions. | Yes. But treat 2.5× as a soft minimum, not an optimized value. |
| ESS-L2-8 (EMA slope positive) | Ensure dynamic support is rising | Low. EMA[0] > EMA[3] is a direct comparison. The 3-candle lookback is a parameter. | Low-Medium. The lookback (3 candles = 12 hours) is a reasonable choice but untested. | Low reduction (~10%). Most EMA touches in uptrends already occur on a rising EMA. | Small positive. Removes a handful of late-cycle entries. | Neutral to small positive. | Yes. Low cost, adds structural coherence. |
| ESS-L2-9 (Trailing stop) | Protect unrealized profits | Low. Mechanical calculation. | Low for the rule itself. The trailing distance (1.5× ATR) adds one parameter but it is secondary to the initial stop. | N/A (affects R, not entry count). | Neutral to slight negative on win rate (more trades close at breakeven rather than full TP). | Positive on expectancy. Protects against giving back large gains. | Yes. But fix trailing distance before backtesting. |

---

## Part 2: S2 — Support Breakdown Short

### Minimal Viable Strategy Spec (MVS)

**Core hypothesis in one sentence:**
When a clearly established horizontal support level (touched 3+ times on the 4H chart) breaks down on a high-volume 4H candle close, price tends to continue lower.

**MVS Rules — 4 rules only:**

```
MVS-S2-1: Identify support level: a price zone where the 4H candle low has come within 
           0.5% of the same level at least 3 times in the prior 60 candles, 
           with each touch followed by at least a 1× ATR(14) upward move 
           (confirming support held).

MVS-S2-2: Breakdown trigger: a 4H candle closes more than 0.3% below the support level.

MVS-S2-3: Volume confirmation: breakdown candle volume > 1.5× the 20-period 4H volume average.

MVS-S2-4: Entry at close of breakdown candle. Stop at 0.5× ATR(14) above the support level.
           Exit target: 2× ATR(14) below entry price (fixed mechanical target in MVS).
           
           [MODIFICACIÓN — Slippage note] Effective entry price for short: 
           close_price × (1 - slippage_bps / 10000) where slippage_bps = 10.
           Funding rate cost applied at exit per Phase 1 cost model.
```

No trend filter. No EMA context. No retest logic. No funding rate signal filter. Just: clear support level, volume-confirmed breakdown, mechanical stop and target. This is the purest form of the hypothesis.

### Enhanced Strategy Spec (ESS)

```
ESS-S2-5: The 4H 50 EMA must be above the current price at entry, OR price must have 
           crossed below the 50 EMA within the prior 10 candles. This filters out 
           breakdowns that occur in strong uptrend contexts where recoveries are likely.

ESS-S2-6: The daily 200 SMA must not be more than 3× ATR(14, daily) below the current 
           price. This prevents shorting into deeply oversold conditions on the macro chart
           where a mean-reversion bounce is likely.

ESS-S2-7: Minimum support level "age": the first touch of the support level must have 
           occurred at least 10 candles (40 hours) before the breakdown. 
           This prevents shorting freshly formed micro-levels.

ESS-S2-8: No trade if the prior 5-day price range (daily high - daily low average) is in 
           the bottom 20th percentile of the prior 60-day distribution. 
           This avoids breakdowns in dead markets where volume confirmation is meaningless.

ESS-S2-9: Time-based exit: if price has not moved 1× ATR below entry within 6 candles (24H),
           exit at market. A breakdown that stalls is likely to reverse.
```

**What was considered and deliberately excluded from ESS:**

- **RSI filter on breakdown:** if volume is confirming the breakdown, RSI provides redundant momentum information. Two momentum proxies (volume and RSI) are correlated. Excluded.
- **Retest entry mode:** rejected as discussed in the overfitting section. One entry mode only.
- **Funding rate filter:** deferred to v2 / S3 strategy as a **signal filter**. Adds infrastructure complexity. **[MODIFICACIÓN — Clarification]** Funding rate is modeled as a **cost** in the fee structure per Phase 1 mandate. This exclusion refers only to using funding rate as an entry condition.
- **Multiple timeframe support confluence:** adds significant codability risk and subjectivity. If 4H support breaks with volume, daily context is partially captured by ESS-S2-5 and ESS-S2-6.

### Rule Classification Table — S2

| Rule | Description | Classification | Justification |
|---|---|---|---|
| MVS-S2-1 | Support level detection (3+ touches, 60-candle lookback) | Core hypothesis rule | This IS the hypothesis. Without a defined support level, there is no strategy. The touch count (3) and lookback (60 candles) are parameters but a minimum threshold is non-negotiable. |
| MVS-S2-2 | 4H close below support by 0.3% | Core hypothesis rule | Differentiates close-through from wick-through. A wick breakdown with a close above is noise; a body close below is a structural event. The 0.3% threshold is a parameter but the distinction is necessary. |
| MVS-S2-3 | Volume >= 1.5× average on breakdown | Core hypothesis rule | Without volume confirmation, the hypothesis has no causal mechanism. A low-volume breakdown is a thin-market artifact, not a genuine supply/demand shift. This is the most important single filter in the strategy. |
| MVS-S2-4 | Fixed ATR stop and TP | Risk control rule | Non-negotiable. Specific multipliers must be fixed before testing. |
| ESS-S2-5 | 4H 50 EMA context filter | Anti-noise filter | Prevents shorting at support levels in strong uptrends where the "support break" is really just a brief penetration before recovery. Has legitimate justification. |
| ESS-S2-6 | Daily 200 SMA proximity floor | Risk control rule | Prevents shorting into macro oversold conditions. The 3× ATR threshold is a parameter but the rule's existence is justified by the asymmetric flush risk when price is already deeply extended below the macro mean. |
| ESS-S2-7 | Support age minimum (10 candles) | Anti-noise filter | Freshly formed support levels (touched 3 times in 10 candles) are different in character from mature support levels. Very new "support" often reflects consolidation rather than genuine buy-side commitment at a level. Justified but borderline. |
| ESS-S2-8 | Low-volatility market filter | Anti-noise filter | Volume confirmation is less meaningful in structurally thin markets. A 1.5× volume threshold means little if the absolute volume is tiny. This filter adds a relative volatility check. Justified but the 20th percentile threshold is a parameter. |
| ESS-S2-9 | 24H time exit | Risk control rule | Breakdowns that do not follow through are likely to reverse. Holding a stalled short exposes capital to an unpredictable recovery. The 6-candle (24H) threshold is a parameter but the rule's existence is clearly justified. |

**Rules considered and rejected:**

| Rejected Rule | Reason |
|---|---|
| Retest entry (pullback to broken support before entering) | Creates dual-entry logic that is a hidden source of curve-fitting. One entry mode only. |
| RSI < 50 at breakdown | Redundant with volume confirmation and EMA context filter. Momentum information already captured. |
| BTC trend alignment for altcoin shorts | Valid concept but introduces inter-asset dependency. Reserve for multi-asset version. Not in v1 scope. |
| Minimum prior uptrend requirement before breakdown | Too similar to distribution pattern logic (S1), which was rejected for subjectivity. |
| Max consecutive down candles before breakdown | This is a micro-pattern within the setup that has no causal justification. |

### Research Matrix — S2

| Rule | Purpose | Codability Risk | Overfitting Risk | Effect on Trade Count | Effect on Win Rate | Effect on Avg R | Keep for v1? |
|---|---|---|---|---|---|---|---|
| MVS-S2-1 (Support detection) | Define the level being traded | High. Most complex piece of code in the strategy. Touch tolerance, lookback window, minimum bounce requirement, and deduplication of adjacent touches are all parameters within this single rule. | High. Changing any sub-parameter of the detection algorithm changes the entire signal set. Must be implemented once and frozen. | Primary driver of signal frequency. Tighter detection = fewer, higher-quality levels. | Moderate positive effect from tighter detection. | Moderate positive. Better-defined levels tend to produce cleaner breakdowns. | Yes. But the detection algorithm is the highest-priority item to get right before any backtesting begins. |
| MVS-S2-2 (Breakdown close threshold) | Confirm body close, not wick | Low. close < level × (1 - 0.003) is deterministic. | Low-Medium. The 0.3% threshold is a parameter. However, the direction of the rule is mechanically necessary — any threshold between 0.1% and 0.5% serves the same purpose. Sensitivity sweep appropriate. | Low-Moderate. Increasing threshold from 0.3% to 0.5% reduces trades by ~20–30%. | Small positive effect. | Small positive. Larger gap = more conviction, but also worse entry price. | Yes. Fix at 0.3%. |
| MVS-S2-3 (Volume 1.5×) | Filter out thin/illiquid breakdowns | Low. Relative volume is a direct ratio calculation. | High. This single parameter more than any other determines the strategy's behavior. 1.5× is the most important number to fix before backtesting. If swept against results, it will overfit directly to the historical distribution of breakdown volumes. | High reduction. Eliminates a large portion of breakdowns (rough estimate 40–60% of raw breakdown signals fail volume check). | High positive. Volume is the primary quality filter. | Positive. High-volume breakdowns tend to follow through further. | Yes. Fix at 1.5× and do not tune. |
| MVS-S2-4 (ATR stop + TP) | Define trade risk boundaries | Low. ATR is standard. | High. Same concern as L2. The stop multiplier (0.5× ATR above level) and TP multiplier (2× ATR below entry) directly determine apparent win rate. Must be fixed before any backtest run. | N/A. | The ratio between stop distance and TP distance determines win rate by construction at any given volatility level. | Directly defined by multipliers. | Yes. Fix stop at 0.5× ATR, TP at 2× ATR. Non-negotiable. |
| ESS-S2-5 (50 EMA context) | Avoid shorting strong uptrends | Low. price < EMA50 or price crossed EMA50 within 10 candles is deterministic if the crossover is defined precisely. | Medium. The 50 EMA period and the 10-candle lookback for recent crossover are both parameters. However, the EMA period (50) is a widely used convention and the crossover lookback is secondary. | Moderate reduction (~15–25%). | Moderate positive. Removes the highest-risk short setups. | Moderate positive. Avoids the worst mean-reverting losses. | Yes. |
| ESS-S2-6 (Daily 200 SMA floor) | Prevent shorting into deep macro oversold | Medium. Requires daily ATR calculation and comparison against daily price position relative to 200 SMA. | Low-Medium. The 3× ATR threshold is a parameter but its purpose is to create a floor, not to be optimized. Conservative choice preferred. | Low reduction. Only triggers in deep bear conditions near macro lows. | Small positive in extreme conditions. | Small positive. Prevents rare but large mean-reversion losses. | Yes. This is a risk control rule. Keep. |
| ESS-S2-7 (Support age >= 10 candles) | Exclude freshly formed micro-levels | Low. Timestamp comparison between first touch and breakdown is deterministic. | Low. The 10-candle minimum is not a parameter that will produce meaningfully different results if changed to 8 or 12. | Low-Moderate reduction (~10–15%). Mostly removes breakdowns from very recent consolidation zones. | Small positive. Older support levels tend to be more meaningful. | Small positive. | Yes. Low cost, adds structural coherence. |
| ESS-S2-8 (Low-volatility market filter) | Avoid breakdowns in dead markets | Medium. Requires ATR percentile calculation over rolling 60-day window. | Medium. The 20th percentile threshold is a parameter. However, the direction is clear: very low volatility environments invalidate volume comparisons. | Low reduction under normal conditions. | Small positive. | Neutral to small positive. | Conditional. Include in ESS backtest but test whether it improves out-of-sample performance. Low priority. |
| ESS-S2-9 (24H time exit) | Exit stalled breakdowns | Low. Candle count comparison is deterministic. | Low. The 6-candle threshold is a parameter but its purpose is structural, not performance-optimizing. Any value between 4 and 8 candles would produce similar behavior. | N/A (affects exit, not entry). | Negative effect on gross win rate (forces exits at loss when breakdown stalls). | Positive on expectancy. Eliminates the long tail of stalled-then-reversed losses. | Yes. Risk control rule. Non-negotiable. |

---

## Part 3: Regime Segmentation — Mathematical Definitions

These definitions must be applied identically in all backtests for both strategies. They must be computed from data available at each point in time (no lookahead). Regime labels are assigned to each trading day based on conditions met at the close of that day.

### Regime Definition Framework

All regime indicators are computed on BTC daily OHLCV data as the macro reference asset, regardless of which asset is being traded. BTC is the regime anchor.

**Regime variables computed daily:**

```
SMA_200     = Simple moving average of BTC daily close, 200 periods
SMA_50      = Simple moving average of BTC daily close, 50 periods
ATR_14_D    = Average True Range of BTC daily, 14 periods
ATR_pct     = ATR_14_D / BTC_close  (normalized ATR as % of price)
ROC_20      = (BTC_close - BTC_close[20]) / BTC_close[20]  (20-day return)
VOL_ratio   = Current ATR_14_D / SMA(ATR_14_D, 60)  (volatility vs 60-day average)
```

> **[MODIFICACIÓN — Regime classifier updated: 5 regimes → 6 regimes]**
> The original classifier used a single HIGH_VOLATILITY regime. Per Phase 1 mandate, high volatility during bull markets and during bear markets produce fundamentally different behavior and must be classified separately.

**Regime classification rules (applied in this exact order — first match wins):**

```python
def classify_regime(btc_close, SMA_200, SMA_50, ATR_pct, ROC_20, VOL_ratio):
    
    # REGIME 1: STRONG BULL
    # Condition: Price well above both MAs, strong positive momentum, 
    #            normal-to-low volatility
    # NOTE: VOL_ratio < 1.5 ensures high-volatility days are NOT captured here.
    #       A day with strong momentum AND extreme volatility falls through 
    #       to HIGH_VOL_BULLISH below. This is intentional.
    if (btc_close > SMA_200 * 1.05 and 
        btc_close > SMA_50 and 
        ROC_20 > 0.10 and 
        VOL_ratio < 1.5):
        return "STRONG_BULL"
    
    # [FIX — ORDERING CORRECTED] REGIME 2A: HIGH VOLATILITY — BULLISH
    # MUST be checked BEFORE WEAK_BULL. Otherwise, WEAK_BULL's broad 
    # condition (price > SMA_200 and ROC_20 > -0.05) captures all 
    # bullish high-vol days, making HIGH_VOL_BULLISH unreachable.
    # Condition: Volatility spike while price is above 200 SMA
    # Behavior: FOMO-driven spikes, aggressive dip-buying, V-shaped recoveries
    # Support breakdowns in this regime are predominantly false
    if VOL_ratio >= 2.0 and btc_close > SMA_200:
        return "HIGH_VOL_BULLISH"
    
    # [FIX — ORDERING CORRECTED] REGIME 2B: HIGH VOLATILITY — BEARISH
    # Checked before BEAR for the same reason: BEAR's condition would 
    # otherwise absorb high-vol bearish days.
    # Condition: Volatility spike while price is below 200 SMA
    # Behavior: Capitulation selling, cascading liquidations, dead-cat bounces
    # Support breakdowns in this regime have genuine follow-through
    if VOL_ratio >= 2.0 and btc_close <= SMA_200:
        return "HIGH_VOL_BEARISH"
    
    # REGIME 3: WEAK BULL / CONSOLIDATION
    # Condition: Price above 200 SMA but momentum fading or mildly negative
    # NOTE: Reaches here only if VOL_ratio < 2.0 (high-vol already captured above)
    if (btc_close > SMA_200 and 
        ROC_20 > -0.05):
        return "WEAK_BULL"
    
    # REGIME 4: BEAR TREND
    # Condition: Price below 200 SMA, negative momentum
    # NOTE: Reaches here only if VOL_ratio < 2.0
    if (btc_close < SMA_200 and 
        ROC_20 < -0.05):
        return "BEAR"
    
    # REGIME 5: TRANSITION / UNCERTAIN
    # Condition: Everything else — price near 200 SMA, weak momentum,
    #            or conflicting signals
    return "TRANSITION"
```

> **[FIX — Ordering rationale]** In the original 5-regime classifier, HIGH_VOLATILITY was placed after WEAK_BULL, which meant it only captured bearish high-vol days (bullish high-vol was absorbed by WEAK_BULL). With the split into HIGH_VOL_BULLISH and HIGH_VOL_BEARISH, both must be checked before WEAK_BULL and BEAR to correctly capture their respective conditions. STRONG_BULL is safe at position 1 because it explicitly requires VOL_ratio < 1.5, which excludes all days with VOL_ratio >= 2.0.

**Regime classification is point-in-time.** Each day's regime is determined using only data available at that day's close. No forward-looking regime labels.

**Regime frequency expectation (approximate, based on BTC 2018–2024):**

- STRONG_BULL: ~25% of trading days
- WEAK_BULL: ~17% of trading days (reduced from ~20% — days with VOL_ratio >= 2.0 now correctly classified as HIGH_VOL_BULLISH instead)
- HIGH_VOL_BULLISH: ~6% of trading days (captures euphoric spikes previously misclassified as WEAK_BULL)
- HIGH_VOL_BEARISH: ~5% of trading days (captures panic crashes previously the only HIGH_VOLATILITY subtype)
- BEAR: ~29% of trading days (marginally reduced — some extreme bear days now classified as HIGH_VOL_BEARISH)
- TRANSITION: ~18% of trading days

Note: These are estimates. The actual distribution must be computed from the dataset and reported before any backtest is interpreted. The key change from the prior estimate is that HIGH_VOL_BULLISH increased from ~4% to ~6% because the ordering fix now correctly routes euphoric bull volatility away from WEAK_BULL.

---

### Required Backtest Reporting Format by Regime

Every backtest must produce the following output structure. A single aggregate performance number without regime breakdown is insufficient for strategy evaluation and will not be accepted.

```
BACKTEST REPORT — [STRATEGY NAME] — [ASSET] — [DATE RANGE]
═══════════════════════════════════════════════════════════

SECTION 1: AGGREGATE PERFORMANCE
─────────────────────────────────
Total trades:           [N]
Win rate:               [%]
Profit factor:          [ratio]
Expectancy per trade:   [$ or R]
Total return:           [%]
Max drawdown:           [%]
Sharpe ratio:           [value, annualized]
Avg R-multiple:         [value]
Longest losing streak:  [N trades]
Avg trade duration:     [hours]

SECTION 2: PERFORMANCE BY REGIME
──────────────────────────────────
For each regime {STRONG_BULL, WEAK_BULL, HIGH_VOL_BULLISH, 
                 HIGH_VOL_BEARISH, BEAR, TRANSITION}:
  [MODIFICACIÓN: now 6 regimes, not 5]

  Regime: [NAME]
  ─────────────
  Trades in regime:         [N]      (% of total)
  Win rate:                 [%]
  Profit factor:            [ratio]
  Expectancy:               [R]
  Contribution to total PnL:[%]
  Max drawdown in regime:   [%]
  Avg R-multiple:           [value]
  Notes:                    [flag if N < 15 — statistically insufficient]

SECTION 3: WALK-FORWARD VALIDATION
────────────────────────────────────
Method A — Rolling windows:
  Split method: [rolling 6-month windows, 4-month train / 2-month test]
  
  For each window:
    Period:         [date range]
    Train trades:   [N]
    Test trades:    [N]
    Train PF:       [ratio]
    Test PF:        [ratio]
    Delta (overfit indicator): Train PF - Test PF = [value]
    
  Mean test PF across all windows:     [value]
  Std dev of test PF across windows:   [value]
  % of windows where test PF > 1.0:    [%]

[MODIFICACIÓN — Method B added]
Method B — Expanding windows:
  Split method: [expanding train set, fixed 6-month test, 
                 advancing in 6-month non-overlapping increments]
  
  [FIX — Step size explicit] Windows advance by 6 months (test periods 
  do not overlap). Example with data starting 2020-01:
    Window 1: Train 2020-01 → 2021-06, Test 2021-07 → 2021-12
    Window 2: Train 2020-01 → 2021-12, Test 2022-01 → 2022-06
    Window 3: Train 2020-01 → 2022-06, Test 2022-07 → 2022-12
    Window 4: Train 2020-01 → 2022-12, Test 2023-01 → 2023-06
    ... etc.
  
  For each window:
    Train period:   [start of data → end of train]
    Test period:    [next 6 months after train]
    Train trades:   [N]
    Test trades:    [N]
    Train PF:       [ratio]
    Test PF:        [ratio]
    Delta:          Train PF - Test PF = [value]
  
  Mean test PF across all windows:     [value]
  Std dev of test PF across windows:   [value]
  % of windows where test PF > 1.0:    [%]
  
  Note: Method B reflects how the strategy would be used in practice 
  (never discarding old training data). If Method A shows degradation 
  but Method B is stable, the strategy may be sensitive to 
  out-of-distribution train periods. Report both.

SECTION 4: PARAMETER SENSITIVITY
──────────────────────────────────
For each fixed parameter:
  Parameter:          [name]
  Fixed value:        [value]
  Range tested:       [±20% of fixed value]
  Performance range:  [min PF — max PF across range]
  Sensitivity label:  [STABLE / MODERATE / FRAGILE]
  
  STABLE:   Performance range < 0.3 PF units across ±20% variation
  MODERATE: Performance range 0.3–0.8 PF units
  FRAGILE:  Performance range > 0.8 PF units

[MODIFICACIÓN — Slippage sensitivity added]
Slippage sensitivity (not a strategy parameter — a cost model assumption):
  Slippage values tested: [0, 5, 10, 15 bps]
  
  For each value:
    Slippage:       [bps]
    PF:             [ratio]
    Expectancy:     [R]
    Win rate:       [%]
  
  If PF drops below 1.0 at 15 bps slippage:
      WARNING: Strategy is not tradeable under realistic execution conditions.
  If PF drops below 1.0 at 10 bps:
      CRITICAL: Strategy edge is entirely consumed by execution costs.

SECTION 5: TRADE LOG (first 20 and last 20 trades shown)
──────────────────────────────────────────────────────────
[trade_id | entry_date | entry_price | effective_entry_price | 
 stop | target | exit_date | exit_price | exit_reason | 
 R_multiple_net | regime | gross_pnl | fee_total | funding_cost | 
 net_pnl | mae | mfe]

[MODIFICACIÓN — New fields added:]
  effective_entry_price: entry_price adjusted for slippage
  funding_cost:          funding rate cost for trade holding period
  mae:                   Maximum Adverse Excursion — largest unrealized loss 
                         during trade, computed from bar extremes (not closes).
                         For longs: mae = effective_entry_price - min(bar_lows 
                         from entry bar+1 to exit bar). 
                         For shorts: mae = max(bar_highs from entry bar+1 
                         to exit bar) - effective_entry_price.
                         Always expressed as a positive number (magnitude of 
                         worst drawdown). Useful for diagnosing whether stops 
                         are too tight (MAE clusters near stop distance).
  mfe:                   Maximum Favorable Excursion — largest unrealized gain 
                         during trade, computed from bar extremes.
                         For longs: mfe = max(bar_highs from entry bar+1 
                         to exit bar) - effective_entry_price.
                         For shorts: mfe = effective_entry_price - min(bar_lows 
                         from entry bar+1 to exit bar).
                         Always positive. Useful for diagnosing whether targets 
                         are too ambitious (MFE clusters below target distance).

[MODIFICACIÓN — New Section 6 added]
SECTION 6: BUY-AND-HOLD COMPARISON (L2 only)
──────────────────────────────────────────────
Per 6-month period (aligned with Period Isolation Report):

  Period          | L2 PF  | L2 Expectancy | BTC B&H Return | Correlation
  ─────────────────────────────────────────────────────────────────────────
  2020-01 to 06   | [x]    | [R]           | [%]            |
  2020-07 to 12   | [x]    | [R]           | [%]            |
  ... etc.

  Pearson correlation (L2 period PF, BTC period return): [r]
  
  If r > 0.80:
      WARNING: STRATEGY PERFORMANCE CORRELATED WITH UNDERLYING TREND.
      L2's entry signal may not add value over regime beta exposure.
      The entry logic must demonstrate marginal improvement over 
      buy-and-hold in the same bull-market windows.
  
  This diagnostic does not disqualify L2 — it contextualizes the edge.
  A trend-following strategy SHOULD correlate with the trend. The question 
  is whether the entry signal provides better risk-adjusted returns than 
  undifferentiated long exposure during the same periods.
```

---

## Part 4: Performance Thresholds — Promising / Inconclusive / Reject

These thresholds are defined before any backtest is run. Changing them after seeing results is a form of overfitting to backtest outcomes.

---

### L2 — EMA Pullback Long

**For the MVS (minimum viable spec):**

> **[MODIFICACIÓN — Regime count updated: "3 of 5" → "4 of 6"]**

| Outcome Label | Criteria | Interpretation |
|---|---|---|
| **PROMISING** | Total trades ≥ 50 AND profit factor ≥ 1.30 AND win rate ≥ 48% AND max drawdown ≤ 20% AND at least **4 of 6** regimes show positive expectancy AND walk-forward mean test PF ≥ 1.15 AND walk-forward test PF > 1.0 in ≥ 60% of windows (**both** Method A **and** B) | The core hypothesis shows genuine edge across multiple regimes and survives out-of-sample validation under both rolling and expanding validation. Proceed to ESS backtest. |
| **INCONCLUSIVE** | Total trades ≥ 50 AND profit factor between 1.05–1.30 OR win rate 42–48% OR walk-forward test PF between 0.95–1.15 in either Method A or B OR fewer than 4 regimes positive OR **Method B passes but Method A fails** (indicates strategy degrades in local windows despite performing well with full training history — possible overfitting to the full period) | Results do not clearly confirm or reject the hypothesis. The strategy may have edge but it cannot be demonstrated at this sample size. Do not proceed to live paper trading. Consider: more data, different asset, longer period. Flag as requiring further research. |
| **REJECT** | Profit factor < 1.05 OR max drawdown > 30% OR win rate < 40% OR total trades < 30 (insufficient sample) OR walk-forward test PF < 0.95 in majority of windows OR strategy profitable only in STRONG_BULL regime | No evidence of systematic edge. Additional filters (ESS) should not be tested — if the core hypothesis fails, filters cannot rescue it. |

**For the ESS (enhanced spec), additional criteria:**

After the MVS passes the PROMISING threshold:
- ESS must show profit factor improvement of at least +0.10 over MVS on out-of-sample data. If ESS improves in-sample but not out-of-sample, the filters are overfitting. Reject the filters, keep MVS.
- ESS trade count must not fall below 35 total (filters cannot be so restrictive that sample size becomes statistically meaningless).

---

### S2 — Support Breakdown Short

**For the MVS:**

> **[MODIFICACIÓN — HIGH_VOLATILITY → HIGH_VOL_BEARISH in PROMISING criteria]**

| Outcome Label | Criteria | Interpretation |
|---|---|---|
| **PROMISING** | Total trades ≥ 40 AND profit factor ≥ 1.25 AND win rate ≥ 44% AND max drawdown ≤ 25% AND strategy shows positive expectancy in at least **BEAR and HIGH_VOL_BEARISH** regimes AND walk-forward mean test PF ≥ 1.10 AND walk-forward test PF > 1.0 in ≥ 55% of windows (**both** Method A **and** B) | Note: lower thresholds than L2 because shorting has structural headwinds in crypto. These are calibrated accordingly. **[MODIFICACIÓN]** Positive expectancy in HIGH_VOL_BULLISH is NOT required and NOT expected — support breakdowns in euphoric high-volatility environments are predominantly false. |
| **INCONCLUSIVE** | Total trades ≥ 40 AND profit factor between 1.00–1.25 OR walk-forward test PF between 0.90–1.10 in either Method A or B OR positive expectancy only in BEAR regime (without HIGH_VOL_BEARISH) OR **Method B passes but Method A fails** | Edge unclear. Short strategies with edge only in trending bear regimes are not robust — they require perfect regime timing which is not available in real time. Must also show edge in volatile bear conditions. |
| **REJECT** | Profit factor < 1.00 OR max drawdown > 35% OR win rate < 38% OR total trades < 25 OR strategy shows negative expectancy in STRONG_BULL and WEAK_BULL (expected) but also in **both BEAR and HIGH_VOL_BEARISH** (unacceptable — if it can't make money in any bearish environment, it has no business being a short strategy). **[FIX]** Negative expectancy in only one of BEAR or HIGH_VOL_BEARISH is not an automatic reject — it is INCONCLUSIVE and requires investigation into why one bearish sub-regime works and the other doesn't. |

**Special requirement for S2 not applicable to L2:**
S2 must be evaluated separately on 2022 bear-market data and on 2023–2024 recovery data. If the entire profit factor is explained by 2022 performance, the strategy has no regime-general edge. This is a hard requirement.

---

## Part 5: Hard Kill Criteria

These are operational kill switches that terminate live paper trading of a strategy regardless of its backtest performance. They must be implemented in code and cannot be overridden manually.

---

### L2 — Hard Kill Criteria

```
KILL-L2-1: DRAWDOWN KILL
If live paper trading equity falls 15% below starting capital at any point,
halt all new entries immediately. Review required before resuming.
Rationale: A 15% drawdown in paper trading on a strategy that showed 
a max 20% backtest drawdown suggests the strategy is performing 
significantly worse than expected. This is a signal of regime mismatch 
or implementation error, not normal variance.

KILL-L2-2: CONSECUTIVE LOSS STREAK
If the strategy records 8 consecutive losing trades, halt new entries.
Review required before resuming.
Rationale: 8 consecutive losses on a strategy with ~50% historical 
win rate has a probability of approximately (0.5^8) = 0.4% under 
the historical model. If it occurs, something is wrong with the 
regime, the implementation, or the strategy has stopped working.

KILL-L2-3: PROFIT FACTOR DEGRADATION
If rolling 30-trade profit factor drops below 0.80,
halt new entries. Review required before resuming.
Rationale: A profit factor of 0.80 on 30 trades represents 
statistically meaningful underperformance relative to a 1.30+ 
backtest result. Not noise — systematic degradation.

KILL-L2-4: DATA QUALITY KILL
If the data feed produces more than 3 missing candles in any 24-hour 
period, or if ATR values deviate by more than 50% from their 
5-day average without a corresponding price move, halt trading.
Rationale: Bad data produces bad signals. Never attribute 
poor performance to the strategy when data quality may be the cause.

KILL-L2-5: MACRO REGIME OVERRIDE
If BTC daily price closes below its 200 SMA for 5 consecutive days,
suspend the long strategy entirely regardless of signal quality.
Resume only when price reclaims and holds the 200 SMA for 3 
consecutive daily closes.
Rationale: L2 is structurally dependent on a bull market. Operating 
it in a confirmed bear market violates the strategy's foundational 
assumption and will produce a sequence of losses that the strategy 
was never designed to avoid.
```

---

### S2 — Hard Kill Criteria

```
KILL-S2-1: DRAWDOWN KILL
If live paper trading equity falls 20% below starting capital,
halt all new entries. Review required before resuming.
Rationale: Higher threshold than L2 because short strategies 
in crypto have higher variance. 20% is still significantly 
worse than the 25% max backtest drawdown threshold and warrants review.

KILL-S2-2: CONSECUTIVE LOSS STREAK
If the strategy records 7 consecutive losing trades, halt new entries.
Rationale: At a historical win rate of ~44%, 7 consecutive losses 
has a probability of approximately (0.56^7) = 1.5% under the model.
Possible but unlikely. More likely indicates regime mismatch.

KILL-S2-3: PROFIT FACTOR DEGRADATION
If rolling 25-trade profit factor drops below 0.75, halt new entries.
Rationale: S2 has a lower expected profit factor than L2.
The kill threshold is calibrated accordingly but still represents
clear underperformance.

KILL-S2-4: STRONG BULL / EUPHORIC VOLATILITY OVERRIDE
[MODIFICACIÓN — Added HIGH_VOL_BULLISH as kill trigger]
If BTC is in the STRONG_BULL regime (as defined mathematically above)
for 10 consecutive days, OR in the HIGH_VOL_BULLISH regime for 
5 consecutive days, suspend the short strategy entirely.
Resume only after STRONG_BULL/HIGH_VOL_BULLISH regime ends for 
3 consecutive days.
Rationale: Support breakdowns in strong bull markets AND in euphoric 
high-volatility environments are predominantly false breakdowns. 
The strategy's structural edge dissolves in both regimes. 
HIGH_VOL_BULLISH uses a shorter trigger (5 days vs 10) because 
euphoric spikes are more intense and shorter-lived than sustained 
bull trends — the danger materializes faster.

KILL-S2-5: FUNDING RATE EXTREME KILL
[MODIFICACIÓN — Removed "(futures only)" — perpetuals are mandatory per Phase 1]
If the perpetual funding rate is consistently positive (longs paying) 
at above 0.05% per 8H for 5 consecutive periods, suspend new short 
entries. The market is crowded long and may squeeze violently before 
any breakdown materializes.
Rationale: Taking short entries into a funding-rate-driven squeeze 
is the most common cause of catastrophic short losses in crypto.
This kill criterion costs missed trades. That cost is acceptable.

KILL-S2-6: DATA QUALITY KILL
Same as KILL-L2-4. If data quality degrades, halt trading.
Support level detection is particularly sensitive to data quality —
a single missing or corrupted candle can invalidate a level 
that would otherwise be tradeable or produce a false level 
that should not exist.
```

---

## Summary: What Must Happen Before Any Code Is Written

**For L2:**

1. Fix all parameters listed in the research matrix before opening any backtest data.
2. Implement EMA touch detection (MVS-L2-2 touch logic) and test it on sample data for correctness before connecting to signal logic.
3. Confirm the backtesting engine has no lookahead in EMA calculation — EMA at bar N must not include bar N+1 data.
4. Run MVS backtest first. Compare against PROMISING/INCONCLUSIVE/REJECT thresholds.
5. Only if MVS is PROMISING, run ESS backtest and compare improvement on out-of-sample only.

**For S2:**

1. Fix all parameters before opening any backtest data.
2. Build and unit-test the support level detection algorithm in complete isolation before connecting it to any signal or backtest logic. This is the single most important implementation task.
3. Implement only the direct breakdown entry mode. No retest mode. No dual-entry logic.
4. Run MVS backtest first.
5. Validate separately on 2022 and 2023–2024 periods.
6. Only if MVS is PROMISING proceed to ESS.

> **[MODIFICACIÓN — Cross-strategy forward reference added]**
>
> **For the combined portfolio (Phase 3 requirement):**
>
> After both L2 and S2 MVS backtests are complete and evaluated individually, Phase 3 must produce a **Portfolio Correlation Diagnostic** that overlays both equity curves and quantifies correlated drawdowns during TRANSITION regime periods. This diagnostic is defined in Phase 1's Mandatory Diagnostic Requirements table and specified in Phase 2.5/3. It does not affect individual strategy evaluation but is required before any combined live paper trading begins.

Nothing in this document should be changed after backtesting begins. Any parameter change after seeing backtest results is a form of curve-fitting and invalidates the research process. If results are inconclusive, the correct response is more data or a different asset — not parameter tuning.
