# 📦 Module 2 — Signals, Risk Management & Trade Journal (Phase 2)

**Status:** ✅ Complete  
**Phase:** 2 of 7  
**Files:** `core/signals.py`, `risk/position_sizer.py`, `risk/portfolio_risk.py`, `learning/journal.py`  
**Tests:** `tests/test_module2.py` (40 tests)

---

## Overview

Module 2 bridges the gap between "this stock looks good" (Module 1 scanner) and "here is exactly how to trade it." It adds three critical capabilities:

1. **Signal Generation** — Converts scanner results into complete trade setups with entry, stop loss, profit targets, and risk:reward ratios.
2. **Position Sizing & Portfolio Risk** — Calculates exactly how many shares to buy per trade, enforces maximum position counts, and monitors daily loss limits.
3. **Trade Journal** — Automatically logs every trade with full details and computes performance statistics (win rate, profit factor, max drawdown, etc.).

**Week 2 Milestone:** The system now tells you exactly what to buy, how much, and where to put stops — and logs everything automatically.

---

## Components

### `core/signals.py` — Trade Signal Generator

Takes the top-ranked stocks from the scanner and generates complete trade setups using ATR-based dynamic stop-loss and profit target calculations.

**Trade Setup Formula:**
```
Entry Price   = current closing price
Risk (R)      = ATR × ATR_STOP_MULTIPLIER (default: 2.0)
Stop Loss     = Entry - R
Take Profit 1 = Entry + (2 × R)   → close 50% of position (2:1 R:R)
Take Profit 2 = Entry + (3 × R)   → close remaining 50% (3:1 R:R)
```

| Function | Description |
|----------|-------------|
| `generate_trade_setup(scan_result)` | Converts a single scanner result into a full trade setup |
| `classify_signal_strength(score, rr_ratio)` | Labels signal as STRONG / MEDIUM / WEAK |
| `generate_all_signals(scan_results, min_rr)` | Processes all results, filters by R:R, sorts by strength |
| `save_signals(signals, output_dir)` | Saves to `data/signals_YYYY-MM-DD.csv` |
| `print_signals_report(signals)` | Formatted console table with all setups |

**Signal Strength Classification:**

| Strength | Criteria | Meaning |
|----------|----------|---------|
| **STRONG** | Score ≥ 7.0 AND R:R ≥ 2.0 | Multiple bullish indicators + good R:R |
| **MEDIUM** | Score ≥ 5.0 AND R:R ≥ 1.5 | Decent setup with acceptable R:R |
| **WEAK** | Everything else | Few signals or poor R:R — trade with caution |

**Filtering:** Only signals with R:R ≥ `MIN_RR_RATIO` (default 1.5) are output.

**Example Output:**
```
📈 TRADE SIGNALS — 2026-03-30 10:00
==========================================================================================
  Symbol   Strength  Entry     Stop       TP1       TP2     R:R  Score  Reason
------------------------------------------------------------------------------------------
  XOM      STRONG    $112.50   $106.30   $124.90   $131.10  2.00   8.0  Strong buy: RSI oversold + MACD crossover
  HAL      MEDIUM    $ 38.20   $ 35.40   $ 43.80   $ 46.60  2.00   6.0  Moderate buy: MACD crossover
==========================================================================================
```

---

### `risk/position_sizer.py` — Position Size Calculator

Implements the **2% Risk Rule** used by professional traders: calculates the exact number of shares to buy so that if the stop loss is hit, the maximum dollar loss equals 2% of the account balance.

**Formula:**
```
max_risk_amount = account_balance × risk_percent     (e.g., $10,000 × 2% = $200)
risk_per_share  = entry_price - stop_loss_price      (e.g., $50.00 - $48.00 = $2.00)
position_size   = max_risk_amount / risk_per_share   (e.g., $200 / $2 = 100 shares)
```

| Function | Description |
|----------|-------------|
| `calculate_position_size(account_balance, entry_price, stop_loss_price, risk_percent, allow_fractional)` | Returns shares, value, risk amount |

**Safety Checks Built In:**
1. ✅ Position value capped at 35% of account (`MAX_POSITION_SIZE`)
2. ✅ Entry must be above stop loss (validates long-only trades)
3. ✅ Returns `valid=False` for invalid inputs (no exceptions thrown)
4. ✅ Floors to whole shares by default (fractional shares optional)
5. ✅ Rejects if risk budget can't afford even 1 share

**Return Dictionary:**
```python
{
    "shares_to_buy": 70,           # Number of shares
    "total_position_value": 3500.0, # Dollar value of position
    "risk_amount": 140.0,           # Max loss if stop hit
    "risk_per_share": 2.0,          # Dollar distance to stop
    "max_risk_allowed": 200.0,      # Budget from 2% rule
    "position_pct": 35.0,           # Position as % of account
    "capped": True,                 # Whether 35% cap was applied
    "valid": True,                  # Whether calculation succeeded
    "message": "Buy 70 shares..."   # Human-readable summary
}
```

---

### `risk/portfolio_risk.py` — Portfolio Risk Manager

Enforces portfolio-level constraints that protect the account from catastrophic losses. This is the "discipline engine" that prevents overexposure and emotional trading.

| Rule | Default | Description |
|------|---------|-------------|
| Max Open Positions | 3 | Prevents having too many trades open at once |
| Daily Loss Limit | 5% | Halts ALL trading if account drops 5% in one day |
| No Duplicate Positions | — | Cannot open two positions in the same stock |

**Class:** `PortfolioRiskManager`

| Method | Description |
|--------|-------------|
| `can_open_position()` | Returns True if new trades are allowed |
| `add_position(symbol, shares, entry_price, ...)` | Registers a new open position |
| `remove_position(symbol)` | Closes/removes a tracked position |
| `update_daily_pnl(pnl_change)` | Updates running daily P&L, checks loss limit |
| `check_daily_loss_limit()` | Returns True if daily loss limit is breached |
| `get_portfolio_summary()` | Returns full portfolio state dictionary |
| `reset_daily_state()` | Resets daily P&L and trading halt for new day |
| `save_violations_log(output_dir)` | Writes violations to `data/violations_YYYY-MM-DD.log` |

**Violation Logging:** Every rule violation is timestamped and logged both in-memory and to a file, creating an audit trail for review.

---

### `learning/journal.py` — Automated Trade Journal

Automatically logs every trade to `data/trades.csv` and provides comprehensive performance analytics. The journal is the foundation for the Learning Engine (Module 6) which will use historical trade data to train ML models.

**Journal Columns:**
```
date, symbol, direction, entry_price, exit_price, shares, stop_loss,
take_profit_1, take_profit_2, risk_reward, profit_loss_dollar,
profit_loss_percent, win_loss, exit_reason, notes
```

**Class:** `TradeJournal`

| Method | Description |
|--------|-------------|
| `log_trade(symbol, direction, entry_price, exit_price, shares, ...)` | Writes a completed trade to CSV |
| `get_all_trades()` | Returns all trades as a pandas DataFrame |
| `get_performance_stats()` | Calculates comprehensive performance metrics |
| `print_performance_report()` | Formatted console output of all stats |

**Performance Metrics Calculated:**

| Metric | Description |
|--------|-------------|
| Total Trades | Number of completed trades |
| Win Rate % | Percentage of winning trades |
| Average Win | Mean dollar profit on winning trades |
| Average Loss | Mean dollar loss on losing trades |
| Profit Factor | Gross profits / Gross losses (>1.0 = profitable) |
| Total P&L | Sum of all trade profits and losses |
| Max Drawdown | Largest peak-to-trough decline in cumulative P&L |
| Best Trade | Largest single trade profit |
| Worst Trade | Largest single trade loss |
| Monthly P&L | Breakdown of P&L by calendar month |

**Auto-Calculated Fields:** When `log_trade()` is called, dollar P&L, percentage P&L, and WIN/LOSS classification are computed automatically from the entry and exit prices. Supports both LONG and SHORT directions.

**Example Performance Report:**
```
📋 TRADE JOURNAL — Performance Report
============================================================
  Total Trades:     25
  Wins:             16
  Losses:           9
  Win Rate:         64.0%
------------------------------------------------------------
  Average Win:      +$87.50
  Average Loss:     -$42.30
  Best Trade:       +$312.00
  Worst Trade:      -$98.50
------------------------------------------------------------
  Profit Factor:    2.31
  Total P&L:        +$1,019.30
  Max Drawdown:     -$215.80
------------------------------------------------------------
  Monthly P&L:
    2026-01:  +$347.20
    2026-02:  +$412.60
    2026-03:  +$259.50
============================================================
```

---

## Configuration Added (config/settings.py)

Module 2 added these settings:

```python
# Take Profit multipliers relative to risk (R)
TP1_MULTIPLIER = 2.0    # TP1 = entry + (2 × R) → close 50%
TP2_MULTIPLIER = 3.0    # TP2 = entry + (3 × R) → close remaining 50%

# Trade journal path
JOURNAL_PATH = "data/trades.csv"
```

These work alongside the existing safety rules:
- `MAX_RISK_PER_TRADE = 0.02` (2% per trade)
- `MAX_POSITIONS = 3`
- `DAILY_LOSS_LIMIT = 0.05` (5%)
- `MIN_RR_RATIO = 1.5`
- `MAX_POSITION_SIZE = 0.35` (35%)
- `ATR_STOP_MULTIPLIER = 2.0`

---

## Usage

### Generate Signals (from scanner results)
```bash
python -m core.signals
```

### Use in Code
```python
from core.scanner import run_full_scan
from core.signals import generate_all_signals, print_signals_report
from risk.position_sizer import calculate_position_size
from risk.portfolio_risk import PortfolioRiskManager
from learning.journal import TradeJournal

# Step 1: Scan the market
scan_results = run_full_scan()

# Step 2: Generate trade signals
signals = generate_all_signals(scan_results)
print_signals_report(signals)

# Step 3: Size a position
for signal in signals:
    sizing = calculate_position_size(
        account_balance=10000,
        entry_price=signal["entry_price"],
        stop_loss_price=signal["stop_loss"],
    )
    if sizing["valid"]:
        print(sizing["message"])

# Step 4: Track portfolio risk
manager = PortfolioRiskManager(account_balance=10000)
if manager.can_open_position():
    manager.add_position("AAPL", sizing["shares_to_buy"], signal["entry_price"])

# Step 5: Log the trade when closed
journal = TradeJournal()
journal.log_trade(
    symbol="AAPL", direction="LONG",
    entry_price=150.0, exit_price=158.0, shares=70,
    stop_loss=146.0, take_profit_1=158.0,
    exit_reason="tp1",
)
journal.print_performance_report()
```

---

## Tests

40 unit tests in `tests/test_module2.py`, organized into 4 classes:

| Class | Tests | What It Covers |
|-------|-------|----------------|
| `TestSignals` | 10 | Trade setup generation, strength classification, filtering, sorting, CSV output |
| `TestPositionSizer` | 8 | 2% rule calculation, 35% cap, fractional shares, invalid inputs |
| `TestPortfolioRisk` | 12 | Max positions, daily loss limit, halt/resume, violations logging |
| `TestJournal` | 10 | Trade logging (LONG/SHORT), P&L calculation, performance stats, drawdown |

```bash
python -m pytest tests/test_module2.py -v
```

---

## How Module 2 Connects to Other Modules

```
Module 1 (Scanner)                    Module 2 (Signals + Risk + Journal)
┌──────────────┐                     ┌──────────────────────────────────┐
│  scanner.py  │──scan_results──────▶│  signals.py                      │
│              │                     │  ├─ generate_all_signals()       │
│  Scores:     │                     │  └─ Entry, Stop, TP1, TP2, R:R  │
│  0-10 / stock│                     │                                  │
└──────────────┘                     │  position_sizer.py               │
                                     │  ├─ calculate_position_size()    │
                                     │  └─ Shares, Value, Risk          │
                                     │                                  │
                                     │  portfolio_risk.py               │
                                     │  ├─ PortfolioRiskManager         │
                                     │  └─ Max positions, daily limit   │
                                     │                                  │
                                     │  journal.py                      │
                                     │  ├─ TradeJournal                 │
                                     │  └─ Log trades, calc stats       │
                                     └──────────────────────────────────┘
                                                    │
                                                    ▼
                                     Module 5 (Execution Engine — future)
                                     Module 6 (Learning Engine — future)
```
