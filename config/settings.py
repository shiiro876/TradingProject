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

# =============================================================================
# 📈 SIGNAL GENERATOR SETTINGS — Module 2 configuration
# =============================================================================

# Take Profit multipliers relative to risk (R)
# TP1 = entry + (TP1_MULTIPLIER × risk_per_share)  → close 50% of position
# TP2 = entry + (TP2_MULTIPLIER × risk_per_share)  → close remaining 50%
TP1_MULTIPLIER = 2.0
TP2_MULTIPLIER = 3.0

# =============================================================================
# 📋 TRADE JOURNAL SETTINGS — Module 2 configuration
# =============================================================================

# Path to the trade journal CSV file
JOURNAL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trades.csv")

# =============================================================================
# 📰 NEWS & SENTIMENT SETTINGS — Module 3 configuration
# =============================================================================

# Sentiment score thresholds (VADER compound score ranges from -1.0 to +1.0)
SENTIMENT_POSITIVE_THRESHOLD = 0.20    # Above this = POSITIVE
SENTIMENT_NEGATIVE_THRESHOLD = -0.20   # Below this = NEGATIVE
# Between the two = NEUTRAL

# Number of headlines to fetch per stock from NewsAPI
NEWS_MAX_HEADLINES = 10

# Major event keyword categories for detection
# If a headline contains any of these keywords, it's flagged as a major event
MAJOR_EVENT_KEYWORDS = {
    "earnings": ["earnings", "quarterly results", "profit", "revenue beat",
                 "revenue miss", "EPS", "guidance"],
    "analyst": ["upgrade", "downgrade", "price target", "buy rating",
                "sell rating", "overweight", "underweight", "outperform"],
    "merger": ["merger", "acquisition", "acquire", "takeover", "buyout",
               "deal", "joint venture"],
    "sector": ["oil supply", "oil price", "interest rate", "fed rate",
               "inflation", "recession", "tariff", "sanctions", "regulation"],
}

# =============================================================================
# 🌐 MACRO / SECTOR ROTATION SETTINGS — Module 3 configuration
# =============================================================================

# Sector ETF tickers used for macro/sector analysis
# Maps sector names to their corresponding SPDR ETF symbols
SECTOR_ETFS = {
    "Energy": "XLE",
    "Technology": "XLK",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Healthcare": "XLV",
    "Utilities": "XLU",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Materials": "XLB",
}

# Periods for sector performance comparison
SECTOR_PERFORMANCE_PERIODS = {
    "1_week": 5,     # 5 trading days
    "1_month": 21,   # ~21 trading days
}

# Threshold for flagging a sector as "strong" or "weak"
SECTOR_STRONG_THRESHOLD = 2.0    # Sector return > +2% = strong
SECTOR_WEAK_THRESHOLD = -2.0     # Sector return < -2% = weak

# Minimum rank change to flag sector rotation
SECTOR_ROTATION_MIN_CHANGE = 3   # Must move ≥3 ranks to flag rotation

# =============================================================================
# 🛡️ TRAILING STOP SETTINGS — Module 4 configuration
# =============================================================================

# Default trailing stop method: "atr", "percentage", or "breakeven_then_trail"
TRAILING_STOP_METHOD = "atr"

# ATR-based trailing stop: trail distance = ATR × multiplier
TRAILING_STOP_ATR_MULTIPLIER = 1.5

# Percentage-based trailing stop: trail distance = price × percentage
TRAILING_STOP_PERCENTAGE = 0.03  # 3% trailing stop distance

# Breakeven trigger: move stop to breakeven once price reaches this multiple of R
# E.g., 1.0 means move stop to entry when price moves 1R in your favor
BREAKEVEN_TRIGGER_R_MULTIPLE = 1.0

# "Never let a winner become a loser" — after breakeven is hit, keep stop at
# entry + this small buffer to guarantee a scratch or tiny profit
BREAKEVEN_BUFFER_PCT = 0.001  # 0.1% above entry

# =============================================================================
# 🎯 RISK MANAGER SETTINGS — Module 4 configuration
# =============================================================================

# Maximum number of open positions allowed in the SAME sector
MAX_SECTOR_CONCENTRATION = 2

# Maximum portfolio drawdown before halting all new trades permanently
# (Requires manual reset — protects against systematic strategy failure)
MAX_DRAWDOWN_PCT = 0.15  # 15% drawdown from peak → halt trading

# Minimum account balance threshold (absolute floor — never trade below this)
MIN_ACCOUNT_BALANCE = 500.0  # Safety floor in dollars

# =============================================================================
# 🚀 EXECUTION ENGINE SETTINGS — Module 5 configuration
# =============================================================================

# Default order type for market entries
DEFAULT_ORDER_TYPE = "market"

# Monitoring interval in seconds (how often to check positions for exits)
MONITOR_INTERVAL_SECONDS = 60

# Partial close ratio at TP1: close this fraction of shares at first target
TP1_CLOSE_RATIO = 0.50  # Close 50% at TP1, keep 50% running to TP2

# =============================================================================
# 🧠 LEARNING ENGINE SETTINGS — Module 6 configuration
# =============================================================================

# Minimum number of historical trades before ML model training is useful
MIN_TRADES_FOR_TRAINING = 10

# Default model file path for persistence
MODEL_SAVE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trade_model.pkl")

# Default backtest period (number of trading bars to simulate)
BACKTEST_DEFAULT_MIN_SCORE = 5.0

# Optimizer: maximum number of parameter combinations to test
OPTIMIZER_MAX_COMBINATIONS = 500

# =============================================================================
# 🖥️ DASHBOARD & ALERTS SETTINGS — Module 7 configuration
# =============================================================================

# Maximum number of alerts to keep in memory
ALERT_HISTORY_MAX = 200

# Default number of recent trades to show in dashboard
DASHBOARD_RECENT_TRADES = 10

# Chart dimensions for console dashboard
CHART_WIDTH = 60
CHART_HEIGHT = 15
