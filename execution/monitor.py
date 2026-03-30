# =============================================================================
# execution/monitor.py — Position Monitor & Exit Manager
# =============================================================================
#
# PURPOSE:
#   Continuously monitors open positions and automatically triggers exits
#   when predefined conditions are met:
#
#     1. Trailing stop hit  — Price falls to or below the trailing stop.
#     2. Take Profit 1 hit  — Price reaches TP1, close 50% of position.
#     3. Take Profit 2 hit  — Price reaches TP2, close remaining position.
#     4. Daily loss limit   — System-wide halt triggered by portfolio risk.
#
#   This module is the "autopilot" that manages exits without human
#   intervention. It works by periodically checking each open position
#   against its exit levels and triggering the appropriate action.
#
# KEY FUNCTIONS:
#   - PositionMonitor(order_manager, risk_manager)
#       Class that scans positions and auto-exits.
#
#   - check_position(symbol, current_price, current_atr)
#       Checks one position for exit conditions.
#
#   - check_all_positions(price_data)
#       Checks all open positions at once.
#
#   - run_monitoring_cycle(price_fetcher)
#       Single monitoring pass using a price fetcher callback.
#
# USAGE:
#   from execution.monitor import PositionMonitor
#   monitor = PositionMonitor(order_manager, risk_manager)
#   actions = monitor.check_all_positions({"AAPL": {"price": 160.0}})
#   for action in actions:
#       print(f"{action['symbol']}: {action['action']} at ${action['price']}")
#
# =============================================================================

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class PositionMonitor:
    """
    Monitors open positions and triggers automatic exits.

    Checks each position against:
      - Trailing stop (via RiskManager.update_price)
      - Take Profit 1 (close 50%)
      - Take Profit 2 (close remaining)

    Attributes:
        order_manager  (OrderManager): The order manager for executing closes.
        risk_manager   (RiskManager):  The risk manager for price updates.
        tp1_triggered  (set):          Symbols that have already hit TP1.
        exit_log       (list):         Log of all auto-exit actions.
    """

    def __init__(self, order_manager, risk_manager):
        """
        Initialize the position monitor.

        Args:
            order_manager: OrderManager instance for closing positions.
            risk_manager:  RiskManager instance for price updates and stops.
        """
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.tp1_triggered: set[str] = set()
        self.exit_log: list[dict] = []

        logger.info("PositionMonitor initialized.")

    def check_position(
        self,
        symbol: str,
        current_price: float,
        current_atr: float | None = None,
    ) -> dict | None:
        """
        Check a single position for exit conditions.

        Updates the trailing stop via RiskManager, then checks:
          1. Trailing stop hit → close entire position
          2. Take Profit 2 hit → close entire remaining position
          3. Take Profit 1 hit → close 50% of position (only once)

        TP2 is checked BEFORE TP1 so that if price gaps through both levels,
        we exit at the better price rather than doing a partial close.

        Args:
            symbol:        Stock ticker.
            current_price: Latest market price.
            current_atr:   Updated ATR value (optional).

        Returns:
            Action dict if an exit was triggered, or None if no action needed.
        """
        # Get active order record
        order_record = self.order_manager.active_orders.get(symbol)
        if order_record is None:
            return None

        # Update price in risk manager (ratchets trailing stop)
        update = self.risk_manager.update_price(
            symbol=symbol,
            current_price=current_price,
            current_atr=current_atr,
        )

        if update is None:
            return None

        # Check 1: Trailing stop hit → close full position
        if update["stop_hit"]:
            exit_price = update["trailing_stop"] if update["trailing_stop"] else current_price
            result = self.order_manager.close_position(
                symbol=symbol,
                exit_price=exit_price,
                reason="trailing_stop",
            )
            if result:
                self.tp1_triggered.discard(symbol)
                action = {
                    "symbol": symbol,
                    "action": "trailing_stop_exit",
                    "price": exit_price,
                    "shares_closed": result["shares"],
                    "realized_pnl": result["realized_pnl"],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.exit_log.append(action)
                logger.info(
                    "AUTO-EXIT [STOP]: %s — closed at $%.2f, P&L=$%+.2f.",
                    symbol, exit_price, result["realized_pnl"],
                )
                return action
            return None

        # Check 2: Take Profit 2 hit → close full remaining position
        tp2 = order_record.get("take_profit_2")
        if tp2 and current_price >= tp2:
            result = self.order_manager.close_position(
                symbol=symbol,
                exit_price=current_price,
                reason="tp2",
            )
            if result:
                self.tp1_triggered.discard(symbol)
                action = {
                    "symbol": symbol,
                    "action": "tp2_exit",
                    "price": current_price,
                    "shares_closed": result["shares"],
                    "realized_pnl": result["realized_pnl"],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.exit_log.append(action)
                logger.info(
                    "AUTO-EXIT [TP2]: %s — closed at $%.2f, P&L=$%+.2f.",
                    symbol, current_price, result["realized_pnl"],
                )
                return action
            return None

        # Check 3: Take Profit 1 hit → close 50% (only once per position)
        tp1 = order_record.get("take_profit_1")
        if tp1 and current_price >= tp1 and symbol not in self.tp1_triggered:
            total_shares = order_record["shares"]
            shares_to_close = max(1, total_shares // 2)

            # Sell partial via broker
            sell_result = self.order_manager.broker.submit_order(
                symbol=symbol,
                shares=shares_to_close,
                side="sell",
                price=current_price,
            )

            if sell_result["status"] == "filled":
                # Update the active order record with remaining shares
                order_record["shares"] = total_shares - shares_to_close

                # Update portfolio position
                if symbol in self.risk_manager.portfolio.open_positions:
                    pos = self.risk_manager.portfolio.open_positions[symbol]
                    pos["shares"] = order_record["shares"]

                # Mark TP1 as triggered
                self.tp1_triggered.add(symbol)

                realized_pnl = sell_result.get("realized_pnl", 0)

                # Log partial close to journal
                if self.order_manager.journal is not None:
                    self.order_manager.journal.log_trade(
                        symbol=symbol,
                        direction="LONG",
                        entry_price=order_record["entry_price"],
                        exit_price=current_price,
                        shares=shares_to_close,
                        stop_loss=order_record.get("stop_loss"),
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                        exit_reason="tp1",
                        notes=f"Partial close: {shares_to_close}/{total_shares} shares",
                    )

                action = {
                    "symbol": symbol,
                    "action": "tp1_partial_exit",
                    "price": current_price,
                    "shares_closed": shares_to_close,
                    "shares_remaining": order_record["shares"],
                    "realized_pnl": realized_pnl,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.exit_log.append(action)
                logger.info(
                    "AUTO-EXIT [TP1]: %s — sold %d/%d shares at $%.2f, "
                    "P&L=$%+.2f. Remaining: %d shares.",
                    symbol, shares_to_close, total_shares,
                    current_price, realized_pnl, order_record["shares"],
                )
                return action

        # No action needed
        return None

    def check_all_positions(
        self,
        price_data: dict[str, dict],
    ) -> list[dict]:
        """
        Check all open positions for exit conditions.

        Args:
            price_data: Dictionary mapping symbol -> {"price": float,
                        "atr": float (optional)}.

        Returns:
            List of action dicts for all exits triggered this cycle.
        """
        actions = []

        # Iterate over a copy of active symbols since closing modifies the dict
        symbols = list(self.order_manager.active_orders.keys())

        for symbol in symbols:
            data = price_data.get(symbol)
            if data is None:
                continue

            current_price = data.get("price", 0)
            current_atr = data.get("atr")

            if current_price <= 0:
                continue

            action = self.check_position(symbol, current_price, current_atr)
            if action:
                actions.append(action)

        return actions

    def run_monitoring_cycle(
        self,
        price_fetcher=None,
    ) -> list[dict]:
        """
        Run a single monitoring pass using a price fetcher callback.

        The price_fetcher is called with a list of symbols and should return
        a dict mapping symbol -> {"price": float, "atr": float (optional)}.

        This method enables flexible integration: the caller provides the
        function that fetches current prices (from yfinance, Alpaca, etc.).

        Args:
            price_fetcher: Callable(list[str]) -> dict[str, dict].
                           If None, no monitoring is performed.

        Returns:
            List of exit actions triggered during this cycle.
        """
        if price_fetcher is None:
            return []

        symbols = self.order_manager.get_active_symbols()
        if not symbols:
            return []

        price_data = price_fetcher(symbols)
        return self.check_all_positions(price_data)

    def get_exit_log(self) -> list[dict]:
        """
        Get the full exit action log.

        Returns:
            List of all auto-exit action dictionaries.
        """
        return list(self.exit_log)

    def get_monitoring_summary(self) -> dict:
        """
        Get a summary of the monitor's current state.

        Returns:
            Dictionary with position counts, TP1 triggers, and exit stats.
        """
        active_count = len(self.order_manager.active_orders)
        tp1_count = len(self.tp1_triggered)
        total_exits = len(self.exit_log)

        exit_by_reason = {}
        for action in self.exit_log:
            reason = action.get("action", "unknown")
            exit_by_reason[reason] = exit_by_reason.get(reason, 0) + 1

        total_realized = sum(
            a.get("realized_pnl", 0) for a in self.exit_log
        )

        return {
            "active_positions": active_count,
            "tp1_triggered": tp1_count,
            "total_exits": total_exits,
            "exits_by_reason": exit_by_reason,
            "total_realized_pnl": round(total_realized, 2),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def print_monitoring_report(self) -> None:
        """
        Print a formatted monitoring status report.
        """
        summary = self.get_monitoring_summary()

        print("\n" + "=" * 70)
        print(f"  📡 POSITION MONITOR — "
              f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 70)

        print(f"\n  Active Positions:   {summary['active_positions']}")
        print(f"  TP1 Triggered:      {summary['tp1_triggered']}")
        print(f"  Total Exits:        {summary['total_exits']}")
        print(f"  Realized P&L:       ${summary['total_realized_pnl']:+,.2f}")

        if summary["exits_by_reason"]:
            print(f"\n  Exits by Reason:")
            for reason, count in summary["exits_by_reason"].items():
                print(f"    {reason:<25} {count}")

        # Show recent exits
        if self.exit_log:
            print(f"\n  Recent Exits:")
            for action in self.exit_log[-5:]:
                pnl = action.get("realized_pnl", 0)
                print(
                    f"    {action['symbol']:<8} {action['action']:<25} "
                    f"${action['price']:>8.2f}  P&L=${pnl:>+8.2f}"
                )

        print("=" * 70 + "\n")
