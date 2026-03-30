# =============================================================================
# tests/test_module4.py — Unit Tests for Module 4 (Risk Manager)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 4 components:
#     - risk/trailing_stop.py:  Trailing stop strategies (ATR, %, breakeven)
#     - risk/risk_manager.py:   Master risk orchestrator (evaluate, register,
#                                update, close, drawdown, sector concentration)
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module4.py -v
#
# =============================================================================

import os
import sys

import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Test Suite: risk/trailing_stop.py — TrailingStopManager
# =============================================================================

class TestTrailingStopInit:
    """Verify TrailingStopManager initialization and configuration."""

    def test_valid_method_atr(self):
        """ATR method should initialize without error."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        assert tsm.method == "atr"
        assert tsm.positions == {}

    def test_valid_method_percentage(self):
        """Percentage method should initialize without error."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="percentage")
        assert tsm.method == "percentage"

    def test_valid_method_breakeven(self):
        """Breakeven-then-trail method should initialize without error."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="breakeven_then_trail")
        assert tsm.method == "breakeven_then_trail"

    def test_invalid_method_raises(self):
        """Invalid method should raise ValueError."""
        from risk.trailing_stop import TrailingStopManager
        with pytest.raises(ValueError, match="Invalid trailing stop method"):
            TrailingStopManager(method="invalid_method")


class TestTrailingStopRegistration:
    """Verify position registration and state tracking."""

    def test_register_position(self):
        """register_position should store position state with correct fields."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        state = tsm.register_position("AAPL", entry_price=150.0,
                                       initial_stop=144.0, atr_value=3.0)

        assert state["symbol"] == "AAPL"
        assert state["entry_price"] == 150.0
        assert state["initial_stop"] == 144.0
        assert state["current_stop"] == 144.0
        assert state["highest_price"] == 150.0
        assert state["risk_per_share"] == 6.0
        assert state["atr_value"] == 3.0
        assert state["breakeven_hit"] is False
        assert state["stop_updates"] == 0

    def test_register_multiple_positions(self):
        """Should track multiple positions independently."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", 150.0, 144.0, 3.0)
        tsm.register_position("XOM", 80.0, 76.0, 2.0)

        assert len(tsm.positions) == 2
        assert tsm.get_stop("AAPL") == 144.0
        assert tsm.get_stop("XOM") == 76.0

    def test_get_stop_unregistered(self):
        """get_stop should return None for unregistered symbols."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        assert tsm.get_stop("FAKE") is None


class TestATRTrailingStop:
    """Verify ATR-based trailing stop calculations."""

    def test_atr_trail_moves_up_with_price(self):
        """Stop should ratchet up as price increases."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=3.0)

        # Price moves up: new_stop = 160 - (3.0 * 1.5) = 155.5
        new_stop = tsm.update("AAPL", current_price=160.0)
        assert new_stop == 155.5

    def test_atr_trail_never_moves_down(self):
        """Stop should NOT move down when price drops (ratchet rule)."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=3.0)

        # Price rises, stop moves up
        tsm.update("AAPL", current_price=160.0)  # stop = 155.5

        # Price drops — stop should stay at 155.5
        new_stop = tsm.update("AAPL", current_price=156.0)
        assert new_stop == 155.5

    def test_atr_trail_with_updated_atr(self):
        """Providing a new ATR should affect the trail distance."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=3.0)

        # Price rises to 165, but ATR widens to 5.0
        # new_stop = 165 - (5.0 * 1.5) = 157.5
        new_stop = tsm.update("AAPL", current_price=165.0, current_atr=5.0)
        assert new_stop == 157.5

    def test_atr_trail_zero_atr_stays_put(self):
        """If ATR is 0, stop should not change."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=0.0)

        new_stop = tsm.update("AAPL", current_price=160.0)
        assert new_stop == 144.0  # No change (ATR=0)

    def test_update_unregistered_returns_none(self):
        """Updating an unregistered symbol should return None."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        assert tsm.update("FAKE", 100.0) is None


class TestPercentageTrailingStop:
    """Verify percentage-based trailing stop calculations."""

    def test_percentage_trail_basic(self):
        """Stop should trail at highest_price * (1 - 0.03)."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="percentage")
        tsm.register_position("AAPL", entry_price=100.0,
                               initial_stop=94.0, atr_value=3.0)

        # Price rises to 110: stop = 110 * (1 - 0.03) = 106.70
        new_stop = tsm.update("AAPL", current_price=110.0)
        assert new_stop == 106.70

    def test_percentage_trail_ratchet(self):
        """Stop should not drop when price falls."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="percentage")
        tsm.register_position("AAPL", entry_price=100.0,
                               initial_stop=94.0, atr_value=3.0)

        tsm.update("AAPL", current_price=110.0)  # stop = 106.70
        new_stop = tsm.update("AAPL", current_price=105.0)  # drop
        assert new_stop == 106.70  # Ratchet holds


class TestBreakevenTrailingStop:
    """Verify the breakeven-then-trail two-phase strategy."""

    def test_phase1_no_trail_before_breakeven(self):
        """Before reaching 1R profit, stop should stay at original level."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="breakeven_then_trail")
        tsm.register_position("AAPL", entry_price=100.0,
                               initial_stop=94.0, atr_value=3.0)
        # risk_per_share = 6.0, breakeven target = 100 + 6 = 106

        # Price at 104 (less than 1R) — stop should stay at 94
        new_stop = tsm.update("AAPL", current_price=104.0)
        assert new_stop == 94.0

    def test_phase2_breakeven_triggered(self):
        """At 1R profit, stop should jump to entry + buffer."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="breakeven_then_trail")
        tsm.register_position("AAPL", entry_price=100.0,
                               initial_stop=94.0, atr_value=3.0)

        # Price hits 106 (1R profit) — stop moves to breakeven
        new_stop = tsm.update("AAPL", current_price=106.0)
        # Breakeven = 100 * (1 + 0.001) = 100.10
        assert new_stop == 100.10

    def test_phase2_then_atr_trail(self):
        """After breakeven, should switch to ATR trailing."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="breakeven_then_trail")
        tsm.register_position("AAPL", entry_price=100.0,
                               initial_stop=94.0, atr_value=3.0)

        # Trigger breakeven
        tsm.update("AAPL", current_price=106.0)  # stop -> 100.10

        # Now price rises to 115 — ATR trail kicks in
        # highest = 115, trail = 115 - (3.0 * 1.5) = 110.50
        new_stop = tsm.update("AAPL", current_price=115.0)
        assert new_stop == 110.50


class TestStopHitCheck:
    """Verify stop hit detection."""

    def test_stop_hit_at_stop_level(self):
        """Price exactly at stop should trigger hit."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=3.0)

        assert tsm.check_stop_hit("AAPL", 144.0) is True

    def test_stop_hit_below_stop(self):
        """Price below stop should trigger hit."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=3.0)

        assert tsm.check_stop_hit("AAPL", 140.0) is True

    def test_stop_not_hit_above(self):
        """Price above stop should NOT trigger hit."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", entry_price=150.0,
                               initial_stop=144.0, atr_value=3.0)

        assert tsm.check_stop_hit("AAPL", 145.0) is False

    def test_stop_hit_unregistered(self):
        """Unregistered symbol should return False."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        assert tsm.check_stop_hit("FAKE", 100.0) is False


class TestTrailingStopHelpers:
    """Verify helper methods (remove, get_all, get_state)."""

    def test_remove_position(self):
        """remove_position should clean up state."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", 150.0, 144.0, 3.0)

        removed = tsm.remove_position("AAPL")
        assert removed is not None
        assert removed["symbol"] == "AAPL"
        assert "AAPL" not in tsm.positions

    def test_remove_nonexistent(self):
        """Removing a non-existent position should return None."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        assert tsm.remove_position("FAKE") is None

    def test_get_all_stops(self):
        """get_all_stops should return dict of symbol -> stop."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", 150.0, 144.0, 3.0)
        tsm.register_position("XOM", 80.0, 76.0, 2.0)

        stops = tsm.get_all_stops()
        assert stops == {"AAPL": 144.0, "XOM": 76.0}

    def test_get_position_state(self):
        """get_position_state should return a copy of the state dict."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        tsm.register_position("AAPL", 150.0, 144.0, 3.0)

        state = tsm.get_position_state("AAPL")
        assert state is not None
        assert state["symbol"] == "AAPL"
        # Ensure it's a copy (modifying returned dict doesn't affect internal)
        state["symbol"] = "MODIFIED"
        assert tsm.positions["AAPL"]["symbol"] == "AAPL"

    def test_get_position_state_nonexistent(self):
        """get_position_state for non-existent should return None."""
        from risk.trailing_stop import TrailingStopManager
        tsm = TrailingStopManager(method="atr")
        assert tsm.get_position_state("FAKE") is None


# =============================================================================
# Test Suite: risk/risk_manager.py — RiskManager
# =============================================================================

class TestRiskManagerInit:
    """Verify RiskManager initialization."""

    def test_basic_init(self):
        """RiskManager should initialize with all sub-managers."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        assert rm.account_balance == 10000
        assert rm.peak_balance == 10000
        assert rm.drawdown_halted is False
        assert rm.trade_log == []
        assert rm.sector_map == {}

    def test_init_with_custom_trailing(self):
        """Custom trailing method should be passed to sub-manager."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000, trailing_method="percentage")
        assert rm.trailing_stops.method == "percentage"


class TestEvaluateTrade:
    """Verify pre-trade risk evaluation (the gate)."""

    def test_approve_valid_trade(self):
        """A valid trade should be approved with all checks passed."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        decision = rm.evaluate_trade(
            symbol="AAPL", entry_price=150.0, stop_loss=144.0,
            atr_value=3.0, scanner_score=8.0, signal_strength="STRONG",
            sector="Technology",
        )

        assert decision["approved"] is True
        assert decision["shares_to_buy"] > 0
        assert decision["position_value"] > 0
        assert decision["risk_amount"] > 0
        assert len(decision["reasons"]) == 0
        assert "account_balance_floor" in decision["checks_passed"]
        assert "max_drawdown" in decision["checks_passed"]
        assert "position_sizing" in decision["checks_passed"]

    def test_reject_low_balance(self):
        """Trade should be rejected if account balance is below floor."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=100)  # Below $500 floor

        decision = rm.evaluate_trade("AAPL", 150.0, 144.0)
        assert decision["approved"] is False
        assert any("below minimum" in r for r in decision["reasons"])

    def test_reject_drawdown_halted(self):
        """Trade should be rejected if max drawdown has been breached."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.drawdown_halted = True

        decision = rm.evaluate_trade("AAPL", 150.0, 144.0)
        assert decision["approved"] is False
        assert any("drawdown" in r.lower() for r in decision["reasons"])

    def test_reject_daily_loss_halted(self):
        """Trade should be rejected if daily loss limit is breached."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.portfolio.update_daily_pnl(-600)  # 6% loss > 5% limit

        decision = rm.evaluate_trade("AAPL", 150.0, 144.0)
        assert decision["approved"] is False
        assert any("daily loss" in r.lower() or "halted" in r.lower()
                    for r in decision["reasons"])

    def test_reject_max_positions(self):
        """Trade should be rejected when max positions are already open."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        # Fill up positions
        rm.portfolio.add_position("A", 10, 100.0)
        rm.portfolio.add_position("B", 10, 100.0)
        rm.portfolio.add_position("C", 10, 100.0)

        decision = rm.evaluate_trade("AAPL", 150.0, 144.0)
        assert decision["approved"] is False
        assert any("max positions" in r.lower() for r in decision["reasons"])

    def test_reject_sector_concentration(self):
        """Trade should be rejected when sector concentration limit is hit."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=50000)

        # Add 2 Tech positions (max per sector = 2)
        rm.register_fill("AAPL", 10, 150.0, 144.0, sector="Technology")
        rm.register_fill("MSFT", 10, 300.0, 288.0, sector="Technology")

        decision = rm.evaluate_trade(
            "GOOGL", 140.0, 134.0, sector="Technology"
        )
        assert decision["approved"] is False
        assert any("sector concentration" in r.lower()
                    for r in decision["reasons"])

    def test_approve_different_sector(self):
        """Trade in a different sector should pass concentration check."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=50000)

        rm.register_fill("AAPL", 10, 150.0, 144.0, sector="Technology")
        rm.register_fill("MSFT", 10, 300.0, 288.0, sector="Technology")

        decision = rm.evaluate_trade(
            "XOM", 80.0, 76.0, sector="Energy"
        )
        assert decision["approved"] is True

    def test_reject_invalid_stop(self):
        """Trade with stop >= entry should be rejected."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        decision = rm.evaluate_trade("AAPL", 150.0, 155.0)
        assert decision["approved"] is False
        assert any("must be above" in r.lower() or "invalid" in r.lower()
                    for r in decision["reasons"])

    def test_decision_logged(self):
        """Every evaluate_trade call should be logged in trade_log."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        rm.evaluate_trade("AAPL", 150.0, 144.0)
        rm.evaluate_trade("XOM", 80.0, 76.0)

        assert len(rm.trade_log) == 2
        assert rm.trade_log[0]["symbol"] == "AAPL"
        assert rm.trade_log[1]["symbol"] == "XOM"


class TestRegisterFill:
    """Verify trade registration in all sub-managers."""

    def test_register_fill_success(self):
        """register_fill should add to portfolio and trailing stops."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        result = rm.register_fill(
            "AAPL", shares=33, entry_price=150.0, stop_loss=144.0,
            take_profit_1=162.0, take_profit_2=168.0,
            atr_value=3.0, sector="Technology",
        )

        assert result is True
        assert "AAPL" in rm.portfolio.open_positions
        assert rm.trailing_stops.get_stop("AAPL") == 144.0
        assert rm.sector_map["AAPL"] == "Technology"

    def test_register_fill_blocked(self):
        """register_fill should return False if portfolio rules block it."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        # Fill up positions
        rm.register_fill("A", 10, 100.0, 94.0)
        rm.register_fill("B", 10, 100.0, 94.0)
        rm.register_fill("C", 10, 100.0, 94.0)

        # 4th should fail
        result = rm.register_fill("D", 10, 100.0, 94.0)
        assert result is False


class TestUpdatePrice:
    """Verify price update and trailing stop integration."""

    def test_update_price_updates_pnl_and_stop(self):
        """update_price should update both trailing stop and unrealized P&L."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, atr_value=3.0)

        result = rm.update_price("AAPL", current_price=160.0)

        assert result is not None
        assert result["current_price"] == 160.0
        assert result["unrealized_pnl"] == 100.0  # (160 - 150) * 10
        assert result["trailing_stop"] == 155.5    # 160 - (3 * 1.5)
        assert result["stop_hit"] is False

    def test_update_price_detects_stop_hit(self):
        """update_price should flag when trailing stop is hit."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, atr_value=3.0)

        result = rm.update_price("AAPL", current_price=143.0)
        assert result["stop_hit"] is True

    def test_update_price_unknown_symbol(self):
        """Updating an unknown symbol should return None."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        assert rm.update_price("FAKE", 100.0) is None


class TestClosePosition:
    """Verify position closing and P&L tracking."""

    def test_close_winning_trade(self):
        """Closing a winning trade should increase account balance."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, atr_value=3.0,
                          sector="Technology")

        result = rm.close_position("AAPL", exit_price=160.0,
                                    reason="take_profit")

        assert result is not None
        assert result["realized_pnl"] == 100.0  # (160-150) * 10
        assert result["reason"] == "take_profit"
        assert rm.account_balance == 10100.0
        assert "AAPL" not in rm.portfolio.open_positions
        assert "AAPL" not in rm.sector_map

    def test_close_losing_trade(self):
        """Closing a losing trade should decrease account balance."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, atr_value=3.0)

        result = rm.close_position("AAPL", exit_price=144.0,
                                    reason="trailing_stop")

        assert result["realized_pnl"] == -60.0  # (144-150) * 10
        assert rm.account_balance == 9940.0

    def test_close_updates_peak_balance(self):
        """Winning trades should update peak balance for drawdown tracking."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, atr_value=3.0)

        rm.close_position("AAPL", exit_price=170.0)
        assert rm.peak_balance == 10200.0  # (170-150) * 10 = +200

    def test_close_nonexistent_returns_none(self):
        """Closing a non-existent position should return None."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        assert rm.close_position("FAKE", 100.0) is None


class TestDrawdownMonitoring:
    """Verify drawdown tracking and halt behavior."""

    def test_no_drawdown_initially(self):
        """Initial drawdown should be 0%."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        assert rm.get_current_drawdown() == 0.0

    def test_drawdown_after_loss(self):
        """Drawdown should increase after losing trades."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 100, 100.0, 90.0, atr_value=5.0)

        # Close at a loss: -$500 = 5% drawdown
        rm.close_position("AAPL", exit_price=95.0)
        dd = rm.get_current_drawdown()
        assert dd == 0.05

    def test_drawdown_halt_triggered(self):
        """15% drawdown should halt trading."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 100, 100.0, 80.0, atr_value=10.0)

        # Close at -$1600 loss = 16% drawdown
        rm.close_position("AAPL", exit_price=84.0)
        assert rm.drawdown_halted is True

        # New trade should be rejected
        decision = rm.evaluate_trade("XOM", 80.0, 76.0)
        assert decision["approved"] is False

    def test_drawdown_reset(self):
        """Manual drawdown reset should re-enable trading."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.drawdown_halted = True
        rm.account_balance = 8500

        rm.reset_drawdown_halt()
        assert rm.drawdown_halted is False
        assert rm.peak_balance == 8500  # Reset to current


class TestDayReset:
    """Verify daily state reset."""

    def test_reset_daily_clears_pnl(self):
        """reset_daily_state should clear daily P&L and re-enable trading."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.portfolio.update_daily_pnl(-600)  # Triggers halt

        assert rm.portfolio.trading_halted is True

        rm.reset_daily_state()
        assert rm.portfolio.daily_pnl == 0.0
        assert rm.portfolio.trading_halted is False

    def test_reset_does_not_affect_drawdown(self):
        """Daily reset should NOT clear a drawdown halt."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.drawdown_halted = True

        rm.reset_daily_state()
        assert rm.drawdown_halted is True  # Still halted


class TestRiskSummary:
    """Verify risk summary and reporting."""

    def test_risk_summary_structure(self):
        """get_risk_summary should return all expected fields."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        summary = rm.get_risk_summary()

        assert "account_balance" in summary
        assert "peak_balance" in summary
        assert "current_drawdown" in summary
        assert "drawdown_halted" in summary
        assert "portfolio" in summary
        assert "trailing_stops" in summary
        assert "sector_exposure" in summary
        assert "trades_evaluated" in summary
        assert "trades_approved" in summary
        assert "trades_rejected" in summary
        assert "generated_at" in summary

    def test_summary_tracks_sector_exposure(self):
        """Sector exposure should reflect open positions."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=50000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, sector="Technology")
        rm.register_fill("XOM", 10, 80.0, 76.0, sector="Energy")

        summary = rm.get_risk_summary()
        assert summary["sector_exposure"]["Technology"] == 1
        assert summary["sector_exposure"]["Energy"] == 1

    def test_summary_tracks_decisions(self):
        """Decision counts should reflect evaluate_trade calls."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        rm.evaluate_trade("AAPL", 150.0, 144.0)  # Approved
        rm.evaluate_trade("XOM", 80.0, 85.0)     # Rejected (stop > entry)

        summary = rm.get_risk_summary()
        assert summary["trades_evaluated"] == 2
        assert summary["trades_approved"] == 1
        assert summary["trades_rejected"] == 1

    def test_print_risk_report_no_error(self, capsys):
        """print_risk_report should execute without errors."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)
        rm.register_fill("AAPL", 10, 150.0, 144.0, atr_value=3.0,
                          sector="Technology")

        rm.print_risk_report()
        captured = capsys.readouterr()
        assert "RISK STATUS REPORT" in captured.out
        assert "AAPL" in captured.out

    def test_print_risk_report_empty(self, capsys):
        """print_risk_report should handle empty state gracefully."""
        from risk.risk_manager import RiskManager
        rm = RiskManager(account_balance=10000)

        rm.print_risk_report()
        captured = capsys.readouterr()
        assert "RISK STATUS REPORT" in captured.out


class TestModule4Settings:
    """Verify that all Module 4 settings are present and valid."""

    def test_trailing_stop_settings(self):
        """Trailing stop configuration should be present and sensible."""
        from config.settings import (
            TRAILING_STOP_METHOD,
            TRAILING_STOP_ATR_MULTIPLIER,
            TRAILING_STOP_PERCENTAGE,
            BREAKEVEN_TRIGGER_R_MULTIPLE,
            BREAKEVEN_BUFFER_PCT,
        )

        assert TRAILING_STOP_METHOD in ("atr", "percentage", "breakeven_then_trail")
        assert TRAILING_STOP_ATR_MULTIPLIER > 0
        assert 0 < TRAILING_STOP_PERCENTAGE < 1
        assert BREAKEVEN_TRIGGER_R_MULTIPLE > 0
        assert 0 <= BREAKEVEN_BUFFER_PCT < 0.01  # Should be tiny

    def test_risk_manager_settings(self):
        """Risk manager configuration should be present and sensible."""
        from config.settings import (
            MAX_SECTOR_CONCENTRATION,
            MAX_DRAWDOWN_PCT,
            MIN_ACCOUNT_BALANCE,
        )

        assert MAX_SECTOR_CONCENTRATION >= 1
        assert 0 < MAX_DRAWDOWN_PCT < 1
        assert MIN_ACCOUNT_BALANCE > 0
