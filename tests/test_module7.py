# =============================================================================
# tests/test_module7.py — Unit Tests for Module 7 (Dashboard & Alerts)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 7 components:
#     - dashboard/app.py:    Main dashboard aggregation & display
#     - dashboard/charts.py: Text-based chart rendering
#     - dashboard/alerts.py: Alert creation, storage, and delivery
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module7.py -v
#
# =============================================================================

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Helpers: Mock components for dashboard testing
# =============================================================================

def make_mock_broker(cash=10000.0, positions=None):
    """Create a mock PaperBroker for testing."""
    broker = MagicMock()
    pos = positions or {}
    position_value = sum(p.get("shares", 0) * p.get("current_price", 0) for p in pos.values())

    broker.get_account.return_value = {
        "cash": cash,
        "equity": cash + position_value,
        "position_value": position_value,
        "open_positions": len(pos),
        "paper_trading": True,
    }
    broker.get_all_positions.return_value = pos
    return broker


def make_mock_risk_manager(drawdown=5.0, halted=False, trailing_stops=None):
    """Create a mock RiskManager for testing."""
    rm = MagicMock()
    rm.get_risk_summary.return_value = {
        "current_drawdown_pct": drawdown,
        "trading_halted": halted,
        "trailing_stops": trailing_stops or {},
    }
    return rm


def make_mock_order_manager(active_orders=None):
    """Create a mock OrderManager for testing."""
    om = MagicMock()
    om.get_active_orders.return_value = active_orders or {}
    return om


def make_mock_journal(trades=5, win_rate=60.0, total_pnl=500.0):
    """Create a mock TradeJournal for testing."""
    journal = MagicMock()
    journal.get_performance_stats.return_value = {
        "total_trades": trades,
        "wins": int(trades * win_rate / 100),
        "losses": trades - int(trades * win_rate / 100),
        "win_rate": win_rate,
        "avg_win": 150.0,
        "avg_loss": -80.0,
        "profit_factor": 1.85,
        "total_pnl": total_pnl,
        "best_trade": 300.0,
        "worst_trade": -120.0,
        "max_drawdown": -200.0,
        "monthly_pnl": {"2025-01": 300.0, "2025-02": 200.0},
    }
    return journal


def make_mock_trainer(is_trained=True, accuracy=0.72):
    """Create a mock TradeTrainer for testing."""
    trainer = MagicMock()
    trainer.get_training_summary.return_value = {
        "is_trained": is_trained,
        "training_stats": {
            "trained": is_trained,
            "total_trades": 30,
            "accuracy": accuracy,
            "win_rate": 0.55,
        },
        "feature_importance": {
            "scanner_score": 0.35,
            "risk_reward": 0.25,
            "entry_price": 0.20,
        },
    }
    return trainer


def make_equity_data(n_points=30, start_balance=10000):
    """Create synthetic equity curve data for chart testing."""
    import random
    random.seed(42)
    data = []
    balance = start_balance
    for i in range(n_points):
        balance += random.uniform(-100, 150)
        balance = max(balance, 5000)
        data.append({
            "date": f"2025-01-{i+1:02d}",
            "equity": round(balance, 2),
            "cash": round(balance * 0.7, 2),
            "open_positions": random.randint(0, 3),
        })
    return data


# =============================================================================
# Test Suite: dashboard/app.py — Dashboard
# =============================================================================

class TestDashboardInit:
    """Verify Dashboard initialization."""

    def test_init_no_args(self):
        """Dashboard should initialize with no components."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        assert dash.risk_manager is None
        assert dash.order_manager is None
        assert dash.broker is None
        assert dash.journal is None
        assert dash.trainer is None
        assert dash.alert_manager is None

    def test_init_with_components(self):
        """Dashboard should accept all component types."""
        from dashboard.app import Dashboard
        broker = make_mock_broker()
        rm = make_mock_risk_manager()
        dash = Dashboard(risk_manager=rm, broker=broker)
        assert dash.broker is broker
        assert dash.risk_manager is rm


class TestDashboardAccountSummary:
    """Verify account summary aggregation."""

    def test_account_summary_with_broker(self):
        """Account summary should return broker data."""
        from dashboard.app import Dashboard
        broker = make_mock_broker(cash=8500, positions={
            "AAPL": {"shares": 10, "current_price": 150.0, "avg_entry_price": 145.0, "unrealized_pnl": 50.0}
        })
        rm = make_mock_risk_manager(drawdown=3.5)
        dash = Dashboard(broker=broker, risk_manager=rm)

        summary = dash.get_account_summary()
        assert summary["cash"] == 8500
        assert summary["open_positions"] == 1
        assert summary["current_drawdown"] == 3.5
        assert summary["trading_halted"] is False

    def test_account_summary_no_broker(self):
        """Account summary without broker should return zeros."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        summary = dash.get_account_summary()
        assert summary["cash"] == 0.0
        assert summary["equity"] == 0.0

    def test_account_summary_halted(self):
        """Account summary should show halted status."""
        from dashboard.app import Dashboard
        rm = make_mock_risk_manager(halted=True)
        dash = Dashboard(risk_manager=rm, broker=make_mock_broker())
        summary = dash.get_account_summary()
        assert summary["trading_halted"] is True


class TestDashboardPositions:
    """Verify position detail aggregation."""

    def test_position_details_with_positions(self):
        """Should return enriched position details."""
        from dashboard.app import Dashboard
        positions = {
            "AAPL": {
                "shares": 10, "avg_entry_price": 150.0,
                "current_price": 155.0, "unrealized_pnl": 50.0,
            },
        }
        broker = make_mock_broker(positions=positions)
        dash = Dashboard(broker=broker)
        details = dash.get_position_details()
        assert len(details) == 1
        assert details[0]["symbol"] == "AAPL"
        assert details[0]["shares"] == 10
        assert details[0]["unrealized_pnl"] == 50.0

    def test_position_details_empty(self):
        """Should return empty list when no positions."""
        from dashboard.app import Dashboard
        dash = Dashboard(broker=make_mock_broker())
        assert dash.get_position_details() == []

    def test_position_details_no_broker(self):
        """Should return empty list when no broker."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        assert dash.get_position_details() == []


class TestDashboardPerformance:
    """Verify performance overview aggregation."""

    def test_performance_with_journal(self):
        """Should return journal performance stats."""
        from dashboard.app import Dashboard
        journal = make_mock_journal(trades=20, win_rate=55.0, total_pnl=800.0)
        dash = Dashboard(journal=journal)
        perf = dash.get_performance_overview()
        assert perf["total_trades"] == 20
        assert perf["win_rate"] == 55.0
        assert perf["total_pnl"] == 800.0

    def test_performance_no_journal(self):
        """Should return zeroed stats without journal."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        perf = dash.get_performance_overview()
        assert perf["total_trades"] == 0
        assert perf["win_rate"] == 0.0


class TestDashboardModelStatus:
    """Verify ML model status aggregation."""

    def test_model_trained(self):
        """Should report trained model status."""
        from dashboard.app import Dashboard
        trainer = make_mock_trainer(is_trained=True, accuracy=0.72)
        dash = Dashboard(trainer=trainer)
        status = dash.get_model_status()
        assert status["is_trained"] is True
        assert "accuracy" in status["training_stats"]

    def test_model_not_trained(self):
        """Should report untrained model status."""
        from dashboard.app import Dashboard
        trainer = make_mock_trainer(is_trained=False)
        dash = Dashboard(trainer=trainer)
        status = dash.get_model_status()
        assert status["is_trained"] is False

    def test_model_no_trainer(self):
        """Should handle missing trainer gracefully."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        status = dash.get_model_status()
        assert status["is_trained"] is False


class TestDashboardAlerts:
    """Verify alert integration."""

    def test_recent_alerts_with_manager(self):
        """Should return alerts from alert manager."""
        from dashboard.app import Dashboard
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("Test alert 1", level="INFO")
        am.send_alert("Test alert 2", level="WARNING")
        dash = Dashboard(alert_manager=am)
        alerts = dash.get_recent_alerts(limit=5)
        assert len(alerts) == 2

    def test_recent_alerts_no_manager(self):
        """Should return empty list without alert manager."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        assert dash.get_recent_alerts() == []


class TestDashboardSystemSnapshot:
    """Verify full system snapshot."""

    def test_snapshot_structure(self):
        """System snapshot should have all expected sections."""
        from dashboard.app import Dashboard
        dash = Dashboard(
            broker=make_mock_broker(),
            risk_manager=make_mock_risk_manager(),
            journal=make_mock_journal(),
            trainer=make_mock_trainer(),
        )
        snapshot = dash.get_system_snapshot()
        assert "timestamp" in snapshot
        assert "account" in snapshot
        assert "positions" in snapshot
        assert "performance" in snapshot
        assert "model" in snapshot
        assert "alerts" in snapshot

    def test_snapshot_empty_components(self):
        """Snapshot with no components should still have all sections."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        snapshot = dash.get_system_snapshot()
        assert snapshot["account"]["cash"] == 0.0
        assert snapshot["positions"] == []
        assert snapshot["performance"]["total_trades"] == 0


class TestDashboardPrint:
    """Verify dashboard printing."""

    def test_print_dashboard_full(self, capsys):
        """print_dashboard with all components should not raise."""
        from dashboard.app import Dashboard
        dash = Dashboard(
            broker=make_mock_broker(cash=8500, positions={
                "AAPL": {"shares": 10, "avg_entry_price": 150.0,
                         "current_price": 155.0, "unrealized_pnl": 50.0},
            }),
            risk_manager=make_mock_risk_manager(drawdown=3.5),
            journal=make_mock_journal(),
            trainer=make_mock_trainer(),
        )
        dash.print_dashboard()
        captured = capsys.readouterr()
        assert "TRADING DASHBOARD" in captured.out
        assert "ACCOUNT" in captured.out
        assert "PERFORMANCE" in captured.out
        assert "POSITIONS" in captured.out

    def test_print_dashboard_empty(self, capsys):
        """print_dashboard with no components should not raise."""
        from dashboard.app import Dashboard
        dash = Dashboard()
        dash.print_dashboard()
        captured = capsys.readouterr()
        assert "TRADING DASHBOARD" in captured.out

    def test_print_dashboard_halted(self, capsys):
        """print_dashboard should show halted status."""
        from dashboard.app import Dashboard
        dash = Dashboard(
            broker=make_mock_broker(),
            risk_manager=make_mock_risk_manager(halted=True),
        )
        dash.print_dashboard()
        captured = capsys.readouterr()
        assert "HALTED" in captured.out


# =============================================================================
# Test Suite: dashboard/charts.py — Chart Renderers
# =============================================================================

class TestEquityCurve:
    """Verify equity curve rendering."""

    def test_render_equity_curve_basic(self):
        """Should produce a multi-line chart string."""
        from dashboard.charts import render_equity_curve
        data = make_equity_data(n_points=30)
        result = render_equity_curve(data)
        assert isinstance(result, str)
        assert "EQUITY CURVE" in result
        assert len(result.split("\n")) > 5

    def test_render_equity_curve_empty(self):
        """Should handle empty data."""
        from dashboard.charts import render_equity_curve
        result = render_equity_curve([])
        assert "No equity data" in result

    def test_render_equity_curve_single_point(self):
        """Should handle single data point."""
        from dashboard.charts import render_equity_curve
        result = render_equity_curve([{"equity": 10000}])
        assert isinstance(result, str)


class TestPnlBars:
    """Verify P&L bar chart rendering."""

    def test_render_pnl_bars_basic(self):
        """Should render bars for each period."""
        from dashboard.charts import render_pnl_bars
        data = {"2025-01": 500.0, "2025-02": -200.0, "2025-03": 300.0}
        result = render_pnl_bars(data)
        assert "P&L BY PERIOD" in result
        assert "2025-01" in result
        assert "2025-02" in result

    def test_render_pnl_bars_empty(self):
        """Should handle empty data."""
        from dashboard.charts import render_pnl_bars
        result = render_pnl_bars({})
        assert "No P&L data" in result

    def test_render_pnl_bars_all_positive(self):
        """Should handle all positive P&L."""
        from dashboard.charts import render_pnl_bars
        data = {"Jan": 100.0, "Feb": 200.0}
        result = render_pnl_bars(data)
        assert isinstance(result, str)


class TestWinLossChart:
    """Verify win/loss chart rendering."""

    def test_render_win_loss_basic(self):
        """Should render win/loss bar and stats."""
        from dashboard.charts import render_win_loss_chart
        stats = {
            "total_trades": 20, "wins": 12, "losses": 8,
            "win_rate": 60.0, "avg_win": 150.0, "avg_loss": -80.0,
        }
        result = render_win_loss_chart(stats)
        assert "WIN/LOSS" in result
        assert "60.0%" in result

    def test_render_win_loss_empty(self):
        """Should handle zero trades."""
        from dashboard.charts import render_win_loss_chart
        result = render_win_loss_chart({"total_trades": 0})
        assert "No trades" in result


class TestDrawdownChart:
    """Verify drawdown chart rendering."""

    def test_render_drawdown_basic(self):
        """Should render drawdown visualization."""
        from dashboard.charts import render_drawdown_chart
        data = make_equity_data(n_points=30)
        result = render_drawdown_chart(data)
        assert isinstance(result, str)
        assert "DRAWDOWN" in result

    def test_render_drawdown_empty(self):
        """Should handle empty data."""
        from dashboard.charts import render_drawdown_chart
        result = render_drawdown_chart([])
        assert "No equity data" in result


class TestSectorHeatmap:
    """Verify sector heatmap rendering."""

    def test_render_sector_heatmap_basic(self):
        """Should display sector concentrations."""
        from dashboard.charts import render_sector_heatmap
        data = {"Technology": 2, "Energy": 1, "Healthcare": 0}
        result = render_sector_heatmap(data)
        assert "SECTOR CONCENTRATION" in result
        assert "Technology" in result

    def test_render_sector_heatmap_empty(self):
        """Should handle empty sector data."""
        from dashboard.charts import render_sector_heatmap
        result = render_sector_heatmap({})
        assert "No sector data" in result


class TestSparkline:
    """Verify sparkline rendering."""

    def test_render_sparkline_basic(self):
        """Should produce a string of block characters."""
        from dashboard.charts import render_sparkline
        values = [1, 3, 5, 7, 9, 7, 5, 3, 1]
        result = render_sparkline(values)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_sparkline_empty(self):
        """Should return empty string for no data."""
        from dashboard.charts import render_sparkline
        assert render_sparkline([]) == ""

    def test_render_sparkline_constant(self):
        """Should handle constant values (no range)."""
        from dashboard.charts import render_sparkline
        result = render_sparkline([5, 5, 5, 5])
        assert isinstance(result, str)

    def test_render_sparkline_long(self):
        """Should subsample long value lists."""
        from dashboard.charts import render_sparkline
        values = list(range(100))
        result = render_sparkline(values, width=20)
        assert len(result) <= 20


class TestTradeTable:
    """Verify trade table rendering."""

    def test_render_trade_table_basic(self):
        """Should format trades into a table."""
        from dashboard.charts import render_trade_table
        trades = [
            {"symbol": "AAPL", "entry_price": 150, "exit_price": 155,
             "shares": 10, "pnl": 50, "exit_reason": "tp1"},
            {"symbol": "XOM", "entry_price": 80, "exit_price": 75,
             "shares": 20, "pnl": -100, "exit_reason": "stop"},
        ]
        result = render_trade_table(trades)
        assert "RECENT TRADES" in result
        assert "AAPL" in result
        assert "XOM" in result

    def test_render_trade_table_empty(self):
        """Should handle empty trade list."""
        from dashboard.charts import render_trade_table
        result = render_trade_table([])
        assert "No trades" in result


# =============================================================================
# Test Suite: dashboard/alerts.py — AlertManager
# =============================================================================

class TestAlertManagerInit:
    """Verify AlertManager initialization."""

    def test_init_no_telegram(self):
        """AlertManager without credentials should disable Telegram."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        assert am.telegram_enabled is False
        assert am.alert_history == []

    def test_init_with_telegram(self):
        """AlertManager with credentials should enable Telegram."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="test_token", telegram_chat_id="12345")
        assert am.telegram_enabled is True


class TestAlertSending:
    """Verify alert creation and storage."""

    def test_send_info_alert(self):
        """INFO alert should be stored correctly."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.send_alert("Test message", level="INFO")
        assert result["level"] == "INFO"
        assert result["message"] == "Test message"
        assert "timestamp" in result
        assert len(am.alert_history) == 1

    def test_send_warning_alert(self):
        """WARNING alert should be stored correctly."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.send_alert("Warning test", level="WARNING")
        assert result["level"] == "WARNING"

    def test_send_critical_alert(self):
        """CRITICAL alert should be stored correctly."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.send_alert("Critical test", level="CRITICAL")
        assert result["level"] == "CRITICAL"

    def test_send_invalid_level_defaults_to_info(self):
        """Invalid level should default to INFO."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.send_alert("Test", level="INVALID")
        assert result["level"] == "INFO"

    def test_multiple_alerts_stored(self):
        """Multiple alerts should accumulate in history."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("Alert 1")
        am.send_alert("Alert 2")
        am.send_alert("Alert 3")
        assert len(am.alert_history) == 3


class TestAlertConvenienceMethods:
    """Verify convenience alert methods."""

    def test_alert_trade_fill_buy(self):
        """Trade fill alert for buy should contain correct info."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_trade_fill("AAPL", "buy", 33, 150.0)
        assert "AAPL" in result["message"]
        assert "33" in result["message"]
        assert "150.00" in result["message"]
        assert "BUY" in result["message"]

    def test_alert_trade_fill_sell(self):
        """Trade fill alert for sell should contain correct info."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_trade_fill("AAPL", "sell", 33, 155.0)
        assert "SELL" in result["message"]

    def test_alert_position_exit_win(self):
        """Exit alert for winning trade should be INFO level."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_position_exit("AAPL", "tp1", 150.0, 162.0)
        assert result["level"] == "INFO"
        assert "AAPL" in result["message"]

    def test_alert_position_exit_loss(self):
        """Exit alert for losing trade should be WARNING level."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_position_exit("AAPL", "stop", -100.0, 140.0)
        assert result["level"] == "WARNING"

    def test_alert_drawdown_info(self):
        """Low drawdown should be INFO level."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_drawdown_warning(5.0)
        assert result["level"] == "INFO"

    def test_alert_drawdown_warning(self):
        """Medium drawdown should be WARNING level."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_drawdown_warning(12.0)
        assert result["level"] == "WARNING"

    def test_alert_drawdown_critical(self):
        """High drawdown should be CRITICAL level."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_drawdown_warning(16.0)
        assert result["level"] == "CRITICAL"

    def test_alert_trading_halted(self):
        """Trading halted alert should be CRITICAL."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_trading_halted("Max drawdown exceeded")
        assert result["level"] == "CRITICAL"
        assert "HALTED" in result["message"]

    def test_alert_daily_loss_warning(self):
        """Daily loss under 5% should be WARNING."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_daily_loss_limit(4.0)
        assert result["level"] == "WARNING"

    def test_alert_daily_loss_critical(self):
        """Daily loss at 5%+ should be CRITICAL."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_daily_loss_limit(5.5)
        assert result["level"] == "CRITICAL"

    def test_alert_system_error(self):
        """System error alert should be CRITICAL."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.alert_system_error("Database connection lost")
        assert result["level"] == "CRITICAL"
        assert "SYSTEM ERROR" in result["message"]


class TestAlertHistory:
    """Verify alert history retrieval."""

    def test_get_alert_history_ordered(self):
        """History should return newest first."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("First")
        am.send_alert("Second")
        am.send_alert("Third")
        history = am.get_alert_history(limit=3)
        assert history[0]["message"] == "Third"
        assert history[2]["message"] == "First"

    def test_get_alert_history_limited(self):
        """History should respect the limit parameter."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        for i in range(20):
            am.send_alert(f"Alert {i}")
        history = am.get_alert_history(limit=5)
        assert len(history) == 5


class TestAlertSummary:
    """Verify alert summary calculation."""

    def test_alert_summary(self):
        """Summary should count alerts by level."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("A", level="INFO")
        am.send_alert("B", level="INFO")
        am.send_alert("C", level="WARNING")
        am.send_alert("D", level="CRITICAL")
        summary = am.get_alert_summary()
        assert summary["total"] == 4
        assert summary["info"] == 2
        assert summary["warning"] == 1
        assert summary["critical"] == 1

    def test_alert_summary_empty(self):
        """Summary with no alerts should be all zeros."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        summary = am.get_alert_summary()
        assert summary["total"] == 0

    def test_clear_history(self):
        """clear_history should remove all alerts."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("A")
        am.send_alert("B")
        count = am.clear_history()
        assert count == 2
        assert len(am.alert_history) == 0

    def test_print_alert_summary_no_error(self, capsys):
        """print_alert_summary should not raise."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("Test alert", level="INFO")
        am.print_alert_summary()
        captured = capsys.readouterr()
        assert "ALERT SUMMARY" in captured.out


class TestTelegramIntegration:
    """Verify Telegram delivery (mocked)."""

    @patch("dashboard.alerts.requests.post")
    def test_telegram_send_success(self, mock_post):
        """Should send Telegram message when credentials are configured."""
        from dashboard.alerts import AlertManager
        mock_post.return_value = MagicMock(status_code=200)

        am = AlertManager(telegram_token="test_token", telegram_chat_id="12345")
        result = am.send_alert("Test telegram message", level="INFO")

        assert result["telegram_sent"] is True
        mock_post.assert_called_once()

    @patch("dashboard.alerts.requests.post")
    def test_telegram_send_failure(self, mock_post):
        """Should handle Telegram API failure gracefully."""
        from dashboard.alerts import AlertManager
        mock_post.return_value = MagicMock(status_code=403, text="Forbidden")

        am = AlertManager(telegram_token="test_token", telegram_chat_id="12345")
        result = am.send_alert("Test message", level="INFO")

        assert result["telegram_sent"] is False

    @patch("dashboard.alerts.requests.post")
    def test_telegram_send_exception(self, mock_post):
        """Should handle network exceptions gracefully."""
        from dashboard.alerts import AlertManager
        import requests as req
        mock_post.side_effect = req.RequestException("Network error")

        am = AlertManager(telegram_token="test_token", telegram_chat_id="12345")
        result = am.send_alert("Test message", level="INFO")

        assert result["telegram_sent"] is False

    def test_telegram_not_sent_when_disabled(self):
        """Should not attempt Telegram when not configured."""
        from dashboard.alerts import AlertManager
        am = AlertManager(telegram_token="", telegram_chat_id="")
        result = am.send_alert("Test", level="INFO")
        assert result["telegram_sent"] is False


# =============================================================================
# Test Suite: Integration Tests
# =============================================================================

class TestDashboardAlertIntegration:
    """Integration tests combining dashboard with alerts."""

    def test_dashboard_with_alert_manager(self, capsys):
        """Dashboard should display alerts from alert manager."""
        from dashboard.app import Dashboard
        from dashboard.alerts import AlertManager

        am = AlertManager(telegram_token="", telegram_chat_id="")
        am.send_alert("Trade filled: AAPL", level="INFO")
        am.send_alert("Drawdown warning: 10%", level="WARNING")

        dash = Dashboard(
            broker=make_mock_broker(),
            alert_manager=am,
        )
        dash.print_dashboard()
        captured = capsys.readouterr()
        assert "AAPL" in captured.out
        assert "Drawdown" in captured.out


class TestDashboardChartsIntegration:
    """Integration tests combining dashboard with charts."""

    def test_charts_render_with_real_equity_data(self):
        """All chart functions should work with realistic data."""
        from dashboard.charts import (
            render_equity_curve,
            render_pnl_bars,
            render_win_loss_chart,
            render_drawdown_chart,
            render_sector_heatmap,
            render_sparkline,
            render_trade_table,
        )

        equity_data = make_equity_data(n_points=60)
        pnl_data = {"Jan": 300, "Feb": -100, "Mar": 500}
        stats = {"total_trades": 30, "wins": 18, "losses": 12,
                 "win_rate": 60.0, "avg_win": 200, "avg_loss": -100}
        sector_data = {"Technology": 2, "Energy": 1}
        trades = [
            {"symbol": "AAPL", "entry_price": 150, "exit_price": 160,
             "shares": 10, "pnl": 100, "exit_reason": "tp2"},
        ]
        values = [e["equity"] for e in equity_data]

        # All should return strings without errors
        assert isinstance(render_equity_curve(equity_data), str)
        assert isinstance(render_pnl_bars(pnl_data), str)
        assert isinstance(render_win_loss_chart(stats), str)
        assert isinstance(render_drawdown_chart(equity_data), str)
        assert isinstance(render_sector_heatmap(sector_data), str)
        assert isinstance(render_sparkline(values), str)
        assert isinstance(render_trade_table(trades), str)


class TestModule7Settings:
    """Verify Module 7 settings are present in config."""

    def test_dashboard_settings_exist(self):
        """All dashboard settings should be defined and valid."""
        from config.settings import (
            ALERT_HISTORY_MAX,
            DASHBOARD_RECENT_TRADES,
            CHART_WIDTH,
            CHART_HEIGHT,
        )
        assert ALERT_HISTORY_MAX > 0
        assert DASHBOARD_RECENT_TRADES > 0
        assert CHART_WIDTH > 0
        assert CHART_HEIGHT > 0

    def test_telegram_settings_exist(self):
        """Telegram settings should be present (may be empty)."""
        from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
        assert isinstance(TELEGRAM_BOT_TOKEN, str)
        assert isinstance(TELEGRAM_CHAT_ID, str)
