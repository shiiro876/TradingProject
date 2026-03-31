# =============================================================================
# dashboard/app.py — Main Dashboard (Command Center)
# =============================================================================
#
# PURPOSE:
#   The central dashboard that aggregates data from every module in the
#   trading system and presents a unified view of the system's current state.
#   This is the "command center" where you can see everything at a glance:
#
#     - Account status (balance, equity, P&L, drawdown)
#     - Open positions with trailing stops and unrealized P&L
#     - Trade journal performance stats (win rate, profit factor, etc.)
#     - ML model confidence and recommendations
#     - Recent alerts and exit log
#
#   The dashboard is designed to work without any external UI dependencies.
#   It produces rich console output using ASCII tables and formatted text.
#   A future Streamlit web dashboard can be layered on top of the same
#   data-gathering methods.
#
# KEY FUNCTIONS:
#   - Dashboard(risk_manager, order_manager, broker, journal, trainer)
#       Aggregates all system components into a single view.
#
#   - get_system_snapshot()       → Full state dict from all components.
#   - get_account_summary()      → Account balance, equity, positions.
#   - get_position_details()     → Open positions with P&L and stops.
#   - get_performance_overview() → Journal-based win rate, profit factor.
#   - get_model_status()         → ML model state and recent predictions.
#   - get_recent_alerts()        → Latest alerts from the alert manager.
#   - print_dashboard()          → Formatted full-screen console output.
#
# USAGE:
#   from dashboard.app import Dashboard
#   dash = Dashboard(risk_manager=rm, order_manager=om, broker=broker,
#                    journal=journal, trainer=trainer)
#   dash.print_dashboard()
#
# =============================================================================

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Dashboard:
    """
    Central dashboard that aggregates and displays the full trading system state.

    Pulls data from every module — risk manager, broker, order manager,
    trade journal, and ML trainer — to present a unified command center view.

    Attributes:
        risk_manager   (RiskManager | None):  Risk state and drawdown info.
        order_manager  (OrderManager | None): Active orders and positions.
        broker         (PaperBroker | None):  Account balance and positions.
        journal        (TradeJournal | None): Historical performance stats.
        trainer        (TradeTrainer | None): ML model confidence.
        alert_manager  (AlertManager | None): Notification/alert system.
    """

    def __init__(
        self,
        risk_manager=None,
        order_manager=None,
        broker=None,
        journal=None,
        trainer=None,
        alert_manager=None,
    ):
        """
        Initialize the dashboard with trading system components.

        All parameters are optional — the dashboard will gracefully handle
        missing components by showing "N/A" for unavailable data.

        Args:
            risk_manager:  RiskManager instance (Module 4).
            order_manager: OrderManager instance (Module 5).
            broker:        PaperBroker instance (Module 5).
            journal:       TradeJournal instance (Module 2).
            trainer:       TradeTrainer instance (Module 6).
            alert_manager: AlertManager instance (Module 7).
        """
        self.risk_manager = risk_manager
        self.order_manager = order_manager
        self.broker = broker
        self.journal = journal
        self.trainer = trainer
        self.alert_manager = alert_manager

        logger.info("Dashboard initialized.")

    def get_account_summary(self) -> dict:
        """
        Get the current account status from the broker and risk manager.

        Returns:
            Dictionary with:
                cash            (float): Available cash.
                equity          (float): Total equity (cash + positions).
                position_value  (float): Unrealized position value.
                open_positions  (int):   Number of open positions.
                paper_trading   (bool):  Whether in paper trading mode.
                current_drawdown (float): Current drawdown percentage.
                trading_halted  (bool):  Whether trading is halted.
        """
        account = {}

        if self.broker is not None:
            broker_data = self.broker.get_account()
            account["cash"] = broker_data.get("cash", 0.0)
            account["equity"] = broker_data.get("equity", 0.0)
            account["position_value"] = broker_data.get("position_value", 0.0)
            account["open_positions"] = broker_data.get("open_positions", 0)
            account["paper_trading"] = broker_data.get("paper_trading", True)
        else:
            account["cash"] = 0.0
            account["equity"] = 0.0
            account["position_value"] = 0.0
            account["open_positions"] = 0
            account["paper_trading"] = True

        if self.risk_manager is not None:
            try:
                risk_summary = self.risk_manager.get_risk_summary()
                account["current_drawdown"] = risk_summary.get("current_drawdown_pct", 0.0)
                account["trading_halted"] = risk_summary.get("trading_halted", False)
            except Exception:
                account["current_drawdown"] = 0.0
                account["trading_halted"] = False
        else:
            account["current_drawdown"] = 0.0
            account["trading_halted"] = False

        return account

    def get_position_details(self) -> list[dict]:
        """
        Get details of all open positions including P&L and stop levels.

        Returns:
            List of dicts, each with: symbol, shares, entry_price,
            current_price, unrealized_pnl, stop_loss, take_profit_1,
            take_profit_2, trailing_stop.
        """
        positions = []

        if self.broker is not None:
            broker_positions = self.broker.get_all_positions()
            for symbol, pos in broker_positions.items():
                detail = {
                    "symbol": symbol,
                    "shares": pos.get("shares", 0),
                    "entry_price": pos.get("avg_entry_price", 0.0),
                    "current_price": pos.get("current_price", 0.0),
                    "unrealized_pnl": pos.get("unrealized_pnl", 0.0),
                }

                # Enrich with risk manager data if available
                if self.risk_manager is not None:
                    try:
                        risk_summary = self.risk_manager.get_risk_summary()
                        ts_positions = risk_summary.get("trailing_stops", {})
                        if symbol in ts_positions:
                            ts = ts_positions[symbol]
                            detail["trailing_stop"] = ts.get("current_stop", 0.0)
                    except Exception:
                        pass

                # Enrich with order data if available
                if self.order_manager is not None:
                    try:
                        active = self.order_manager.get_active_orders()
                        if symbol in active:
                            order = active[symbol]
                            detail["stop_loss"] = order.get("stop_loss", 0.0)
                            detail["take_profit_1"] = order.get("take_profit_1", 0.0)
                            detail["take_profit_2"] = order.get("take_profit_2", 0.0)
                    except Exception:
                        pass

                positions.append(detail)

        return positions

    def get_performance_overview(self) -> dict:
        """
        Get performance statistics from the trade journal.

        Returns:
            Dictionary with journal performance stats (win rate, profit factor,
            total P&L, max drawdown, etc.) or zeroed values if unavailable.
        """
        if self.journal is not None:
            try:
                return self.journal.get_performance_stats()
            except Exception:
                pass

        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "total_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "max_drawdown": 0.0,
            "monthly_pnl": {},
        }

    def get_model_status(self) -> dict:
        """
        Get the ML model state and training summary.

        Returns:
            Dictionary with model trained status, accuracy, win rate,
            feature importance, and recommendation counts.
        """
        if self.trainer is not None:
            try:
                summary = self.trainer.get_training_summary()
                return {
                    "is_trained": summary.get("is_trained", False),
                    "training_stats": summary.get("training_stats", {}),
                    "feature_importance": summary.get("feature_importance", {}),
                }
            except Exception:
                pass

        return {
            "is_trained": False,
            "training_stats": {},
            "feature_importance": {},
        }

    def get_recent_alerts(self, limit: int = 10) -> list[dict]:
        """
        Get the most recent alerts from the alert manager.

        Args:
            limit: Maximum number of alerts to return.

        Returns:
            List of alert dicts (newest first).
        """
        if self.alert_manager is not None:
            try:
                return self.alert_manager.get_alert_history(limit=limit)
            except Exception:
                pass
        return []

    def get_system_snapshot(self) -> dict:
        """
        Get a complete snapshot of the entire trading system state.

        Aggregates data from all components into a single dictionary
        suitable for display, logging, or serialization.

        Returns:
            Dictionary with sections: account, positions, performance,
            model, alerts, timestamp.
        """
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account": self.get_account_summary(),
            "positions": self.get_position_details(),
            "performance": self.get_performance_overview(),
            "model": self.get_model_status(),
            "alerts": self.get_recent_alerts(),
        }

    def print_dashboard(self) -> None:
        """
        Print a comprehensive dashboard to the console.

        Shows all system state in a formatted ASCII display suitable
        for terminal viewing.
        """
        snapshot = self.get_system_snapshot()
        acct = snapshot["account"]
        perf = snapshot["performance"]
        model = snapshot["model"]
        positions = snapshot["positions"]
        alerts = snapshot["alerts"]

        mode = "📝 PAPER" if acct.get("paper_trading", True) else "🔴 LIVE"
        halted = "⛔ HALTED" if acct.get("trading_halted", False) else "✅ ACTIVE"

        print("\n" + "=" * 70)
        print(f"  🖥️  TRADING DASHBOARD — {snapshot['timestamp']}")
        print(f"  Mode: {mode}  |  Status: {halted}")
        print("=" * 70)

        # Account Section
        print("\n  📊 ACCOUNT")
        print("  " + "-" * 40)
        print(f"  Cash:             ${acct['cash']:>12,.2f}")
        print(f"  Equity:           ${acct['equity']:>12,.2f}")
        print(f"  Position Value:   ${acct['position_value']:>12,.2f}")
        print(f"  Open Positions:   {acct['open_positions']:>12}")
        dd = acct.get("current_drawdown", 0)
        print(f"  Drawdown:         {dd:>11.1f}%")

        # Performance Section
        print("\n  📈 PERFORMANCE")
        print("  " + "-" * 40)
        if perf["total_trades"] > 0:
            print(f"  Total Trades:     {perf['total_trades']:>12}")
            print(f"  Win Rate:         {perf['win_rate']:>11.1f}%")
            print(f"  Profit Factor:    {perf['profit_factor']:>12.2f}")
            print(f"  Total P&L:        ${perf['total_pnl']:>+11,.2f}")
            print(f"  Max Drawdown:     ${perf['max_drawdown']:>11,.2f}")
        else:
            print("  No trades recorded yet.")

        # Positions Section
        print("\n  📋 OPEN POSITIONS")
        print("  " + "-" * 66)
        if positions:
            print(
                f"  {'Symbol':<8} {'Shares':>7} {'Entry':>9} {'Current':>9} "
                f"{'P&L':>10} {'Stop':>9}"
            )
            print("  " + "-" * 66)
            for pos in positions:
                stop = pos.get("trailing_stop", pos.get("stop_loss", 0))
                print(
                    f"  {pos['symbol']:<8} {pos['shares']:>7} "
                    f"${pos['entry_price']:>8.2f} ${pos['current_price']:>8.2f} "
                    f"${pos['unrealized_pnl']:>+9.2f} ${stop:>8.2f}"
                )
        else:
            print("  No open positions.")

        # ML Model Section
        print("\n  🧠 ML MODEL")
        print("  " + "-" * 40)
        if model["is_trained"]:
            stats = model["training_stats"]
            print(f"  Status:           {'Trained ✅':>12}")
            print(f"  Accuracy:         {stats.get('accuracy', 0):>11.1%}")
            print(f"  Training Trades:  {stats.get('total_trades', 0):>12}")
        else:
            print("  Status:           Not trained")

        # Alerts Section
        print("\n  🔔 RECENT ALERTS")
        print("  " + "-" * 66)
        if alerts:
            for alert in alerts[:5]:
                level = alert.get("level", "INFO")
                msg = alert.get("message", "")
                ts = alert.get("timestamp", "")
                icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(level, "⚪")
                print(f"  {icon} [{ts}] {msg}")
        else:
            print("  No recent alerts.")

        print("\n" + "=" * 70 + "\n")
