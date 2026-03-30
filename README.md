# 🤖 TradingBot — AI-Powered Algorithmic Trading System

An automated stock trading system built in Python that scans markets, identifies trade setups, manages risk, executes trades, and learns from every trade over time.

---

## 📦 Module 1 — Market Scanner (Phase 1 / Stage 1)

**Status:** ✅ Complete  
**Purpose:** Scans 50+ stocks every day, runs technical analysis on each one, scores them based on bullish signals, and returns the top 5 stocks to watch with plain-English reasoning.

This module replaces the manual process of checking charts one by one. It automates what a trader does each morning: evaluate price action, volume, momentum indicators, and trend direction to find the best trade candidates.

---

### 🏗️ Project Structure

```
TradingBot/
│
├── core/                        # Core trading logic (analysis & scanning)
│   ├── __init__.py              # Package docstring
│   ├── utils.py                 # Market data fetching pipeline (yfinance)
│   ├── indicators.py            # Technical indicator calculations
│   └── scanner.py               # Stock scanning, scoring & ranking engine
│
├── config/                      # Configuration & settings
│   ├── __init__.py              # Package docstring
│   ├── settings.py              # All strategy parameters & safety rules
│   └── .env.example             # API key template (copy to .env)
│
├── data/                        # Data storage
│   ├── __init__.py              # Package docstring
│   └── watchlist.csv            # Stock universe (50 S&P 500 stocks)
│
├── risk/                        # Risk management (Module 2 — placeholder)
├── execution/                   # Trade execution (Module 5 — placeholder)
├── learning/                    # ML learning engine (Module 6 — placeholder)
├── dashboard/                   # Dashboard & alerts (Module 7 — placeholder)
│
├── tests/
│   └── test_module1.py          # 24 unit tests covering all Module 1 code
│
├── .gitignore                   # Excludes .env, __pycache__, generated data
├── requirements.txt             # Python dependencies
├── Trading Source of truth .docx  # Original project specification document
└── README.md                    # This file
```

---

### 📊 What Module 1 Does

1. **Loads Stock Universe** — Reads `data/watchlist.csv` containing 50 diversified S&P 500 stocks across Technology, Energy, Healthcare, Financials, Industrials, Consumer Staples, Utilities, and Communication Services sectors.

2. **Fetches Market Data** — Downloads 3 months of daily OHLCV (Open, High, Low, Close, Volume) data from Yahoo Finance using the `yfinance` library.

3. **Calculates Technical Indicators** — For each stock, computes:
   | Indicator | What It Measures | Bullish Signal |
   |-----------|-----------------|----------------|
   | **RSI (14)** | Overbought/oversold momentum | RSI ≤ 30 (oversold bounce) |
   | **MACD (12/26/9)** | Momentum crossovers | MACD crosses above signal line |
   | **50-day & 200-day SMA** | Trend direction | Price above both MAs |
   | **Bollinger Bands (20, 2σ)** | Volatility breakouts | Price > upper band |
   | **Volume Analysis** | Unusual activity | Volume ≥ 2× 20-day average |
   | **ATR (14)** | Volatility / stop-loss sizing | ATR% between 1%–5% |

4. **Scores Each Stock (0–10)** — Assigns weighted points for each bullish signal detected:
   - RSI oversold: +2.0 pts
   - MACD crossover: +2.0 pts
   - Price above MAs: +1.5 pts
   - Bollinger breakout: +1.5 pts
   - Volume surge: +2.0 pts
   - Favorable ATR: +1.0 pts
   - **Maximum possible score: 10.0**

5. **Returns Top 5 Stocks** — Ranks all stocks by score and returns the top 5 with a plain-English reason, e.g.:
   > "Strong buy: RSI oversold (28.5) + MACD bullish crossover + Volume surge (2.8x avg)"

6. **Saves Results** — Writes scan output to `data/daily_scan_YYYY-MM-DD.csv` and `data/daily_scan.csv` (latest).

---

### 🚀 Getting Started

#### Prerequisites
- Python 3.11+ installed
- pip (Python package manager)

#### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd TradingBot

# 2. (Recommended) Create a virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp config/.env.example config/.env
# Edit config/.env with your API keys (not needed for Module 1)
```

#### Running the Scanner

```bash
# Run the market scanner from the project root
python -m core.scanner
```

**Example Output:**
```
🔍 Starting Market Scanner...

================================================================================
  📊 DAILY MARKET SCAN — 2026-03-30 10:00
================================================================================
  #   Symbol   Score   Price       RSI   MACD      Volume   Reason
--------------------------------------------------------------------------------
  1   XOM      8.0     $112.50    28.5   Bullish   Surge    Strong buy: RSI oversold + MACD crossover + Volume surge
  2   HAL      7.5     $38.20     32.1   Bullish   Surge    Strong buy: MACD crossover + Volume surge + Price above 50MA
  3   CVX      6.0     $158.90    45.2   Bullish   Normal   Moderate buy: MACD crossover + Price above 50MA & 200MA
  4   CAT      5.5     $342.10    48.0   Neutral   Surge    Moderate buy: Volume surge + Price above 50MA & 200MA
  5   NVDA     5.0     $890.25    52.3   Neutral   Normal   Moderate buy: Price above 50MA & 200MA + Bollinger breakout
================================================================================
```

#### Running Tests

```bash
# Run all 24 Module 1 tests
python -m pytest tests/test_module1.py -v
```

---

### 📁 File-by-File Documentation

#### `config/settings.py`
Central configuration file. Contains:
- **Safety rules** — Hard-coded risk limits (2% max risk per trade, 3 max positions, 5% daily loss limit, paper trading mode ON by default)
- **Scanner settings** — Top N count (5), data period (3 months), data interval (daily)
- **Indicator parameters** — RSI period (14), MACD (12/26/9), MA periods (50/200), Bollinger Bands (20, 2σ), Volume average (20-day), ATR period (14)
- **Score weights** — How many points each bullish signal contributes to the score

#### `core/utils.py`
Data access layer. Functions:
- `get_stock_data(symbol, period, interval)` — Downloads OHLCV data for one stock via yfinance
- `get_multiple_stocks(symbols, period, interval)` — Batch downloads for a list of symbols
- `load_watchlist(csv_path)` — Reads stock symbols from a CSV file

#### `core/indicators.py`
Technical analysis engine. Functions:
- `calculate_rsi(df)` — RSI with oversold/overbought flags
- `calculate_macd(df)` — MACD with bullish crossover detection
- `calculate_moving_averages(df)` — 50MA, 200MA, golden cross detection
- `calculate_bollinger_bands(df)` — Upper/lower bands, breakout detection
- `calculate_volume_signal(df)` — Volume ratio and surge detection
- `calculate_atr(df)` — Average True Range for volatility measurement
- `calculate_all_indicators(df)` — Runs all of the above, returns combined dict

#### `core/scanner.py`
Scanning and scoring engine. Functions:
- `score_stock(indicators)` — Converts indicator signals to a 0–10 score
- `generate_reason(indicators, score)` — Builds plain-English explanation
- `scan_stock(symbol, df)` — Full analysis for one stock
- `run_full_scan(symbols, period, interval, top_n)` — End-to-end scan pipeline
- `save_scan_results(results, output_dir)` — Saves to dated CSV
- `print_scan_report(results)` — Formatted console output

#### `data/watchlist.csv`
The stock universe containing 50 diversified stocks across 8 sectors:
- Technology (10): AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, AMD, INTC
- Energy (7): XOM, CVX, HAL, SLB, COP, OXY, MRO
- Healthcare (7): JNJ, UNH, PFE, ABBV, MRK, LLY, TMO
- Financials (6): JPM, V, MA, BAC, GS, WFC
- Industrials (7): CAT, DE, BA, HON, UNP, CMC, GE, LMT
- Consumer Staples (5): PG, KO, PEP, WMT, COST
- Utilities (4): NEE, DUK, SO, AEP
- Communication Services (4): T, VZ, DIS, NFLX

#### `tests/test_module1.py`
24 unit tests organized into 4 test classes:
- **TestSettings** (4 tests) — Validates all configuration constants
- **TestUtils** (4 tests) — Tests data loading and watchlist parsing
- **TestIndicators** (8 tests) — Tests each indicator + combined + edge cases
- **TestScanner** (8 tests) — Tests scoring, reasoning, scan pipeline, CSV output

---

### 🔒 Safety Rules (Hard-Coded)

These safety parameters are defined in `config/settings.py` and should not be changed without careful validation:

| Rule | Value | Purpose |
|------|-------|---------|
| `PAPER_TRADING` | `True` | Prevents real money trades until validated |
| `MAX_RISK_PER_TRADE` | 2% | Limits loss on any single trade |
| `MAX_POSITIONS` | 3 | Prevents overexposure |
| `DAILY_LOSS_LIMIT` | 5% | Stops trading if daily loss exceeds this |
| `MIN_RR_RATIO` | 1.5 | Only takes trades with favorable risk:reward |
| `MAX_POSITION_SIZE` | 35% | Prevents concentration in one stock |

---

### 🗺️ Build Roadmap — Upcoming Modules

| Phase | Module | Description | Status |
|-------|--------|-------------|--------|
| **1** | Market Scanner | Scans stocks, scores setups, returns top picks | ✅ Complete |
| **2** | Technical Analysis / Signals | Generates full trade setups (entry, stop, targets) | ⬜ Planned |
| **3** | News & Sentiment | Reads financial news, scores sentiment | ⬜ Planned |
| **4** | Risk Manager | Position sizing, stop losses, portfolio limits | ⬜ Planned |
| **5** | Execution Engine | Places trades via Alpaca API | ⬜ Planned |
| **6** | Learning Engine | ML model that learns from trade history | ⬜ Planned |
| **7** | Dashboard & Journal | Streamlit dashboard, Telegram alerts, trade journal | ⬜ Planned |

---

### 📦 Dependencies (Module 1)

| Package | Version | Purpose |
|---------|---------|---------|
| `yfinance` | ≥0.2.36 | Yahoo Finance market data API |
| `pandas` | ≥2.0.0 | DataFrame operations and data manipulation |
| `pandas-ta` | ≥0.3.14b1 | Technical analysis indicator library |
| `numpy` | ≥1.24.0 | Numerical computations |
| `python-dotenv` | ≥1.0.0 | Environment variable management |
| `pytest` | (dev) | Test framework |
