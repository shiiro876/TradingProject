# =============================================================================
# tests/test_module5.py — Unit Tests for Module 5 (Execution Engine)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 5 components:
#     - execution/broker.py:   Paper trading broker (buy, sell, account)
#     - execution/orders.py:   Order lifecycle (signal → fill → registration)
#     - execution/monitor.py:  Position monitoring & auto-exits (stop, TP1, TP2)
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module5.py -v
#
# =============================================================================

import os
import sys

import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Helper: Build synthetic signal dict (mirrors core/signals.py output)
# =============================================================================

def make_signal(
    symbol="AAPL",
    entry_price=150.0,
    stop_loss=144.0,
    take_profit_1=162.0,
    take_profit_2=168.0,
    risk_per_share=6.0,
    rr_ratio=2.0,
    signal_strength="STRONG",
    scanner_score=8.0,
    reason="Test signal",
):
    """Create a synthetic trade signal dict for testing."""
    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_per_share": risk_per_share,
        "rr_ratio": rr_ratio,
        "signal_strength": signal_strength,
        "scanner_score": scanner_score,
        "reason": reason,
    }


# =============================================================================
# Test Suite: execution/broker.py — PaperBroker
# =============================================================================

class TestPaperBrokerInit:
    """Verify PaperBroker initialization."""

    def test_init_balance(self):
        """PaperBroker should initialize with correct balance."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        assert broker.account_balance == 10000
        assert broker.positions == {}
        assert broker.order_history == []

    def test_get_account(self):
        """get_account should return account snapshot."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        account = broker.get_account()
        assert account["cash"] == 10000
        assert account["equity"] == 10000
        assert account["position_value"] == 0
        assert account["open_positions"] == 0
        assert account["paper_trading"] is True


class TestPaperBrokerBuy:
    """Verify buy order execution."""

    def test_buy_basic(self):
        """Basic buy should deduct cash and add position."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        result = broker.submit_order("AAPL", shares=10, side="buy", price=150.0)

        assert result["status"] == "filled"
        assert result["symbol"] == "AAPL"
        assert result["shares"] == 10
        assert result["fill_price"] == 150.0
        assert broker.account_balance == 8500.0  # 10000 - 1500
        assert "AAPL" in broker.positions
        assert broker.positions["AAPL"]["shares"] == 10

    def test_buy_insufficient_funds(self):
        """Buy exceeding cash should be rejected."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=100)
        result = broker.submit_order("AAPL", shares=10, side="buy", price=150.0)

        assert result["status"] == "rejected"
        assert "Insufficient funds" in result["reason"]
        assert broker.account_balance == 100  # Unchanged

    def test_buy_adds_to_existing_position(self):
        """Buying more of an existing position should average in."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=50000)
        broker.submit_order("AAPL", shares=10, side="buy", price=100.0)
        broker.submit_order("AAPL", shares=10, side="buy", price=200.0)

        pos = broker.positions["AAPL"]
        assert pos["shares"] == 20
        assert pos["avg_entry_price"] == 150.0  # (1000 + 2000) / 20

    def test_buy_zero_shares_rejected(self):
        """Zero shares should be rejected."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        result = broker.submit_order("AAPL", shares=0, side="buy", price=150.0)
        assert result["status"] == "rejected"

    def test_buy_negative_price_rejected(self):
        """Negative price should be rejected."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        result = broker.submit_order("AAPL", shares=10, side="buy", price=-1)
        assert result["status"] == "rejected"


class TestPaperBrokerSell:
    """Verify sell order execution."""

    def test_sell_basic(self):
        """Basic sell should add cash and remove position."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=10, side="buy", price=100.0)
        result = broker.submit_order("AAPL", shares=10, side="sell", price=110.0)

        assert result["status"] == "filled"
        assert result["realized_pnl"] == 100.0  # (110-100) * 10
        assert "AAPL" not in broker.positions  # Fully closed
        assert broker.account_balance == 10100.0  # 9000 + 1100

    def test_sell_partial(self):
        """Partial sell should reduce position, not close it."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=10, side="buy", price=100.0)
        result = broker.submit_order("AAPL", shares=5, side="sell", price=110.0)

        assert result["status"] == "filled"
        assert result["realized_pnl"] == 50.0  # (110-100) * 5
        assert broker.positions["AAPL"]["shares"] == 5

    def test_sell_no_position_rejected(self):
        """Selling without a position should be rejected."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        result = broker.submit_order("AAPL", shares=10, side="sell", price=150.0)

        assert result["status"] == "rejected"
        assert "No open position" in result["reason"]

    def test_sell_more_than_held_rejected(self):
        """Selling more shares than held should be rejected."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=5, side="buy", price=100.0)
        result = broker.submit_order("AAPL", shares=10, side="sell", price=110.0)

        assert result["status"] == "rejected"
        assert "only 5 held" in result["reason"]

    def test_sell_at_loss(self):
        """Selling at a loss should calculate negative P&L."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=10, side="buy", price=100.0)
        result = broker.submit_order("AAPL", shares=10, side="sell", price=90.0)

        assert result["realized_pnl"] == -100.0  # (90-100) * 10


class TestPaperBrokerInvalidSide:
    """Verify invalid order side handling."""

    def test_invalid_side(self):
        """Invalid side should be rejected."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        result = broker.submit_order("AAPL", shares=10, side="short", price=150.0)
        assert result["status"] == "rejected"
        assert "Invalid side" in result["reason"]


class TestPaperBrokerHelpers:
    """Verify helper methods."""

    def test_get_position(self):
        """get_position should return position or None."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        assert broker.get_position("AAPL") is None

        broker.submit_order("AAPL", shares=10, side="buy", price=150.0)
        pos = broker.get_position("AAPL")
        assert pos is not None
        assert pos["shares"] == 10

    def test_get_all_positions(self):
        """get_all_positions should return all open positions."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=50000)
        broker.submit_order("AAPL", shares=10, side="buy", price=150.0)
        broker.submit_order("XOM", shares=20, side="buy", price=80.0)

        positions = broker.get_all_positions()
        assert len(positions) == 2
        assert "AAPL" in positions
        assert "XOM" in positions

    def test_update_position_price(self):
        """update_position_price should update current price and P&L."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=10, side="buy", price=100.0)

        assert broker.update_position_price("AAPL", 110.0) is True
        pos = broker.positions["AAPL"]
        assert pos["current_price"] == 110.0
        assert pos["unrealized_pnl"] == 100.0  # (110-100) * 10

    def test_update_position_price_nonexistent(self):
        """Updating nonexistent position should return False."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        assert broker.update_position_price("FAKE", 100.0) is False

    def test_order_history(self):
        """Order history should track all submitted orders."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=10, side="buy", price=150.0)
        broker.submit_order("AAPL", shares=10, side="sell", price=155.0)

        history = broker.get_order_history()
        assert len(history) == 2
        assert history[0]["side"] == "buy"
        assert history[1]["side"] == "sell"

    def test_account_equity_with_positions(self):
        """Equity should include position value."""
        from execution.broker import PaperBroker
        broker = PaperBroker(account_balance=10000)
        broker.submit_order("AAPL", shares=10, side="buy", price=100.0)

        account = broker.get_account()
        assert account["cash"] == 9000.0
        assert account["position_value"] == 1000.0
        assert account["equity"] == 10000.0


class TestGetBroker:
    """Verify broker factory function."""

    def test_get_broker_returns_paper(self):
        """get_broker should return PaperBroker when PAPER_TRADING=True."""
        from execution.broker import get_broker, PaperBroker
        broker = get_broker(account_balance=10000)
        assert isinstance(broker, PaperBroker)
        assert broker.account_balance == 10000


# =============================================================================
# Test Suite: execution/orders.py — OrderManager
# =============================================================================

class TestOrderManagerInit:
    """Verify OrderManager initialization."""

    def test_init(self):
        """OrderManager should initialize with all dependencies."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        assert om.active_orders == {}


class TestExecuteSignal:
    """Verify signal execution lifecycle."""

    def test_execute_approved_signal(self):
        """Approved signal should result in a filled order."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        signal = make_signal()
        result = om.execute_signal(signal, sector="Technology")

        assert result["status"] == "filled"
        assert result["shares"] > 0
        assert result["symbol"] == "AAPL"
        assert "AAPL" in om.active_orders

    def test_execute_rejected_signal(self):
        """Signal rejected by risk manager should return 'rejected' status."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        # Very low balance: risk gate will reject
        rm = RiskManager(account_balance=100)
        broker = PaperBroker(account_balance=100)
        om = OrderManager(rm, broker)

        signal = make_signal()
        result = om.execute_signal(signal)

        assert result["status"] == "rejected"
        assert result["fill"] is None
        assert "AAPL" not in om.active_orders

    def test_execute_registers_in_risk_manager(self):
        """Filled order should be registered in all risk sub-managers."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        signal = make_signal()
        result = om.execute_signal(signal, sector="Technology")

        assert result["status"] == "filled"
        # Verify risk manager tracks the position
        assert "AAPL" in rm.portfolio.open_positions
        assert rm.trailing_stops.get_stop("AAPL") is not None
        assert rm.sector_map.get("AAPL") == "Technology"

    def test_execute_multiple_signals(self):
        """Should handle multiple signals up to max positions."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=50000)
        broker = PaperBroker(account_balance=50000)
        om = OrderManager(rm, broker)

        sig1 = make_signal(symbol="AAPL", entry_price=100.0, stop_loss=94.0)
        sig2 = make_signal(symbol="XOM", entry_price=80.0, stop_loss=76.0)
        sig3 = make_signal(symbol="JPM", entry_price=90.0, stop_loss=84.0)

        r1 = om.execute_signal(sig1, sector="Technology")
        r2 = om.execute_signal(sig2, sector="Energy")
        r3 = om.execute_signal(sig3, sector="Financials")

        assert r1["status"] == "filled"
        assert r2["status"] == "filled"
        assert r3["status"] == "filled"
        assert len(om.active_orders) == 3

    def test_execute_fourth_signal_rejected(self):
        """4th signal should be rejected (max positions = 3)."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=50000)
        broker = PaperBroker(account_balance=50000)
        om = OrderManager(rm, broker)

        for sym in ["AAPL", "XOM", "JPM"]:
            om.execute_signal(make_signal(symbol=sym, entry_price=100.0, stop_loss=94.0))

        r4 = om.execute_signal(make_signal(symbol="TSLA", entry_price=200.0, stop_loss=190.0))
        assert r4["status"] == "rejected"

    def test_execute_insufficient_broker_funds(self):
        """Order should fail if broker has insufficient funds (edge case)."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        # RiskManager thinks we have 10000 but broker only has 100
        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=100)
        om = OrderManager(rm, broker)

        signal = make_signal()
        result = om.execute_signal(signal)
        assert result["status"] == "failed"


class TestClosePosition:
    """Verify position closing lifecycle."""

    def test_close_winning_trade(self):
        """Closing at profit should record positive P&L."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        signal = make_signal()
        om.execute_signal(signal, sector="Technology")

        result = om.close_position("AAPL", exit_price=160.0, reason="manual")
        assert result is not None
        assert result["realized_pnl"] > 0
        assert "AAPL" not in om.active_orders

    def test_close_losing_trade(self):
        """Closing at loss should record negative P&L."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        signal = make_signal()
        om.execute_signal(signal, sector="Technology")

        result = om.close_position("AAPL", exit_price=140.0, reason="trailing_stop")
        assert result is not None
        assert result["realized_pnl"] < 0

    def test_close_nonexistent_returns_none(self):
        """Closing a symbol with no active order should return None."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        assert om.close_position("FAKE", 100.0) is None

    def test_close_logs_to_journal(self, tmp_path):
        """Closing a position should log to the trade journal."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager
        from learning.journal import TradeJournal

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        om = OrderManager(rm, broker, journal=journal)

        signal = make_signal()
        om.execute_signal(signal, sector="Technology")
        om.close_position("AAPL", exit_price=160.0, reason="tp1")

        trades = journal.get_all_trades()
        assert len(trades) == 1
        assert trades.iloc[0]["symbol"] == "AAPL"
        assert trades.iloc[0]["exit_reason"] == "tp1"


class TestOrderManagerHelpers:
    """Verify order manager helper methods."""

    def test_get_active_symbols(self):
        """get_active_symbols should list open symbols."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=50000)
        broker = PaperBroker(account_balance=50000)
        om = OrderManager(rm, broker)

        om.execute_signal(make_signal(symbol="AAPL", entry_price=100.0, stop_loss=94.0))
        om.execute_signal(make_signal(symbol="XOM", entry_price=80.0, stop_loss=76.0))

        symbols = om.get_active_symbols()
        assert "AAPL" in symbols
        assert "XOM" in symbols

    def test_has_position(self):
        """has_position should return True/False correctly."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        assert om.has_position("AAPL") is False
        om.execute_signal(make_signal())
        assert om.has_position("AAPL") is True

    def test_execution_summary(self):
        """get_execution_summary should return all expected fields."""
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)

        summary = om.get_execution_summary()
        assert "account" in summary
        assert "active_positions" in summary
        assert "risk_summary" in summary
        assert "total_orders" in summary


class TestSignalRR:
    """Verify signal R:R helper function."""

    def test_valid_rr(self):
        """Should calculate R:R from entry, stop, TP1."""
        from execution.orders import signal_rr
        order_record = {
            "entry_price": 150.0,
            "stop_loss": 144.0,
            "take_profit_1": 162.0,
        }
        assert signal_rr(order_record) == 2.0

    def test_rr_no_tp1(self):
        """Should return None if TP1 is missing."""
        from execution.orders import signal_rr
        order_record = {"entry_price": 150.0, "stop_loss": 144.0}
        assert signal_rr(order_record) is None

    def test_rr_invalid_setup(self):
        """Should return None if entry <= stop."""
        from execution.orders import signal_rr
        order_record = {"entry_price": 100.0, "stop_loss": 105.0}
        assert signal_rr(order_record) is None


# =============================================================================
# Test Suite: execution/monitor.py — PositionMonitor
# =============================================================================

class TestMonitorInit:
    """Verify PositionMonitor initialization."""

    def test_init(self):
        """PositionMonitor should initialize correctly."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        assert monitor.tp1_triggered == set()
        assert monitor.exit_log == []


class TestMonitorTrailingStop:
    """Verify trailing stop exit detection."""

    def test_stop_hit_triggers_exit(self):
        """Price below trailing stop should trigger auto-exit."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        # Price drops below stop (144.0)
        action = monitor.check_position("AAPL", current_price=143.0)

        assert action is not None
        assert action["action"] == "trailing_stop_exit"
        assert action["realized_pnl"] < 0
        assert "AAPL" not in om.active_orders

    def test_price_above_stop_no_action(self):
        """Price above stop should not trigger any exit."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        # Price still above stop
        action = monitor.check_position("AAPL", current_price=152.0)
        assert action is None


class TestMonitorTP2:
    """Verify Take Profit 2 exit."""

    def test_tp2_triggers_full_exit(self):
        """Price at TP2 should close full position."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        # Price hits TP2 (168.0)
        action = monitor.check_position("AAPL", current_price=168.0)

        assert action is not None
        assert action["action"] == "tp2_exit"
        assert action["realized_pnl"] > 0
        assert "AAPL" not in om.active_orders


class TestMonitorTP1:
    """Verify Take Profit 1 partial exit."""

    def test_tp1_triggers_partial_exit(self):
        """Price at TP1 should close 50% of position."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        signal = make_signal()
        result = om.execute_signal(signal, sector="Technology")
        original_shares = result["shares"]

        # Price hits TP1 (162.0)
        action = monitor.check_position("AAPL", current_price=162.0)

        assert action is not None
        assert action["action"] == "tp1_partial_exit"
        expected_closed = max(1, original_shares // 2)
        assert action["shares_closed"] == expected_closed
        assert action["shares_remaining"] == original_shares - expected_closed
        assert "AAPL" in om.active_orders  # Still open (partial close)

    def test_tp1_only_triggers_once(self):
        """TP1 should only trigger once per position."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        # First TP1 hit
        action1 = monitor.check_position("AAPL", current_price=162.0)
        assert action1 is not None
        assert action1["action"] == "tp1_partial_exit"

        # Second time at TP1 — should NOT trigger again
        action2 = monitor.check_position("AAPL", current_price=163.0)
        assert action2 is None  # TP1 already triggered

    def test_tp1_then_tp2_full_lifecycle(self):
        """TP1 partial → TP2 full close lifecycle."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        # TP1 hit → partial close
        action1 = monitor.check_position("AAPL", current_price=162.0)
        assert action1["action"] == "tp1_partial_exit"

        # TP2 hit → close remaining
        action2 = monitor.check_position("AAPL", current_price=168.0)
        assert action2 is not None
        assert action2["action"] == "tp2_exit"
        assert "AAPL" not in om.active_orders


class TestMonitorCheckAll:
    """Verify batch position checking."""

    def test_check_all_positions(self):
        """check_all_positions should handle multiple positions."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=50000)
        broker = PaperBroker(account_balance=50000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(
            make_signal(symbol="AAPL", entry_price=150.0, stop_loss=144.0,
                       take_profit_1=162.0, take_profit_2=168.0),
            sector="Technology",
        )
        om.execute_signal(
            make_signal(symbol="XOM", entry_price=80.0, stop_loss=76.0,
                       take_profit_1=88.0, take_profit_2=92.0),
            sector="Energy",
        )

        price_data = {
            "AAPL": {"price": 152.0},  # No action
            "XOM": {"price": 75.0},    # Stop hit
        }

        actions = monitor.check_all_positions(price_data)
        assert len(actions) == 1
        assert actions[0]["symbol"] == "XOM"
        assert actions[0]["action"] == "trailing_stop_exit"

    def test_check_all_no_data(self):
        """No price data should result in no actions."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        actions = monitor.check_all_positions({})
        assert actions == []


class TestMonitorRunCycle:
    """Verify monitoring cycle with price fetcher."""

    def test_run_cycle_with_fetcher(self):
        """run_monitoring_cycle should use callback to fetch prices."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")

        def mock_price_fetcher(symbols):
            return {"AAPL": {"price": 152.0}}  # No exit triggered

        actions = monitor.run_monitoring_cycle(price_fetcher=mock_price_fetcher)
        assert actions == []

    def test_run_cycle_no_fetcher(self):
        """No price fetcher should return empty list."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        actions = monitor.run_monitoring_cycle()
        assert actions == []

    def test_run_cycle_no_positions(self):
        """No positions should result in no actions."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        def mock_fetcher(symbols):
            return {}

        actions = monitor.run_monitoring_cycle(price_fetcher=mock_fetcher)
        assert actions == []


class TestMonitorSummary:
    """Verify monitoring summary and reporting."""

    def test_monitoring_summary_structure(self):
        """get_monitoring_summary should return expected fields."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        summary = monitor.get_monitoring_summary()
        assert "active_positions" in summary
        assert "tp1_triggered" in summary
        assert "total_exits" in summary
        assert "exits_by_reason" in summary
        assert "total_realized_pnl" in summary

    def test_print_monitoring_report_no_error(self, capsys):
        """print_monitoring_report should execute without errors."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        monitor.print_monitoring_report()
        captured = capsys.readouterr()
        assert "POSITION MONITOR" in captured.out

    def test_exit_log_tracks_exits(self):
        """Exit log should accumulate all auto-exits."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        om.execute_signal(make_signal(), sector="Technology")
        monitor.check_position("AAPL", current_price=143.0)  # Stop hit

        log = monitor.get_exit_log()
        assert len(log) == 1
        assert log[0]["action"] == "trailing_stop_exit"


class TestMonitorCheckUnknownPosition:
    """Verify handling of unknown symbols."""

    def test_check_unknown_symbol(self):
        """Checking unknown symbol should return None."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        om = OrderManager(rm, broker)
        monitor = PositionMonitor(om, rm)

        action = monitor.check_position("FAKE", current_price=100.0)
        assert action is None


# =============================================================================
# Test Suite: Module 5 Integration Tests
# =============================================================================

class TestFullTradeLifecycle:
    """End-to-end integration test: signal → execute → monitor → close."""

    def test_full_lifecycle_with_journal(self, tmp_path):
        """Complete trade lifecycle with journal logging."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager
        from learning.journal import TradeJournal

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        om = OrderManager(rm, broker, journal=journal)
        monitor = PositionMonitor(om, rm)

        # 1. Execute signal
        signal = make_signal()
        result = om.execute_signal(signal, sector="Technology")
        assert result["status"] == "filled"
        entry_shares = result["shares"]

        # 2. Monitor — price rises, no exit
        action = monitor.check_position("AAPL", current_price=155.0)
        assert action is None

        # 3. Price hits TP1 — partial close
        action_tp1 = monitor.check_position("AAPL", current_price=162.0)
        assert action_tp1 is not None
        assert action_tp1["action"] == "tp1_partial_exit"

        # 4. Price hits TP2 — full close
        action_tp2 = monitor.check_position("AAPL", current_price=168.0)
        assert action_tp2 is not None
        assert action_tp2["action"] == "tp2_exit"

        # 5. Verify journal has logged the trades
        trades = journal.get_all_trades()
        assert len(trades) >= 1  # At least TP1 partial logged

        # 6. Verify position is fully closed
        assert "AAPL" not in om.active_orders

    def test_lifecycle_stop_loss_exit(self, tmp_path):
        """Trade enters and exits at trailing stop."""
        from execution.monitor import PositionMonitor
        from execution.orders import OrderManager
        from execution.broker import PaperBroker
        from risk.risk_manager import RiskManager
        from learning.journal import TradeJournal

        rm = RiskManager(account_balance=10000)
        broker = PaperBroker(account_balance=10000)
        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        om = OrderManager(rm, broker, journal=journal)
        monitor = PositionMonitor(om, rm)

        # Execute
        signal = make_signal()
        om.execute_signal(signal, sector="Technology")

        # Price drops to stop
        action = monitor.check_position("AAPL", current_price=143.0)
        assert action is not None
        assert action["action"] == "trailing_stop_exit"
        assert "AAPL" not in om.active_orders

        # Journal should have the trade
        trades = journal.get_all_trades()
        assert len(trades) == 1
        assert trades.iloc[0]["exit_reason"] == "trailing_stop"


class TestModule5Settings:
    """Verify Module 5 settings are present in config."""

    def test_execution_settings_exist(self):
        """All execution settings should be present and valid."""
        from config.settings import (
            DEFAULT_ORDER_TYPE,
            MONITOR_INTERVAL_SECONDS,
            TP1_CLOSE_RATIO,
        )

        assert DEFAULT_ORDER_TYPE == "market"
        assert MONITOR_INTERVAL_SECONDS > 0
        assert 0 < TP1_CLOSE_RATIO <= 1.0
