# =============================================================================
# config/settings.py — System-Wide Configuration & Strategy Parameters
# =============================================================================
#
# PURPOSE:
#   Central configuration file for the entire trading system. All tunable
#   parameters, risk limits, and safety rules are defined here so that no
#   "magic numbers" appear scattered across the codebase.
#
# SAFETY RULES:
#   The risk parameters below are hard-coded safety limits. They should NOT
#   be changed without careful deliberation and validation via backtesting.
#
# USAGE:
#   from config.settings import (
#       PAPER_TRADING, MAX_RISK_PER_TRADE, SCANNER_TOP_N, ...
#   )
#
# =============================================================================

import os
from dotenv import load_dotenv

# Load environment variables from config/.env (API keys, secrets)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# =============================================================================
# 🔑 API CREDENTIALS (loaded from .env — never hard-code these)
# =============================================================================
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =============================================================================
# 🔒 SAFETY RULES — Hard-coded risk limits (change with extreme caution)
# =============================================================================

# Paper trading mode: True = simulated trades only (no real money at risk)
# Set to False ONLY after 30+ days of validated paper trading
PAPER_TRADING = True

# Maximum percentage of account balance to risk on a single trade (2%)
MAX_RISK_PER_TRADE = 0.02

# Maximum number of simultaneous open positions
MAX_POSITIONS = 3

# Daily loss limit: stop all trading if account drops this % in one day (5%)
DAILY_LOSS_LIMIT = 0.05

# Minimum acceptable Risk:Reward ratio for any trade entry
MIN_RR_RATIO = 1.5

# Maximum portion of account to allocate to a single position (35%)
MAX_POSITION_SIZE = 0.35

# Starting capital in ZAR (South African Rand)
STARTING_CAPITAL_ZAR = 2000

# =============================================================================
# 📊 SCANNER SETTINGS — Module 1 configuration
# =============================================================================

# Number of top-ranked stocks to return from each scan
SCANNER_TOP_N = 5

# Historical data period for scanning (yfinance period string)
# Options: "1mo", "3mo", "6mo", "1y", "2y"
SCANNER_DATA_PERIOD = "3mo"

# Historical data interval for scanning (yfinance interval string)
# Options: "1d" (daily), "1h" (hourly), "5m" (5-minute)
SCANNER_DATA_INTERVAL = "1d"

# Path to the CSV file containing the stock universe to scan
WATCHLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "watchlist.csv")

# Path to the output directory for scan results
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# =============================================================================
# 📈 TECHNICAL INDICATOR PARAMETERS
# =============================================================================

# RSI (Relative Strength Index) configuration
RSI_PERIOD = 14           # Standard lookback period for RSI calculation
RSI_OVERSOLD = 30         # Below this = oversold (potential buy signal)
RSI_OVERBOUGHT = 70       # Above this = overbought (potential sell signal)

# MACD (Moving Average Convergence Divergence) configuration
MACD_FAST = 12            # Fast EMA period
MACD_SLOW = 26            # Slow EMA period
MACD_SIGNAL = 9           # Signal line EMA period

# Moving Average periods
MA_SHORT = 50             # Short-term moving average (50-day)
MA_LONG = 200             # Long-term moving average (200-day)

# Bollinger Bands configuration
BB_PERIOD = 20            # Lookback period for Bollinger Bands
BB_STD_DEV = 2.0          # Number of standard deviations for band width

# Volume analysis configuration
VOLUME_AVG_PERIOD = 20    # Period for average volume calculation
VOLUME_SURGE_MULTIPLIER = 2.0  # Volume must be >= this × average to flag surge

# ATR (Average True Range) for volatility / stop-loss calculation
ATR_PERIOD = 14           # Lookback period for ATR
ATR_STOP_MULTIPLIER = 2.0  # Stop loss distance = entry - (ATR × this multiplier)

# =============================================================================
# 🏷️ SCORING WEIGHTS — How each indicator contributes to the scanner score
# =============================================================================
# Each bullish signal adds these points to a stock's total score (out of 10).
# Weights are tuned so that a stock showing ALL bullish signals scores 10.

SCORE_WEIGHTS = {
    "rsi_bullish": 2.0,         # RSI in bullish territory (oversold bounce)
    "macd_bullish": 2.0,        # MACD bullish crossover detected
    "price_above_ma": 1.5,      # Price trading above 50-day & 200-day MA
    "bollinger_breakout": 1.5,  # Price breaking above upper Bollinger Band
    "volume_surge": 2.0,        # Volume significantly above average
    "atr_favorable": 1.0,       # ATR indicates manageable volatility
}
