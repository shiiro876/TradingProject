# 📦 Module 5 — Execution Engine (Phase 5)

**Status:** ✅ Complete  
**Phase:** 5 of 7  
**Files:** `execution/broker.py`, `execution/orders.py`, `execution/monitor.py`  
**Tests:** `tests/test_module5.py` (56 tests)  

---

## Overview

Module 5 is the **Execution Engine** — the bridge between trade signals and actual order placement. It manages the complete lifecycle of a trade:

```
Signal (Module 2) → Risk Gate (Module 4) → Order Placement → Fill → Monitoring → Exit
```

The module operates in **paper trading mode** by default, simulating all orders locally without any broker API dependency. This allows full development, testing, and validation before connecting to a live broker.

---

## Components

### `execution/broker.py` — Broker Interface & Paper Trading Simulator

Provides a unified interface for order execution, regardless of whether the system runs in paper or live mode.

**PaperBroker** simulates:
- Instant market fills at the requested price
- Account balance tracking (cash, equity, positions)
- Buy orders: deducts cash, adds/averages into positions
- Sell orders: adds cash, reduces/closes positions
- Partial sells (for TP1 partial closes)
- Order history logging with unique IDs

**Key Methods:**

| Method | Description |
|--------|-------------|
| `submit_order(symbol, shares, side, price)` | Place a buy or sell order |
| `get_account()` | Get cash, equity, position value |
| `get_position(symbol)` | Get a specific position |
| `get_all_positions()` | Get all open positions |
| `update_position_price(symbol, price)` | Update position's market price |
| `get_order_history()` | Get all order records |

**Factory Function:**
```python
from execution.broker import get_broker
broker = get_broker(account_balance=10000)  # Returns PaperBroker
```

### `execution/orders.py` — Order Lifecycle Manager

Coordinates the complete signal-to-fill workflow by tying together the RiskManager, PaperBroker, and TradeJournal.

**Workflow:**
1. Receive trade signal from `core/signals.py`
2. Validate through `RiskManager.evaluate_trade()` — the 7-check gate
3. If approved, place BUY order via broker
4. If filled, register in RiskManager (portfolio, trailing stop, sector)
5. Track active orders locally for monitoring

**Key Methods:**

| Method | Description |
|--------|-------------|
| `execute_signal(signal, sector)` | Full lifecycle: evaluate → place → register |
| `close_position(symbol, exit_price, reason)` | Sell, update risk, log to journal |
| `get_active_orders()` | Get all open order records |
| `get_active_symbols()` | List symbols with open positions |
| `has_position(symbol)` | Check if position exists |
| `get_execution_summary()` | Full state snapshot |

### `execution/monitor.py` — Position Monitor & Exit Manager

Automatically monitors open positions and triggers exits when conditions are met.

**Exit Conditions (checked in priority order):**
1. **Trailing Stop Hit** → Close entire position (via RiskManager)
2. **Take Profit 2** → Close entire remaining position
3. **Take Profit 1** → Close 50% of position (partial exit, only once)

**Key Methods:**

| Method | Description |
|--------|-------------|
| `check_position(symbol, price, atr)` | Check one position for exits |
| `check_all_positions(price_data)` | Check all positions at once |
| `run_monitoring_cycle(price_fetcher)` | Single pass using a callback |
| `get_monitoring_summary()` | Current state snapshot |
| `print_monitoring_report()` | Formatted console output |

---

## Usage

### Complete Trade Lifecycle

```python
from execution.broker import get_broker
from execution.orders import OrderManager
from execution.monitor import PositionMonitor
from risk.risk_manager import RiskManager
from learning.journal import TradeJournal

# Initialize all components
rm = RiskManager(account_balance=10000)
broker = get_broker(account_balance=10000)
journal = TradeJournal()
om = OrderManager(rm, broker, journal)
monitor = PositionMonitor(om, rm)

# 1. Execute a trade signal
signal = {
    "symbol": "AAPL",
    "entry_price": 150.0,
    "stop_loss": 144.0,
    "take_profit_1": 162.0,
    "take_profit_2": 168.0,
    "risk_per_share": 6.0,
    "scanner_score": 8.0,
    "signal_strength": "STRONG",
}

result = om.execute_signal(signal, sector="Technology")
if result["status"] == "filled":
    print(f"Bought {result['shares']} shares at ${result['entry_price']}")

# 2. Monitor positions (called periodically)
price_data = {"AAPL": {"price": 155.0, "atr": 3.0}}
actions = monitor.check_all_positions(price_data)

# 3. Or use a price fetcher callback
def fetch_prices(symbols):
    # Could use yfinance, Alpaca, etc.
    return {"AAPL": {"price": 162.0}}

actions = monitor.run_monitoring_cycle(price_fetcher=fetch_prices)

# 4. Manual close if needed
result = om.close_position("AAPL", exit_price=160.0, reason="manual")
```

### Monitoring with Auto-Exits

```python
# TP1 Partial Close (50% of shares)
# When price reaches $162 (TP1), monitor automatically:
#   - Sells 50% of shares
#   - Logs partial close to journal
#   - Keeps remaining shares running toward TP2

# TP2 Full Close
# When price reaches $168 (TP2), monitor automatically:
#   - Sells all remaining shares
#   - Logs full close to journal
#   - Removes position from all trackers

# Trailing Stop Exit
# If price drops to trailing stop level:
#   - Sells all shares immediately
#   - Logs stop loss exit to journal
```

---

## Configuration (config/settings.py)

```python
# Module 5 settings
DEFAULT_ORDER_TYPE = "market"          # Order type for entries
MONITOR_INTERVAL_SECONDS = 60          # How often to check positions
TP1_CLOSE_RATIO = 0.50                 # Close 50% at TP1
```

---

## Architecture

```
                    ┌─────────────────────────┐
                    │   core/signals.py        │
                    │   Trade Signal Dict      │
                    └───────────┬─────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                  execution/orders.py — OrderManager               │
│                                                                   │
│   execute_signal()                                                │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │ RiskManager   │───▶│ PaperBroker  │───▶│ register_fill│      │
│   │ evaluate_trade│    │ submit_order │    │ (all trackers)│      │
│   └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                   │
│   close_position()                                                │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │ PaperBroker  │───▶│ RiskManager  │───▶│ TradeJournal │      │
│   │ submit_sell   │    │ close_position│   │ log_trade    │      │
│   └──────────────┘    └──────────────┘    └──────────────┘      │
└───────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                execution/monitor.py — PositionMonitor             │
│                                                                   │
│   check_position() / check_all_positions()                        │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │ update_price  │───▶│ check_stop   │───▶│ auto-exit    │      │
│   │ (trail ratchet│    │ check TP2    │    │ via OrderMgr │      │
│   │  + P&L update)│    │ check TP1    │    │              │      │
│   └──────────────┘    └──────────────┘    └──────────────┘      │
└───────────────────────────────────────────────────────────────────┘
```

---

## Tests

56 unit tests in `tests/test_module5.py`, organized into 18 test classes:

| Class | Tests | What It Covers |
|-------|-------|----------------|
| `TestPaperBrokerInit` | 2 | Balance init, get_account |
| `TestPaperBrokerBuy` | 5 | Basic buy, insufficient funds, averaging, zero shares, negative price |
| `TestPaperBrokerSell` | 5 | Basic sell, partial sell, no position, oversell, loss |
| `TestPaperBrokerInvalidSide` | 1 | Invalid order side rejection |
| `TestPaperBrokerHelpers` | 6 | get_position, get_all, update_price, order history, equity |
| `TestGetBroker` | 1 | Factory returns PaperBroker |
| `TestOrderManagerInit` | 1 | Initialization |
| `TestExecuteSignal` | 6 | Approved, rejected, registered, multiple, max positions, insufficient funds |
| `TestClosePosition` | 4 | Win, loss, nonexistent, journal logging |
| `TestOrderManagerHelpers` | 3 | Active symbols, has_position, summary |
| `TestSignalRR` | 3 | Valid R:R, missing TP1, invalid setup |
| `TestMonitorInit` | 1 | Initialization |
| `TestMonitorTrailingStop` | 2 | Stop hit exit, no action above stop |
| `TestMonitorTP2` | 1 | Full exit at TP2 |
| `TestMonitorTP1` | 3 | Partial exit, only-once rule, TP1→TP2 lifecycle |
| `TestMonitorCheckAll` | 2 | Batch checking, no data |
| `TestMonitorRunCycle` | 3 | With fetcher, no fetcher, no positions |
| `TestMonitorSummary` | 3 | Structure, report printing, exit log |
| `TestMonitorCheckUnknownPosition` | 1 | Unknown symbol |
| `TestFullTradeLifecycle` | 2 | Full TP1→TP2 lifecycle, stop loss lifecycle |
| `TestModule5Settings` | 1 | Config values |

```bash
python -m pytest tests/test_module5.py -v
```

---

## How Module 5 Connects to Other Modules

| Module | Connection | Direction |
|--------|-----------|-----------|
| Module 2 (Signals) | `core/signals.py` output → `execute_signal()` input | Input |
| Module 4 (Risk) | `RiskManager.evaluate_trade()` gate | Gate |
| Module 4 (Risk) | `RiskManager.register_fill()`, `update_price()`, `close_position()` | Integration |
| Module 2 (Journal) | `TradeJournal.log_trade()` on every close | Output |
| Module 7 (Dashboard) | `get_execution_summary()`, `get_monitoring_summary()` | Output |
