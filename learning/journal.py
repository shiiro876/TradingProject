# =============================================================================
# learning/journal.py — Automated Trade Journal
# =============================================================================
#
# PURPOSE:
#   Automatically logs every trade to a CSV file and provides comprehensive
#   performance statistics. This replaces manual journaling — every trade
#   entry, exit, P&L, and reason is recorded without human intervention.
#
#   A trade journal is critical for improving as a trader because it allows
#   systematic review of what works and what doesn't. The performance stats
#   (win rate, profit factor, max drawdown, etc.) are the key metrics used
#   to evaluate whether a trading strategy is profitable.
#
# JOURNAL COLUMNS:
#   date, symbol, direction, entry_price, exit_price, shares, stop_loss,
#   take_profit_1, take_profit_2, risk_reward, profit_loss_dollar,
#   profit_loss_percent, win_loss, exit_reason, notes
#
# KEY FUNCTIONS:
#   - TradeJournal(journal_path)
#       Class that manages the trade journal CSV file.
#
#   - log_trade(...)            → Write a new trade entry to the CSV.
#   - get_all_trades()          → Load all historical trades as a DataFrame.
#   - get_performance_stats()   → Calculate win rate, profit factor, etc.
#   - print_performance_report() → Formatted console output of stats.
#
# USAGE:
#   from learning.journal import TradeJournal
#   journal = TradeJournal()
#   journal.log_trade(
#       symbol="AAPL", direction="LONG", entry_price=150.0,
#       exit_price=155.0, shares=50, exit_reason="tp1",
#   )
#   stats = journal.get_performance_stats()
#   journal.print_performance_report()
#
# =============================================================================

import os
import logging
from datetime import datetime

import pandas as pd

from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

# Column schema for the trade journal CSV
JOURNAL_COLUMNS = [
    "date",               # Date the trade was closed (YYYY-MM-DD)
    "symbol",             # Stock ticker (e.g., "AAPL")
    "direction",          # Trade direction: "LONG" or "SHORT"
    "entry_price",        # Price at which the trade was entered
    "exit_price",         # Price at which the trade was closed
    "shares",             # Number of shares traded
    "stop_loss",          # Stop loss price that was set
    "take_profit_1",      # First profit target price
    "take_profit_2",      # Second profit target price
    "risk_reward",        # Risk:reward ratio of the trade setup
    "profit_loss_dollar", # Dollar profit or loss (positive = profit)
    "profit_loss_percent",# Percentage return on the trade
    "win_loss",           # "WIN" if profitable, "LOSS" if not
    "exit_reason",        # Why the trade was closed: stop/tp1/tp2/manual
    "notes",              # Optional notes or observations
]


class TradeJournal:
    """
    Manages the automated trade journal for logging and analyzing trades.

    The journal is stored as a CSV file at the configured path. New trades
    are appended to the file, and performance statistics are calculated
    from all historical entries.

    Attributes:
        journal_path (str): Absolute path to the journal CSV file.
    """

    def __init__(self, journal_path: str | None = None):
        """
        Initialize the trade journal.

        Creates the journal CSV file with headers if it does not already exist.

        Args:
            journal_path: Path to the CSV file. Defaults to data/trades.csv.
        """
        if journal_path is None:
            journal_path = os.path.join(DATA_DIR, "trades.csv")

        self.journal_path = journal_path

        # Create the file with headers if it doesn't exist yet
        if not os.path.isfile(self.journal_path):
            os.makedirs(os.path.dirname(self.journal_path), exist_ok=True)
            pd.DataFrame(columns=JOURNAL_COLUMNS).to_csv(
                self.journal_path, index=False
            )
            logger.info("Created new trade journal at '%s'.", self.journal_path)

    def log_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        shares: int | float,
        stop_loss: float | None = None,
        take_profit_1: float | None = None,
        take_profit_2: float | None = None,
        risk_reward: float | None = None,
        exit_reason: str = "manual",
        notes: str = "",
    ) -> dict:
        """
        Log a completed trade to the journal CSV.

        Automatically calculates dollar P&L, percentage P&L, and win/loss
        classification from the entry and exit prices.

        Args:
            symbol:         Stock ticker (e.g., "AAPL").
            direction:      "LONG" or "SHORT".
            entry_price:    Price at entry.
            exit_price:     Price at exit.
            shares:         Number of shares traded.
            stop_loss:      Stop loss price that was set (optional).
            take_profit_1:  First profit target (optional).
            take_profit_2:  Second profit target (optional).
            risk_reward:    The R:R ratio of the setup (optional).
            exit_reason:    Why closed: "stop", "tp1", "tp2", or "manual".
            notes:          Free-text notes (optional).

        Returns:
            Dictionary containing the full trade record that was written.
        """
        # Calculate P&L based on direction
        if direction.upper() == "LONG":
            pl_dollar = round((exit_price - entry_price) * shares, 2)
        else:  # SHORT
            pl_dollar = round((entry_price - exit_price) * shares, 2)

        # Calculate percentage return relative to entry value
        entry_value = entry_price * shares
        pl_percent = round((pl_dollar / entry_value) * 100, 2) if entry_value > 0 else 0.0

        # Classify as win or loss
        win_loss = "WIN" if pl_dollar > 0 else "LOSS"

        # Build the trade record
        trade_record = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "symbol": symbol,
            "direction": direction.upper(),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "shares": shares,
            "stop_loss": stop_loss,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "risk_reward": risk_reward,
            "profit_loss_dollar": pl_dollar,
            "profit_loss_percent": pl_percent,
            "win_loss": win_loss,
            "exit_reason": exit_reason,
            "notes": notes,
        }

        # Append to CSV file
        row_df = pd.DataFrame([trade_record])
        row_df.to_csv(self.journal_path, mode="a", header=False, index=False)

        logger.info(
            "Trade logged: %s %s — %s shares @ $%.2f → $%.2f = %s $%.2f (%+.2f%%).",
            direction.upper(), symbol, shares, entry_price, exit_price,
            win_loss, pl_dollar, pl_percent,
        )

        return trade_record

    def get_all_trades(self) -> pd.DataFrame:
        """
        Load all trades from the journal CSV into a DataFrame.

        Returns:
            DataFrame with all journal columns. Returns an empty DataFrame
            with correct columns if the journal is empty or unreadable.
        """
        try:
            df = pd.read_csv(self.journal_path)
            if df.empty:
                return pd.DataFrame(columns=JOURNAL_COLUMNS)
            return df
        except Exception as exc:
            logger.error("Failed to read journal: %s", exc)
            return pd.DataFrame(columns=JOURNAL_COLUMNS)

    def get_performance_stats(self) -> dict:
        """
        Calculate comprehensive performance statistics from the trade journal.

        Metrics computed:
          - Total trades, wins, losses
          - Win rate percentage
          - Average win and average loss in dollars
          - Profit factor (gross profits / gross losses)
          - Total P&L in dollars
          - Max drawdown (largest peak-to-trough decline)
          - Best and worst individual trades
          - Monthly P&L breakdown

        Returns:
            Dictionary of performance metrics. Returns zeroed metrics if
            the journal has no trades.
        """
        df = self.get_all_trades()

        if df.empty or "profit_loss_dollar" not in df.columns:
            return _empty_stats()

        total_trades = len(df)
        wins = df[df["win_loss"] == "WIN"]
        losses = df[df["win_loss"] == "LOSS"]

        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round((win_count / total_trades) * 100, 2) if total_trades > 0 else 0.0

        # Average win and loss amounts
        avg_win = round(wins["profit_loss_dollar"].mean(), 2) if not wins.empty else 0.0
        avg_loss = round(losses["profit_loss_dollar"].mean(), 2) if not losses.empty else 0.0

        # Profit factor = gross profits / |gross losses|
        gross_profits = wins["profit_loss_dollar"].sum() if not wins.empty else 0.0
        gross_losses = abs(losses["profit_loss_dollar"].sum()) if not losses.empty else 0.0
        profit_factor = round(gross_profits / gross_losses, 2) if gross_losses > 0 else float("inf")

        # Total P&L
        total_pnl = round(df["profit_loss_dollar"].sum(), 2)

        # Best and worst trades
        best_trade = round(df["profit_loss_dollar"].max(), 2) if total_trades > 0 else 0.0
        worst_trade = round(df["profit_loss_dollar"].min(), 2) if total_trades > 0 else 0.0

        # Max drawdown calculation (cumulative P&L peak-to-trough)
        cumulative_pnl = df["profit_loss_dollar"].cumsum()
        running_max = cumulative_pnl.cummax()
        drawdown = cumulative_pnl - running_max
        max_drawdown = round(drawdown.min(), 2) if not drawdown.empty else 0.0

        # Monthly P&L summary
        monthly_pnl = {}
        if "date" in df.columns:
            try:
                df_copy = df.copy()
                df_copy["month"] = pd.to_datetime(df_copy["date"]).dt.to_period("M").astype(str)
                monthly_pnl = df_copy.groupby("month")["profit_loss_dollar"].sum().round(2).to_dict()
            except Exception:
                monthly_pnl = {}

        return {
            "total_trades": total_trades,
            "wins": win_count,
            "losses": loss_count,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "total_pnl": total_pnl,
            "best_trade": best_trade,
            "worst_trade": worst_trade,
            "max_drawdown": max_drawdown,
            "monthly_pnl": monthly_pnl,
        }

    def print_performance_report(self) -> None:
        """
        Print a formatted performance report to the console.

        Displays all key metrics in a clear, readable format suitable for
        daily or weekly review of trading performance.
        """
        stats = self.get_performance_stats()

        print("\n" + "=" * 60)
        print("  📋 TRADE JOURNAL — Performance Report")
        print("=" * 60)

        if stats["total_trades"] == 0:
            print("  No trades recorded yet.")
            print("=" * 60)
            return

        print(f"  Total Trades:     {stats['total_trades']}")
        print(f"  Wins:             {stats['wins']}")
        print(f"  Losses:           {stats['losses']}")
        print(f"  Win Rate:         {stats['win_rate']:.1f}%")
        print("-" * 60)
        print(f"  Average Win:      ${stats['avg_win']:+.2f}")
        print(f"  Average Loss:     ${stats['avg_loss']:+.2f}")
        print(f"  Best Trade:       ${stats['best_trade']:+.2f}")
        print(f"  Worst Trade:      ${stats['worst_trade']:+.2f}")
        print("-" * 60)
        print(f"  Profit Factor:    {stats['profit_factor']:.2f}")
        print(f"  Total P&L:        ${stats['total_pnl']:+.2f}")
        print(f"  Max Drawdown:     ${stats['max_drawdown']:.2f}")

        # Monthly summary
        if stats["monthly_pnl"]:
            print("-" * 60)
            print("  Monthly P&L:")
            for month, pnl in stats["monthly_pnl"].items():
                print(f"    {month}:  ${pnl:+.2f}")

        print("=" * 60 + "\n")


def _empty_stats() -> dict:
    """
    Return zeroed performance stats when no trades exist.

    Ensures downstream code receives a consistent dictionary shape even
    when the journal is empty.
    """
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
