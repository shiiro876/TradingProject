# =============================================================================
# tests/test_module1.py — Unit Tests for Module 1 (Market Scanner)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 1 components:
#     - config/settings.py: Configuration values are correct and accessible
#     - core/utils.py:      Data fetching and watchlist loading work correctly
#     - core/indicators.py: All technical indicators compute without errors
#     - core/scanner.py:    Scoring, reasoning, and scan pipeline work end-to-end
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module1.py -v
#
#   Or run a specific test:
#     python -m pytest tests/test_module1.py::TestIndicators::test_rsi_calculation -v
#
# =============================================================================

import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Helper: Generate synthetic OHLCV data for testing
# =============================================================================

def make_ohlcv(rows: int = 250, trend: str = "up") -> pd.DataFrame:
    """
    Create a synthetic OHLCV DataFrame for testing indicators.

    Generates realistic-looking price data with controlled trends so that
    indicator calculations can be validated without network calls.

    Args:
        rows:  Number of data points (trading days) to generate.
        trend: "up" for an uptrend, "down" for a downtrend, "flat" for sideways.

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume] and a
        DatetimeIndex.
    """
    np.random.seed(42)  # Reproducible results across test runs
    dates = pd.date_range(end=pd.Timestamp.now(), periods=rows, freq="B")

    # Base price series with controlled trend
    if trend == "up":
        base = 100 + np.cumsum(np.random.normal(0.1, 1.0, rows))
    elif trend == "down":
        base = 200 + np.cumsum(np.random.normal(-0.1, 1.0, rows))
    else:
        base = 150 + np.cumsum(np.random.normal(0.0, 0.5, rows))

    # Ensure no negative prices
    base = np.maximum(base, 1.0)

    # Generate OHLCV from the base series
    close = base
    open_ = close + np.random.normal(0, 0.5, rows)
    high = np.maximum(open_, close) + np.abs(np.random.normal(0.5, 0.3, rows))
    low = np.minimum(open_, close) - np.abs(np.random.normal(0.5, 0.3, rows))
    volume = np.random.randint(1_000_000, 10_000_000, rows).astype(float)

    # Inject a volume spike near the end to test volume_surge detection
    volume[-1] = volume[-5:-1].mean() * 3

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


# =============================================================================
# Test Suite: config/settings.py
# =============================================================================

class TestSettings:
    """Verify that all configuration constants are accessible and valid."""

    def test_safety_parameters_exist(self):
        """All core safety parameters must be defined."""
        from config.settings import (
            PAPER_TRADING, MAX_RISK_PER_TRADE, MAX_POSITIONS,
            DAILY_LOSS_LIMIT, MIN_RR_RATIO, MAX_POSITION_SIZE,
        )
        assert PAPER_TRADING is True, "Paper trading should be True by default"
        assert 0 < MAX_RISK_PER_TRADE <= 0.05
        assert MAX_POSITIONS > 0
        assert 0 < DAILY_LOSS_LIMIT <= 0.10
        assert MIN_RR_RATIO >= 1.0
        assert 0 < MAX_POSITION_SIZE <= 1.0

    def test_scanner_settings_exist(self):
        """Scanner configuration must be defined."""
        from config.settings import SCANNER_TOP_N, SCANNER_DATA_PERIOD
        assert SCANNER_TOP_N > 0
        assert SCANNER_DATA_PERIOD in ("1mo", "3mo", "6mo", "1y", "2y")

    def test_indicator_parameters_exist(self):
        """All indicator parameter constants must be defined and positive."""
        from config.settings import (
            RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT,
            MACD_FAST, MACD_SLOW, MACD_SIGNAL,
            MA_SHORT, MA_LONG,
            BB_PERIOD, BB_STD_DEV,
            ATR_PERIOD,
        )
        assert RSI_PERIOD > 0
        assert 0 < RSI_OVERSOLD < RSI_OVERBOUGHT <= 100
        assert 0 < MACD_FAST < MACD_SLOW
        assert MACD_SIGNAL > 0
        assert 0 < MA_SHORT < MA_LONG
        assert BB_PERIOD > 0
        assert BB_STD_DEV > 0
        assert ATR_PERIOD > 0

    def test_score_weights_sum(self):
        """Score weights should sum to approximately 10.0."""
        from config.settings import SCORE_WEIGHTS
        total = sum(SCORE_WEIGHTS.values())
        assert 9.0 <= total <= 11.0, f"Score weights sum to {total}, expected ~10.0"


# =============================================================================
# Test Suite: core/utils.py
# =============================================================================

class TestUtils:
    """Verify data fetching utilities and watchlist loading."""

    def test_load_watchlist_from_file(self, tmp_path):
        """load_watchlist should read symbols from a CSV file."""
        from core.utils import load_watchlist

        # Create a temporary CSV file using pytest's tmp_path fixture
        csv_file = tmp_path / "test_watchlist.csv"
        csv_file.write_text("Symbol,Name,Sector\nAAPL,Apple,Tech\nMSFT,Microsoft,Tech\nXOM,Exxon,Energy\n")

        symbols = load_watchlist(str(csv_file))
        assert symbols == ["AAPL", "MSFT", "XOM"]

    def test_load_watchlist_missing_file(self):
        """load_watchlist should raise FileNotFoundError for missing files."""
        from core.utils import load_watchlist

        with pytest.raises(FileNotFoundError):
            load_watchlist("/nonexistent/path/watchlist.csv")

    def test_load_watchlist_missing_column(self, tmp_path):
        """load_watchlist should raise KeyError if 'Symbol' column is missing."""
        from core.utils import load_watchlist

        csv_file = tmp_path / "bad_watchlist.csv"
        csv_file.write_text("Ticker,Name\nAAPL,Apple\n")

        with pytest.raises(KeyError):
            load_watchlist(str(csv_file))

    def test_load_default_watchlist(self):
        """The default watchlist.csv should exist and contain symbols."""
        from core.utils import load_watchlist
        from config.settings import WATCHLIST_PATH

        symbols = load_watchlist(WATCHLIST_PATH)
        assert len(symbols) > 0, "Default watchlist should contain at least 1 symbol"
        assert all(isinstance(s, str) for s in symbols)


# =============================================================================
# Test Suite: core/indicators.py
# =============================================================================

class TestIndicators:
    """Verify all technical indicator calculations."""

    @pytest.fixture
    def uptrend_df(self):
        """Provide a 250-row uptrending OHLCV DataFrame."""
        return make_ohlcv(rows=250, trend="up")

    @pytest.fixture
    def short_df(self):
        """Provide a very short DataFrame to test insufficient-data handling."""
        return make_ohlcv(rows=5, trend="flat")

    def test_rsi_calculation(self, uptrend_df):
        """RSI should return a value between 0 and 100."""
        from core.indicators import calculate_rsi
        result = calculate_rsi(uptrend_df)
        assert "rsi_value" in result
        assert result["rsi_value"] is not None
        assert 0 <= result["rsi_value"] <= 100
        assert isinstance(result["rsi_bullish"], bool)
        assert isinstance(result["rsi_bearish"], bool)

    def test_macd_calculation(self, uptrend_df):
        """MACD should return value, signal, histogram, and crossover flag."""
        from core.indicators import calculate_macd
        result = calculate_macd(uptrend_df)
        assert "macd_value" in result
        assert "macd_signal" in result
        assert "macd_histogram" in result
        assert "macd_bullish" in result
        assert result["macd_value"] is not None

    def test_moving_averages_calculation(self, uptrend_df):
        """Moving averages should return MA values and price-above flags."""
        from core.indicators import calculate_moving_averages
        result = calculate_moving_averages(uptrend_df)
        assert "ma_short_value" in result
        assert "ma_long_value" in result
        assert "price_above_ma" in result
        assert isinstance(result["price_above_ma"], bool)

    def test_bollinger_bands_calculation(self, uptrend_df):
        """Bollinger Bands should return upper, middle, lower, and breakout flag."""
        from core.indicators import calculate_bollinger_bands
        result = calculate_bollinger_bands(uptrend_df)
        assert "bb_upper" in result
        assert "bb_middle" in result
        assert "bb_lower" in result
        assert isinstance(result["bb_breakout"], bool)
        # Upper band must be above lower band
        if result["bb_upper"] is not None and result["bb_lower"] is not None:
            assert result["bb_upper"] > result["bb_lower"]

    def test_volume_signal_calculation(self, uptrend_df):
        """Volume signal should detect the injected volume spike."""
        from core.indicators import calculate_volume_signal
        result = calculate_volume_signal(uptrend_df)
        assert "volume_ratio" in result
        assert "volume_surge" in result
        # We injected a 3× spike, so surge should be True
        assert result["volume_surge"] is True
        assert result["volume_ratio"] >= 2.0

    def test_atr_calculation(self, uptrend_df):
        """ATR should return a positive value."""
        from core.indicators import calculate_atr
        result = calculate_atr(uptrend_df)
        assert "atr_value" in result
        assert result["atr_value"] is not None
        assert result["atr_value"] > 0
        assert "atr_percent" in result

    def test_calculate_all_indicators(self, uptrend_df):
        """calculate_all_indicators should return all expected keys."""
        from core.indicators import calculate_all_indicators
        result = calculate_all_indicators(uptrend_df)

        expected_keys = [
            "rsi_value", "rsi_bullish", "rsi_bearish",
            "macd_value", "macd_signal", "macd_histogram", "macd_bullish",
            "ma_short_value", "ma_long_value", "price_above_ma",
            "bb_upper", "bb_middle", "bb_lower", "bb_breakout",
            "volume_current", "volume_average", "volume_ratio", "volume_surge",
            "atr_value", "atr_percent",
            "current_price",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_insufficient_data_returns_empty_result(self, short_df):
        """calculate_all_indicators should handle insufficient data gracefully."""
        from core.indicators import calculate_all_indicators
        result = calculate_all_indicators(short_df)
        # All signal flags should be False when data is insufficient
        assert result["rsi_bullish"] is False
        assert result["macd_bullish"] is False
        assert result["volume_surge"] is False


# =============================================================================
# Test Suite: core/scanner.py
# =============================================================================

class TestScanner:
    """Verify the scanning, scoring, and reporting pipeline."""

    def test_score_stock_all_bullish(self):
        """A stock with all bullish signals should score close to 10.0."""
        from core.scanner import score_stock

        all_bullish = {
            "rsi_bullish": True,
            "macd_bullish": True,
            "price_above_ma": True,
            "bb_breakout": True,
            "volume_surge": True,
            "atr_percent": 2.5,  # Within favorable range
        }
        score = score_stock(all_bullish)
        assert score == 10.0

    def test_score_stock_no_signals(self):
        """A stock with no bullish signals should score 0.0."""
        from core.scanner import score_stock

        no_signals = {
            "rsi_bullish": False,
            "macd_bullish": False,
            "price_above_ma": False,
            "bb_breakout": False,
            "volume_surge": False,
            "atr_percent": 0.1,  # Outside favorable range
        }
        score = score_stock(no_signals)
        assert score == 0.0

    def test_generate_reason_with_signals(self):
        """generate_reason should list active signals in the output string."""
        from core.scanner import generate_reason

        indicators = {
            "rsi_bullish": True, "rsi_value": 28.5,
            "macd_bullish": True,
            "price_above_ma": False, "price_above_short": True,
            "bb_breakout": False,
            "volume_surge": True, "volume_ratio": 2.8,
            "golden_cross": False,
        }
        reason = generate_reason(indicators, score=6.0)
        assert "RSI oversold" in reason
        assert "MACD bullish crossover" in reason
        assert "Volume surge" in reason

    def test_generate_reason_no_signals(self):
        """generate_reason should indicate 'No signal' when score is low."""
        from core.scanner import generate_reason

        indicators = {
            "rsi_bullish": False,
            "macd_bullish": False,
            "price_above_ma": False, "price_above_short": False,
            "bb_breakout": False,
            "volume_surge": False,
            "golden_cross": False,
        }
        reason = generate_reason(indicators, score=0.0)
        assert "No signal" in reason or "No strong signals" in reason

    def test_scan_stock_with_synthetic_data(self):
        """scan_stock should return a well-formed result dictionary."""
        from core.scanner import scan_stock

        df = make_ohlcv(rows=250, trend="up")
        result = scan_stock("TEST", df)

        assert result["symbol"] == "TEST"
        assert 0.0 <= result["score"] <= 10.0
        assert isinstance(result["reason"], str)
        assert result["current_price"] is not None
        assert "indicators" in result

    def test_save_scan_results(self):
        """save_scan_results should create a CSV file with correct columns."""
        from core.scanner import save_scan_results

        results = [
            {
                "symbol": "AAPL", "score": 8.0, "current_price": 150.0,
                "rsi_value": 35.0, "macd_signal": "Bullish",
                "volume_signal": "Surge", "atr_value": 2.5,
                "reason": "Strong buy: test",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_scan_results(results, output_dir=tmpdir)
            assert os.path.isfile(path)

            df = pd.read_csv(path)
            assert "symbol" in df.columns
            assert "score" in df.columns
            assert "reason" in df.columns
            assert len(df) == 1
            assert df.iloc[0]["symbol"] == "AAPL"

    def test_print_scan_report_no_error(self, capsys):
        """print_scan_report should execute without raising errors."""
        from core.scanner import print_scan_report

        results = [
            {
                "symbol": "AAPL", "score": 8.0, "current_price": 150.0,
                "rsi_value": 35.0, "macd_signal": "Bullish",
                "volume_signal": "Surge", "reason": "Strong buy: test",
            },
        ]
        print_scan_report(results)
        captured = capsys.readouterr()
        assert "AAPL" in captured.out
        assert "DAILY MARKET SCAN" in captured.out

    def test_print_scan_report_empty(self, capsys):
        """print_scan_report should handle empty results gracefully."""
        from core.scanner import print_scan_report

        print_scan_report([])
        captured = capsys.readouterr()
        assert "No stocks matched" in captured.out
