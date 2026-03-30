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
│   └── signals.py                 # Trade signal generator (entry/stop/targets)
│
├── risk/                          # Risk management
│   ├── __init__.py
│   ├── position_sizer.py          # Position size calculator (2% rule)
│   └── portfolio_risk.py          # Portfolio risk manager (max positions, daily limits)
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
├── execution/                     # Trade execution (Module 5 — placeholder)
├── dashboard/                     # Dashboard & alerts (Module 7 — placeholder)
│
├── tests/
│   ├── test_module1.py            # 24 tests: scanner, indicators, utils
│   └── test_module2.py            # 40 tests: signals, position sizing, risk, journal
│
├── docs/
│   ├── module1_market_scanner.md  # Module 1 detailed documentation
│   └── module2_signals_risk_journal.md  # Module 2 detailed documentation
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
# Run all tests (64 total)
python -m pytest tests/ -v

# Module 1 only (24 tests)
python -m pytest tests/test_module1.py -v

# Module 2 only (40 tests)
python -m pytest tests/test_module2.py -v
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

---

## 🗺️ Build Roadmap

| Phase | Module | Description | Status |
|-------|--------|-------------|--------|
| **1** | Market Scanner | Scans stocks, scores setups, returns top picks | ✅ Complete |
| **2** | Signals & Risk | Trade setups, position sizing, portfolio risk, journal | ✅ Complete |
| **3** | News & Sentiment | Reads financial news, scores sentiment | ⬜ Planned |
| **4** | Risk Manager (Advanced) | Enhanced risk rules, trailing stops | ⬜ Planned |
| **5** | Execution Engine | Places trades via Alpaca API | ⬜ Planned |
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
| `pytest` | (dev) | Test framework |
