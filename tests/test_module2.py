# =============================================================================
# tests/test_module2.py — Unit Tests for Module 2 (Signals, Risk, Journal)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 2 components:
#     - core/signals.py:          Signal generation, strength classification
#     - risk/position_sizer.py:   Position size calculations, safety caps
#     - risk/portfolio_risk.py:   Portfolio risk rules, daily loss limits
#     - learning/journal.py:      Trade logging, performance statistics
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module2.py -v
#
# =============================================================================

import os
import sys

import pandas as pd
import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Test Suite: core/signals.py
# =============================================================================

class TestSignals:
    """Verify trade signal generation and filtering."""

    def _make_scan_result(self, symbol="AAPL", score=8.0, price=150.0, atr=3.0):
        """Helper to create a mock scanner result dict."""
        return {
            "symbol": symbol,
            "score": score,
            "current_price": price,
            "atr_value": atr,
            "rsi_value": 35.0,
            "macd_signal": "Bullish",
            "volume_signal": "Surge",
            "reason": "Strong buy: test signal",
            "indicators": {},
        }

    def test_generate_trade_setup_basic(self):
        """generate_trade_setup should return a valid setup with correct levels."""
        from core.signals import generate_trade_setup

        result = self._make_scan_result(price=100.0, atr=2.0)
        setup = generate_trade_setup(result)

        assert setup is not None
        assert setup["symbol"] == "AAPL"
        assert setup["entry_price"] == 100.0
        # Stop loss = entry - (ATR × 2.0) = 100 - 4 = 96
        assert setup["stop_loss"] == 96.0
        # Risk per share = 4.0
        assert setup["risk_per_share"] == 4.0
        # TP1 = entry + (2 × risk) = 100 + 8 = 108
        assert setup["take_profit_1"] == 108.0
        # TP2 = entry + (3 × risk) = 100 + 12 = 112
        assert setup["take_profit_2"] == 112.0
        # R:R = (TP1 - entry) / risk = 8 / 4 = 2.0
        assert setup["rr_ratio"] == 2.0

    def test_generate_trade_setup_no_price(self):
        """generate_trade_setup should return None for missing/zero price."""
        from core.signals import generate_trade_setup

        result = self._make_scan_result(price=0.0)
        assert generate_trade_setup(result) is None

        result2 = self._make_scan_result()
        result2["current_price"] = None
        assert generate_trade_setup(result2) is None

    def test_generate_trade_setup_no_atr(self):
        """generate_trade_setup should return None for missing/zero ATR."""
        from core.signals import generate_trade_setup

        result = self._make_scan_result(atr=0.0)
        assert generate_trade_setup(result) is None

        result2 = self._make_scan_result()
        result2["atr_value"] = None
        assert generate_trade_setup(result2) is None

    def test_generate_trade_setup_atr_too_large(self):
        """generate_trade_setup should return None if risk >= entry price."""
        from core.signals import generate_trade_setup

        # ATR=60 × multiplier(2) = 120 risk, entry=100 → risk > entry
        result = self._make_scan_result(price=100.0, atr=60.0)
        assert generate_trade_setup(result) is None

    def test_classify_signal_strength(self):
        """classify_signal_strength should return correct labels."""
        from core.signals import classify_signal_strength

        assert classify_signal_strength(8.0, 2.5) == "STRONG"
        assert classify_signal_strength(7.0, 2.0) == "STRONG"
        assert classify_signal_strength(6.0, 1.8) == "MEDIUM"
        assert classify_signal_strength(5.0, 1.5) == "MEDIUM"
        assert classify_signal_strength(3.0, 1.0) == "WEAK"
        assert classify_signal_strength(4.0, 1.4) == "WEAK"

    def test_generate_all_signals_filters_by_rr(self):
        """generate_all_signals should exclude signals below min R:R."""
        from core.signals import generate_all_signals

        # All our setups have R:R of 2.0 (formula: TP1 distance / risk)
        results = [
            self._make_scan_result("AAPL", score=8.0, price=100.0, atr=2.0),
            self._make_scan_result("XOM", score=7.0, price=50.0, atr=1.0),
        ]

        # With min_rr=2.0, all should pass (R:R is exactly 2.0)
        signals = generate_all_signals(results, min_rr=2.0)
        assert len(signals) == 2

        # With min_rr=3.0, none should pass
        signals = generate_all_signals(results, min_rr=3.0)
        assert len(signals) == 0

    def test_generate_all_signals_sorted_by_strength(self):
        """Signals should be sorted: STRONG first, then MEDIUM, then WEAK."""
        from core.signals import generate_all_signals

        results = [
            self._make_scan_result("WEAK_STOCK", score=3.0, price=100.0, atr=2.0),
            self._make_scan_result("STRONG_STOCK", score=8.0, price=100.0, atr=2.0),
            self._make_scan_result("MEDIUM_STOCK", score=5.5, price=100.0, atr=2.0),
        ]

        signals = generate_all_signals(results, min_rr=1.0)
        assert len(signals) == 3
        assert signals[0]["symbol"] == "STRONG_STOCK"
        assert signals[1]["symbol"] == "MEDIUM_STOCK"
        assert signals[2]["symbol"] == "WEAK_STOCK"

    def test_save_signals(self, tmp_path):
        """save_signals should create a CSV with correct columns."""
        from core.signals import save_signals

        signals = [
            {
                "symbol": "AAPL", "entry_price": 150.0, "stop_loss": 146.0,
                "take_profit_1": 158.0, "take_profit_2": 162.0,
                "risk_per_share": 4.0, "rr_ratio": 2.0,
                "signal_strength": "STRONG", "scanner_score": 8.0,
                "reason": "Strong buy: test",
            },
        ]

        path = save_signals(signals, output_dir=str(tmp_path))
        assert os.path.isfile(path)

        df = pd.read_csv(path)
        assert "symbol" in df.columns
        assert "entry_price" in df.columns
        assert "rr_ratio" in df.columns
        assert len(df) == 1

    def test_print_signals_report_no_error(self, capsys):
        """print_signals_report should execute without raising errors."""
        from core.signals import print_signals_report

        signals = [
            {
                "symbol": "AAPL", "entry_price": 150.0, "stop_loss": 146.0,
                "take_profit_1": 158.0, "take_profit_2": 162.0,
                "risk_per_share": 4.0, "rr_ratio": 2.0,
                "signal_strength": "STRONG", "scanner_score": 8.0,
                "reason": "Strong buy: test",
            },
        ]
        print_signals_report(signals)
        captured = capsys.readouterr()
        assert "AAPL" in captured.out
        assert "TRADE SIGNALS" in captured.out

    def test_print_signals_report_empty(self, capsys):
        """print_signals_report should handle empty signals gracefully."""
        from core.signals import print_signals_report

        print_signals_report([])
        captured = capsys.readouterr()
        assert "No actionable signals" in captured.out


# =============================================================================
# Test Suite: risk/position_sizer.py
# =============================================================================

class TestPositionSizer:
    """Verify position size calculations and safety caps."""

    def test_basic_position_sizing(self):
        """Standard position sizing with 2% risk."""
        from risk.position_sizer import calculate_position_size

        result = calculate_position_size(
            account_balance=10000,
            entry_price=50.0,
            stop_loss_price=48.0,
        )

        assert result["valid"] is True
        # Max risk = 10000 × 0.02 = $200
        # Risk per share = 50 - 48 = $2
        # Raw shares = floor(200 / 2) = 100
        # But: 100 × $50 = $5,000 > 35% of $10,000 ($3,500)
        # Capped to: floor(3500 / 50) = 70 shares
        assert result["shares_to_buy"] == 70
        assert result["risk_per_share"] == 2.0
        assert result["capped"] is True
        assert result["total_position_value"] == 3500.0

    def test_position_size_cap(self):
        """Position should be capped at 35% of account."""
        from risk.position_sizer import calculate_position_size

        # With tight stop ($0.10), many shares are allowed by 2% rule,
        # but total value would exceed 35% cap
        result = calculate_position_size(
            account_balance=10000,
            entry_price=100.0,
            stop_loss_price=99.90,
        )

        assert result["valid"] is True
        assert result["capped"] is True
        # Max position = 10000 × 0.35 = $3500
        # Max shares at $100 = floor(3500 / 100) = 35
        assert result["shares_to_buy"] == 35
        assert result["total_position_value"] == 3500.0

    def test_fractional_shares(self):
        """allow_fractional=True should not floor shares."""
        from risk.position_sizer import calculate_position_size

        result = calculate_position_size(
            account_balance=1000,
            entry_price=50.0,
            stop_loss_price=47.0,
            allow_fractional=True,
        )

        assert result["valid"] is True
        # Max risk = 1000 × 0.02 = $20
        # Risk per share = $3
        # Shares = 20 / 3 = 6.6667
        assert result["shares_to_buy"] == 6.6667

    def test_invalid_negative_balance(self):
        """Should return valid=False for negative account balance."""
        from risk.position_sizer import calculate_position_size

        result = calculate_position_size(
            account_balance=-5000,
            entry_price=50.0,
            stop_loss_price=48.0,
        )
        assert result["valid"] is False
        assert result["shares_to_buy"] == 0

    def test_invalid_stop_above_entry(self):
        """Should return valid=False if stop loss >= entry price."""
        from risk.position_sizer import calculate_position_size

        result = calculate_position_size(
            account_balance=10000,
            entry_price=50.0,
            stop_loss_price=52.0,
        )
        assert result["valid"] is False

    def test_invalid_zero_price(self):
        """Should return valid=False for zero entry price."""
        from risk.position_sizer import calculate_position_size

        result = calculate_position_size(
            account_balance=10000,
            entry_price=0.0,
            stop_loss_price=0.0,
        )
        assert result["valid"] is False

    def test_risk_budget_too_small(self):
        """Should return valid=False when can't buy even 1 share."""
        from risk.position_sizer import calculate_position_size

        # Account=100, risk=2% → $2 max risk
        # Risk per share = 100 - 95 = $5 → can't afford even 1 share
        result = calculate_position_size(
            account_balance=100,
            entry_price=100.0,
            stop_loss_price=95.0,
        )
        assert result["valid"] is False

    def test_custom_risk_percent(self):
        """Should respect custom risk_percent parameter."""
        from risk.position_sizer import calculate_position_size

        result = calculate_position_size(
            account_balance=10000,
            entry_price=50.0,
            stop_loss_price=48.0,
            risk_percent=0.01,  # 1% instead of default 2%
        )

        assert result["valid"] is True
        # Max risk = 10000 × 0.01 = $100
        # Shares = floor(100 / 2) = 50
        assert result["shares_to_buy"] == 50
        assert result["risk_amount"] == 100.0


# =============================================================================
# Test Suite: risk/portfolio_risk.py
# =============================================================================

class TestPortfolioRisk:
    """Verify portfolio-level risk management rules."""

    def test_can_open_position_initially(self):
        """Should allow opening positions when under the limit."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000)
        assert manager.can_open_position() is True

    def test_max_positions_enforced(self):
        """Should block new positions when at the maximum."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000, max_positions=2)
        assert manager.add_position("AAPL", 50, 150.0) is True
        assert manager.add_position("XOM", 30, 100.0) is True
        # Now at max (2) — should block
        assert manager.can_open_position() is False
        assert manager.add_position("MSFT", 20, 200.0) is False

    def test_remove_position_allows_new(self):
        """Removing a position should allow opening another."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000, max_positions=1)
        manager.add_position("AAPL", 50, 150.0)
        assert manager.can_open_position() is False

        manager.remove_position("AAPL")
        assert manager.can_open_position() is True

    def test_remove_nonexistent_position(self):
        """Removing a non-existent position should return None."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000)
        assert manager.remove_position("FAKE") is None

    def test_no_duplicate_positions(self):
        """Should not allow adding a duplicate symbol."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000)
        assert manager.add_position("AAPL", 50, 150.0) is True
        assert manager.add_position("AAPL", 30, 155.0) is False

    def test_daily_loss_limit_halts_trading(self):
        """Trading should halt when daily loss exceeds the limit."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(
            account_balance=10000, daily_loss_limit=0.05,
        )

        # Lose $500 (exactly 5% of $10,000)
        manager.update_daily_pnl(-500.0)
        assert manager.trading_halted is True
        assert manager.can_open_position() is False

    def test_daily_loss_limit_not_triggered(self):
        """Trading should continue when loss is within limits."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(
            account_balance=10000, daily_loss_limit=0.05,
        )

        # Lose $400 (4% — within limit)
        manager.update_daily_pnl(-400.0)
        assert manager.trading_halted is False
        assert manager.can_open_position() is True

    def test_reset_daily_state(self):
        """reset_daily_state should clear daily P&L and re-enable trading."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000)
        manager.update_daily_pnl(-600.0)
        assert manager.trading_halted is True

        manager.reset_daily_state()
        assert manager.trading_halted is False
        assert manager.daily_pnl == 0.0
        assert manager.can_open_position() is True

    def test_portfolio_summary(self):
        """get_portfolio_summary should return correct aggregated data."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000)
        manager.add_position("AAPL", 10, 150.0)

        summary = manager.get_portfolio_summary()
        assert summary["account_balance"] == 10000
        assert summary["open_positions"] == 1
        assert summary["total_position_value"] == 1500.0
        assert summary["trading_halted"] is False

    def test_violations_log(self):
        """Violations should be recorded in the log."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000, max_positions=1)
        manager.add_position("AAPL", 50, 150.0)
        manager.add_position("XOM", 30, 100.0)  # Should fail and log violation

        assert len(manager.violations_log) >= 1
        assert manager.violations_log[0]["rule"] == "MAX_POSITIONS"

    def test_save_violations_log(self, tmp_path):
        """save_violations_log should write to a file."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000, max_positions=1)
        manager.add_position("AAPL", 50, 150.0)
        manager.add_position("XOM", 30, 100.0)  # Triggers violation

        path = manager.save_violations_log(output_dir=str(tmp_path))
        assert path is not None
        assert os.path.isfile(path)

        with open(path, "r") as f:
            content = f.read()
            assert "MAX_POSITIONS" in content

    def test_save_violations_log_empty(self, tmp_path):
        """save_violations_log should return None when no violations."""
        from risk.portfolio_risk import PortfolioRiskManager

        manager = PortfolioRiskManager(account_balance=10000)
        path = manager.save_violations_log(output_dir=str(tmp_path))
        assert path is None


# =============================================================================
# Test Suite: learning/journal.py
# =============================================================================

class TestJournal:
    """Verify trade journal logging and performance statistics."""

    def test_journal_creates_file(self, tmp_path):
        """TradeJournal should create the CSV file on init."""
        from learning.journal import TradeJournal

        journal_file = str(tmp_path / "test_trades.csv")
        journal = TradeJournal(journal_path=journal_file)
        assert os.path.isfile(journal_file)

    def test_log_winning_trade(self, tmp_path):
        """log_trade should correctly log a winning LONG trade."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        record = journal.log_trade(
            symbol="AAPL", direction="LONG",
            entry_price=150.0, exit_price=155.0, shares=50,
            stop_loss=146.0, take_profit_1=158.0, exit_reason="tp1",
        )

        assert record["win_loss"] == "WIN"
        assert record["profit_loss_dollar"] == 250.0  # (155-150) × 50
        assert record["profit_loss_percent"] > 0

    def test_log_losing_trade(self, tmp_path):
        """log_trade should correctly log a losing LONG trade."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        record = journal.log_trade(
            symbol="XOM", direction="LONG",
            entry_price=100.0, exit_price=96.0, shares=30,
            stop_loss=96.0, exit_reason="stop",
        )

        assert record["win_loss"] == "LOSS"
        assert record["profit_loss_dollar"] == -120.0  # (96-100) × 30
        assert record["profit_loss_percent"] < 0

    def test_log_short_trade(self, tmp_path):
        """log_trade should handle SHORT direction correctly."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        record = journal.log_trade(
            symbol="TSLA", direction="SHORT",
            entry_price=200.0, exit_price=190.0, shares=10,
            exit_reason="tp1",
        )

        # SHORT: profit = (entry - exit) × shares = (200-190) × 10 = $100
        assert record["win_loss"] == "WIN"
        assert record["profit_loss_dollar"] == 100.0

    def test_get_all_trades(self, tmp_path):
        """get_all_trades should return all logged trades as a DataFrame."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        journal.log_trade("AAPL", "LONG", 150.0, 155.0, 50, exit_reason="tp1")
        journal.log_trade("XOM", "LONG", 100.0, 96.0, 30, exit_reason="stop")

        df = journal.get_all_trades()
        assert len(df) == 2
        assert df.iloc[0]["symbol"] == "AAPL"
        assert df.iloc[1]["symbol"] == "XOM"

    def test_performance_stats_with_trades(self, tmp_path):
        """get_performance_stats should calculate correct metrics."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        journal.log_trade("AAPL", "LONG", 150.0, 160.0, 10, exit_reason="tp1")  # Win $100
        journal.log_trade("XOM", "LONG", 100.0, 95.0, 10, exit_reason="stop")   # Loss -$50
        journal.log_trade("MSFT", "LONG", 300.0, 310.0, 5, exit_reason="tp2")   # Win $50

        stats = journal.get_performance_stats()
        assert stats["total_trades"] == 3
        assert stats["wins"] == 2
        assert stats["losses"] == 1
        assert stats["win_rate"] == pytest.approx(66.67, abs=0.01)
        assert stats["total_pnl"] == 100.0  # 100 + (-50) + 50
        assert stats["best_trade"] == 100.0
        assert stats["worst_trade"] == -50.0
        assert stats["profit_factor"] == 3.0  # 150 / 50

    def test_performance_stats_empty(self, tmp_path):
        """get_performance_stats should handle empty journal gracefully."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        stats = journal.get_performance_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_print_performance_report_no_error(self, tmp_path, capsys):
        """print_performance_report should execute without errors."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        journal.log_trade("AAPL", "LONG", 150.0, 160.0, 10, exit_reason="tp1")

        journal.print_performance_report()
        captured = capsys.readouterr()
        assert "Performance Report" in captured.out
        assert "Win Rate" in captured.out

    def test_print_performance_report_empty(self, tmp_path, capsys):
        """print_performance_report should handle empty journal gracefully."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        journal.print_performance_report()
        captured = capsys.readouterr()
        assert "No trades recorded" in captured.out

    def test_max_drawdown_calculation(self, tmp_path):
        """Max drawdown should measure the largest peak-to-trough decline."""
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        # Win $100, then lose $150, then win $50 → drawdown from 100 peak to -50
        journal.log_trade("A", "LONG", 100.0, 110.0, 10, exit_reason="tp1")  # +$100
        journal.log_trade("B", "LONG", 100.0, 85.0, 10, exit_reason="stop")  # -$150
        journal.log_trade("C", "LONG", 100.0, 105.0, 10, exit_reason="tp1")  # +$50

        stats = journal.get_performance_stats()
        # Cumulative P&L: [100, -50, 0]
        # Running max:    [100, 100, 100]
        # Drawdown:       [0, -150, -100]
        # Max drawdown = -150
        assert stats["max_drawdown"] == -150.0
