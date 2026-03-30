# =============================================================================
# execution/orders.py — Order Lifecycle Manager
# =============================================================================
#
# PURPOSE:
#   Manages the complete lifecycle of a trade order from signal to fill:
#
#     Signal → Risk Check → Order Placement → Fill → Registration
#
#   This is the bridge between the signal generator (Module 2) and the broker
#   (execution/broker.py). It takes a trade signal dict, validates it through
#   the RiskManager gate, places the order via the broker, and registers the
#   fill in all risk trackers.
#
# KEY FUNCTIONS:
#   - OrderManager(risk_manager, broker, journal)
#       Class that coordinates signal-to-fill workflow.
#
#   - execute_signal(signal)
#       Evaluates a signal, places an order if approved, registers the fill.
#       Returns order result with risk decision, fill details, and status.
#
#   - close_position(symbol, exit_price, reason)
#       Sells a position, updates risk trackers, and logs to journal.
#
#   - get_pending_orders() / get_filled_orders()
#       Query order state.
#
# USAGE:
#   from execution.orders import OrderManager
#   from execution.broker import get_broker
#   from risk.risk_manager import RiskManager
#   from learning.journal import TradeJournal
#
#   rm = RiskManager(account_balance=10000)
#   broker = get_broker(account_balance=10000)
#   journal = TradeJournal()
#   om = OrderManager(rm, broker, journal)
#
#   result = om.execute_signal(signal)
#   if result["status"] == "filled":
#       print(f"Bought {result['shares']} shares of {result['symbol']}")
#
# =============================================================================

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Coordinates the complete order lifecycle: signal → risk gate → broker
    → fill registration → journal logging.

    This class ties together the RiskManager (Module 4), PaperBroker
    (execution/broker.py), and TradeJournal (Module 2) into a single
    workflow.

    Attributes:
        risk_manager (RiskManager):  The master risk orchestrator.
        broker       (PaperBroker):  The broker for placing orders.
        journal      (TradeJournal): The trade journal for logging.
        active_orders (dict):        Mapping of symbol -> fill record.
    """

    def __init__(self, risk_manager, broker, journal=None):
        """
        Initialize the order manager.

        Args:
            risk_manager: RiskManager instance for pre-trade validation.
            broker:       PaperBroker (or live broker) for order execution.
            journal:      TradeJournal for logging trades (optional).
        """
        self.risk_manager = risk_manager
        self.broker = broker
        self.journal = journal
        self.active_orders: dict[str, dict] = {}

        logger.info("OrderManager initialized.")

    def execute_signal(
        self,
        signal: dict,
        sector: str | None = None,
    ) -> dict:
        """
        Execute a trade signal through the full lifecycle.

        Steps:
          1. Extract entry/stop/target from signal dict.
          2. Run through RiskManager.evaluate_trade() gate.
          3. If approved, place BUY order via broker.
          4. If filled, register in RiskManager and track locally.
          5. Return comprehensive result dict.

        Args:
            signal: Trade signal dict from core/signals.py containing at
                    minimum: symbol, entry_price, stop_loss, take_profit_1,
                    take_profit_2, scanner_score, signal_strength.
            sector: Stock's sector for concentration tracking (optional).

        Returns:
            Dictionary with status ("filled", "rejected", "failed"),
            risk decision, fill details, and error info if applicable.
        """
        symbol = signal.get("symbol", "UNKNOWN")
        entry_price = signal.get("entry_price", 0)
        stop_loss = signal.get("stop_loss", 0)
        take_profit_1 = signal.get("take_profit_1")
        take_profit_2 = signal.get("take_profit_2")
        atr_value = signal.get("risk_per_share", 0) / 2.0 if signal.get("risk_per_share") else 0
        scanner_score = signal.get("scanner_score", 0)
        signal_strength = signal.get("signal_strength", "WEAK")

        # Step 1: Risk gate
        decision = self.risk_manager.evaluate_trade(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss=stop_loss,
            atr_value=atr_value,
            scanner_score=scanner_score,
            signal_strength=signal_strength,
            sector=sector,
        )

        if not decision["approved"]:
            logger.info(
                "Signal REJECTED for %s: %s",
                symbol, "; ".join(decision["reasons"]),
            )
            return {
                "status": "rejected",
                "symbol": symbol,
                "decision": decision,
                "fill": None,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        shares = decision["shares_to_buy"]

        # Step 2: Place order via broker
        fill = self.broker.submit_order(
            symbol=symbol,
            shares=shares,
            side="buy",
            price=entry_price,
        )

        if fill["status"] != "filled":
            logger.warning(
                "Order FAILED for %s: %s",
                symbol, fill.get("reason", "unknown"),
            )
            return {
                "status": "failed",
                "symbol": symbol,
                "decision": decision,
                "fill": fill,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        # Step 3: Register fill in risk manager
        self.risk_manager.register_fill(
            symbol=symbol,
            shares=shares,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            atr_value=atr_value,
            sector=sector,
        )

        # Step 4: Track locally
        self.active_orders[symbol] = {
            "symbol": symbol,
            "shares": shares,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "sector": sector,
            "signal_strength": signal_strength,
            "scanner_score": scanner_score,
            "fill": fill,
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        logger.info(
            "Signal EXECUTED: %s — %d shares @ $%.2f. "
            "Stop=$%.2f, TP1=$%.2f, TP2=$%.2f.",
            symbol, shares, entry_price, stop_loss,
            take_profit_1 or 0, take_profit_2 or 0,
        )

        return {
            "status": "filled",
            "symbol": symbol,
            "shares": shares,
            "entry_price": entry_price,
            "decision": decision,
            "fill": fill,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "manual",
    ) -> dict | None:
        """
        Close an open position: sell via broker, update risk, log to journal.

        Args:
            symbol:     Stock ticker.
            exit_price: Price at which to sell.
            reason:     Exit reason: "trailing_stop", "tp1", "tp2", "manual".

        Returns:
            Dictionary with closing details, or None if position not found.
        """
        order_record = self.active_orders.get(symbol)
        if order_record is None:
            logger.warning("Cannot close '%s': no active order tracked.", symbol)
            return None

        shares = order_record["shares"]
        entry_price = order_record["entry_price"]

        # Step 1: Sell via broker
        sell_result = self.broker.submit_order(
            symbol=symbol,
            shares=shares,
            side="sell",
            price=exit_price,
        )

        if sell_result["status"] != "filled":
            logger.warning(
                "Sell order FAILED for %s: %s",
                symbol, sell_result.get("reason", "unknown"),
            )
            return None

        # Step 2: Close in risk manager
        rm_result = self.risk_manager.close_position(
            symbol=symbol,
            exit_price=exit_price,
            reason=reason,
        )

        # Step 3: Log to journal
        if self.journal is not None:
            self.journal.log_trade(
                symbol=symbol,
                direction="LONG",
                entry_price=entry_price,
                exit_price=exit_price,
                shares=shares,
                stop_loss=order_record.get("stop_loss"),
                take_profit_1=order_record.get("take_profit_1"),
                take_profit_2=order_record.get("take_profit_2"),
                risk_reward=signal_rr(order_record),
                exit_reason=reason,
                notes=f"Signal: {order_record.get('signal_strength', '')} "
                      f"(score={order_record.get('scanner_score', 0)})",
            )

        # Step 4: Clean up
        del self.active_orders[symbol]

        realized_pnl = rm_result["realized_pnl"] if rm_result else sell_result.get("realized_pnl", 0)

        logger.info(
            "Position CLOSED: %s — P&L=$%+.2f, reason=%s.",
            symbol, realized_pnl, reason,
        )

        return {
            "symbol": symbol,
            "shares": shares,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "realized_pnl": realized_pnl,
            "reason": reason,
            "sell_order": sell_result,
            "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def get_active_orders(self) -> dict[str, dict]:
        """
        Get all currently active (open) order records.

        Returns:
            Dictionary mapping symbol -> order record.
        """
        return dict(self.active_orders)

    def get_active_symbols(self) -> list[str]:
        """
        Get list of symbols with active positions.

        Returns:
            List of ticker symbols.
        """
        return list(self.active_orders.keys())

    def has_position(self, symbol: str) -> bool:
        """
        Check if there's an active position for a symbol.

        Args:
            symbol: Stock ticker.

        Returns:
            True if position exists, False otherwise.
        """
        return symbol in self.active_orders

    def get_execution_summary(self) -> dict:
        """
        Get a summary of execution state for reporting.

        Returns:
            Dictionary with account info, active positions, and order counts.
        """
        account = self.broker.get_account()
        risk_summary = self.risk_manager.get_risk_summary()

        return {
            "account": account,
            "active_positions": len(self.active_orders),
            "active_symbols": self.get_active_symbols(),
            "risk_summary": risk_summary,
            "total_orders": len(self.broker.get_order_history()),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


def signal_rr(order_record: dict) -> float | None:
    """
    Extract risk:reward ratio from an order record.

    Calculates R:R from entry, stop, and TP1 if available.

    Args:
        order_record: The active order tracking dict.

    Returns:
        Risk:reward ratio as float, or None if data insufficient.
    """
    entry = order_record.get("entry_price", 0)
    stop = order_record.get("stop_loss", 0)
    tp1 = order_record.get("take_profit_1")

    if entry <= 0 or stop <= 0 or entry <= stop:
        return None

    risk = entry - stop
    if tp1 and tp1 > entry and risk > 0:
        return round((tp1 - entry) / risk, 2)
    return None
