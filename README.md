# 🤖 TradingBot — AI-Powered Algorithmic Trading System

An automated stock trading system built in Python that scans markets, identifies trade setups, manages risk, executes trades, and learns from every trade over time.

> **Full module documentation lives in the [`docs/`](docs/) folder.**

---

## 🏗️ Project Structure

```
TradingBot/
│
├── core/                          # Core trading logic
│   ├── __init__.py
│   ├── utils.py                   # Market data pipeline (yfinance)
│   ├── indicators.py              # Technical indicator calculations
│   ├── scanner.py                 # Stock scanning, scoring & ranking
│   ├── signals.py                 # Trade signal generator (entry/stop/targets)
│   ├── news.py                    # News sentiment analysis (VADER)
│   └── macro.py                   # Sector rotation & macro analysis
│
├── risk/                          # Risk management
│   ├── __init__.py
│   ├── position_sizer.py          # Position size calculator (2% rule)
│   ├── portfolio_risk.py          # Portfolio risk manager (max positions, daily limits)
│   ├── trailing_stop.py           # Trailing stop manager (ATR/pct/breakeven)
│   └── risk_manager.py            # Master risk orchestrator (discipline engine)
│
├── learning/                      # Learning & journaling
│   ├── __init__.py
│   └── journal.py                 # Automated trade journal + performance stats
│
├── config/                        # Configuration
│   ├── __init__.py
│   ├── settings.py                # All strategy parameters & safety rules
│   └── .env.example               # API key template (copy to .env)
│
├── data/                          # Data storage
│   ├── __init__.py
│   └── watchlist.csv              # Stock universe (50 S&P 500 stocks)
│
├── execution/                     # Trade execution (Module 5)
│   ├── __init__.py
│   ├── broker.py                  # Broker interface & paper trading simulator
│   ├── orders.py                  # Order lifecycle manager (signal → fill)
│   └── monitor.py                 # Position monitoring & auto-exits
├── dashboard/                     # Dashboard & alerts (Module 7 — placeholder)
│
├── tests/
│   ├── test_module1.py            # 24 tests: scanner, indicators, utils
│   ├── test_module2.py            # 40 tests: signals, position sizing, risk, journal
│   ├── test_module3.py            # 51 tests: news sentiment, macro sector analysis
│   ├── test_module4.py            # 59 tests: trailing stops, risk manager, drawdown
│   └── test_module5.py            # 56 tests: broker, orders, monitor, integration
│
├── docs/
│   ├── module1_market_scanner.md          # Module 1 detailed documentation
│   ├── module2_signals_risk_journal.md    # Module 2 detailed documentation
│   ├── module3_news_sentiment.md          # Module 3 detailed documentation
│   ├── module4_risk_manager.md            # Module 4 detailed documentation
│   └── module5_execution.md               # Module 5 detailed documentation
│
├── .gitignore
├── requirements.txt
├── Trading Source of truth .docx  # Original project specification
└── README.md                      # This file
```

---

## 📦 Completed Modules

### Module 1 — Market Scanner (Phase 1) ✅

**Files:** `core/utils.py`, `core/indicators.py`, `core/scanner.py`  
**Docs:** [`docs/module1_market_scanner.md`](docs/module1_market_scanner.md)

Scans 50+ stocks daily, runs 6 technical indicators (RSI, MACD, MA, Bollinger Bands, Volume, ATR), scores each stock 0–10, and returns the top 5 picks with plain-English reasoning.

```bash
python -m core.scanner
```

### Module 2 — Signals, Risk & Trade Journal (Phase 2) ✅

**Files:** `core/signals.py`, `risk/position_sizer.py`, `risk/portfolio_risk.py`, `learning/journal.py`  
**Docs:** [`docs/module2_signals_risk_journal.md`](docs/module2_signals_risk_journal.md)

Generates complete trade setups (entry, stop loss, TP1, TP2, R:R ratio), calculates exact position sizes using the 2% risk rule, enforces portfolio constraints (3 max positions, 5% daily loss limit), and automatically logs every trade with comprehensive performance statistics.

```bash
python -m core.signals
```

### Module 3 — News & Sentiment + Macro Sector Analysis (Phase 3) ✅

**Files:** `core/news.py`, `core/macro.py`  
**Docs:** [`docs/module3_news_sentiment.md`](docs/module3_news_sentiment.md)

Fetches financial news headlines and scores sentiment using VADER analysis (POSITIVE / NEGATIVE / NEUTRAL). Detects major events (earnings, analyst upgrades, mergers, geopolitical events). Tracks 10 sector ETFs, ranks sectors by performance, detects sector rotation, and provides score adjustments for stocks in strong/weak sectors.

```bash
# News sentiment (requires NEWS_API_KEY in config/.env)
python -m core.news

# Sector / macro analysis
python -m core.macro
```

### Module 4 — Risk Manager: The Discipline Engine (Phase 4) ✅

**Files:** `risk/trailing_stop.py`, `risk/risk_manager.py`  
**Docs:** [`docs/module4_risk_manager.md`](docs/module4_risk_manager.md)

The "discipline engine" that prevents the trading system from blowing up. Adds trailing stops that ratchet upward to protect profits ("never let a winner become a loser"), sector concentration limits (max 2 positions per sector), drawdown monitoring (15% halt), and a master risk orchestrator that provides a single approve/deny gate for every trade.

```python
from risk.risk_manager import RiskManager
rm = RiskManager(account_balance=10000)
decision = rm.evaluate_trade("AAPL", entry_price=150, stop_loss=144,
                             sector="Technology")
```

### Module 5 — Execution Engine (Phase 5) ✅

**Files:** `execution/broker.py`, `execution/orders.py`, `execution/monitor.py`  
**Docs:** [`docs/module5_execution.md`](docs/module5_execution.md)

The execution engine that bridges signals to order placement. Includes a paper trading broker simulator, order lifecycle manager (signal → risk gate → fill → registration), and automatic position monitoring with trailing stop exits, TP1 partial closes (50%), and TP2 full exits.

```python
from execution.broker import get_broker
from execution.orders import OrderManager
from execution.monitor import PositionMonitor
from risk.risk_manager import RiskManager

rm = RiskManager(account_balance=10000)
broker = get_broker(account_balance=10000)
om = OrderManager(rm, broker)
monitor = PositionMonitor(om, rm)

result = om.execute_signal(signal, sector="Technology")
actions = monitor.check_all_positions({"AAPL": {"price": 162.0}})
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- pip (Python package manager)

### Installation

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
# Edit config/.env with your API keys (not needed for Modules 1-2)
```

### Running Tests

```bash
# Run all tests (230 total)
python -m pytest tests/ -v

# Module 1 only (24 tests)
python -m pytest tests/test_module1.py -v

# Module 2 only (40 tests)
python -m pytest tests/test_module2.py -v

# Module 3 only (51 tests)
python -m pytest tests/test_module3.py -v

# Module 4 only (59 tests)
python -m pytest tests/test_module4.py -v

# Module 5 only (56 tests)
python -m pytest tests/test_module5.py -v
```

---

## 🔒 Safety Rules (Hard-Coded)

| Rule | Value | Purpose |
|------|-------|---------|
| `PAPER_TRADING` | `True` | Prevents real money trades until validated |
| `MAX_RISK_PER_TRADE` | 2% | Limits loss on any single trade |
| `MAX_POSITIONS` | 3 | Prevents overexposure |
| `DAILY_LOSS_LIMIT` | 5% | Stops trading if daily loss exceeds this |
| `MIN_RR_RATIO` | 1.5 | Only takes trades with favorable risk:reward |
| `MAX_POSITION_SIZE` | 35% | Prevents concentration in one stock |
| `ATR_STOP_MULTIPLIER` | 2.0 | Stop distance = ATR × 2 |
| `TRAILING_STOP_ATR_MULTIPLIER` | 1.5 | Trailing stop distance = ATR × 1.5 |
| `MAX_SECTOR_CONCENTRATION` | 2 | Max positions in same sector |
| `MAX_DRAWDOWN_PCT` | 15% | Halt trading if account drops 15% from peak |
| `MIN_ACCOUNT_BALANCE` | $500 | Never trade below this balance |

---

## 🗺️ Build Roadmap

| Phase | Module | Description | Status |
|-------|--------|-------------|--------|
| **1** | Market Scanner | Scans stocks, scores setups, returns top picks | ✅ Complete |
| **2** | Signals & Risk | Trade setups, position sizing, portfolio risk, journal | ✅ Complete |
| **3** | News & Sentiment | News sentiment analysis, sector rotation detection | ✅ Complete |
| **4** | Risk Manager (Advanced) | Trailing stops, sector concentration, drawdown monitoring | ✅ Complete |
| **5** | Execution Engine | Paper trading broker, order lifecycle, position monitoring | ✅ Complete |
| **6** | Learning Engine | ML model that learns from trade history | ⬜ Planned |
| **7** | Dashboard & Alerts | Streamlit dashboard, Telegram notifications | ⬜ Planned |

---

## 📦 Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `yfinance` | ≥0.2.36 | Yahoo Finance market data API |
| `pandas` | ≥2.0.0 | DataFrame operations and data manipulation |
| `pandas-ta` | ≥0.3.14b1 | Technical analysis indicator library |
| `numpy` | ≥1.24.0 | Numerical computations |
| `python-dotenv` | ≥1.0.0 | Environment variable management |
| `vaderSentiment` | ≥3.3.2 | Lexicon-based sentiment analysis (VADER) |
| `requests` | ≥2.31.0 | HTTP client for external API calls (NewsAPI) |
| `pytest` | (dev) | Test framework |
