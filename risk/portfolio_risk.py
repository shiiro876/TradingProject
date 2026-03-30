# =============================================================================
# risk/portfolio_risk.py — Portfolio-Level Risk Manager
# =============================================================================
#
# PURPOSE:
#   Enforces portfolio-level risk rules that protect the overall account from
#   catastrophic losses. While position_sizer.py handles per-trade risk, this
#   module handles PORTFOLIO-WIDE constraints:
#
#   1. Maximum open positions (default: 3) — prevents over-diversification
#      and ensures each position gets meaningful capital allocation.
#   2. Daily loss limit (default: 5%) — if the account drops more than 5%
#      in a single day, ALL trading is halted to prevent emotional revenge
#      trading.
#   3. Rule violation logging — every time a rule is triggered, it is logged
#      to a file for audit and review.
#
# KEY FUNCTIONS:
#   - PortfolioRiskManager(account_balance, max_positions, daily_loss_limit)
#       Class that tracks positions and enforces portfolio risk rules.
#
#   - can_open_position()       → True/False if a new trade is allowed.
#   - add_position(...)         → Register a new open position.
#   - remove_position(symbol)   → Close a position.
#   - update_daily_pnl(pnl)    → Update today's P&L and check loss limit.
#   - check_daily_loss_limit()  → Returns True if daily loss limit breached.
#   - get_portfolio_summary()   → Returns a summary dict of current state.
#
# USAGE:
#   from risk.portfolio_risk import PortfolioRiskManager
#   manager = PortfolioRiskManager(account_balance=10000)
#   if manager.can_open_position():
#       manager.add_position("AAPL", 50, 150.00)
#
# =============================================================================

import os
import logging
from datetime import datetime

from config.settings import MAX_POSITIONS, DAILY_LOSS_LIMIT, DATA_DIR

logger = logging.getLogger(__name__)


class PortfolioRiskManager:
    """
    Manages portfolio-level risk by tracking open positions, enforcing
    maximum position counts, and monitoring daily P&L against loss limits.

    This is the "discipline engine" that prevents the trader (or bot) from
    taking on excessive risk. It acts as a gatekeeper: before any new trade
    is placed, it must pass through this manager's checks.

    Attributes:
        account_balance (float): Starting account balance for the day.
        max_positions   (int):   Maximum simultaneous open positions allowed.
        daily_loss_limit (float): Maximum daily loss as a fraction (e.g., 0.05).
        open_positions  (dict):  Mapping of symbol → position details.
        daily_pnl       (float): Running total of today's realized + unrealized P&L.
        trading_halted  (bool):  True if daily loss limit has been breached.
        violations_log  (list):  In-memory log of all rule violations.
    """

    def __init__(
        self,
        account_balance: float,
        max_positions: int = MAX_POSITIONS,
        daily_loss_limit: float = DAILY_LOSS_LIMIT,
    ):
        """
        Initialize the portfolio risk manager.

        Args:
            account_balance:  Current account balance in dollars.
            max_positions:    Max simultaneous open positions (default: 3).
            daily_loss_limit: Max daily loss as fraction of account (default: 0.05).
        """
        self.account_balance = account_balance
        self.max_positions = max_positions
        self.daily_loss_limit = daily_loss_limit

        # State tracking
        self.open_positions: dict[str, dict] = {}
        self.daily_pnl: float = 0.0
        self.trading_halted: bool = False
        self.violations_log: list[dict] = []

        logger.info(
            "PortfolioRiskManager initialized: balance=$%.2f, max_positions=%d, "
            "daily_loss_limit=%.1f%%.",
            account_balance, max_positions, daily_loss_limit * 100,
        )

    def can_open_position(self) -> bool:
        """
        Check whether a new position can be opened.

        A new position is allowed only if:
          1. Trading has not been halted (daily loss limit not breached).
          2. The number of open positions is below the maximum.

        Returns:
            True if a new position is permitted, False otherwise.
        """
        if self.trading_halted:
            self._log_violation(
                "TRADE_BLOCKED",
                "Trading halted: daily loss limit breached. No new positions allowed.",
            )
            return False

        if len(self.open_positions) >= self.max_positions:
            self._log_violation(
                "MAX_POSITIONS",
                f"Max positions reached ({self.max_positions}). "
                f"Cannot open new position.",
            )
            return False

        return True

    def add_position(
        self,
        symbol: str,
        shares: int | float,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit_1: float | None = None,
        take_profit_2: float | None = None,
    ) -> bool:
        """
        Register a new open position in the portfolio tracker.

        Args:
            symbol:        Stock ticker (e.g., "AAPL").
            shares:        Number of shares purchased.
            entry_price:   Price at which the position was entered.
            stop_loss:     Stop loss price (optional, for tracking).
            take_profit_1: First profit target (optional).
            take_profit_2: Second profit target (optional).

        Returns:
            True if position was successfully added, False if blocked by rules.
        """
        if not self.can_open_position():
            return False

        if symbol in self.open_positions:
            logger.warning("Position in '%s' already exists. Not adding duplicate.", symbol)
            return False

        self.open_positions[symbol] = {
            "symbol": symbol,
            "shares": shares,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "current_price": entry_price,
            "unrealized_pnl": 0.0,
        }

        logger.info(
            "Position opened: %s — %s shares @ $%.2f. "
            "Open positions: %d / %d.",
            symbol, shares, entry_price,
            len(self.open_positions), self.max_positions,
        )
        return True

    def remove_position(self, symbol: str) -> dict | None:
        """
        Remove (close) a position from the portfolio tracker.

        Args:
            symbol: The ticker symbol of the position to close.

        Returns:
            The position dictionary that was removed, or None if not found.
        """
        position = self.open_positions.pop(symbol, None)

        if position is None:
            logger.warning("Cannot remove '%s': no open position found.", symbol)
            return None

        logger.info(
            "Position closed: %s. Remaining open positions: %d / %d.",
            symbol, len(self.open_positions), self.max_positions,
        )
        return position

    def update_daily_pnl(self, pnl_change: float) -> None:
        """
        Update today's running P&L and check the daily loss limit.

        This should be called whenever a trade is closed (realized P&L) or
        when unrealized P&L is recalculated during monitoring.

        Args:
            pnl_change: Dollar amount to add to today's P&L. Negative values
                        represent losses.
        """
        self.daily_pnl += pnl_change

        logger.info(
            "Daily P&L updated: %+.2f → Total: %+.2f (%.2f%% of account).",
            pnl_change, self.daily_pnl,
            (self.daily_pnl / self.account_balance) * 100 if self.account_balance > 0 else 0,
        )

        # Check if daily loss limit has been breached
        if self.check_daily_loss_limit():
            self.trading_halted = True
            self._log_violation(
                "DAILY_LOSS_LIMIT",
                f"Daily loss limit breached: P&L=${self.daily_pnl:.2f} "
                f"({(self.daily_pnl / self.account_balance) * 100:.2f}%). "
                f"All trading halted for today.",
            )

    def check_daily_loss_limit(self) -> bool:
        """
        Check if today's losses have exceeded the daily loss limit.

        The daily loss limit is a safety mechanism: if the account drops more
        than the configured percentage (default 5%) in a single day, trading
        is halted to prevent emotional decision-making.

        Returns:
            True if the daily loss limit has been breached (losses exceed limit).
        """
        if self.account_balance <= 0:
            return True

        max_loss = self.account_balance * self.daily_loss_limit
        return self.daily_pnl <= -max_loss

    def get_open_position_count(self) -> int:
        """Return the number of currently open positions."""
        return len(self.open_positions)

    def get_portfolio_summary(self) -> dict:
        """
        Generate a summary of the current portfolio state.

        Returns a dictionary suitable for logging, display, or passing to
        the dashboard module.

        Returns:
            Dictionary with account info, position details, P&L, and status.
        """
        total_position_value = sum(
            pos["shares"] * pos["current_price"]
            for pos in self.open_positions.values()
        )

        total_unrealized_pnl = sum(
            pos["unrealized_pnl"]
            for pos in self.open_positions.values()
        )

        return {
            "account_balance": self.account_balance,
            "open_positions": len(self.open_positions),
            "max_positions": self.max_positions,
            "total_position_value": round(total_position_value, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_pnl_pct": round(
                (self.daily_pnl / self.account_balance) * 100, 2
            ) if self.account_balance > 0 else 0.0,
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "trading_halted": self.trading_halted,
            "positions": dict(self.open_positions),
            "violations_today": len(self.violations_log),
        }

    def reset_daily_state(self) -> None:
        """
        Reset daily tracking state for a new trading day.

        Called at the start of each trading day to reset the daily P&L
        counter and re-enable trading if it was halted.
        """
        self.daily_pnl = 0.0
        self.trading_halted = False
        self.violations_log.clear()
        logger.info("Daily state reset. Trading re-enabled.")

    def save_violations_log(self, output_dir: str = DATA_DIR) -> str | None:
        """
        Save the violations log to a file for audit purposes.

        Args:
            output_dir: Directory to write the log file to.

        Returns:
            Path to the saved log file, or None if no violations occurred.
        """
        if not self.violations_log:
            return None

        os.makedirs(output_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_path = os.path.join(output_dir, f"violations_{date_str}.log")

        with open(log_path, "a", encoding="utf-8") as f:
            for entry in self.violations_log:
                f.write(
                    f"[{entry['timestamp']}] {entry['rule']}: {entry['message']}\n"
                )

        logger.info("Violations log saved to '%s' (%d entries).", log_path, len(self.violations_log))
        return log_path

    def _log_violation(self, rule: str, message: str) -> None:
        """
        Record a rule violation in the in-memory log.

        Args:
            rule:    The rule that was violated (e.g., "MAX_POSITIONS").
            message: Human-readable description of the violation.
        """
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rule": rule,
            "message": message,
        }
        self.violations_log.append(entry)
        logger.warning("RISK VIOLATION [%s]: %s", rule, message)
