# 📦 Module 4 — Risk Manager: The Discipline Engine (Phase 4)

**Status:** ✅ Complete  
**Phase:** 4 of 7  
**Files:** `risk/trailing_stop.py`, `risk/risk_manager.py`  
**Tests:** `tests/test_module4.py` (59 tests)

---

## Overview

Module 4 is the **discipline engine** — it ensures the trading system never takes on excessive risk, protects profits with trailing stops, and halts trading before catastrophic losses can occur. It ties together all risk components from Module 2 into a single, authoritative gate that every trade must pass through.

**Core philosophy:** *"Never let a winner turn into a loser."*

### What Module 4 Adds

1. **Trailing Stop Manager** (`risk/trailing_stop.py`) — Dynamic stops that ratchet upward as price moves in your favor, locking in profits. Supports three strategies: ATR trail, percentage trail, and breakeven-then-trail.

2. **Master Risk Manager** (`risk/risk_manager.py`) — Single entry point for all risk decisions. Orchestrates position sizing, portfolio limits, trailing stops, sector concentration, and drawdown monitoring into one approve/deny gate.

**Module 4 Milestone:** The system automatically protects profits, enforces sector diversification, and will never let the account blow up.

---

## Components

### `risk/trailing_stop.py` — Trailing Stop Manager

Manages dynamic stop losses that **only move up, never down** (the ratchet rule). As the stock price increases, the trailing stop follows it upward, locking in gains.

**Three Strategies:**

| Strategy | Formula | Best For |
|----------|---------|----------|
| `atr` | `highest_price - (ATR × 1.5)` | Volatile stocks (adapts to volatility) |
| `percentage` | `highest_price × (1 - 0.03)` | Stable stocks (predictable trail) |
| `breakeven_then_trail` | Phase 1: Keep original stop until 1R profit. Phase 2: ATR trail. | Capital preservation priority |

**Key Methods:**

| Method | Description |
|--------|-------------|
| `register_position(symbol, entry_price, initial_stop, atr_value)` | Start tracking a position's trailing stop |
| `update(symbol, current_price, current_atr)` | Recalculate stop (ratchet up only) |
| `check_stop_hit(symbol, current_price)` | Returns True if price ≤ stop |
| `get_stop(symbol)` | Returns current trailing stop level |
| `get_all_stops()` | Returns dict of all stops |
| `remove_position(symbol)` | Stop tracking after position closed |

**Breakeven-Then-Trail Example:**
```
Entry: $100, Stop: $94 (R = $6)
  - Price at $104 → Stop stays at $94 (Phase 1: not yet 1R)
  - Price at $106 → Stop jumps to $100.10 (breakeven + 0.1% buffer)
  - Price at $115 → Stop trails to $110.50 (ATR trail: 115 - 3×1.5)
  - Price drops to $111 → Stop stays at $110.50 (ratchet holds)
  - Price drops to $110 → STOP HIT! Close position at $110.
```

### `risk/risk_manager.py` — Master Risk Manager

The **single gate** every trade must pass through. Runs 7 risk checks and returns an approve/deny decision.

**Pre-Trade Risk Checks (in order):**

| # | Check | Threshold | Action if Failed |
|---|-------|-----------|-----------------|
| 1 | Account balance floor | ≥ $500 | Reject trade |
| 2 | Max drawdown | < 15% from peak | Reject trade (requires manual reset) |
| 3 | Daily loss limit | < 5% daily loss | Reject trade (resets next day) |
| 4 | Max open positions | ≤ 3 positions | Reject trade |
| 5 | Sector concentration | ≤ 2 per sector | Reject trade |
| 6 | Valid risk (entry > stop) | Entry > stop loss | Reject trade |
| 7 | Position sizing | 2% risk rule | Reject if can't size |

**Key Methods:**

| Method | Description |
|--------|-------------|
| `evaluate_trade(symbol, entry, stop, ...)` | Run ALL checks → approve/deny dict |
| `register_fill(symbol, shares, entry, stop, ...)` | Register filled trade in all sub-managers |
| `update_price(symbol, current_price, atr)` | Update trailing stop + unrealized P&L |
| `close_position(symbol, exit_price, reason)` | Close position, update P&L and balance |
| `get_risk_summary()` | Full system-wide risk snapshot |
| `print_risk_report()` | Formatted console output |
| `reset_daily_state()` | Reset daily P&L for new trading day |
| `reset_drawdown_halt()` | Manual drawdown halt reset |

---

## Configuration Added (config/settings.py)

### Trailing Stop Settings
```python
TRAILING_STOP_METHOD = "atr"            # Default strategy
TRAILING_STOP_ATR_MULTIPLIER = 1.5      # Trail distance = ATR × 1.5
TRAILING_STOP_PERCENTAGE = 0.03         # 3% trailing distance
BREAKEVEN_TRIGGER_R_MULTIPLE = 1.0      # Move to breakeven at 1R profit
BREAKEVEN_BUFFER_PCT = 0.001            # 0.1% buffer above entry
```

### Risk Manager Settings
```python
MAX_SECTOR_CONCENTRATION = 2            # Max 2 positions in same sector
MAX_DRAWDOWN_PCT = 0.15                 # 15% drawdown = halt trading
MIN_ACCOUNT_BALANCE = 500.0             # Never trade below $500
```

---

## Usage

### Basic Trade Flow
```python
from risk.risk_manager import RiskManager

# Initialize with account balance
rm = RiskManager(account_balance=10000)

# Step 1: Evaluate a trade (the gate)
decision = rm.evaluate_trade(
    symbol="AAPL",
    entry_price=150.0,
    stop_loss=144.0,
    atr_value=3.0,
    scanner_score=8.0,
    signal_strength="STRONG",
    sector="Technology",
)

if decision["approved"]:
    # Step 2: Register the fill
    rm.register_fill(
        "AAPL", shares=decision["shares_to_buy"],
        entry_price=150.0, stop_loss=144.0,
        take_profit_1=162.0, take_profit_2=168.0,
        atr_value=3.0, sector="Technology",
    )

    # Step 3: Monitor (called periodically)
    result = rm.update_price("AAPL", current_price=158.0, current_atr=2.8)
    print(f"Trailing stop: ${result['trailing_stop']}")
    print(f"Unrealized P&L: ${result['unrealized_pnl']}")

    if result["stop_hit"]:
        # Step 4: Close on stop hit
        close = rm.close_position("AAPL", exit_price=158.0,
                                   reason="trailing_stop")
        print(f"P&L: ${close['realized_pnl']}")
```

### Using Trailing Stops Directly
```python
from risk.trailing_stop import TrailingStopManager

tsm = TrailingStopManager(method="breakeven_then_trail")
tsm.register_position("XOM", entry_price=80.0, initial_stop=76.0, atr_value=2.0)

# Price moves up
tsm.update("XOM", current_price=86.0)  # Breakeven triggered!
tsm.update("XOM", current_price=92.0)  # ATR trail kicks in

print(tsm.get_stop("XOM"))  # Dynamic stop level
```

---

## Tests

59 unit tests in `tests/test_module4.py`, organized into 14 test classes:

| Class | Tests | What It Covers |
|-------|-------|----------------|
| `TestTrailingStopInit` | 4 | Valid methods (ATR/pct/BE), invalid method raises |
| `TestTrailingStopRegistration` | 3 | Registration, multiple positions, unregistered |
| `TestATRTrailingStop` | 5 | Trail up, ratchet rule, updated ATR, zero ATR, unregistered |
| `TestPercentageTrailingStop` | 2 | Basic trail, ratchet rule |
| `TestBreakevenTrailingStop` | 3 | Phase 1 (no trail), Phase 2 (breakeven), Phase 2→ATR |
| `TestStopHitCheck` | 4 | At stop, below stop, above stop, unregistered |
| `TestTrailingStopHelpers` | 5 | Remove, remove nonexistent, get_all, get_state, copy safety |
| `TestRiskManagerInit` | 2 | Basic init, custom trailing method |
| `TestEvaluateTrade` | 9 | Approve valid, reject (balance/drawdown/daily/positions/sector/stop), log |
| `TestRegisterFill` | 2 | Success, blocked |
| `TestUpdatePrice` | 3 | PnL + stop update, stop hit detection, unknown symbol |
| `TestClosePosition` | 4 | Win, loss, peak balance update, nonexistent |
| `TestDrawdownMonitoring` | 4 | Initial, after loss, halt triggered, manual reset |
| `TestDayReset` | 2 | Clears daily state, preserves drawdown halt |
| `TestRiskSummary` | 5 | Structure, sector exposure, decision tracking, reporting |
| `TestModule4Settings` | 2 | Trailing stop config, risk manager config |

```bash
python -m pytest tests/test_module4.py -v
```

---

## How Module 4 Connects to Other Modules

```
Module 1 (Scanner)    Module 2 (Signals)
┌──────────────┐     ┌──────────────────┐
│ scanner.py   │────▶│ signals.py       │
│ Score 0-10   │     │ Entry/Stop/TP1/2 │
└──────────────┘     └────────┬─────────┘
                              │
                              ▼
                 Module 4 — RISK MANAGER (The Gate)
                 ┌─────────────────────────────────────┐
                 │  risk_manager.py (Orchestrator)      │
                 │  ├─ evaluate_trade() ← THE GATE     │
                 │  ├─ register_fill()                  │
                 │  ├─ update_price()                   │
                 │  └─ close_position()                 │
                 │                                      │
                 │  Uses:                               │
                 │  ├─ position_sizer.py (2% rule)     │
                 │  ├─ portfolio_risk.py (limits/P&L)  │
                 │  ├─ trailing_stop.py (dynamic stop) │
                 │  └─ macro.py sector data            │
                 └──────────────┬──────────────────────┘
                                │
                                ▼
                 Module 5 (Execution) — future
                 ┌──────────────────────┐
                 │ broker.py            │
                 │ orders.py            │
                 │ monitor.py           │
                 └──────────────────────┘
```

**Integration points:**
- `evaluate_trade()` uses `position_sizer.py` for share calculation
- `evaluate_trade()` uses `portfolio_risk.py` for position limits and daily P&L
- `register_fill()` starts trailing stops via `trailing_stop.py`
- `update_price()` ratchets trailing stops and updates unrealized P&L
- `close_position()` updates realized P&L, account balance, and drawdown tracking
- Sector concentration uses the `sector` field from `macro.py`'s watchlist mapping
