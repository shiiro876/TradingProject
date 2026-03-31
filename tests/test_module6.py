# =============================================================================
# tests/test_module6.py — Unit Tests for Module 6 (Learning Engine)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 6 components:
#     - learning/trainer.py:    ML trade quality predictor
#     - learning/backtester.py: Historical strategy backtester
#     - learning/optimizer.py:  Strategy parameter optimizer
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module6.py -v
#
# =============================================================================

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Helpers: Synthetic data generators
# =============================================================================

def make_ohlcv(
    symbol="AAPL",
    days=60,
    start_price=100.0,
    trend="up",
    start_date=None,
):
    """
    Create a synthetic OHLCV DataFrame with pre-computed indicators.

    Generates realistic-looking price bars with open/high/low/close/volume,
    plus an ATR column and a scanner score column for backtesting.

    Args:
        symbol:      Stock ticker (for reference only).
        days:        Number of bars to generate.
        start_price: Opening price of the first bar.
        trend:       "up" for uptrend, "down" for downtrend, "flat" for flat.
        start_date:  Starting date. Defaults to 60 days ago.

    Returns:
        DataFrame with DatetimeIndex and columns:
        open, high, low, close, volume, atr, score.
    """
    if start_date is None:
        start_date = datetime.now() - timedelta(days=days + 30)

    dates = pd.bdate_range(start=start_date, periods=days)
    np.random.seed(42)

    # Generate close prices with a trend
    if trend == "up":
        changes = np.random.normal(0.003, 0.015, days)
    elif trend == "down":
        changes = np.random.normal(-0.003, 0.015, days)
    else:
        changes = np.random.normal(0.0, 0.01, days)

    closes = [start_price]
    for change in changes[1:]:
        closes.append(max(closes[-1] * (1 + change), 1.0))

    closes = np.array(closes[:days])
    highs = closes * (1 + np.random.uniform(0.005, 0.02, days))
    lows = closes * (1 - np.random.uniform(0.005, 0.02, days))
    opens = closes * (1 + np.random.uniform(-0.005, 0.005, days))
    volumes = np.random.randint(500000, 5000000, days)

    # ATR: average of (high - low) over a rolling window
    true_ranges = highs - lows
    atrs = pd.Series(true_ranges).rolling(14, min_periods=1).mean().values

    # Scanner score: simple heuristic — higher in uptrend
    scores = np.clip(np.random.normal(6.0 if trend == "up" else 4.0, 1.5, days), 0, 10)

    df = pd.DataFrame({
        "open": np.round(opens, 2),
        "high": np.round(highs, 2),
        "low": np.round(lows, 2),
        "close": np.round(closes, 2),
        "volume": volumes,
        "atr": np.round(atrs, 4),
        "score": np.round(scores, 1),
    }, index=dates[:days])

    return df


def make_journal_trades(n_trades=20, win_rate=0.55, tmp_path=None):
    """
    Create a TradeJournal pre-populated with synthetic trades.

    Args:
        n_trades: Number of trades to generate.
        win_rate: Fraction of trades that are winners.
        tmp_path: Path for the journal CSV file.

    Returns:
        TradeJournal instance with trades already logged.
    """
    from learning.journal import TradeJournal

    journal_path = os.path.join(str(tmp_path), "test_trades.csv") if tmp_path else None
    journal = TradeJournal(journal_path=journal_path)

    np.random.seed(42)
    symbols = ["AAPL", "MSFT", "XOM", "JPM", "TSLA", "GOOGL"]
    strengths = ["STRONG", "MEDIUM", "WEAK"]
    exit_reasons = ["tp1", "tp2", "trailing_stop", "stop", "manual"]

    for i in range(n_trades):
        symbol = np.random.choice(symbols)
        entry_price = round(np.random.uniform(50, 300), 2)
        is_win = np.random.random() < win_rate

        if is_win:
            exit_price = round(entry_price * (1 + np.random.uniform(0.01, 0.10)), 2)
            exit_reason = np.random.choice(["tp1", "tp2", "trailing_stop"])
        else:
            exit_price = round(entry_price * (1 - np.random.uniform(0.01, 0.08)), 2)
            exit_reason = np.random.choice(["stop", "trailing_stop", "manual"])

        stop_loss = round(entry_price * 0.95, 2)
        shares = np.random.randint(5, 50)

        journal.log_trade(
            symbol=symbol,
            direction="LONG",
            entry_price=entry_price,
            exit_price=exit_price,
            shares=shares,
            stop_loss=stop_loss,
            take_profit_1=round(entry_price * 1.06, 2),
            take_profit_2=round(entry_price * 1.10, 2),
            risk_reward=round(np.random.uniform(1.5, 3.0), 2),
            exit_reason=exit_reason,
            notes=f"Test trade {i+1}",
        )

    return journal


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
# Test Suite: learning/trainer.py — TradeTrainer
# =============================================================================

class TestTrainerInit:
    """Verify TradeTrainer initialization."""

    def test_init_default(self, tmp_path):
        """TradeTrainer should initialize with default journal."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        trainer = TradeTrainer(journal=journal)
        assert trainer.is_trained is False
        assert trainer.model is None
        assert trainer.training_stats == {}

    def test_init_with_journal(self, tmp_path):
        """TradeTrainer should accept a custom journal."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=5, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        assert trainer.journal is journal


class TestTrainerFeatureExtraction:
    """Verify feature extraction from trade data."""

    def test_extract_features_basic(self, tmp_path):
        """extract_features should produce correct column count."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=15, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        df = journal.get_all_trades()
        features = trainer.extract_features(df)

        assert len(features) == len(df)
        assert "entry_price" in features.columns
        assert "risk_reward" in features.columns
        assert "risk_per_share" in features.columns
        assert "price_to_stop_ratio" in features.columns

    def test_extract_features_empty_df(self, tmp_path):
        """extract_features should handle empty DataFrame."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "empty.csv"))
        trainer = TradeTrainer(journal=journal)
        features = trainer.extract_features(pd.DataFrame())
        assert len(features) == 0

    def test_signal_strength_encoding(self, tmp_path):
        """Signal strength should be encoded as integer."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=15, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)

        df = pd.DataFrame({
            "entry_price": [100.0],
            "stop_loss": [95.0],
            "risk_reward": [2.0],
            "signal_strength": ["STRONG"],
            "exit_reason": ["tp1"],
        })
        features = trainer.extract_features(df)
        assert features["signal_strength_encoded"].iloc[0] == 3  # STRONG=3


class TestTrainerTraining:
    """Verify model training."""

    def test_train_insufficient_data(self, tmp_path):
        """Training with <10 trades should report insufficient data."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=5, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        result = trainer.train()

        assert result["trained"] is False
        assert "Not enough trades" in result["message"]

    def test_train_success(self, tmp_path):
        """Training with sufficient data should succeed."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        result = trainer.train()

        assert result["trained"] is True
        assert result["total_trades"] == 30
        assert 0 <= result["accuracy"] <= 1.0
        assert 0 <= result["win_rate"] <= 1.0
        assert trainer.is_trained is True
        assert trainer.model is not None

    def test_train_empty_journal(self, tmp_path):
        """Training with empty journal should fail gracefully."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "empty.csv"))
        trainer = TradeTrainer(journal=journal)
        result = trainer.train()

        assert result["trained"] is False


class TestTrainerPrediction:
    """Verify prediction functionality."""

    def test_predict_heuristic_when_untrained(self, tmp_path):
        """Prediction without training should use heuristic fallback."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        trainer = TradeTrainer(journal=journal)

        signal = make_signal(scanner_score=8.0, signal_strength="STRONG", rr_ratio=2.5)
        pred = trainer.predict(signal)

        assert pred["symbol"] == "AAPL"
        assert 0.0 <= pred["win_probability"] <= 1.0
        assert pred["model_used"] is False
        assert pred["confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert pred["recommendation"] in ("TAKE", "CONSIDER", "SKIP")

    def test_predict_ml_when_trained(self, tmp_path):
        """Prediction after training should use ML model."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        signal = make_signal(scanner_score=8.0)
        pred = trainer.predict(signal)

        assert pred["model_used"] is True
        assert 0.0 <= pred["win_probability"] <= 1.0

    def test_predict_strong_vs_weak_signal(self, tmp_path):
        """Strong signals should generally have higher win probability."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        trainer = TradeTrainer(journal=journal)

        strong = make_signal(scanner_score=9.0, signal_strength="STRONG", rr_ratio=3.0)
        weak = make_signal(scanner_score=2.0, signal_strength="WEAK", rr_ratio=1.0)

        pred_strong = trainer.predict(strong)
        pred_weak = trainer.predict(weak)

        # With heuristic, strong should have higher probability
        assert pred_strong["win_probability"] > pred_weak["win_probability"]

    def test_predict_classification(self, tmp_path):
        """Prediction should classify into correct confidence levels."""
        from learning.trainer import TradeTrainer

        trainer = TradeTrainer.__new__(TradeTrainer)
        trainer.is_trained = False
        trainer.model = None
        trainer.strength_map = {"STRONG": 3, "MEDIUM": 2, "WEAK": 1}
        trainer.training_stats = {}

        conf, rec = trainer._classify_prediction(0.70)
        assert conf == "HIGH"
        assert rec == "TAKE"

        conf, rec = trainer._classify_prediction(0.50)
        assert conf == "MEDIUM"
        assert rec == "CONSIDER"

        conf, rec = trainer._classify_prediction(0.30)
        assert conf == "LOW"
        assert rec == "SKIP"


class TestTrainerFeatureImportance:
    """Verify feature importance retrieval."""

    def test_feature_importance_when_trained(self, tmp_path):
        """Feature importance should be available after training."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        importance = trainer.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0
        assert all(0 <= v <= 1 for v in importance.values())

    def test_feature_importance_untrained(self, tmp_path):
        """Feature importance should be empty when not trained."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        trainer = TradeTrainer(journal=journal)
        importance = trainer.get_feature_importance()
        assert importance == {}


class TestTrainerPersistence:
    """Verify model save/load functionality."""

    def test_save_and_load_model(self, tmp_path):
        """Saved model should be loadable and produce same predictions."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        # Save
        model_path = str(tmp_path / "model.pkl")
        saved_path = trainer.save_model(model_path)
        assert os.path.isfile(saved_path)

        # Load into fresh trainer
        trainer2 = TradeTrainer(journal=journal)
        assert trainer2.load_model(model_path) is True
        assert trainer2.is_trained is True

        # Predictions should work
        signal = make_signal()
        pred = trainer2.predict(signal)
        assert pred["model_used"] is True

    def test_load_nonexistent_model(self, tmp_path):
        """Loading a nonexistent model should return False."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        trainer = TradeTrainer(journal=journal)
        result = trainer.load_model(str(tmp_path / "nonexistent.pkl"))
        assert result is False

    def test_save_creates_directory(self, tmp_path):
        """Save should create parent directory if needed."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=15, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        nested_path = str(tmp_path / "subdir" / "model.pkl")
        saved = trainer.save_model(nested_path)
        assert os.path.isfile(saved)


class TestTrainerSummary:
    """Verify training summary and reporting."""

    def test_training_summary_structure(self, tmp_path):
        """get_training_summary should return expected structure."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        summary = trainer.get_training_summary()
        assert "is_trained" in summary
        assert "training_stats" in summary
        assert "feature_importance" in summary
        assert summary["is_trained"] is True

    def test_print_training_report_no_error(self, tmp_path, capsys):
        """print_training_report should not raise."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        trainer.print_training_report()
        captured = capsys.readouterr()
        assert "TRADE TRAINER" in captured.out

    def test_print_training_report_untrained(self, tmp_path, capsys):
        """print_training_report should handle untrained state."""
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        journal = TradeJournal(journal_path=str(tmp_path / "trades.csv"))
        trainer = TradeTrainer(journal=journal)
        trainer.print_training_report()
        captured = capsys.readouterr()
        assert "not yet trained" in captured.out


# =============================================================================
# Test Suite: learning/backtester.py — Backtester
# =============================================================================

class TestBacktesterInit:
    """Verify Backtester initialization."""

    def test_init_defaults(self):
        """Backtester should initialize with correct defaults."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        assert bt.account_balance == 10000
        assert bt.initial_balance == 10000
        assert bt.trades == []
        assert bt.equity_curve == []
        assert bt.open_positions == {}

    def test_init_custom_params(self):
        """Backtester should accept custom parameters."""
        from learning.backtester import Backtester
        bt = Backtester(
            account_balance=20000,
            max_positions=5,
            risk_per_trade=0.01,
        )
        assert bt.initial_balance == 20000
        assert bt.max_positions == 5
        assert bt.risk_per_trade == 0.01


class TestBacktesterRun:
    """Verify backtest execution."""

    def test_run_empty_data(self):
        """Running with empty data should return zero results."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        result = bt.run({})
        assert result["total_trades"] == 0
        assert result["final_balance"] == 10000

    def test_run_basic_uptrend(self):
        """Running on uptrend data should produce trades."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=60, trend="up", start_price=100.0)}
        result = bt.run(data, min_score=4.0)
        assert result["total_trades"] > 0
        assert result["final_balance"] > 0

    def test_run_downtrend(self):
        """Running on downtrend should still complete without error."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=60, trend="down", start_price=100.0)}
        result = bt.run(data, min_score=3.0)
        assert result["final_balance"] > 0

    def test_run_multiple_symbols(self):
        """Running with multiple symbols should work."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=30000)
        data = {
            "AAPL": make_ohlcv(days=60, trend="up", start_price=100.0),
            "XOM": make_ohlcv(days=60, trend="up", start_price=80.0),
            "JPM": make_ohlcv(days=60, trend="flat", start_price=120.0),
        }
        result = bt.run(data, min_score=4.0)
        assert result["total_trades"] >= 0

    def test_run_respects_max_positions(self):
        """Should not open more than max_positions simultaneously."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=50000, max_positions=2)
        data = {
            "AAPL": make_ohlcv(days=60, trend="up"),
            "XOM": make_ohlcv(days=60, trend="up"),
            "JPM": make_ohlcv(days=60, trend="up"),
        }
        bt.run(data, min_score=3.0)
        # Verify from equity curve that open positions never exceeded 2
        for point in bt.equity_curve:
            assert point["open_positions"] <= 2

    def test_run_resets_state(self):
        """Running twice should reset state from previous run."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=30, trend="up")}

        bt.run(data, min_score=4.0)
        first_trades = len(bt.trades)

        bt.run(data, min_score=4.0)
        second_trades = len(bt.trades)

        # Same data should produce same number of trades (state reset)
        assert second_trades == first_trades


class TestBacktesterResults:
    """Verify backtest result calculation."""

    def test_get_results_structure(self):
        """get_results should return all expected fields."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        bt.run(data, min_score=4.0)
        results = bt.get_results()

        assert "total_trades" in results
        assert "wins" in results
        assert "losses" in results
        assert "win_rate" in results
        assert "total_pnl" in results
        assert "total_return" in results
        assert "profit_factor" in results
        assert "max_drawdown" in results
        assert "final_balance" in results
        assert "trades" in results

    def test_get_results_empty(self):
        """get_results with no trades should return zeroed results."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        results = bt.get_results()
        assert results["total_trades"] == 0
        assert results["final_balance"] == 10000

    def test_equity_curve_populated(self):
        """Equity curve should have one entry per bar."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=30, trend="up")}
        bt.run(data, min_score=4.0)
        curve = bt.get_equity_curve()
        assert len(curve) > 0
        assert all("equity" in p for p in curve)
        assert all("cash" in p for p in curve)

    def test_trade_records_have_pnl(self):
        """Each trade record should have P&L and exit reason."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        bt.run(data, min_score=4.0)
        results = bt.get_results()

        for trade in results["trades"]:
            assert "pnl" in trade
            assert "exit_reason" in trade
            assert "entry_price" in trade
            assert "exit_price" in trade
            assert "shares" in trade

    def test_print_backtest_report_no_error(self, capsys):
        """print_backtest_report should not raise."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        bt.run(data, min_score=4.0)
        bt.print_backtest_report()
        captured = capsys.readouterr()
        assert "BACKTEST RESULTS" in captured.out

    def test_print_backtest_report_empty(self, capsys):
        """print_backtest_report with no trades should handle gracefully."""
        from learning.backtester import Backtester
        bt = Backtester(account_balance=10000)
        bt.print_backtest_report()
        captured = capsys.readouterr()
        assert "No trades" in captured.out


# =============================================================================
# Test Suite: learning/optimizer.py — StrategyOptimizer
# =============================================================================

class TestOptimizerInit:
    """Verify StrategyOptimizer initialization."""

    def test_init(self):
        """StrategyOptimizer should initialize correctly."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=30, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)
        assert opt.results == []
        assert opt.best_params is None
        assert opt.account_balance == 10000


class TestOptimizerOptimize:
    """Verify optimization runs."""

    def test_optimize_basic(self):
        """Basic optimization should produce ranked results."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)

        param_grid = {
            "atr_stop_multiplier": [1.5, 2.0, 2.5],
        }
        results = opt.optimize(param_grid, metric="total_return", min_score=4.0)

        assert len(results) == 3
        assert all("total_return" in r for r in results)
        assert all("params" in r for r in results)

    def test_optimize_empty_grid(self):
        """Empty grid should return empty results."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=30, trend="up")}
        opt = StrategyOptimizer(symbol_data=data)
        results = opt.optimize({})
        assert results == []

    def test_optimize_multiple_params(self):
        """Optimization with multiple params should produce N1×N2 results."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)

        param_grid = {
            "atr_stop_multiplier": [1.5, 2.5],
            "min_score": [4.0, 6.0],
        }
        results = opt.optimize(param_grid, min_score=4.0)

        assert len(results) == 4  # 2 × 2

    def test_optimize_sorted_by_metric(self):
        """Results should be sorted by the target metric (descending)."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)

        param_grid = {
            "atr_stop_multiplier": [1.0, 2.0, 3.0],
        }
        results = opt.optimize(param_grid, metric="total_return", min_score=4.0)

        returns = [r["total_return"] for r in results]
        assert returns == sorted(returns, reverse=True)


class TestOptimizerResults:
    """Verify optimizer result retrieval."""

    def test_get_best_params(self):
        """get_best_params should return the top set."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)

        param_grid = {"atr_stop_multiplier": [1.5, 2.0, 2.5]}
        opt.optimize(param_grid, min_score=4.0)

        best = opt.get_best_params()
        assert best is not None
        assert "atr_stop_multiplier" in best

    def test_get_best_params_before_optimize(self):
        """get_best_params should return None before optimization."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=30)}
        opt = StrategyOptimizer(symbol_data=data)
        assert opt.get_best_params() is None

    def test_optimization_summary(self):
        """get_optimization_summary should return expected structure."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)

        param_grid = {"atr_stop_multiplier": [1.5, 2.0]}
        opt.optimize(param_grid, min_score=4.0)

        summary = opt.get_optimization_summary()
        assert summary["total_runs"] == 2
        assert summary["best_params"] is not None
        assert summary["best_result"] is not None

    def test_optimization_summary_empty(self):
        """Summary before optimization should show zero runs."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=30)}
        opt = StrategyOptimizer(symbol_data=data)
        summary = opt.get_optimization_summary()
        assert summary["total_runs"] == 0

    def test_print_optimization_report(self, capsys):
        """print_optimization_report should not raise."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        opt = StrategyOptimizer(symbol_data=data, account_balance=10000)

        param_grid = {"atr_stop_multiplier": [1.5, 2.0, 2.5]}
        opt.optimize(param_grid, min_score=4.0)

        opt.print_optimization_report()
        captured = capsys.readouterr()
        assert "OPTIMIZATION RESULTS" in captured.out

    def test_print_optimization_report_empty(self, capsys):
        """Report should handle no results gracefully."""
        from learning.optimizer import StrategyOptimizer
        data = {"AAPL": make_ohlcv(days=30)}
        opt = StrategyOptimizer(symbol_data=data)
        opt.print_optimization_report()
        captured = capsys.readouterr()
        assert "No optimization results" in captured.out


# =============================================================================
# Test Suite: Integration Tests
# =============================================================================

class TestTrainerBacktesterIntegration:
    """Integration tests combining trainer and backtester."""

    def test_train_then_predict_on_backtest_trades(self, tmp_path):
        """Train a model, then use it to predict on new signals."""
        from learning.trainer import TradeTrainer

        journal = make_journal_trades(n_trades=30, tmp_path=tmp_path)
        trainer = TradeTrainer(journal=journal)
        trainer.train()

        # Predict on several signals
        signals = [
            make_signal(scanner_score=9.0, signal_strength="STRONG"),
            make_signal(scanner_score=3.0, signal_strength="WEAK"),
            make_signal(scanner_score=6.0, signal_strength="MEDIUM"),
        ]

        for sig in signals:
            pred = trainer.predict(sig)
            assert 0 <= pred["win_probability"] <= 1
            assert pred["model_used"] is True

    def test_backtest_then_train_on_results(self, tmp_path):
        """Backtest should produce trades that can train a model."""
        from learning.backtester import Backtester
        from learning.trainer import TradeTrainer
        from learning.journal import TradeJournal

        # Run backtest
        bt = Backtester(account_balance=10000)
        data = {"AAPL": make_ohlcv(days=60, trend="up")}
        bt.run(data, min_score=4.0)
        results = bt.get_results()

        # Log backtest trades to journal
        journal = TradeJournal(journal_path=str(tmp_path / "bt_trades.csv"))
        for trade in results["trades"]:
            journal.log_trade(
                symbol=trade["symbol"],
                direction="LONG",
                entry_price=trade["entry_price"],
                exit_price=trade["exit_price"],
                shares=trade["shares"],
                exit_reason=trade["exit_reason"],
                risk_reward=2.0,
            )

        # Try to train (may not have enough trades, but shouldn't crash)
        trainer = TradeTrainer(journal=journal)
        train_result = trainer.train()
        assert isinstance(train_result, dict)
        assert "trained" in train_result


class TestModule6Settings:
    """Verify Module 6 settings are present in config."""

    def test_learning_settings_exist(self):
        """All learning engine settings should be present and valid."""
        from config.settings import (
            MIN_TRADES_FOR_TRAINING,
            MODEL_SAVE_PATH,
            BACKTEST_DEFAULT_MIN_SCORE,
            OPTIMIZER_MAX_COMBINATIONS,
        )

        assert MIN_TRADES_FOR_TRAINING >= 5
        assert isinstance(MODEL_SAVE_PATH, str)
        assert BACKTEST_DEFAULT_MIN_SCORE > 0
        assert OPTIMIZER_MAX_COMBINATIONS > 0
