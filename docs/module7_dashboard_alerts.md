# Module 7 — Dashboard & Alerts

> **Files:** `dashboard/app.py`, `dashboard/charts.py`, `dashboard/alerts.py`  
> **Tests:** `tests/test_module7.py` (70 tests)

---

## Overview

Module 7 is the final module of the TradingBot system. It provides a unified **command center** that aggregates data from every module (scanner, signals, risk, execution, journal, ML model) and presents it in a single dashboard view. It also includes **ASCII chart generators** for terminal-based visualization and a **Telegram notification system** for real-time alerts.

### Components

| File | Class | Purpose |
|------|-------|---------|
| `dashboard/app.py` | `Dashboard` | Main dashboard that aggregates all system state |
| `dashboard/charts.py` | *(functions)* | Text-based chart renderers (equity, P&L, drawdown) |
| `dashboard/alerts.py` | `AlertManager` | Alert creation, storage, and Telegram delivery |

---

## dashboard/app.py — Dashboard (Command Center)

The `Dashboard` class pulls data from every trading system component and presents a unified view.

### Constructor

```python
Dashboard(
    risk_manager=None,    # RiskManager instance (Module 4)
    order_manager=None,   # OrderManager instance (Module 5)
    broker=None,          # PaperBroker instance (Module 5)
    journal=None,         # TradeJournal instance (Module 2)
    trainer=None,         # TradeTrainer instance (Module 6)
    alert_manager=None,   # AlertManager instance (Module 7)
)
```

All parameters are optional — the dashboard gracefully handles missing components.

### Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_account_summary()` | `dict` | Cash, equity, positions, drawdown, halt status |
| `get_position_details()` | `list[dict]` | Open positions with P&L, stops, targets |
| `get_performance_overview()` | `dict` | Journal stats (win rate, PF, total P&L) |
| `get_model_status()` | `dict` | ML model trained status, accuracy, features |
| `get_recent_alerts(limit)` | `list[dict]` | Recent alerts from AlertManager |
| `get_system_snapshot()` | `dict` | Full state across all sections |
| `print_dashboard()` | `None` | Formatted ASCII dashboard to console |

### Usage

```python
from dashboard.app import Dashboard

dash = Dashboard(
    risk_manager=rm,
    order_manager=om,
    broker=broker,
    journal=journal,
    trainer=trainer,
    alert_manager=alerts,
)

# Full console dashboard
dash.print_dashboard()

# Programmatic access
snapshot = dash.get_system_snapshot()
print(f"Account equity: ${snapshot['account']['equity']:,.2f}")
print(f"Win rate: {snapshot['performance']['win_rate']:.1f}%")
```

---

## dashboard/charts.py — Text-Based Chart Generators

All chart functions return multi-line strings suitable for console output.

### Functions

| Function | Input | Description |
|----------|-------|-------------|
| `render_equity_curve(equity_data)` | `list[dict]` | ASCII line chart of balance over time |
| `render_pnl_bars(pnl_data)` | `dict[str, float]` | Horizontal bar chart of P&L by period |
| `render_win_loss_chart(stats)` | `dict` | Win/loss ratio visualization with stats |
| `render_drawdown_chart(equity_data)` | `list[dict]` | Drawdown percentage over time |
| `render_sector_heatmap(sector_data)` | `dict[str, int]` | Sector concentration display |
| `render_sparkline(values)` | `list[float]` | Compact inline sparkline (Unicode blocks) |
| `render_trade_table(trades)` | `list[dict]` | Formatted table of recent trades |

### Usage

```python
from dashboard.charts import (
    render_equity_curve,
    render_pnl_bars,
    render_win_loss_chart,
    render_sparkline,
)

# Equity curve from backtester
equity = backtester.get_equity_curve()
print(render_equity_curve(equity))

# Monthly P&L from journal
stats = journal.get_performance_stats()
print(render_pnl_bars(stats["monthly_pnl"]))
print(render_win_loss_chart(stats))

# Inline sparkline
values = [e["equity"] for e in equity]
print(f"Performance: {render_sparkline(values)}")
```

---

## dashboard/alerts.py — Alert & Notification Manager

The `AlertManager` handles alert creation, in-memory storage, and optional Telegram delivery.

### Alert Levels

| Level | Icon | Description |
|-------|------|-------------|
| `INFO` | 🟢 | Routine events (trade fills, position opened) |
| `WARNING` | 🟡 | Needs attention (approaching limits, losing trades) |
| `CRITICAL` | 🔴 | Immediate action needed (halt, system error) |

### Constructor

```python
AlertManager(
    telegram_token=None,    # Telegram Bot API token (defaults to config)
    telegram_chat_id=None,  # Telegram chat ID (defaults to config)
)
```

### Key Methods

| Method | Args | Description |
|--------|------|-------------|
| `send_alert(message, level)` | `str`, `str` | Create and deliver an alert |
| `alert_trade_fill(symbol, side, shares, price)` | — | Alert for trade fill |
| `alert_position_exit(symbol, reason, pnl, exit_price)` | — | Alert for position exit |
| `alert_drawdown_warning(drawdown_pct)` | `float` | Drawdown threshold alert |
| `alert_trading_halted(reason)` | `str` | Critical halt alert |
| `alert_daily_loss_limit(daily_loss_pct)` | `float` | Daily loss limit alert |
| `alert_system_error(error_message)` | `str` | System error alert |
| `get_alert_history(limit)` | `int` | Recent alerts (newest first) |
| `get_alert_summary()` | — | Count alerts by level |
| `clear_history()` | — | Clear all stored alerts |
| `print_alert_summary()` | — | Formatted summary to console |

### Usage

```python
from dashboard.alerts import AlertManager

# Initialize (Telegram is optional)
alerts = AlertManager()

# Convenience methods with auto-level
alerts.alert_trade_fill("AAPL", "buy", 33, 150.0)       # → INFO
alerts.alert_position_exit("AAPL", "tp1", 150.0, 162.0)  # → INFO (winning)
alerts.alert_position_exit("XOM", "stop", -80.0, 72.0)   # → WARNING (losing)
alerts.alert_drawdown_warning(12.5)                        # → WARNING (10-15%)
alerts.alert_drawdown_warning(16.0)                        # → CRITICAL (≥15%)
alerts.alert_trading_halted("Max drawdown exceeded")       # → CRITICAL

# View history
for alert in alerts.get_alert_history(limit=5):
    print(f"[{alert['level']}] {alert['message']}")

# Summary
alerts.print_alert_summary()
```

### Telegram Setup

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get the bot token and your chat ID
3. Add to `config/.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

---

## Configuration

Settings added to `config/settings.py`:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ALERT_HISTORY_MAX` | 200 | Max alerts to keep in memory |
| `DASHBOARD_RECENT_TRADES` | 10 | Recent trades shown in dashboard |
| `CHART_WIDTH` | 60 | Default chart width in characters |
| `CHART_HEIGHT` | 15 | Default chart height in rows |
| `TELEGRAM_BOT_TOKEN` | `""` | Telegram Bot API token (from .env) |
| `TELEGRAM_CHAT_ID` | `""` | Telegram chat ID (from .env) |

---

## Tests

Run Module 7 tests:

```bash
python -m pytest tests/test_module7.py -v
```

**70 tests** across 20 test classes:

| Test Class | Count | What It Tests |
|------------|-------|---------------|
| `TestDashboardInit` | 2 | Dashboard initialization |
| `TestDashboardAccountSummary` | 3 | Account data aggregation |
| `TestDashboardPositions` | 3 | Position detail enrichment |
| `TestDashboardPerformance` | 2 | Journal performance stats |
| `TestDashboardModelStatus` | 3 | ML model status reporting |
| `TestDashboardAlerts` | 2 | Alert manager integration |
| `TestDashboardSystemSnapshot` | 2 | Full system snapshot |
| `TestDashboardPrint` | 3 | Console output formatting |
| `TestEquityCurve` | 3 | Equity curve chart rendering |
| `TestPnlBars` | 3 | P&L bar chart rendering |
| `TestWinLossChart` | 2 | Win/loss visualization |
| `TestDrawdownChart` | 2 | Drawdown chart rendering |
| `TestSectorHeatmap` | 2 | Sector concentration display |
| `TestSparkline` | 4 | Sparkline generation |
| `TestTradeTable` | 2 | Trade table formatting |
| `TestAlertManagerInit` | 2 | AlertManager initialization |
| `TestAlertSending` | 5 | Alert creation and storage |
| `TestAlertConvenienceMethods` | 11 | All convenience alert types |
| `TestAlertHistory` | 2 | History retrieval and ordering |
| `TestAlertSummary` | 4 | Summary counting and clearing |
| `TestTelegramIntegration` | 4 | Telegram delivery (mocked) |
| `TestDashboardAlertIntegration` | 1 | Dashboard ↔ AlertManager |
| `TestDashboardChartsIntegration` | 1 | All charts with realistic data |
| `TestModule7Settings` | 2 | Config settings verification |

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   Dashboard                       │
│  ┌────────────┐ ┌──────────┐ ┌───────────────┐  │
│  │   Broker   │ │  Risk    │ │    Journal    │  │
│  │  (Mod 5)   │ │  Manager │ │    (Mod 2)    │  │
│  │ - cash     │ │  (Mod 4) │ │ - win rate    │  │
│  │ - equity   │ │ - draw%  │ │ - PF          │  │
│  │ - pos      │ │ - halted │ │ - total P&L   │  │
│  └────────────┘ └──────────┘ └───────────────┘  │
│  ┌────────────┐ ┌──────────┐ ┌───────────────┐  │
│  │   Order    │ │ Trainer  │ │    Alert      │  │
│  │  Manager   │ │  (Mod 6) │ │   Manager     │  │
│  │  (Mod 5)   │ │ - model  │ │  (Mod 7)      │  │
│  │ - active   │ │ - acc    │ │ - history     │  │
│  │ - stops    │ │ - feat   │ │ - Telegram    │  │
│  └────────────┘ └──────────┘ └───────────────┘  │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │           Charts Module                   │    │
│  │ equity_curve | pnl_bars | drawdown        │    │
│  │ sparkline | sector_heatmap | trade_table   │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```
