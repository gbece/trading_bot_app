"""
Accounting tests.

TEST-ACC-01: Taker fee calculation
TEST-ACC-02: Funding cost (floor of hours / 8)
TEST-ACC-03: R-multiple for long trades
TEST-ACC-04: R-multiple for short trades
TEST-ACC-05: Fee expressed in R
TEST-ACC-06: Summary stats on known trade set
TEST-ACC-07: Empty trade log returns default stats
"""

from __future__ import annotations

import math
import pytest
import pandas as pd
import numpy as np

from research.accounting.trades import (
    TradeRecord,
    compute_taker_fee,
    compute_funding_cost,
    compute_r_multiple,
    compute_r_in_fees,
    compute_total_fee,
    apply_fees_to_trade,
    build_trade_log,
    compute_summary_stats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(
    direction: str = "long",
    entry_price: float = 30000.0,
    effective_entry: float = 30030.0,  # 10 bps slippage
    stop_price: float = 29400.0,       # 600 below entry
    target_price: float = 31200.0,     # 1200 above entry (~2:1)
    exit_price: float = 31200.0,
    exit_reason: str = "target_hit",
    holding_hours: float = 8.0,
) -> TradeRecord:
    """Create a minimal TradeRecord for testing."""
    entry_time = pd.Timestamp("2023-01-01 00:00:00", tz="UTC")
    exit_time = entry_time + pd.Timedelta(hours=holding_hours)
    stop_dist = abs(effective_entry - stop_price)
    target_dist = abs(target_price - effective_entry)
    planned_R = target_dist / stop_dist if stop_dist > 0 else float("nan")
    gross_pnl = (exit_price - effective_entry) if direction == "long" else (effective_entry - exit_price)

    t = TradeRecord(
        trade_id=1,
        strategy="L2",
        mode="MVS_FULL",
        direction=direction,
        detector_variant=None,
        entry_bar=0,
        entry_time=entry_time,
        entry_price=entry_price,
        effective_entry_price=effective_entry,
        stop_price=stop_price,
        target_price=target_price,
        stop_distance=stop_dist,
        target_distance=target_dist,
        planned_R=planned_R,
        regime="STRONG_BULL",
        atr_at_entry=400.0,
        ema21_at_entry=29800.0,
        support_level=None,
        level_touch_count=None,
        level_age_bars=None,
        breakdown_volume=None,
        vol_sma20=None,
        vol_ratio=None,
        exit_bar=4,
        exit_time=exit_time,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
    )
    return t


# ---------------------------------------------------------------------------
# TEST-ACC-01: Taker fee
# ---------------------------------------------------------------------------

class TestTakerFee:
    """TEST-ACC-01"""

    def test_taker_fee_both_sides(self):
        """
        fee = (entry + exit) * size * fee_rate
        """
        fee = compute_taker_fee(
            entry_price=30000.0,
            exit_price=31200.0,
            position_size=1.0,
            fee_rate=0.0005,
        )
        expected = (30000.0 + 31200.0) * 1.0 * 0.0005
        assert abs(fee - expected) < 1e-9, f"Expected {expected}, got {fee}"

    def test_taker_fee_zero_rate(self):
        fee = compute_taker_fee(30000.0, 31200.0, 1.0, 0.0)
        assert fee == 0.0

    def test_taker_fee_positive(self):
        """Taker fee is always non-negative."""
        fee = compute_taker_fee(30000.0, 29000.0, 1.0, 0.0005)
        assert fee >= 0.0


# ---------------------------------------------------------------------------
# TEST-ACC-02: Funding cost
# ---------------------------------------------------------------------------

class TestFundingCost:
    """TEST-ACC-02"""

    def test_funding_8_hours_one_settlement(self):
        """
        Holding exactly 8H = 1 settlement.
        funding = 1 * 0.0002 * 30000 * 1.0 = 6.0
        """
        entry = pd.Timestamp("2023-01-01 00:00:00", tz="UTC")
        exit_ = pd.Timestamp("2023-01-01 08:00:00", tz="UTC")
        cost = compute_funding_cost(entry, exit_, 30000.0, 1.0, 0.0002)
        assert abs(cost - 6.0) < 1e-9, f"Expected 6.0, got {cost}"

    def test_funding_7h59m_zero_settlements(self):
        """7H 59M → floor(7.983 / 8) = 0 settlements → cost = 0."""
        entry = pd.Timestamp("2023-01-01 00:00:00", tz="UTC")
        exit_ = pd.Timestamp("2023-01-01 07:59:00", tz="UTC")
        cost = compute_funding_cost(entry, exit_, 30000.0, 1.0, 0.0002)
        assert cost == 0.0, f"Expected 0.0, got {cost}"

    def test_funding_24h_three_settlements(self):
        """24H = 3 settlements."""
        entry = pd.Timestamp("2023-01-01 00:00:00", tz="UTC")
        exit_ = pd.Timestamp("2023-01-02 00:00:00", tz="UTC")
        cost = compute_funding_cost(entry, exit_, 30000.0, 1.0, 0.0002)
        expected = 3 * 0.0002 * 30000.0 * 1.0
        assert abs(cost - expected) < 1e-9


# ---------------------------------------------------------------------------
# TEST-ACC-03: R-multiple for long trades
# ---------------------------------------------------------------------------

class TestRMultipleLong:
    """TEST-ACC-03"""

    def test_long_target_hit_is_positive_R(self):
        """
        Long: entry=30030, stop=29400, target=31200.
        stop_dist = 630. target_dist = 1170.
        Gross R at target = 1170/630 ≈ 1.857
        """
        r = compute_r_multiple(
            effective_entry=30030.0,
            exit_price=31200.0,
            stop_price=29400.0,
            direction="long",
        )
        expected = (31200.0 - 30030.0) / (30030.0 - 29400.0)
        assert abs(r - expected) < 1e-9

    def test_long_stop_hit_is_negative_R(self):
        r = compute_r_multiple(
            effective_entry=30030.0,
            exit_price=29400.0,
            stop_price=29400.0,
            direction="long",
        )
        expected = (29400.0 - 30030.0) / (30030.0 - 29400.0)
        assert abs(r - expected) < 1e-9
        assert r < 0

    def test_long_breakeven_is_zero_R(self):
        r = compute_r_multiple(
            effective_entry=30000.0,
            exit_price=30000.0,
            stop_price=29400.0,
            direction="long",
        )
        assert r == 0.0


# ---------------------------------------------------------------------------
# TEST-ACC-04: R-multiple for short trades
# ---------------------------------------------------------------------------

class TestRMultipleShort:
    """TEST-ACC-04"""

    def test_short_target_hit_is_positive_R(self):
        """
        Short: entry=30000, stop=30300 (above), target=29400 (below).
        stop_dist = 300. target_dist = 600.
        Gross R at target = (30000 - 29400) / 300 = 2.0
        """
        r = compute_r_multiple(
            effective_entry=30000.0,
            exit_price=29400.0,
            stop_price=30300.0,
            direction="short",
        )
        expected = (30000.0 - 29400.0) / (30300.0 - 30000.0)
        assert abs(r - expected) < 1e-9
        assert r > 0

    def test_short_stop_hit_is_negative_R(self):
        r = compute_r_multiple(
            effective_entry=30000.0,
            exit_price=30300.0,
            stop_price=30300.0,
            direction="short",
        )
        expected = (30000.0 - 30300.0) / (30300.0 - 30000.0)
        assert r < 0

    def test_short_zero_stop_distance_returns_zero(self):
        r = compute_r_multiple(
            effective_entry=30000.0,
            exit_price=29000.0,
            stop_price=30000.0,  # same as entry
            direction="short",
        )
        assert r == 0.0


# ---------------------------------------------------------------------------
# TEST-ACC-05: Fee in R
# ---------------------------------------------------------------------------

class TestFeeInR:
    """TEST-ACC-05"""

    def test_fee_in_r_calculation(self):
        """
        fee_in_R = total_fee / stop_distance
        stop_distance = |30030 - 29400| = 630
        total_fee = 30.0 (arbitrary)
        fee_in_R = 30.0 / 630 ≈ 0.0476
        """
        fee_in_r = compute_r_in_fees(
            effective_entry_price=30030.0,
            stop_price=29400.0,
            total_fee=30.0,
        )
        expected = 30.0 / 630.0
        assert abs(fee_in_r - expected) < 1e-9

    def test_fee_in_r_zero_distance_returns_zero(self):
        fee_in_r = compute_r_in_fees(
            effective_entry_price=30000.0,
            stop_price=30000.0,
            total_fee=10.0,
        )
        assert fee_in_r == 0.0


# ---------------------------------------------------------------------------
# TEST-ACC-06: Summary stats on known trade set
# ---------------------------------------------------------------------------

class TestSummaryStats:
    """TEST-ACC-06"""

    def _build_log_from_net_r(self, net_r_values: list) -> pd.DataFrame:
        """Build a minimal trade log with specified net_R values."""
        rows = []
        for i, nr in enumerate(net_r_values):
            rows.append({
                "trade_id": i + 1,
                "net_R": nr,
                "gross_R": nr + 0.1,
                "fee_in_R": 0.1,
            })
        return pd.DataFrame(rows)

    def test_profit_factor_all_wins(self):
        """3 winning trades of +2R each → PF should be very large (no losses)."""
        log = self._build_log_from_net_r([2.0, 2.0, 2.0])
        stats = compute_summary_stats(log)
        assert stats["n_trades"] == 3
        assert stats["n_wins"] == 3
        assert stats["n_losses"] == 0
        assert np.isnan(stats["profit_factor"]) or stats["profit_factor"] > 100

    def test_profit_factor_mixed(self):
        """
        2 wins of +2R, 1 loss of -1R.
        gross_win = 4.0, gross_loss = 1.0 → PF = 4.0
        """
        log = self._build_log_from_net_r([2.0, 2.0, -1.0])
        stats = compute_summary_stats(log)
        assert abs(stats["profit_factor"] - 4.0) < 1e-9

    def test_win_rate(self):
        log = self._build_log_from_net_r([1.0, -1.0, 1.0, -1.0])
        stats = compute_summary_stats(log)
        assert abs(stats["win_rate"] - 0.5) < 1e-9

    def test_max_consecutive_losses(self):
        log = self._build_log_from_net_r([1.0, -1.0, -1.0, -1.0, 2.0, -1.0])
        stats = compute_summary_stats(log)
        assert stats["max_consecutive_losses"] == 3

    def test_max_drawdown_r(self):
        """
        R sequence: +2, -1, -1, +3
        Cumulative: 2, 1, 0, 3
        Running max: 2, 2, 2, 3
        Drawdown: 0, 1, 2, 0
        Max drawdown = 2R
        """
        log = self._build_log_from_net_r([2.0, -1.0, -1.0, 3.0])
        stats = compute_summary_stats(log)
        assert abs(stats["max_drawdown_R"] - 2.0) < 1e-9

    def test_expectancy_r(self):
        """Mean of net_R values."""
        log = self._build_log_from_net_r([2.0, -1.0, 3.0, -1.0])
        stats = compute_summary_stats(log)
        assert abs(stats["expectancy_R"] - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# TEST-ACC-07: Empty trade log
# ---------------------------------------------------------------------------

class TestEmptyTradeLog:
    """TEST-ACC-07"""

    def test_empty_log_returns_zero_n_trades(self):
        log = build_trade_log([])
        stats = compute_summary_stats(log)
        assert stats["n_trades"] == 0

    def test_empty_log_metrics_are_nan(self):
        log = build_trade_log([])
        stats = compute_summary_stats(log)
        assert np.isnan(stats["profit_factor"])
        assert np.isnan(stats["win_rate"])
