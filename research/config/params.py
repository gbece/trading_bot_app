"""
Frozen parameters for L2 and S2 research harness.
All values defined in docs/Phase_5_Deployment.md Section 4.2.
Parameters are immutable dataclasses. Call freeze() to serialize to JSON.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, asdict


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


def freeze(
    l2: L2Params | None = None,
    s2: S2Params | None = None,
    detector_a: DetectorAParams | None = None,
    detector_b: DetectorBParams | None = None,
    backtest: BacktestParams | None = None,
) -> str:
    """
    Serialize all provided param objects to a single JSON string.
    Call before any backtest run and write the result to params.json.
    """
    payload: dict = {}
    if l2 is not None:
        payload["l2"] = asdict(l2)
    if s2 is not None:
        payload["s2"] = asdict(s2)
    if detector_a is not None:
        payload["detector_a"] = asdict(detector_a)
    if detector_b is not None:
        payload["detector_b"] = asdict(detector_b)
    if backtest is not None:
        payload["backtest"] = asdict(backtest)
    return json.dumps(payload, indent=2)


def freeze_all() -> str:
    """Serialize all param objects with their default values to JSON."""
    return freeze(
        l2=L2Params(),
        s2=S2Params(),
        detector_a=DetectorAParams(),
        detector_b=DetectorBParams(),
        backtest=BacktestParams(),
    )
