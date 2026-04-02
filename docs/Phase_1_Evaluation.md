# Strict Evaluation Layer — Pre-Selection Analysis

## Evaluation Criteria Definitions
Before scoring, I define what each criterion means precisely. Vague scoring is useless.

### Codability / Objectivity (1–5)
Can every condition in the hypothesis be expressed as an unambiguous mathematical rule? 1 = highly subjective, requires human judgment to apply. 5 = every condition translates directly to a deterministic Python expression with no interpretation required.

### Parameter Fragility (1–5)
How sensitive is the strategy's performance to small changes in its parameters? 1 = change one number slightly and results collapse. 5 = results are stable across a reasonable range of parameter variations. This is scored inversely to fragility — 5 means robust, 1 means brittle.

### Execution Sensitivity (1–5)
How much does the result depend on precise fill timing, entry price, or latency? 1 = requires exact fill at a specific price to be profitable (e.g., intraday scalp where 0.1% slippage destroys edge). 5 = strategy is tolerant of realistic fill imprecision and slippage.

> **[MODIFICACIÓN — Criterio ampliado]** This criterion now explicitly includes three sub-dimensions:
> - **Fill imprecision:** The gap between theoretical entry (bar close) and realistic entry (close + 1–5 seconds of latency). Scored via assumed slippage of 5–15 basis points on entry.
> - **Funding rate exposure (perpetuals only):** If the strategy trades perpetual contracts, each 8-hour funding settlement during the trade's holding period is a cost. In extreme funding environments (>0.05% per 8H), a 24–48 hour hold can cost 0.15–0.45% in funding alone — comparable to or exceeding the round-trip taker fee. Strategies that operate in high-funding regimes (e.g., breakdowns during leveraged crowding, or pullbacks during euphoria) are penalized.
> - **Stop vulnerability to microstructure:** In crypto specifically, stop cascades and wick hunts are a known feature of market microstructure. Strategies with tight stops placed at obvious levels (e.g., just above/below a broken support/resistance) face disproportionate fill risk because those exact levels attract liquidity-seeking behavior from market makers and whales.
>
> A strategy that is tolerant of 15 bps slippage, has short average holding period (minimal funding exposure), and uses stops placed away from obvious cluster points scores 5. A strategy that requires exact fills, holds through multiple funding settlements in volatile conditions, and places stops at obvious structural levels scores 1–2.

### Likely Robustness Across Regimes (1–5)
How likely is the strategy to maintain positive expectancy across different market conditions — bull, bear, sideways, high volatility, low volatility? 1 = works only in one specific regime. 5 = degrades gracefully across multiple regimes.

> **[MODIFICACIÓN — Criterio ampliado]** This criterion now requires distinguishing between volatility sub-types. High volatility during a bull market (euphoria-driven spikes) and high volatility during a bear market (panic-driven crashes) produce fundamentally different market behavior. A strategy that "works in high volatility" must be evaluated separately for:
> - **HIGH_VOL_BULLISH:** VOL_ratio >= 2.0 AND price > SMA_200. Characterized by FOMO-driven spikes, aggressive dip-buying, and rapid V-shaped recoveries.
> - **HIGH_VOL_BEARISH:** VOL_ratio >= 2.0 AND price < SMA_200. Characterized by capitulation selling, cascading liquidations, and dead-cat bounces.
>
> A strategy that appears regime-robust because it "works in high volatility" but only works in one sub-type has a hidden regime dependency. This distinction must carry forward into the regime classifier in Phase 2.

### Expected Sample Size in Backtests (1–5)
Over 2 years of data on a major pair, approximately how many qualifying trades would this strategy generate? 1 = fewer than 20 trades (statistically meaningless). 3 = 50–100 trades (marginal). 5 = 150+ trades (sufficient for meaningful analysis, though not certainty).

### Risk of Narrative Bias / Pattern Over-Interpretation (1–5)
How easy is it to fool yourself into seeing this pattern in historical data where it does not genuinely exist? 1 = extremely easy to overfit or cherry-pick (the pattern is vague and visible everywhere in hindsight). 5 = the pattern has a precise, mechanistic definition that leaves little room for post-hoc interpretation.

---

## Individual Scores and Justifications

### L1 — Breakout-Retest Long (Breakout-Retest with Volume Confirmation)

| Criterion | Score | Justification |
|---|---|---|
| Codability / Objectivity | 3 | The core logic is translatable, but "significant swing high" requires a lookback window and flanking candle count that is inherently parametric. The retest definition (within 0.5% of prior high) is somewhat arbitrary. Two engineers implementing this independently would produce different signal sets. |
| Parameter Fragility | 2 | At least 6 distinct numeric thresholds: volume multiplier (1.5×), retest tolerance (0.5%), ATR multiplier for TP (2×), trailing activation (1×ATR), EMA period (50), breakeven trigger. Each one shifts the trade distribution. The interaction between them compounds fragility. |
| Execution Sensitivity | 3 | Operates on 4H closes, which is tolerant of moderate latency. However, the retest entry is time-sensitive — if price touches and immediately reverses within one candle, the signal is missed or entered at a poor price. Slippage on the confirmation entry is meaningful. **[MODIFICACIÓN]** Funding rate exposure is moderate: average holding period of 2–5 days means 6–15 funding settlements. In neutral funding environments this is negligible (~0.03%), but during high-funding periods (post-breakout euphoria) the cost accumulates and directly erodes the R-multiple. |
| Likely Robustness Across Regimes | 2 | Breakout-retest patterns break down completely in choppy markets, which constitute a large portion of crypto's historical time. The strategy has no mechanism to detect or avoid ranging conditions beyond the 50 EMA filter, which is a weak regime discriminator. **[MODIFICACIÓN]** In HIGH_VOL_BULLISH conditions, breakouts are genuine but retests rarely occur cleanly — price rockets away. In HIGH_VOL_BEARISH conditions, breakouts above resistance are traps. Neither volatility sub-type is favorable for this pattern. |
| Expected Sample Size | 3 | On BTC 4H over 2 years, qualifying setups (real swing break + volume + clean retest + confirmation) would likely number 25–60. Not statistically convincing for parameter optimization, but sufficient for directional assessment. |
| Narrative Bias Risk | 2 | "Breakout-retest" is one of the most commonly retrofitted patterns in retail trading. In hindsight, every significant move has a vaguely identifiable retest. The risk of over-counting qualifying setups in backtest construction is high. The volume filter helps but doesn't eliminate this. |
| **Composite** | **2.5 / 5** | Moderate-to-low confidence in unbiased edge. Fragile parameterization and narrative bias risk are primary concerns. |

---

### L2 — EMA Pullback Long (EMA Pullback with RSI Confirmation)

| Criterion | Score | Justification |
|---|---|---|
| Codability / Objectivity | 4 | Nearly every condition is a direct mathematical comparison: price vs EMA value, RSI value in range, volume relative to average, prior move magnitude in ATR units. The weakest link is "prior trend move was at least 2.5× ATR" — requires defining what constitutes a "move" (from which swing?). Otherwise highly codable. |
| Parameter Fragility | 3 | Fewer parameters than L1. Key sensitivities: EMA period (21 vs 20 vs 13), RSI range (30–52 vs 25–45), ATR multiplier for stop, pullback tolerance (0.3%). The RSI band in particular is untested and likely shifts win rate significantly if moved by 5 points. However, the EMA touch is a clean binary condition that anchors the strategy. |
| Execution Sensitivity | 4 | 4H close-based entries with no intracandle execution requirement. Stop is placed mechanically below EMA. Slippage of 0.1–0.2% has modest impact on a trade targeting the prior swing high (typically 3–8% away). Tolerant of realistic execution delays. **[MODIFICACIÓN]** Funding rate exposure is low-to-moderate: average holding period of 12–48 hours means 1.5–6 funding settlements. During the pullback phase where L2 entries occur, funding tends to be moderate (not extreme), reducing this cost. However, entries during euphoric uptrends (where funding spikes positive) will face higher costs than the fee model alone suggests. Estimated additional cost: 0.01–0.08% per trade depending on regime, which is 0.005–0.04R at typical stop distances. Small but non-zero over 60+ trades. |
| Likely Robustness Across Regimes | 3 | Explicitly requires a bull market (200 SMA daily filter). Within bull markets, it should perform reasonably across different sub-regimes. The weakness is that the 200 SMA filter has significant lag — the strategy may still take trades in the early stages of a bear market reversal before the SMA turns down. **[MODIFICACIÓN]** In HIGH_VOL_BULLISH conditions, the EMA is often pierced violently and recovers rapidly — the pattern may fire but the stop distance is inflated by ATR expansion, compressing the R-multiple. In HIGH_VOL_BEARISH conditions, the macro filter should block trades, but during the lag period (first 1–2 weeks of a downturn), false signals are likely. |
| Expected Sample Size | 4 | EMA touches in confirmed uptrends are more frequent than clean breakout-retests. On BTC 4H over 2 years, with a strict bull-market filter, expect 60–120 qualifying setups. This is the highest sample count among the long hypotheses and the one most amenable to statistical evaluation. |
| Narrative Bias Risk | 3 | "Buy the dip in an uptrend" is a real phenomenon but also one of the most over-narrated patterns. The RSI and volume filters reduce subjectivity. The main bias risk is in defining which EMA touch "counts" — shallow grazes vs. proper tests. This must be explicitly defined in code. **[MODIFICACIÓN]** An additional narrative bias vector not previously noted: the strategy's performance will correlate strongly with BTC's raw buy-and-hold return over the same period. If BTC appreciates 500% over the backtest window (as it did from 2020–2024), any strategy that is long during uptrends will show positive expectancy partly by construction. The diagnostic framework must include a direct comparison of strategy return vs. buy-and-hold return per period to isolate the entry signal's marginal contribution. This is scored here rather than only in the ghost edges section because it affects the fundamental question of whether narrative ("EMA pullbacks work") is separable from regime beta ("being long BTC works"). |
| **Composite** | **3.5 / 5** | Best-scoring long hypothesis. Highest codability, reasonable sample size, moderate fragility. Primary risks are the RSI band choice, lag in the macro filter, and correlation with raw underlying return. |

---

### L3 — VWAP Reclaim Long (VWAP Reclaim with Relative Volume)

| Criterion | Score | Justification |
|---|---|---|
| Codability / Objectivity | 4 | VWAP calculation is deterministic given a daily anchor. Volume comparison is straightforward. The 2× relative volume threshold is a hard cutoff. Time filter is precise. The main ambiguity is "daily VWAP" — must be anchored to the exchange's session open, which varies across data providers and must be implemented consistently. |
| Parameter Fragility | 2 | The 2× volume threshold is very sensitive. On many days, no candle hits 2× average, starving the strategy of signals. Reduce to 1.5× and you get many more signals but lower quality. The time window (13:00–21:00 UTC) also dramatically affects results. The ATR chase filter (within 1× ATR of VWAP) further constrains entries. Too many binary cutoffs stacked together produces extreme fragility. |
| Execution Sensitivity | 2 | This is the most execution-sensitive of the three long hypotheses. A 1H candle close above VWAP with 2× volume means the entry is often already 0.3–0.5% above VWAP by the time the signal fires. This is an intraday strategy where slippage and timing matter significantly. In a backtest using closes, the actual tradeable entry may not be achievable. **[MODIFICACIÓN]** Even 5–10 bps of slippage on an intraday strategy with tight targets materially erodes R. At a target of 1–2% (typical for intraday VWAP reclaim), 10 bps slippage is 5–10% of the target distance — a meaningful drag on expectancy. |
| Likely Robustness Across Regimes | 2 | Intraday VWAP strategies are notoriously regime-dependent. They work well on active trending days and fail on low-volume or news-driven days. Without a robust intraday trend classifier, the strategy takes the same setup in fundamentally different market conditions. |
| Expected Sample Size | 3 | The multiple strict filters (2× volume, time window, 4H trend filter, prior candles below VWAP) mean qualifying setups are moderate in frequency. Roughly 40–80 signals over 2 years on BTC 1H data. Sample size is adequate but not generous, and many will occur during backtestable but not actually tradeable conditions. |
| Narrative Bias Risk | 3 | VWAP reclaims are a genuine institutional concept but heavily popularized in retail discourse. The risk is over-counting "valid" reclaims in hindsight. The strict volume filter reduces this but the time filter selection is itself a form of regime cherry-picking. |
| **Composite** | **2.7 / 5** | Penalized by high execution sensitivity and parameter fragility. The intraday nature makes realistic backtesting harder to trust. Not suitable for v1. |

---

### S1 — Distribution Breakdown Short (Wyckoff-Style Distribution)

| Criterion | Score | Justification |
|---|---|---|
| Codability / Objectivity | 2 | "Distribution structure" is one of the most subjective patterns in technical analysis. Defining a lower high algorithmically is manageable, but confirming it is a distribution rather than a normal consolidation requires contextual judgment that resists clean quantification. The volume decline on rallies condition is codable but sensitive to the averaging window. |
| Parameter Fragility | 2 | Requires many conditions to align: trend duration (20 days), volume ratio on two separate swing highs (≤ 0.8×), structure break volume (≥ 1.5×), EMA direction. Each condition is individually plausible but together they create a very narrow funnel that will generate very few signals — and those few signals will be highly sensitive to the exact threshold choices. |
| Execution Sensitivity | 3 | Daily timeframe entry is tolerant of execution imprecision. However, the structure break entry point (close of breakdown candle) can be significantly extended from any reasonable stop level, making the initial R/R worse than it appears in theory. |
| Likely Robustness Across Regimes | 2 | This pattern is only relevant at market tops. In bear markets (when it would theoretically work best), similar setups at lower levels fail because the market is already in free-fall and the distribution interpretation breaks down. In bull markets, it generates constant false signals. Regime applicability is very narrow. |
| Expected Sample Size | 1 | This is the most critical failure of this hypothesis. On BTC daily data over 2 years, the number of clean distribution structures meeting all stated conditions would likely be fewer than 10–15. This is statistically meaningless. Any apparent edge in a backtest is pattern fitting to noise. |
| Narrative Bias Risk | 1 | Wyckoff distribution is one of the most over-applied and retroactively fitted patterns in crypto social media. Almost any topping structure can be labeled a Wyckoff distribution after the fact. The risk of fooling yourself in a backtest is very high. This is not a criticism of the underlying concept — it is a recognition that quantifying it objectively is extremely difficult. |
| **Composite** | **1.8 / 5** | Lowest-scoring hypothesis overall. Disqualified primarily by sample size inadequacy and narrative bias risk. The concept has theoretical merit but cannot be implemented rigorously enough for systematic trading in v1. |

---

### S2 — Support Breakdown Short (Support Breakdown with Volume)

| Criterion | Score | Justification |
|---|---|---|
| Codability / Objectivity | 3 | Support level detection is the weak point. "Touched at least 3 times without closing below" is codable but sensitive to the lookback window and what constitutes a "touch" (how close is a touch?). The breakdown itself (close below by > 0.3%) is objective. Volume comparison is straightforward. The composite codability is medium. |
| Parameter Fragility | 3 | Fewer parameters than S1. The key sensitivities are: touch tolerance, minimum touch count, breakdown confirmation threshold (0.3%), volume multiplier. The stop placement (above broken support) is relatively stable. The support level itself is the most fragile element — detected support levels shift depending on algorithm parameters. **[MODIFICACIÓN — Nota añadida sobre stop tightness]** Additional fragility concern: the stop at 0.5× ATR above the broken support level is aggressively tight for crypto markets. In BTC specifically, post-breakdown wicks that sweep 0.6–1.0× ATR above the broken level before continuing lower are extremely common (liquidity grabs targeting stop clusters above obvious levels). This stop distance is the most performance-sensitive parameter in S2 — it directly determines which trades survive and which are stopped out by microstructure noise. The stop must be evaluated across 0.5×, 0.8×, and 1.0× ATR in the Exit Structure Isolation Report before any conclusion about the strategy's edge is made. A profit factor that collapses when the stop is widened from 0.5× to 0.8× ATR is evidence that the strategy's apparent edge is an artifact of a well-fitted stop, not genuine breakdown momentum. Scored at 3 rather than 2 because the other parameters are relatively stable, but this single parameter carries outsized risk. |
| Execution Sensitivity | 3 | 4H close-based. The direct entry (on close of breakdown candle) is realistic. The retest entry (wait for pullback to broken support) is preferable but not guaranteed to occur. The dual entry logic is a source of inconsistency if not rigorously implemented — one mode will outperform the other in backtests and selection between them is a form of overfitting. **[MODIFICACIÓN — Funding rate and stop vulnerability expanded]** Two additional execution concerns for S2 specifically: **(a) Funding rate is adversarial.** Breakdowns with high volume often occur when the market is already stressed and funding rates are volatile. If trading perpetuals, short entries during panic periods may face negative funding (shorts paying longs), which adds cost. Conversely, if the breakdown occurs after a period of extreme positive funding (longs paying), a short entry benefits from receiving funding. The direction and magnitude of funding at entry time is unpredictable and adds execution variance that the fee model must capture. **(b) Stop placement at obvious structural levels.** Placing a stop 0.5× ATR above a broken support level is the single most predictable stop location in the entire strategy. Market makers and large participants know that retail short entries after support breaks place stops in this zone. Liquidity sweeps targeting this exact area are a documented feature of crypto market microstructure, particularly on BTC and ETH. This is not paranoia — it is an observable pattern in tick data. The stop is structurally vulnerable to microstructure predation. Scored at 3 (not lowered) because the 4H timeframe provides meaningful protection — most stop hunts complete within the same 4H candle and the close-based entry means the stop is not active until the next candle. But this vulnerability must be monitored in live paper trading. |
| Likely Robustness Across Regimes | 3 | Support breakdowns have genuine mechanical grounding (stop cascade + new short entry + capitulation of prior longs). This is one of the more durable patterns across asset classes, not just crypto. However, in crypto specifically, false breakdowns followed by immediate recovery are frequent enough to matter. The volume filter is the primary defense, and it works reasonably well. **[MODIFICACIÓN]** Regime sub-typing matters for S2: in HIGH_VOL_BEARISH conditions (panic selling), support breakdowns are genuine and follow-through is strong. In HIGH_VOL_BULLISH conditions (euphoric spikes), support breakdowns are almost always false — price recovers violently. The aggregate "HIGH_VOLATILITY" regime conflates these two opposite behaviors. S2's regime performance report must split HIGH_VOL into bullish and bearish sub-types, or the regime analysis will be misleading. |
| Expected Sample Size | 4 | On BTC 4H over 2 years, clear support levels (3+ touches) that eventually break with volume are relatively frequent — 50–100 qualifying setups is realistic. This is the best sample size among short hypotheses. |
| Narrative Bias Risk | 3 | Support/resistance is subject to post-hoc selection bias (you naturally "see" support at levels that later broke down). The 3-touch rule reduces this. The volume confirmation further anchors it. Not perfectly objective but better than S1 and S3. |
| **Composite** | **3.2 / 5** | Best-scoring short hypothesis. Reasonably codable, adequate sample size, mechanically grounded. Weakest links are support level detection codability and the stop placement vulnerability to microstructure predation. |

---

### S3 — Crowded Long Flush Short (Funding Rate + RSI Divergence)

| Criterion | Score | Justification |
|---|---|---|
| Codability / Objectivity | 4 | Funding rate comparison is deterministic. RSI divergence can be defined algorithmically (prior peak RSI vs current peak RSI at a higher price). Volume decline is a relative comparison. The conditions are individually clean. Divergence detection, however, requires defining "prior peak" which introduces a lookback sensitivity. |
| Parameter Fragility | 2 | The funding rate threshold (0.08%/8H) is critical and somewhat arbitrary — it was chosen to represent "extreme" but different exchanges have different historical distributions. RSI divergence pivot detection is highly sensitive to the lookback window. ATR overextension threshold (3×) affects signal frequency significantly. Changing the funding threshold from 0.08% to 0.06% or 0.10% produces dramatically different signal counts. |
| Execution Sensitivity | 3 | 4H entries on close are manageable. The main execution risk is that the flush, when it comes, often happens in a single large candle that gaps through your target. You can be correct and still get a poor fill on the TP. Conversely, the stop is placed above a recent wick high — in a squeeze scenario, price often spikes exactly to that level before flushing. **[MODIFICACIÓN]** Funding rate is paradoxically both the signal and the cost for S3. The strategy enters short when funding is extremely positive (longs paying shorts), which means the short position *receives* funding. This is a rare structural advantage — the execution cost is actually negative (a credit). However, this reverses violently if the squeeze continues: funding can flip to negative in 1–2 settlements, at which point the short pays. The net funding impact is highly path-dependent and cannot be modeled accurately with a flat fee assumption. |
| Likely Robustness Across Regimes | 2 | This is a very specific setup that occurs only during overheated market phases. It has no application in bear markets or neutral periods. The total time the market spends in conditions qualifying for this strategy is small. Moreover, funding rate behavior has changed as the market has matured — what qualified as extreme funding in 2019 is different from 2021 or 2024. |
| Expected Sample Size | 2 | With all 4 conditions required simultaneously (sustained high funding, RSI divergence at a peak, volume fade, overextension), qualifying setups over 2 years of data are likely fewer than 20–30. Too few for statistical confidence. Individual trade outcomes will dominate the backtest result, making it impossible to distinguish edge from luck. |
| Narrative Bias Risk | 2 | RSI divergence is one of the most over-cited and over-fitted patterns in all of technical analysis. The funding rate framing gives it a crypto-specific veneer that makes it feel more rigorous than it is. The risk is that you identify 15 historical setups, 9 of them worked, and conclude the strategy has a 60% win rate — when in reality you have almost no statistical power to make that claim. |
| **Composite** | **2.7 / 5** | Conceptually interesting and the funding rate element is genuinely crypto-specific. However, the combination of small sample size, RSI divergence fragility, and regime specificity makes it unsuitable for v1 production. Worth revisiting if funding rate data pipelines are built. |

---

## Master Scoring Summary Table

| ID | Strategy | Codability | Param Fragility | Exec Sensitivity | Regime Robustness | Sample Size | Narrative Bias Risk | Composite |
|---|---|---|---|---|---|---|---|---|
| L2 | EMA Pullback Long | 4 | 3 | 4 | 3 | 4 | 3 | **3.5** |
| L1 | Breakout-Retest Long | 3 | 2 | 3 | 2 | 3 | 2 | 2.5 |
| L3 | VWAP Reclaim Long | 4 | 2 | 2 | 2 | 3 | 3 | 2.7 |
| S2 | Support Breakdown Short | 3 | 3 | 3 | 3 | 4 | 3 | **3.2** |
| S3 | Funding Rate Flush Short | 4 | 2 | 3 | 2 | 2 | 2 | 2.7 |
| S1 | Distribution Breakdown Short | 2 | 2 | 3 | 2 | 1 | 1 | 1.8 |

Scoring: all criteria scored 1–5 where 5 is best. Composite is unweighted mean.

> **[MODIFICACIÓN — Nota sobre scores sin cambio numérico]** Composite scores remain unchanged from the original evaluation. The expanded criteria definitions (execution sensitivity now including funding rate and slippage; regime robustness now requiring volatility sub-typing) added qualitative depth to the justifications but did not alter the rank-ordering or the selection decision. The modifications surface risks that must be addressed in Phase 2 and Phase 3 design, not in the scoring itself. This is deliberate: changing scores retroactively to reflect concerns identified during the review would itself be a form of post-hoc adjustment.

---

## Strategy Selection Decisions

### Selected for v1 Implementation

**LONG v1: L2 — EMA Pullback Long**
**SHORT v1: S2 — Support Breakdown Short**

**Long selection rationale:**
L2 is the only long hypothesis that scores above 3.0 composite. Its strengths — codability, execution tolerance, sample size — directly address the three biggest practical risks in building a systematic strategy: ambiguous signals, unrealistic backtests, and insufficient data. Its main weakness (the RSI band) is a known, bounded risk that can be tested with a sensitivity sweep. It fits the simplest robust archetype: buy quality dips in confirmed uptrends.

**Short selection rationale:**
S2 is the only short hypothesis with adequate sample size and mechanical grounding. The support breakdown pattern, while imperfect, has a clear causal mechanism (stop cascades, capitulation) that does not rely on pattern interpretation. It scores consistently across all criteria, with no single catastrophic weakness. It is the most defensible short strategy to implement and backtest.

The L2 / S2 pairing is deliberately asymmetric. L2 is a trend-continuation strategy; S2 is a momentum breakdown strategy. They do not need to be logical mirrors of each other. Forcing symmetry would mean building a worse short strategy just to match the long's structure.

> **Instrument Type Declaration**
>
> Both L2 and S2 will trade **BTC/USDT perpetual contracts on Binance**. This is a binding decision for v1 research and production, not a default.
>
> **Rationale:**
> - S2 requires short selling, which eliminates spot markets entirely.
> - Running L2 on spot and S2 on perpetuals would create two different cost models, making cross-strategy comparison unreliable.
> - Perpetuals are the most liquid BTC instrument on Binance, with the tightest spreads and deepest order books.
> - The cost of this decision is that **funding rate is a non-zero cost for both strategies** and must be modeled in the research harness. This cost is accepted.
> - Historical OHLCV data must be sourced from the perpetual contract (BTCUSDT perp), not from spot (BTCUSDT). These produce different candles during funding settlement periods and during high-leverage liquidation events. Mixing data sources is not permitted.

> **[MODIFICACIÓN — Nueva subsección: Cross-Strategy Portfolio Considerations]**
>
> ### Cross-Strategy Portfolio Considerations
>
> L2 and S2 are evaluated independently above. However, they will share capital in production. Three cross-strategy risks must be addressed in Phase 2/3 that this evaluation layer cannot resolve:
>
> **1. Drawdown correlation during regime transitions.**
> L2 is designed to operate in WEAK_BULL and STRONG_BULL regimes. S2 is designed to operate in BEAR and HIGH_VOL_BEARISH regimes. During TRANSITION periods — when the market is shifting between bull and bear — both strategies may generate signals simultaneously, and both may lose. If L2 buys a pullback that turns into a breakdown, and S2 shorts a breakdown that turns into a false break and reverses, the portfolio absorbs losses on both sides. The probability and magnitude of correlated drawdowns during TRANSITION must be quantified by overlaying both equity curves in the research harness. If more than 30% of the combined max drawdown occurs in TRANSITION regime periods, the portfolio needs a TRANSITION kill switch that suspends both strategies. (Note: the 30% threshold is preliminary and subject to calibration from backtest data. It is a starting point for investigation, not a pre-validated cutoff.)
>
> **2. Capital allocation dependency.**
> With a single unit of capital, running both strategies simultaneously requires either splitting capital (reducing position size for each) or queuing trades (missing signals while capital is deployed). The research harness runs each strategy independently with 1 unit notional, but the combined portfolio constraint must be modeled before live paper trading. A naive 50/50 split halves each strategy's R contribution. A priority system (e.g., L2 takes precedence in STRONG_BULL, S2 takes precedence in BEAR) introduces regime-timing dependency.
>
> **3. Net directional exposure.**
> If L2 has an open long and S2 triggers a short on the same asset, the portfolio is partially hedged. If L2 and S2 trade different assets (deferred to v2), this hedge disappears. The directional exposure at any given time must be tracked and reported in the combined portfolio diagnostic.
>
> **Resolution for research harness:** In the research harness, L2 and S2 are executed **independently with separate notional capital** (1 unit each). They do not interact. This is intentional: the purpose of the harness is to evaluate each hypothesis in isolation. Combining them into a single capital pool would introduce trade-queuing and priority logic that contaminates the signal-quality assessment. The combined equity curve diagnostic overlays both independent results to detect correlated drawdowns, but does not simulate shared capital.
>
> **Resolution for pre-production:** Before live paper trading, a capital allocation and conflict resolution policy must be defined. Specifically: what happens when both strategies have open positions simultaneously, and what happens when one strategy triggers while the other already has capital deployed. This is an operational design decision for the paper trading phase, not a research harness concern. It must be resolved before any real capital is at risk, but it must not be resolved inside the research harness where it would add complexity without improving hypothesis testing.
>
> **These three cross-strategy considerations are not evaluation criteria — they do not affect the individual strategy scores. They are implementation requirements for Phase 3 that emerge from the decision to run both strategies concurrently.**

---

### Backup for Future Research

**LONG backup: L1 — Breakout-Retest Long**
Not selected for v1 because swing identification codability is a serious implementation risk and parameter fragility is high. However, if swing detection is implemented carefully and tested on out-of-sample data, this strategy has real merit. The retest pattern is mechanically grounded. Reserve for v2 after L2 is validated.

**SHORT backup: S3 — Funding Rate Flush Short**
Not selected for v1 because sample size is too small for statistical validation and funding rate data pipelines add infrastructure complexity. However, the concept is genuinely crypto-native and the funding rate element provides information unavailable in price-only systems. Worth building as a separate research module once the core infrastructure is in place and a funding rate data feed is reliable.

---

### Explicitly Rejected Hypotheses

**L3 — VWAP Reclaim Long: Rejected.**
The combination of high execution sensitivity and parameter fragility makes this hypothesis unreliable in a systematic context. The 2× volume threshold, time window, and intraday entry timing stack up into a system where backtested performance cannot be trusted to reflect live performance. VWAP reclaims may have genuine intraday edge for a discretionary trader monitoring the screen, but as an automated system on 1H closes, the fill-price assumptions are not realistic. If intraday strategies are ever pursued, this would need a tick-data backtester and a proper execution simulator, neither of which should be in scope for v1.

**S1 — Distribution Breakdown Short: Rejected.**
Sample size of fewer than 15 qualifying trades over 2 years is a hard disqualification. No amount of analytical sophistication can compensate for having almost no statistical basis for evaluating whether the edge is real. Additionally, the narrative bias risk is the highest of any hypothesis — Wyckoff distribution is an interpretive framework that is widely misapplied in crypto. Implementing it systematically without introducing significant look-back bias is extremely difficult. Rejected entirely, not deferred.

---

## Top 5 Ways Each Selected Strategy Could Appear Profitable With No Real Edge

### L2 — EMA Pullback Long: Ghost Edges to Guard Against

**1. Survivorship bias in asset selection.**
If you backtest only BTC and ETH from 2019–2024, you are testing the two assets that survived and appreciated the most. EMA pullbacks on these assets look great because the assets went up. Test on assets that declined significantly over the same period and the strategy will appear much weaker. Any backtest that uses only the "obvious" major pairs is contaminated.

**2. The 200 SMA filter retroactively selects only bull-market periods.**
The daily 200 SMA filter appears to be a sensible trend filter. In practice, it functions as a regime selector that only allows trades during the historically best-performing periods. You are essentially telling the strategy "only trade when price has been going up for a long time" and then reporting that the strategy made money during periods when price was going up. This is circular. The filter must be evaluated on whether it genuinely adds edge on the margin, not whether it co-selects favorable periods.

**3. RSI band selection is fitted to the optimization period.**
The RSI range of 30–52 was chosen based on market intuition. If you sweep RSI entry ranges from 25–80 and find that 30–52 gives the best results, you have overfitted. The correct approach is to define this range before seeing any backtested results, test it on out-of-sample data only, and report performance on both in-sample and out-of-sample periods.

**4. Stop placement below EMA creates asymmetric lookahead in parameter choice.**
The ATR multiplier for the stop (1× ATR below EMA) is a parameter that directly affects which trades are stopped out. Optimizing this multiplier after seeing the backtest result means you are selecting the stop that avoided the historical losses — this is direct overfitting. The stop multiplier must be fixed before backtesting begins and not adjusted based on results.

**5. Declining volume on pullback could be an artifact of time-of-day effects.**
Volume naturally declines during Asian session hours in crypto. A pullback that occurs during Asian hours will almost always show declining volume relative to a 20-period average that includes NY session candles. This means the "declining volume pullback" filter may be selecting for time-of-day rather than genuine supply exhaustion. The strategy could appear to work because it systematically avoids high-volume reversal sessions (NY open), not because the signal itself has edge.

> **[MODIFICACIÓN — Ghost Edge #6 añadido]**
>
> **6. Strategy performance correlation with buy-and-hold return.**
> Over 2020–2024, BTC appreciated roughly 10× from ~$7,000 to ~$70,000+. Any strategy that is systematically long during uptrend periods will capture a portion of this appreciation through regime beta alone, not through entry signal alpha. The critical diagnostic question is: does L2's entry signal (EMA touch + confirmation) produce better results than simply being long at any random point during the same bull-market windows?
>
> The Component Attribution framework (MODE_MACRO_ONLY vs MODE_MVS_FULL) partially addresses this. But an additional diagnostic is needed: **for each 6-month period in the backtest, compute the correlation between L2's period profit factor and BTC's raw buy-and-hold return for that period.** If this correlation exceeds 0.80, the strategy's performance is statistically inseparable from "buy BTC during bull markets." This is not an edge — it is leveraged beta exposure with a complex entry mechanism. The entry signal must demonstrate marginal improvement over buy-and-hold in the same regime windows.
>
> This ghost edge is more dangerous than the others because it cannot be eliminated by fixing parameters or preventing overfitting. It is structural to any trend-following long strategy on an asset that appreciated enormously during the backtest period. The only mitigation is honest attribution analysis and testing on flat or declining periods.

---

### S2 — Support Breakdown Short: Ghost Edges to Guard Against

**1. Support levels are identified with hindsight.**
When coding support detection, it is easy to look at the full candle history and identify levels that were clearly important. In live trading, you identify the level before knowing whether price will break it. Any backtest that uses a support detection algorithm that "sees" the level more clearly in hindsight than it would have been visible at trade time is contaminated. This must be tested by only using data available strictly before each potential entry.

**2. Dual entry logic (direct vs retest) allows cherry-picking.**
If both direct breakdown entry and retest entry are implemented, the backtest will naturally gravitate toward whichever mode performed better historically. If the code allows either entry per setup, you have introduced a hidden optimization: you are effectively choosing the better of two entries per trade in hindsight. This must be eliminated: choose one entry mode and apply it consistently throughout the backtest.

**3. Volume threshold tuning against breakdown success rate.**
The 1.5× volume threshold was chosen to filter out "thin" breakdowns. If you test this threshold against historical results and find that 1.5× gives a 55% win rate while 1.3× gives 45%, you will use 1.5×. But this difference may be noise across 60 trades. Setting the threshold based on historical win rate optimization is overfitting. Fix it before backtesting.

**4. Sample contamination from 2022 BTC bear market.**
If the backtest period includes 2022 (which it should), a large proportion of profitable short signals will come from that extended bear trend. S2 will look excellent in that period by construction — every support level eventually broke in 2022. The strategy's performance in neutral or bull conditions will look much weaker. The composite result will be inflated by the bear-market cluster. Walk-forward testing that includes multiple regime periods is essential to expose this.

**5. Stop placement above "broken support" is vulnerable to post-hoc stop selection.**
The stop is placed "above the broken support level." The exact placement (0.3× ATR above? 0.5× ATR?) is a parameter that directly affects which trades survive and which get stopped out. If you adjust this after seeing backtest results, you are building a stop that avoids historical stop hunts — which is the definition of overfitting. More dangerously, crypto markets frequently spike back above broken support levels before continuing lower, so the stop distance is not arbitrary — it is the most performance-sensitive parameter in the entire strategy and must be fixed conservatively before any backtest is run.

> **[MODIFICACIÓN — Ghost Edge #6 añadido]**
>
> **6. The tight stop creates an illusion of favorable R distribution.**
> With a stop of 0.5× ATR above the broken level and a target of 2× ATR below entry, the theoretical R:R ratio appears attractive (~2.5:1 to 4:1 depending on the gap between entry and level). However, the tight stop means a large percentage of trades will be stopped out by normal post-breakdown retracement noise, producing a low win rate (potentially 35–42%). The strategy's profitability then depends on the few trades that reach the target more than compensating for the many small losses.
>
> The danger: a tight stop with a wide target is mathematically identical in expectancy to a wider stop with a proportionally wider target *if the underlying signal has no edge.* The tight stop just produces more frequent small losses and less frequent large wins — the distribution looks different but the expected value is the same. To distinguish between "genuine edge amplified by favorable R:R" and "no edge masked by favorable R:R distribution," the Exit Structure Isolation Report must compare stop/target configurations that produce similar R:R ratios but different absolute distances (e.g., 0.5× stop / 2× target vs. 1.0× stop / 4× target). If the absolute distance matters more than the ratio, the stop tightness itself is the source of apparent edge (through selection of which breakdowns happen to not retrace), not the breakdown signal.
>
> **Phase 2.5 forward reference:** The current Exit Structure Isolation Report in Phase 2.5 defines exit variants A(1.5/2.0), B(1.0/1.5), C(2.0/3.0) — but none of these hold the R:R ratio constant while varying absolute distance. When Phase 2.5 is modified, a new S2-specific exit variant must be added: **Variant F (constant-R:R):** stop 1.0× ATR / target 4.0× ATR (same ~4:1 R:R as the primary 0.5×/2.0× but at double the absolute distance). This variant directly tests whether the edge is in the signal or in the stop calibration.

---

## Parameters That Must Be Fixed Early to Prevent Overfitting

### L2 — EMA Pullback Long

| Parameter | Value to Fix | Reason |
|---|---|---|
| Trend filter EMA period | 21 (4H) | Core signal anchor. Changing this shifts every entry in the backtest. Fix before testing. |
| Macro filter | 200 SMA daily | Non-negotiable baseline. Do not test alternatives (150 SMA, 100 SMA) until out-of-sample. |
| RSI range lower bound | 30 | Most sensitive to win rate. Fix before seeing results; sweep only in out-of-sample research. Value aligned with Phase 2 ESS-L2-5 specification (30-52). |
| RSI range upper bound | 52 | Same as above. Must move together with lower bound; do not optimize independently. Value aligned with Phase 2 ESS-L2-5 specification (30-52). |
| Pullback tolerance to EMA | 0.3% | Defines what "touches the EMA" means. Has large impact on signal count. Fix it. |
| ATR period | 14 | Standard; do not tune. |
| Stop ATR multiplier | 1.5× ATR below EMA | Most performance-sensitive parameter. Fix conservatively before backtesting. Value aligned with Phase 2 MVS-L2-4 specification. |
| TP target | MVS: 2× ATR(14) above entry (fixed ratio). ESS: prior swing high (structural). | MVS uses a fixed mechanical target per Phase 2 MVS-L2-4. The ESS may use the prior swing high as a structural target, but this is only tested after MVS validation. The swing high identification algorithm must be fixed before ESS testing. |
| Volume decline threshold | 20% below 20-period avg | Fix before testing. Testing multiple thresholds against results is direct overfitting. |
| **[MODIFICACIÓN]** Slippage assumption | 10 bps (0.10%) | Applied to entry price in the direction adverse to the trade (higher for longs, lower for shorts). Fixed before backtesting. Must be tested at 0, 5, 10, and 15 bps in the parameter sensitivity report to quantify execution sensitivity. Not a tunable parameter — it is a cost model assumption. |
| **[MODIFICACIÓN]** Funding rate estimate | 0.02% per 8H settlement | Flat-rate estimate for perpetual contracts, calibrated to approximate historical mean during bull-market conditions (when L2 is most active). Applied per funding settlement crossed during trade holding period. Sensitivity sweep must include 0.01%, 0.02%, and 0.05% per 8H. If spot markets were used, this parameter would be zero — but the Instrument Type Declaration above mandates perpetuals. |

### S2 — Support Breakdown Short

| Parameter | Value to Fix | Reason |
|---|---|---|
| Minimum support touches | 3 | Lower this and you find many more "levels" that are noise. Fix at 3. |
| Touch tolerance | 0.5% of price | Defines what a "touch" means. Has large impact on how many levels are identified. Fix it. |
| Breakdown confirmation threshold | 0.3% close below level | Differentiates close from wick. Sensitive to false positive rate. Fix before testing. |
| Volume multiplier on breakdown | 1.5× 20-period avg | Most important filter. Fix before testing, do not sweep against win rate. |
| Support lookback window | 60 candles (4H) | Determines how far back to look for touches. Critical but rarely discussed. Fix it. |
| Stop placement | 0.5× ATR above broken level | Most performance-sensitive parameter. Fix conservatively. **[MODIFICACIÓN]** This is the single highest-risk frozen parameter in the entire project. The Exit Structure Isolation Report must compare 0.5×, 0.8×, and 1.0× ATR as structural variants (not optimization). If the profit factor range across these three values exceeds 0.60 PF units, flag as STOP-FRAGILE and consider widening to the most conservative (1.0×) as the primary MVS stop. |
| Entry mode | Direct close entry only | Eliminates dual-entry overfitting risk entirely. One mode, applied consistently. |
| Time exit | 24H (6 candles) if no progress | Fix before testing. Not a free parameter. |
| **[MODIFICACIÓN]** Slippage assumption | 10 bps (0.10%) | Same as L2. Applied adversely to entry price. |
| **[MODIFICACIÓN]** Funding rate estimate | 0.02% per 8H settlement | Same flat-rate as L2. Note: S2 trades during breakdown conditions may face higher-than-average funding volatility. Sensitivity sweep at 0.01%, 0.02%, 0.05%. |

---

## Code Sections Requiring Maximum Objectivity

### L2 — EMA Pullback Long

**1. EMA touch detection.**
Must be coded as: `abs(candle_low - ema_value) / ema_value <= 0.003` or `candle_low <= ema_value * 1.003`. This cannot be implemented as a visual "near the EMA" judgment. Every touch decision must be a binary comparison against a fixed numeric tolerance. Do not allow the tolerance to vary.

**2. Prior trend move magnitude.**
"The prior move was at least 2.5× ATR" (per Phase 2 ESS-L2-7) requires defining what constitutes the start and end of the prior move. This must be coded as: identify the most recent swing low before the current position (using a fixed lookback), measure the distance from that swing low to the most recent swing high, compare to ATR. Do not allow human judgment into this measurement.

**3. RSI condition at touch.**
Must be evaluated at the exact 4H candle close that constitutes the EMA touch — not on the following candle, not on the candle before. Lookahead contamination in RSI evaluation is extremely common in naive backtesting implementations. The RSI value used for the entry decision must be computed from data strictly available before the entry candle closes.

**4. Confirmation candle definition.**
**[FIX — Aligned with Phase 2.5 design resolution]** The MVS primary implementation uses **same-bar confirmation**: the EMA touch (low <= EMA21 × 1.003) and the bullish close (close > open) are evaluated on the **same** 4H candle. Entry fires at the close of that candle. This means a single candle must both touch the EMA and close bullish. This is the stricter interpretation — it requires the dip and recovery to co-occur within 4 hours. Phase 2.5 defines a separate structural variant (L2_VARIANT_NEXTBAR) that tests next-bar confirmation as a comparison, not as the primary spec. The same-bar approach was chosen because it requires fewer parameters (no pending-touch state, no wait-period), produces more trades (more testable), and is a subset of next-bar signals (if same-bar has no edge, next-bar also has no edge).

> **[MODIFICACIÓN — Sección #5 añadida]**
>
> **5. Slippage and fee application point.**
> Entry price in the backtest is `close_price`. Effective entry price for P&L calculation must be `close_price * (1 + slippage_bps / 10000)` for longs. This adjustment is applied once at entry, stored in the trade record as `effective_entry_price`, and used for all subsequent P&L and R-multiple calculations. The `entry_price` field retains the raw close price for signal analysis; `effective_entry_price` is used for accounting. Funding rate cost is computed at exit based on `floor(holding_duration_hours / 8) * funding_rate_per_settlement * notional_value` and added to `total_fee`. The default `funding_rate_per_settlement` is 0.0002 (0.02% per 8H), sourced from params. These two adjustments (slippage and funding) must be applied consistently to every trade, including all baseline trades, to maintain comparability.

### S2 — Support Breakdown Short

**1. Support level detection algorithm.**
This is the highest-risk section of the entire codebase for lookahead bias. Must be coded with a strict point-in-time approach: at each candle, the support detection algorithm may only use data from candles that closed before the current candle. No peeking at future candle lows to "confirm" that a level was genuinely important. The lookback window (60 candles) must be applied consistently.

**2. Touch counting logic.**
A "touch" of a support level must be defined as: the candle low came within the touch tolerance of the level AND the candle closed above the level. Must not count the same level touch twice if two consecutive candles both graze the level. A debounce period (minimum 3 candles between touches) prevents double-counting.

**3. Breakdown entry candle.**
Entry is on the close of the candle that breaks down through the level. This candle's data is fully formed before the entry executes. There is no issue with lookahead here as long as entry is placed at the close price of that candle. However, the volume check on this candle must also be computed from data available at close — the 20-period volume average must not include the current candle in its calculation.

**4. Stop level assignment.**
The stop price must be computed at the moment of entry and stored. It must not be recalculated on subsequent candles using updated ATR values. Once set, the stop is fixed unless a mechanical trailing stop rule is applied. Stop recalculation after entry is a subtle form of curve-fitting.

> **[MODIFICACIÓN — Sección #5 añadida]**
>
> **5. Slippage and fee application for shorts.**
> Effective entry price for short trades: `close_price * (1 - slippage_bps / 10000)`. Note the direction: slippage is adverse, meaning a short entry fills *lower* than the close (you get a worse price for a short because price is falling and you're chasing). Funding rate cost for shorts follows the same formula as L2 but with a sign consideration: if trading perpetuals, the funding payment direction depends on whether the funding rate is positive (longs pay shorts — a credit for the short position) or negative (shorts pay longs — a cost). For the MVS research harness using a flat-rate estimate, apply the funding as a cost regardless of direction. This is conservative. A more accurate model using historical funding rates is deferred to ESS or v2.

---

> **[MODIFICACIÓN — Nueva sección final]**
>
> ## Evaluation Layer Addendum: Mandatory Diagnostic Requirements Derived from This Evaluation
>
> The evaluation process surfaced several risks that cannot be resolved by scoring alone. They require specific diagnostic outputs in the research harness. These are not optional enhancements — they are mandatory outputs without which the backtest results cannot be properly interpreted.
>
> | Diagnostic | Applies To | Purpose | Defined In |
> |---|---|---|---|
> | Buy-and-hold correlation per period | L2 | Determine whether L2's performance is separable from BTC's raw return | Phase 3, Period Isolation Report |
> | Slippage sensitivity sweep (0, 5, 10, 15 bps) | L2, S2 | Determine whether realistic execution costs destroy the edge | Phase 3, Parameter Sensitivity Report |
> | Funding rate cost estimation per trade | L2, S2 (perpetuals only) | Quantify hidden holding cost beyond taker fees | Phase 3, Trade Accounting Module |
> | Stop distance structural variants for S2 (0.5×, 0.8×, 1.0× ATR) | S2 | Determine whether the tight stop is the source of apparent edge | Phase 3, Exit Structure Isolation Report |
> | Constant-R:R exit variant for S2 (0.5×/2.0× vs 1.0×/4.0×) | S2 | Determine whether edge is in signal or in stop calibration | Phase 2.5, Exit Structure Isolation spec (new variant F) |
> | HIGH_VOL sub-regime split (bullish vs bearish) | L2, S2 | Prevent misleading regime performance aggregation | Phase 2, Regime Classifier; Phase 3, Regime Report |
> | Cross-strategy drawdown correlation | L2 + S2 combined | Identify correlated loss periods in the combined portfolio | Phase 3, New diagnostic: Portfolio Correlation Report |
> | MAE / MFE per trade | L2, S2 | Diagnose whether stops are too tight and targets too ambitious | Phase 3, Trade Record Schema |
>
> This evaluation layer is now complete. The selection is clear: L2 long, S2 short, with L1 and S3 as future research candidates, and S1 explicitly rejected. Ready to proceed to Phase 2 (formal strategy selection and specification) on your command.
