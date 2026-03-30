# =============================================================================
# risk/risk_manager.py — Master Risk Manager (Discipline Engine)
# =============================================================================
#
# PURPOSE:
#   The single entry point for ALL risk decisions in the trading system.
#   Before any trade is placed, it must pass through this manager's
#   approve/deny gate. This is the "discipline engine" described in the
#   trading system specification.
#
#   It orchestrates the three risk components built in Modules 2 and 4:
#     1. Position Sizer (risk/position_sizer.py)  — Per-trade sizing (2% rule)
#     2. Portfolio Risk (risk/portfolio_risk.py)   — Portfolio limits & daily P&L
#     3. Trailing Stop  (risk/trailing_stop.py)    — Dynamic stop management
#
#   Additionally, it adds:
#     - Sector concentration checks (no more than 2 positions in same sector)
#     - Drawdown monitoring (halt trading if account drops 15% from peak)
#     - Account balance floor (never trade below $500)
#     - Pre-trade validation (single approve/deny decision with full reasoning)
#
# KEY FUNCTIONS:
#   - RiskManager(account_balance, method)
#       Master class that owns PortfolioRiskManager and TrailingStopManager.
#
#   - evaluate_trade(symbol, entry_price, stop_loss, atr_value, scanner_score,
#                    signal_strength, sector)
#       Single function that runs ALL risk checks and returns approve/deny.
#
#   - register_fill(symbol, shares, entry_price, stop_loss, take_profit_1,
#                   take_profit_2, atr_value, sector)
#       Called after a trade is filled — registers it in all sub-managers.
#
#   - update_price(symbol, current_price, current_atr)
#       Updates trailing stop and unrealized P&L for a position.
#
#   - close_position(symbol, exit_price, reason)
#       Closes a position, logs P&L, and removes from all trackers.
#
#   - get_risk_summary()
#       Full system-wide risk status snapshot.
#
# USAGE:
#   from risk.risk_manager import RiskManager
#   rm = RiskManager(account_balance=10000)
#   decision = rm.evaluate_trade("AAPL", entry_price=150, stop_loss=144,
#                                atr_value=3.0, scanner_score=8.0,
#                                signal_strength="STRONG", sector="Technology")
#   if decision["approved"]:
#       # Place the trade
#       rm.register_fill("AAPL", decision["shares_to_buy"], 150, 144, 162, 168,
#                        atr_value=3.0, sector="Technology")
#
# =============================================================================

import logging
from datetime import datetime

from config.settings import (
    MAX_SECTOR_CONCENTRATION,
    MAX_DRAWDOWN_PCT,
    MIN_ACCOUNT_BALANCE,
    MIN_RR_RATIO,
    DATA_DIR,
)
from risk.position_sizer import calculate_position_size
from risk.portfolio_risk import PortfolioRiskManager
from risk.trailing_stop import TrailingStopManager

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Master Risk Manager — the discipline engine that orchestrates all risk
    components and provides a single approve/deny gate for every trade.

    This class owns:
      - PortfolioRiskManager: tracks open positions, daily P&L, violations.
      - TrailingStopManager:  manages trailing stops for all open positions.

    It adds additional checks:
      - Sector concentration: max 2 positions in the same sector.
      - Drawdown monitoring:  halt if account drops 15% from peak equity.
      - Account floor:        never trade below minimum balance threshold.
      - Pre-trade validation:  comprehensive approve/deny with reasons.

    Attributes:
        account_balance (float):  Current account balance.
        peak_balance    (float):  Highest account balance ever seen.
        portfolio       (PortfolioRiskManager): Portfolio-level risk manager.
        trailing_stops  (TrailingStopManager):  Trailing stop manager.
        sector_map      (dict):   Mapping of symbol -> sector for open positions.
        drawdown_halted (bool):   True if max drawdown has been breached.
        trade_log       (list):   Log of all evaluate_trade decisions.
    """

    def __init__(
        self,
        account_balance: float,
        trailing_method: str = "atr",
    ):
        """
        Initialize the master risk manager.

        Args:
            account_balance:  Starting account balance in dollars.
            trailing_method:  Trailing stop strategy for the TrailingStopManager.
        """
        self.account_balance = account_balance
        self.peak_balance = account_balance

        # Sub-managers
        self.portfolio = PortfolioRiskManager(account_balance)
        self.trailing_stops = TrailingStopManager(method=trailing_method)

        # Additional state
        self.sector_map: dict[str, str] = {}  # symbol -> sector
        self.drawdown_halted: bool = False
        self.trade_log: list[dict] = []

        logger.info(
            "RiskManager initialized: balance=$%.2f, trailing='%s'.",
            account_balance, trailing_method,
        )

    # =========================================================================
    # Pre-Trade Evaluation (The Gate)
    # =========================================================================

    def evaluate_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        atr_value: float = 0.0,
        scanner_score: float = 0.0,
        signal_strength: str = "WEAK",
        sector: str | None = None,
    ) -> dict:
        """
        Run ALL risk checks and return an approve/deny decision.

        This is the single gate every trade must pass through. It checks:
          1. Account balance floor ($500 minimum)
          2. Max drawdown limit (15% from peak)
          3. Daily loss limit (from PortfolioRiskManager)
          4. Max open positions (from PortfolioRiskManager)
          5. Sector concentration (max 2 in same sector)
          6. Minimum R:R ratio (from signals — sanity check)
          7. Position sizing (from position_sizer — calculates shares)

        Args:
            symbol:           Stock ticker (e.g., "AAPL").
            entry_price:      Planned entry price.
            stop_loss:        Planned stop loss price.
            atr_value:        Current ATR value for the stock.
            scanner_score:    Score from the scanner (0-10).
            signal_strength:  Signal classification ("STRONG"/"MEDIUM"/"WEAK").
            sector:           Stock's sector (e.g., "Technology").

        Returns:
            Dictionary containing:
                approved        (bool):  True if the trade passes ALL checks.
                reasons         (list):  List of rejection reasons (empty if approved).
                shares_to_buy   (int):   Recommended shares (0 if rejected).
                position_value  (float): Total dollar value of the position.
                risk_amount     (float): Dollar risk if stop is hit.
                risk_reward     (float): Risk:reward ratio.
                checks_passed   (list):  List of checks that passed.
                evaluated_at    (str):   Timestamp.
        """
        reasons: list[str] = []
        checks_passed: list[str] = []
        shares_to_buy = 0
        position_value = 0.0
        risk_amount = 0.0

        # Calculate risk per share for logging
        risk_per_share = entry_price - stop_loss if entry_price > stop_loss else 0
        # R:R ratio requires take-profit info from the signal generator.
        # Here we record risk_per_share; actual R:R comes from signals.py.
        rr_ratio = 0.0

        # Check 1: Account balance floor
        if self.account_balance < MIN_ACCOUNT_BALANCE:
            reasons.append(
                f"Account balance (${self.account_balance:.2f}) below minimum "
                f"(${MIN_ACCOUNT_BALANCE:.2f})."
            )
        else:
            checks_passed.append("account_balance_floor")

        # Check 2: Max drawdown
        if self.drawdown_halted:
            reasons.append(
                f"Trading halted: max drawdown ({MAX_DRAWDOWN_PCT * 100:.0f}%) breached. "
                f"Current balance=${self.account_balance:.2f}, "
                f"peak=${self.peak_balance:.2f}."
            )
        else:
            checks_passed.append("max_drawdown")

        # Check 3: Daily loss limit (delegated to portfolio manager)
        if self.portfolio.trading_halted:
            reasons.append("Daily loss limit breached. Trading halted for today.")
        else:
            checks_passed.append("daily_loss_limit")

        # Check 4: Max open positions
        if not self.portfolio.can_open_position():
            if not self.portfolio.trading_halted:
                reasons.append(
                    f"Max positions ({self.portfolio.max_positions}) already open."
                )
        else:
            checks_passed.append("max_positions")

        # Check 5: Sector concentration
        if sector:
            sector_count = sum(
                1 for s in self.sector_map.values() if s == sector
            )
            if sector_count >= MAX_SECTOR_CONCENTRATION:
                reasons.append(
                    f"Sector concentration limit: already {sector_count} "
                    f"positions in '{sector}' (max {MAX_SECTOR_CONCENTRATION})."
                )
            else:
                checks_passed.append("sector_concentration")
        else:
            checks_passed.append("sector_concentration")

        # Check 6: Valid risk (entry > stop)
        if entry_price <= stop_loss:
            reasons.append(
                f"Invalid setup: entry (${entry_price:.2f}) must be above "
                f"stop loss (${stop_loss:.2f})."
            )
        else:
            checks_passed.append("valid_risk")

        # Check 7: Position sizing (only if no blockers so far)
        if not reasons:
            sizing = calculate_position_size(
                account_balance=self.account_balance,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
            )

            if sizing["valid"]:
                shares_to_buy = sizing["shares_to_buy"]
                position_value = sizing["total_position_value"]
                risk_amount = sizing["risk_amount"]
                checks_passed.append("position_sizing")
            else:
                reasons.append(f"Position sizing failed: {sizing['message']}")

        approved = len(reasons) == 0

        decision = {
            "approved": approved,
            "symbol": symbol,
            "reasons": reasons,
            "shares_to_buy": shares_to_buy,
            "position_value": round(position_value, 2),
            "risk_amount": round(risk_amount, 2),
            "risk_reward": rr_ratio,
            "scanner_score": scanner_score,
            "signal_strength": signal_strength,
            "sector": sector,
            "checks_passed": checks_passed,
            "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Log the decision
        self.trade_log.append(decision)

        if approved:
            logger.info(
                "TRADE APPROVED: %s — %d shares @ $%.2f, risk=$%.2f. "
                "All %d checks passed.",
                symbol, shares_to_buy, entry_price, risk_amount,
                len(checks_passed),
            )
        else:
            logger.warning(
                "TRADE REJECTED: %s — Reasons: %s",
                symbol, "; ".join(reasons),
            )

        return decision

    # =========================================================================
    # Position Lifecycle
    # =========================================================================

    def register_fill(
        self,
        symbol: str,
        shares: int | float,
        entry_price: float,
        stop_loss: float,
        take_profit_1: float | None = None,
        take_profit_2: float | None = None,
        atr_value: float = 0.0,
        sector: str | None = None,
    ) -> bool:
        """
        Register a filled trade in all sub-managers.

        Called after a trade is actually executed (filled by the broker).
        Registers the position in the portfolio tracker and starts the
        trailing stop.

        Args:
            symbol:        Stock ticker.
            shares:        Number of shares bought.
            entry_price:   Fill price.
            stop_loss:     Initial stop loss price.
            take_profit_1: First profit target (optional).
            take_profit_2: Second profit target (optional).
            atr_value:     Current ATR for trailing stop.
            sector:        Stock's sector for concentration tracking.

        Returns:
            True if successfully registered, False if blocked by portfolio rules.
        """
        # Register in portfolio tracker
        added = self.portfolio.add_position(
            symbol=symbol,
            shares=shares,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
        )

        if not added:
            return False

        # Register trailing stop
        self.trailing_stops.register_position(
            symbol=symbol,
            entry_price=entry_price,
            initial_stop=stop_loss,
            atr_value=atr_value,
        )

        # Track sector
        if sector:
            self.sector_map[symbol] = sector

        logger.info(
            "Trade registered: %s — %s shares @ $%.2f, sector=%s.",
            symbol, shares, entry_price, sector or "unknown",
        )
        return True

    def update_price(
        self,
        symbol: str,
        current_price: float,
        current_atr: float | None = None,
    ) -> dict | None:
        """
        Update a position with the latest market price.

        Updates:
          1. Trailing stop level (ratchets up if price increased).
          2. Unrealized P&L in the portfolio tracker.
          3. Checks if the trailing stop has been hit.

        Args:
            symbol:        Stock ticker.
            current_price: Latest market price.
            current_atr:   Updated ATR value (optional).

        Returns:
            Dictionary with the update results, or None if symbol not found.
        """
        if symbol not in self.portfolio.open_positions:
            return None

        pos = self.portfolio.open_positions[symbol]

        # Update trailing stop
        new_stop = self.trailing_stops.update(symbol, current_price, current_atr)

        # Update unrealized P&L in portfolio
        pos["current_price"] = current_price
        pos["unrealized_pnl"] = round(
            (current_price - pos["entry_price"]) * pos["shares"], 2
        )

        # Update the portfolio position's stop to match the trailing stop
        if new_stop is not None:
            pos["stop_loss"] = new_stop

        # Check if trailing stop was hit
        stop_hit = self.trailing_stops.check_stop_hit(symbol, current_price)

        return {
            "symbol": symbol,
            "current_price": current_price,
            "trailing_stop": new_stop,
            "unrealized_pnl": pos["unrealized_pnl"],
            "stop_hit": stop_hit,
        }

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "manual",
    ) -> dict | None:
        """
        Close a position and update all trackers.

        Calculates realized P&L, updates daily P&L, removes from portfolio
        and trailing stop trackers, and removes sector mapping.

        Args:
            symbol:     Stock ticker.
            exit_price: Price at which the position was exited.
            reason:     Reason for closing (e.g., "trailing_stop", "tp1", "manual").

        Returns:
            Dictionary with closing details, or None if symbol not found.
        """
        if symbol not in self.portfolio.open_positions:
            logger.warning("Cannot close '%s': not in open positions.", symbol)
            return None

        pos = self.portfolio.open_positions[symbol]
        shares = pos["shares"]
        entry_price = pos["entry_price"]

        # Calculate realized P&L
        realized_pnl = round((exit_price - entry_price) * shares, 2)

        # Update daily P&L
        self.portfolio.update_daily_pnl(realized_pnl)

        # Update account balance
        self.account_balance += realized_pnl
        self.portfolio.account_balance = self.account_balance

        # Update peak balance for drawdown tracking
        if self.account_balance > self.peak_balance:
            self.peak_balance = self.account_balance

        # Check drawdown
        self._check_drawdown()

        # Remove from all trackers
        removed_pos = self.portfolio.remove_position(symbol)
        self.trailing_stops.remove_position(symbol)
        self.sector_map.pop(symbol, None)

        result = {
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "shares": shares,
            "realized_pnl": realized_pnl,
            "reason": reason,
            "closed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account_balance": round(self.account_balance, 2),
        }

        win_loss = "WIN" if realized_pnl >= 0 else "LOSS"
        logger.info(
            "Position closed: %s — %s $%.2f (entry=$%.2f, exit=$%.2f, "
            "reason=%s). Balance=$%.2f.",
            symbol, win_loss, realized_pnl, entry_price, exit_price,
            reason, self.account_balance,
        )

        return result

    # =========================================================================
    # Drawdown Monitoring
    # =========================================================================

    def _check_drawdown(self) -> bool:
        """
        Check if the account has breached the maximum drawdown limit.

        Drawdown = (peak - current) / peak. If this exceeds MAX_DRAWDOWN_PCT,
        trading is halted permanently (requires manual reset).

        Returns:
            True if drawdown limit has been breached.
        """
        if self.peak_balance <= 0:
            return False

        drawdown = (self.peak_balance - self.account_balance) / self.peak_balance

        if drawdown >= MAX_DRAWDOWN_PCT and not self.drawdown_halted:
            self.drawdown_halted = True
            logger.critical(
                "MAX DRAWDOWN BREACHED: %.1f%% drawdown (peak=$%.2f, "
                "current=$%.2f). ALL TRADING HALTED.",
                drawdown * 100, self.peak_balance, self.account_balance,
            )
            self.portfolio._log_violation(
                "MAX_DRAWDOWN",
                f"Drawdown of {drawdown * 100:.1f}% exceeds limit of "
                f"{MAX_DRAWDOWN_PCT * 100:.0f}%. Trading halted.",
            )

        return self.drawdown_halted

    def get_current_drawdown(self) -> float:
        """
        Calculate the current drawdown percentage from peak equity.

        Returns:
            Drawdown as a decimal (e.g., 0.05 for 5% drawdown). Returns 0.0
            if no drawdown (current balance >= peak).
        """
        if self.peak_balance <= 0:
            return 0.0

        drawdown = (self.peak_balance - self.account_balance) / self.peak_balance
        return max(round(drawdown, 4), 0.0)

    # =========================================================================
    # Day Reset
    # =========================================================================

    def reset_daily_state(self) -> None:
        """
        Reset daily state for a new trading day.

        Resets the daily P&L and re-enables trading if it was halted by the
        daily loss limit (NOT by max drawdown — that requires manual reset).
        """
        self.portfolio.reset_daily_state()
        logger.info("Daily state reset via RiskManager.")

    def reset_drawdown_halt(self) -> None:
        """
        Manually reset the drawdown halt.

        This should only be called after a deliberate review and decision to
        continue trading. It updates the peak balance to the current balance.
        """
        self.drawdown_halted = False
        self.peak_balance = self.account_balance
        logger.info(
            "Drawdown halt manually reset. New peak=$%.2f.",
            self.peak_balance,
        )

    # =========================================================================
    # Summary & Reporting
    # =========================================================================

    def get_risk_summary(self) -> dict:
        """
        Generate a comprehensive risk status snapshot.

        Combines data from all sub-managers into a single overview suitable
        for the dashboard, logging, or decision-making.

        Returns:
            Dictionary with account info, portfolio state, trailing stops,
            drawdown, sector exposure, and decision log.
        """
        portfolio_summary = self.portfolio.get_portfolio_summary()
        all_stops = self.trailing_stops.get_all_stops()

        # Sector exposure summary
        sector_counts: dict[str, int] = {}
        for sector in self.sector_map.values():
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        return {
            "account_balance": round(self.account_balance, 2),
            "peak_balance": round(self.peak_balance, 2),
            "current_drawdown": self.get_current_drawdown(),
            "drawdown_halted": self.drawdown_halted,
            "portfolio": portfolio_summary,
            "trailing_stops": all_stops,
            "sector_exposure": sector_counts,
            "trades_evaluated": len(self.trade_log),
            "trades_approved": sum(1 for t in self.trade_log if t["approved"]),
            "trades_rejected": sum(1 for t in self.trade_log if not t["approved"]),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def print_risk_report(self) -> None:
        """
        Print a formatted console report of the current risk status.

        Displays account overview, open positions with trailing stops,
        sector exposure, and any active risk violations.
        """
        summary = self.get_risk_summary()

        print("\n" + "=" * 80)
        print(f"  RISK STATUS REPORT — "
              f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 80)

        # Account overview
        dd_pct = summary["current_drawdown"] * 100
        print(f"\n  Account Balance:  ${summary['account_balance']:,.2f}")
        print(f"  Peak Balance:     ${summary['peak_balance']:,.2f}")
        print(f"  Current Drawdown: {dd_pct:.1f}%"
              f"{'  *** HALTED ***' if summary['drawdown_halted'] else ''}")
        print(f"  Daily P&L:        ${summary['portfolio']['daily_pnl']:+,.2f} "
              f"({summary['portfolio']['daily_pnl_pct']:+.2f}%)")
        print(f"  Trading Halted:   "
              f"{'YES' if summary['portfolio']['trading_halted'] else 'No'}")

        # Position overview
        port = summary["portfolio"]
        print(f"\n  Open Positions:   {port['open_positions']} / "
              f"{port['max_positions']}")
        print(f"  Unrealized P&L:   ${port['unrealized_pnl']:+,.2f}")

        # Trailing stops
        if summary["trailing_stops"]:
            print(f"\n  {'Symbol':<8} {'Trail Stop':>12}")
            print("  " + "-" * 22)
            for sym, stop in summary["trailing_stops"].items():
                print(f"  {sym:<8} ${stop:>10,.2f}")

        # Sector exposure
        if summary["sector_exposure"]:
            print(f"\n  Sector Exposure:")
            for sector, count in sorted(
                summary["sector_exposure"].items(),
                key=lambda x: x[1], reverse=True,
            ):
                bar = "#" * count
                print(f"    {sector:<25} {count} {bar}")

        # Decision stats
        print(f"\n  Trades Evaluated: {summary['trades_evaluated']}")
        print(f"  Trades Approved:  {summary['trades_approved']}")
        print(f"  Trades Rejected:  {summary['trades_rejected']}")
        print(f"  Violations Today: {port['violations_today']}")

        print("=" * 80 + "\n")
