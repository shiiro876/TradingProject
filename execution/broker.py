# =============================================================================
# execution/broker.py — Broker Interface & Paper Trading Simulator
# =============================================================================
#
# PURPOSE:
#   Provides a unified interface for placing orders and fetching account data,
#   regardless of whether the system is running in PAPER TRADING mode (local
#   simulation) or LIVE mode (Alpaca API). This abstraction allows the entire
#   execution engine to be developed and tested without any broker dependency.
#
# TWO MODES:
#   1. Paper Trading (PAPER_TRADING=True in config/settings.py)
#      - Orders are simulated locally with instant fills at the requested price.
#      - Account balance, positions, and P&L are tracked in-memory.
#      - No external API calls — perfect for development and backtesting.
#
#   2. Live Trading (PAPER_TRADING=False — future implementation)
#      - Orders are routed to the Alpaca API for real market execution.
#      - Account data is fetched from the broker in real time.
#      - Requires ALPACA_API_KEY and ALPACA_SECRET_KEY in config/.env.
#
# KEY CLASSES:
#   - PaperBroker(account_balance)
#       Simulates a broker locally. Tracks positions, fills orders instantly.
#
#   - get_broker(account_balance) → PaperBroker
#       Factory function that returns the correct broker based on PAPER_TRADING.
#
# USAGE:
#   from execution.broker import get_broker
#   broker = get_broker(account_balance=10000)
#   fill = broker.submit_order("AAPL", shares=33, side="buy", price=150.0)
#   account = broker.get_account()
#
# =============================================================================

import logging
from datetime import datetime

from config.settings import PAPER_TRADING

logger = logging.getLogger(__name__)


class PaperBroker:
    """
    Paper trading broker that simulates order execution locally.

    Simulates instant fills, tracks account balance, and maintains an
    in-memory record of all positions and orders. No external API needed.

    Attributes:
        account_balance (float): Current cash balance (not including positions).
        positions       (dict):  Mapping of symbol -> position details.
        order_history   (list):  Log of all submitted orders and their results.
        order_counter   (int):   Auto-incrementing order ID generator.
    """

    def __init__(self, account_balance: float):
        """
        Initialize the paper broker.

        Args:
            account_balance: Starting cash balance in dollars.
        """
        self.account_balance = account_balance
        self.positions: dict[str, dict] = {}
        self.order_history: list[dict] = []
        self.order_counter: int = 0

        logger.info(
            "PaperBroker initialized: balance=$%.2f, mode=PAPER.",
            account_balance,
        )

    def submit_order(
        self,
        symbol: str,
        shares: int | float,
        side: str,
        price: float,
    ) -> dict:
        """
        Submit a market order for immediate execution.

        In paper trading, all orders are filled instantly at the requested
        price. In live trading, this would be a market order routed to the
        exchange.

        Args:
            symbol: Stock ticker (e.g., "AAPL").
            shares: Number of shares to buy/sell.
            side:   "buy" or "sell".
            price:  Execution price (simulated fill price for paper trading).

        Returns:
            Order result dictionary with status, fill details, and order ID.
        """
        self.order_counter += 1
        order_id = f"PAPER-{self.order_counter:06d}"
        side = side.lower()

        # Validate inputs
        if shares <= 0:
            return self._order_result(
                order_id, symbol, side, shares, price,
                status="rejected", reason="Shares must be positive.",
            )

        if price <= 0:
            return self._order_result(
                order_id, symbol, side, shares, price,
                status="rejected", reason="Price must be positive.",
            )

        if side == "buy":
            return self._execute_buy(order_id, symbol, shares, price)
        elif side == "sell":
            return self._execute_sell(order_id, symbol, shares, price)
        else:
            return self._order_result(
                order_id, symbol, side, shares, price,
                status="rejected",
                reason=f"Invalid side '{side}'. Must be 'buy' or 'sell'.",
            )

    def get_account(self) -> dict:
        """
        Get the current account state.

        Returns:
            Dictionary with cash balance, equity, position value, and status.
        """
        position_value = sum(
            pos["shares"] * pos["current_price"]
            for pos in self.positions.values()
        )
        equity = self.account_balance + position_value

        return {
            "cash": round(self.account_balance, 2),
            "equity": round(equity, 2),
            "position_value": round(position_value, 2),
            "open_positions": len(self.positions),
            "paper_trading": True,
        }

    def get_position(self, symbol: str) -> dict | None:
        """
        Get details of an open position.

        Args:
            symbol: Stock ticker.

        Returns:
            Position dictionary, or None if no open position.
        """
        return self.positions.get(symbol)

    def get_all_positions(self) -> dict[str, dict]:
        """
        Get all open positions.

        Returns:
            Dictionary mapping symbol -> position details.
        """
        return dict(self.positions)

    def update_position_price(self, symbol: str, current_price: float) -> bool:
        """
        Update the market price for an open position.

        Used for unrealized P&L tracking.

        Args:
            symbol:        Stock ticker.
            current_price: Latest market price.

        Returns:
            True if position was found and updated, False otherwise.
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]
        pos["current_price"] = current_price
        pos["unrealized_pnl"] = round(
            (current_price - pos["avg_entry_price"]) * pos["shares"], 2
        )
        return True

    def get_order_history(self) -> list[dict]:
        """
        Get the full order history.

        Returns:
            List of all order result dictionaries.
        """
        return list(self.order_history)

    # =========================================================================
    # Private: Execution Logic
    # =========================================================================

    def _execute_buy(
        self, order_id: str, symbol: str, shares: int | float, price: float
    ) -> dict:
        """
        Execute a buy order: deduct cash, add or increase position.
        """
        cost = shares * price

        if cost > self.account_balance:
            return self._order_result(
                order_id, symbol, "buy", shares, price,
                status="rejected",
                reason=f"Insufficient funds: need ${cost:.2f}, "
                       f"have ${self.account_balance:.2f}.",
            )

        # Deduct cash
        self.account_balance -= cost

        # Add or average into existing position
        if symbol in self.positions:
            pos = self.positions[symbol]
            old_cost = pos["shares"] * pos["avg_entry_price"]
            new_cost = old_cost + cost
            new_shares = pos["shares"] + shares
            pos["avg_entry_price"] = round(new_cost / new_shares, 4)
            pos["shares"] = new_shares
            pos["current_price"] = price
            pos["unrealized_pnl"] = round(
                (price - pos["avg_entry_price"]) * new_shares, 2
            )
        else:
            self.positions[symbol] = {
                "symbol": symbol,
                "shares": shares,
                "avg_entry_price": price,
                "current_price": price,
                "unrealized_pnl": 0.0,
                "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        logger.info(
            "BUY filled: %s — %s shares @ $%.2f (cost=$%.2f). "
            "Cash=$%.2f.",
            symbol, shares, price, cost, self.account_balance,
        )

        return self._order_result(
            order_id, symbol, "buy", shares, price,
            status="filled", fill_price=price,
        )

    def _execute_sell(
        self, order_id: str, symbol: str, shares: int | float, price: float
    ) -> dict:
        """
        Execute a sell order: add cash, reduce or close position.
        """
        if symbol not in self.positions:
            return self._order_result(
                order_id, symbol, "sell", shares, price,
                status="rejected",
                reason=f"No open position in '{symbol}' to sell.",
            )

        pos = self.positions[symbol]

        if shares > pos["shares"]:
            return self._order_result(
                order_id, symbol, "sell", shares, price,
                status="rejected",
                reason=f"Cannot sell {shares} shares of '{symbol}': "
                       f"only {pos['shares']} held.",
            )

        # Calculate realized P&L for the sold portion
        realized_pnl = round((price - pos["avg_entry_price"]) * shares, 2)
        proceeds = shares * price

        # Add cash
        self.account_balance += proceeds

        # Update or remove position
        pos["shares"] -= shares
        if pos["shares"] <= 0:
            del self.positions[symbol]
        else:
            pos["current_price"] = price
            pos["unrealized_pnl"] = round(
                (price - pos["avg_entry_price"]) * pos["shares"], 2
            )

        logger.info(
            "SELL filled: %s — %s shares @ $%.2f (proceeds=$%.2f, "
            "P&L=$%+.2f). Cash=$%.2f.",
            symbol, shares, price, proceeds, realized_pnl,
            self.account_balance,
        )

        return self._order_result(
            order_id, symbol, "sell", shares, price,
            status="filled", fill_price=price,
            realized_pnl=realized_pnl,
        )

    def _order_result(
        self,
        order_id: str,
        symbol: str,
        side: str,
        shares: int | float,
        price: float,
        status: str = "filled",
        fill_price: float | None = None,
        reason: str = "",
        realized_pnl: float = 0.0,
    ) -> dict:
        """
        Build a standardized order result dictionary and log it.
        """
        result = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "shares": shares,
            "requested_price": price,
            "fill_price": fill_price,
            "status": status,
            "reason": reason,
            "realized_pnl": realized_pnl,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.order_history.append(result)
        return result


def get_broker(account_balance: float) -> PaperBroker:
    """
    Factory function that returns the appropriate broker instance.

    Currently always returns PaperBroker since PAPER_TRADING=True.
    When live trading is enabled, this will return an Alpaca client instead.

    Args:
        account_balance: Starting account balance in dollars.

    Returns:
        Broker instance (PaperBroker for now).
    """
    if PAPER_TRADING:
        logger.info("Creating PaperBroker (PAPER_TRADING=True).")
        return PaperBroker(account_balance)
    else:
        # Future: return AlpacaBroker(account_balance)
        logger.warning(
            "Live trading not yet implemented. Falling back to PaperBroker."
        )
        return PaperBroker(account_balance)
