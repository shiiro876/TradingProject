# =============================================================================
# risk/trailing_stop.py — Trailing Stop Manager
# =============================================================================
#
# PURPOSE:
#   Manages dynamic (trailing) stop losses that move UP as the price moves in
#   your favor, but NEVER move down. This implements the core trading philosophy:
#
#       "Never let a winner turn into a loser."
#
#   When a trade goes in your favor, the trailing stop ratchets upward to lock
#   in profits. If the price reverses, the stop catches it at a higher level
#   than the original stop loss — protecting gains.
#
# TRAILING STOP STRATEGIES:
#   1. ATR Trail    — Stop trails at (current_price - ATR * multiplier).
#                     Adapts to the stock's current volatility.
#   2. Percentage   — Stop trails at (current_price * (1 - trail_pct)).
#                     Simple and predictable.
#   3. Breakeven    — Moves stop to entry price once price moves 1R in profit,
#                     then trails from there. Two-phase approach.
#
# KEY RULE:
#   The trailing stop can ONLY move UP (for long positions). It never moves
#   down, even if the price drops. This is the ratchet mechanism.
#
# KEY FUNCTIONS:
#   - TrailingStopManager(method)
#       Class that tracks trailing stops for multiple positions.
#
#   - register_position(symbol, entry_price, initial_stop, atr_value)
#       Starts tracking a position's trailing stop.
#
#   - update(symbol, current_price, current_atr)
#       Recalculates the trailing stop based on the latest price.
#       Returns the new stop level (only moves up, never down).
#
#   - check_stop_hit(symbol, current_price)
#       Returns True if the current price has hit or fallen below the stop.
#
#   - get_stop(symbol)
#       Returns the current trailing stop level for a position.
#
# USAGE:
#   from risk.trailing_stop import TrailingStopManager
#   tsm = TrailingStopManager(method="atr")
#   tsm.register_position("AAPL", entry_price=150.0, initial_stop=144.0,
#                          atr_value=3.0)
#   new_stop = tsm.update("AAPL", current_price=160.0, current_atr=3.0)
#   if tsm.check_stop_hit("AAPL", current_price=155.0):
#       print("Stop hit! Close position.")
#
# =============================================================================

import logging
from datetime import datetime

from config.settings import (
    TRAILING_STOP_METHOD,
    TRAILING_STOP_ATR_MULTIPLIER,
    TRAILING_STOP_PERCENTAGE,
    BREAKEVEN_TRIGGER_R_MULTIPLE,
    BREAKEVEN_BUFFER_PCT,
)

logger = logging.getLogger(__name__)


class TrailingStopManager:
    """
    Manages trailing stop losses for multiple open positions.

    The trailing stop ratchets upward as the price increases, locking in
    profits. It never moves down. When the price falls back to the stop
    level, the position should be closed.

    Supports three trailing strategies:
      - "atr":        Trail at current_price - (ATR * multiplier)
      - "percentage":  Trail at current_price * (1 - trail_pct)
      - "breakeven_then_trail": Move to breakeven after 1R profit, then ATR trail

    Attributes:
        method     (str):  The trailing stop strategy to use.
        positions  (dict): Mapping of symbol -> trailing stop state.
    """

    VALID_METHODS = ("atr", "percentage", "breakeven_then_trail")

    def __init__(self, method: str = TRAILING_STOP_METHOD):
        """
        Initialize the trailing stop manager.

        Args:
            method: Trailing stop strategy. One of "atr", "percentage",
                    or "breakeven_then_trail".
        """
        if method not in self.VALID_METHODS:
            raise ValueError(
                f"Invalid trailing stop method '{method}'. "
                f"Valid options: {self.VALID_METHODS}"
            )

        self.method = method
        self.positions: dict[str, dict] = {}

        logger.info("TrailingStopManager initialized with method='%s'.", method)

    def register_position(
        self,
        symbol: str,
        entry_price: float,
        initial_stop: float,
        atr_value: float = 0.0,
    ) -> dict:
        """
        Start tracking a trailing stop for a new position.

        Args:
            symbol:        Stock ticker (e.g., "AAPL").
            entry_price:   Price at which the trade was entered.
            initial_stop:  The original stop loss price from the trade setup.
            atr_value:     Current ATR value for the stock (used in ATR trail).

        Returns:
            Dictionary with the position's trailing stop state.
        """
        risk_per_share = entry_price - initial_stop

        self.positions[symbol] = {
            "symbol": symbol,
            "entry_price": entry_price,
            "initial_stop": initial_stop,
            "current_stop": initial_stop,
            "highest_price": entry_price,
            "risk_per_share": risk_per_share,
            "atr_value": atr_value,
            "breakeven_hit": False,
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stop_updates": 0,
        }

        logger.info(
            "Trailing stop registered: %s — entry=$%.2f, stop=$%.2f, R=$%.2f.",
            symbol, entry_price, initial_stop, risk_per_share,
        )
        return self.positions[symbol].copy()

    def update(
        self,
        symbol: str,
        current_price: float,
        current_atr: float | None = None,
    ) -> float | None:
        """
        Update the trailing stop for a position based on the latest price.

        The stop can ONLY move UP (ratchet). If the calculated new stop is
        below the current stop, the current stop is unchanged.

        Args:
            symbol:        Stock ticker.
            current_price: The latest market price for the stock.
            current_atr:   Updated ATR value (optional, used in ATR-based trails).

        Returns:
            The current trailing stop price after the update, or None if the
            symbol is not registered.
        """
        if symbol not in self.positions:
            logger.warning("Cannot update trailing stop: '%s' not registered.", symbol)
            return None

        pos = self.positions[symbol]

        # Update ATR if provided
        if current_atr is not None:
            pos["atr_value"] = current_atr

        # Track the highest price seen (high water mark)
        if current_price > pos["highest_price"]:
            pos["highest_price"] = current_price

        # Calculate the new candidate stop based on the method
        if self.method == "atr":
            candidate_stop = self._calculate_atr_stop(pos)
        elif self.method == "percentage":
            candidate_stop = self._calculate_percentage_stop(pos)
        elif self.method == "breakeven_then_trail":
            candidate_stop = self._calculate_breakeven_trail_stop(pos, current_price)
        else:
            candidate_stop = pos["current_stop"]

        # RATCHET RULE: stop can only move UP, never down
        if candidate_stop > pos["current_stop"]:
            old_stop = pos["current_stop"]
            pos["current_stop"] = round(candidate_stop, 2)
            pos["stop_updates"] += 1
            pos["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            logger.info(
                "Trailing stop raised: %s — $%.2f -> $%.2f (highest=$%.2f).",
                symbol, old_stop, pos["current_stop"], pos["highest_price"],
            )

        return pos["current_stop"]

    def check_stop_hit(self, symbol: str, current_price: float) -> bool:
        """
        Check if the current price has hit or fallen below the trailing stop.

        Args:
            symbol:        Stock ticker.
            current_price: The latest market price.

        Returns:
            True if the stop has been hit (price <= stop), False otherwise.
            Returns False if the symbol is not registered.
        """
        if symbol not in self.positions:
            return False

        stop = self.positions[symbol]["current_stop"]
        hit = current_price <= stop

        if hit:
            logger.info(
                "TRAILING STOP HIT: %s — price=$%.2f <= stop=$%.2f. "
                "Close position.",
                symbol, current_price, stop,
            )

        return hit

    def get_stop(self, symbol: str) -> float | None:
        """
        Get the current trailing stop level for a position.

        Args:
            symbol: Stock ticker.

        Returns:
            Current stop price, or None if not registered.
        """
        if symbol not in self.positions:
            return None
        return self.positions[symbol]["current_stop"]

    def get_position_state(self, symbol: str) -> dict | None:
        """
        Get the full trailing stop state for a position.

        Args:
            symbol: Stock ticker.

        Returns:
            Copy of the position's trailing stop state dict, or None.
        """
        if symbol not in self.positions:
            return None
        return self.positions[symbol].copy()

    def remove_position(self, symbol: str) -> dict | None:
        """
        Stop tracking a position (after it's been closed).

        Args:
            symbol: Stock ticker.

        Returns:
            The removed position state dict, or None if not found.
        """
        pos = self.positions.pop(symbol, None)
        if pos:
            logger.info("Trailing stop removed: %s.", symbol)
        return pos

    def get_all_stops(self) -> dict[str, float]:
        """
        Get all current trailing stop levels.

        Returns:
            Dictionary mapping symbol -> current stop price.
        """
        return {
            symbol: pos["current_stop"]
            for symbol, pos in self.positions.items()
        }

    # =========================================================================
    # Private: Trailing Stop Calculation Methods
    # =========================================================================

    def _calculate_atr_stop(self, pos: dict) -> float:
        """
        Calculate trailing stop using ATR method.

        Trail distance = ATR * multiplier. The stop trails below the highest
        price seen since entry.

        Formula: new_stop = highest_price - (ATR * TRAILING_STOP_ATR_MULTIPLIER)
        """
        atr = pos["atr_value"]
        if atr <= 0:
            return pos["current_stop"]

        trail_distance = atr * TRAILING_STOP_ATR_MULTIPLIER
        return pos["highest_price"] - trail_distance

    def _calculate_percentage_stop(self, pos: dict) -> float:
        """
        Calculate trailing stop using percentage method.

        Trail distance = highest_price * trail_percentage. The stop always
        stays a fixed percentage below the highest price.

        Formula: new_stop = highest_price * (1 - TRAILING_STOP_PERCENTAGE)
        """
        return pos["highest_price"] * (1 - TRAILING_STOP_PERCENTAGE)

    def _calculate_breakeven_trail_stop(
        self, pos: dict, current_price: float
    ) -> float:
        """
        Two-phase trailing stop: breakeven first, then ATR trail.

        Phase 1: Price hasn't moved 1R in profit yet.
                 Keep original stop loss — don't trail yet.

        Phase 2: Price moved >= 1R in profit (breakeven triggered).
                 Move stop to entry + small buffer ("never let a winner
                 become a loser"), then ATR trail from there.

        This is the most conservative strategy — it prioritizes capital
        preservation and only starts trailing after a meaningful move.
        """
        entry = pos["entry_price"]
        risk_r = pos["risk_per_share"]

        # Check if breakeven trigger has been reached
        if not pos["breakeven_hit"]:
            breakeven_target = entry + (risk_r * BREAKEVEN_TRIGGER_R_MULTIPLE)

            if current_price >= breakeven_target:
                pos["breakeven_hit"] = True
                # Move stop to entry + tiny buffer
                breakeven_stop = entry * (1 + BREAKEVEN_BUFFER_PCT)
                logger.info(
                    "BREAKEVEN triggered: %s — stop moved to $%.2f "
                    "(entry + %.1f%% buffer).",
                    pos["symbol"], breakeven_stop, BREAKEVEN_BUFFER_PCT * 100,
                )
                return breakeven_stop
            else:
                # Not yet at breakeven — keep original stop
                return pos["current_stop"]

        # Phase 2: Breakeven already hit — now ATR trail from highest price
        return self._calculate_atr_stop(pos)
