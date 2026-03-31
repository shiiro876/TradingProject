# =============================================================================
# learning/backtester.py — Historical Strategy Backtester
# =============================================================================
#
# PURPOSE:
#   Replays historical market data through the trading system's pipeline
#   (scanner scoring → signal generation → risk checks → execution → exit)
#   to evaluate how the strategy would have performed in the past.
#
#   Backtesting is essential for validating a strategy before risking real
#   money. It answers: "If I had used these exact rules last month/year,
#   what would my P&L have been?"
#
# HOW IT WORKS:
#   1. Accept OHLCV DataFrames (one per symbol) with pre-computed indicators.
#   2. Walk through each bar chronologically, simulating day-by-day trading.
#   3. At each bar: generate signals, evaluate risk, execute fills, monitor
#      positions for exits (trailing stop, TP1, TP2).
#   4. Track all trades and produce a comprehensive performance report.
#
# KEY CLASSES:
#   - Backtester(account_balance, max_positions, risk_per_trade)
#       Configures and runs the backtest simulation.
#
#   - run(symbol_data)              → Execute the backtest.
#   - get_results()                 → Get trade log and performance metrics.
#   - get_equity_curve()            → Get balance over time.
#   - print_backtest_report()       → Formatted console output.
#
# USAGE:
#   from learning.backtester import Backtester
#   bt = Backtester(account_balance=10000)
#   bt.run(symbol_data={"AAPL": df_aapl, "XOM": df_xom})
#   results = bt.get_results()
#   bt.print_backtest_report()
#
# =============================================================================

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from config.settings import (
    MAX_RISK_PER_TRADE,
    MAX_POSITIONS,
    ATR_STOP_MULTIPLIER,
    MIN_RR_RATIO,
    TP1_MULTIPLIER,
    TP2_MULTIPLIER,
)

logger = logging.getLogger(__name__)


class Backtester:
    """
    Historical strategy backtester that simulates trading over past data.

    Walks through OHLCV data bar-by-bar, generating signals, checking risk,
    simulating entries and exits, and tracking performance. The backtest
    fully respects position limits, risk sizing, and trailing stops.

    Attributes:
        account_balance   (float): Starting account balance.
        max_positions     (int):   Maximum simultaneous positions.
        risk_per_trade    (float): Fraction of account to risk per trade.
        min_rr_ratio      (float): Minimum R:R ratio for signal acceptance.
        atr_stop_mult     (float): ATR multiplier for stop-loss distance.
        trades            (list):  Log of all completed trades.
        equity_curve      (list):  Balance at each bar.
        open_positions    (dict):  Currently open positions.
    """

    def __init__(
        self,
        account_balance: float = 10000.0,
        max_positions: int = MAX_POSITIONS,
        risk_per_trade: float = MAX_RISK_PER_TRADE,
        min_rr_ratio: float = MIN_RR_RATIO,
        atr_stop_multiplier: float = ATR_STOP_MULTIPLIER,
    ):
        """
        Initialize the backtester with strategy parameters.

        Args:
            account_balance:    Starting capital in dollars.
            max_positions:      Maximum number of open positions.
            risk_per_trade:     Fraction of account to risk per trade (0.02=2%).
            min_rr_ratio:       Minimum R:R ratio to accept a signal.
            atr_stop_multiplier: ATR multiplier for stop distance.
        """
        self.initial_balance = account_balance
        self.account_balance = account_balance
        self.max_positions = max_positions
        self.risk_per_trade = risk_per_trade
        self.min_rr_ratio = min_rr_ratio
        self.atr_stop_mult = atr_stop_multiplier

        # State
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.open_positions: dict[str, dict] = {}

        logger.info(
            "Backtester initialized: balance=$%.2f, max_pos=%d, risk=%.1f%%.",
            account_balance, max_positions, risk_per_trade * 100,
        )

    def run(
        self,
        symbol_data: dict[str, pd.DataFrame],
        score_column: str = "score",
        min_score: float = 5.0,
    ) -> dict:
        """
        Execute the backtest on historical data.

        Iterates through each trading day (bar) chronologically. For each bar:
          1. Update open positions: check trailing stops, TP1, TP2.
          2. Look for new entry signals from symbols that score above min_score.
          3. Execute entries if risk checks pass.
          4. Record equity at end of bar.

        The input DataFrames should have these columns:
          - open, high, low, close, volume (standard OHLCV)
          - atr (Average True Range, from indicators.py)
          - score (scanner score 0-10, optional — can be pre-computed or
            a simple stand-in based on indicator flags)

        Args:
            symbol_data:  Dict mapping symbol → OHLCV DataFrame (DatetimeIndex).
            score_column: Column name containing the stock score (default "score").
            min_score:    Minimum score to generate a signal (default 5.0).

        Returns:
            Dictionary with:
                total_trades   (int):   Total completed trades.
                total_return   (float): Percentage return.
                final_balance  (float): Ending balance.
                message        (str):   Summary message.
        """
        if not symbol_data:
            return {
                "total_trades": 0,
                "total_return": 0.0,
                "final_balance": self.account_balance,
                "message": "No data provided.",
            }

        # Reset state for a fresh backtest
        self.account_balance = self.initial_balance
        self.trades = []
        self.equity_curve = []
        self.open_positions = {}

        # Collect all unique dates across all symbols and sort chronologically
        all_dates = set()
        for df in symbol_data.values():
            if isinstance(df.index, pd.DatetimeIndex):
                all_dates.update(df.index)
            elif "date" in df.columns:
                all_dates.update(pd.to_datetime(df["date"]))

        if not all_dates:
            return {
                "total_trades": 0,
                "total_return": 0.0,
                "final_balance": self.account_balance,
                "message": "No dates found in data.",
            }

        sorted_dates = sorted(all_dates)

        # Walk through each bar
        for bar_date in sorted_dates:
            self._process_bar(bar_date, symbol_data, score_column, min_score)

            # Record equity (account + unrealized positions)
            equity = self._calculate_equity(bar_date, symbol_data)
            self.equity_curve.append({
                "date": bar_date,
                "equity": round(equity, 2),
                "cash": round(self.account_balance, 2),
                "open_positions": len(self.open_positions),
            })

        # Close any remaining open positions at last bar's close
        self._close_all_remaining(sorted_dates[-1], symbol_data)

        total_return = round(
            ((self.account_balance - self.initial_balance) / self.initial_balance) * 100, 2
        )

        result = {
            "total_trades": len(self.trades),
            "total_return": total_return,
            "final_balance": round(self.account_balance, 2),
            "message": (
                f"Backtest complete: {len(self.trades)} trades, "
                f"{total_return:+.2f}% return, "
                f"final balance ${self.account_balance:,.2f}."
            ),
        }

        logger.info(result["message"])
        return result

    def get_results(self) -> dict:
        """
        Get comprehensive backtest results and performance metrics.

        Returns:
            Dictionary containing:
                trades          (list):  All completed trade records.
                total_trades    (int):   Number of trades.
                wins / losses   (int):   Count of winning / losing trades.
                win_rate        (float): Percentage of winning trades.
                total_pnl       (float): Total profit/loss in dollars.
                total_return    (float): Percentage return.
                avg_win / avg_loss (float): Average win/loss amounts.
                profit_factor   (float): Gross profit / |gross loss|.
                max_drawdown    (float): Largest peak-to-trough decline.
                final_balance   (float): Ending balance.
        """
        if not self.trades:
            return _empty_backtest_results(self.initial_balance)

        pnls = [t["pnl"] for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = round(sum(pnls), 2)
        win_rate = round(len(wins) / len(pnls) * 100, 2) if pnls else 0.0
        avg_win = round(sum(wins) / len(wins), 2) if wins else 0.0
        avg_loss = round(sum(losses) / len(losses), 2) if losses else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

        # Max drawdown from equity curve
        max_dd = self._calculate_max_drawdown()

        total_return = round(
            ((self.account_balance - self.initial_balance) / self.initial_balance) * 100, 2
        )

        return {
            "trades": self.trades,
            "total_trades": len(self.trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "total_return": total_return,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown": max_dd,
            "final_balance": round(self.account_balance, 2),
            "initial_balance": self.initial_balance,
        }

    def get_equity_curve(self) -> list[dict]:
        """
        Get the equity curve (balance at each bar).

        Returns:
            List of dicts with date, equity, cash, open_positions.
        """
        return list(self.equity_curve)

    def print_backtest_report(self) -> None:
        """
        Print a formatted backtest results report.
        """
        results = self.get_results()

        print("\n" + "=" * 60)
        print("  📊 BACKTEST RESULTS")
        print("=" * 60)

        if results["total_trades"] == 0:
            print("  No trades executed during backtest.")
            print("=" * 60)
            return

        print(f"  Initial Balance:  ${results['initial_balance']:,.2f}")
        print(f"  Final Balance:    ${results['final_balance']:,.2f}")
        print(f"  Total Return:     {results['total_return']:+.2f}%")
        print(f"  Total P&L:        ${results['total_pnl']:+,.2f}")
        print("-" * 60)
        print(f"  Total Trades:     {results['total_trades']}")
        print(f"  Wins:             {results['wins']}")
        print(f"  Losses:           {results['losses']}")
        print(f"  Win Rate:         {results['win_rate']:.1f}%")
        print("-" * 60)
        print(f"  Average Win:      ${results['avg_win']:+,.2f}")
        print(f"  Average Loss:     ${results['avg_loss']:+,.2f}")
        print(f"  Profit Factor:    {results['profit_factor']:.2f}")
        print(f"  Max Drawdown:     ${results['max_drawdown']:,.2f}")
        print("=" * 60 + "\n")

    # =========================================================================
    # Private: Bar-by-bar Processing
    # =========================================================================

    def _process_bar(
        self,
        bar_date,
        symbol_data: dict[str, pd.DataFrame],
        score_column: str,
        min_score: float,
    ) -> None:
        """Process a single bar: update positions, then check for new entries."""

        # Step 1: Update existing positions (check exits)
        symbols_to_close = []
        for symbol, pos in list(self.open_positions.items()):
            df = symbol_data.get(symbol)
            if df is None:
                continue

            bar = self._get_bar(df, bar_date)
            if bar is None:
                continue

            current_high = float(bar.get("high", bar.get("close", 0)))
            current_low = float(bar.get("low", bar.get("close", 0)))
            current_close = float(bar.get("close", 0))
            current_atr = float(bar.get("atr", 0)) if "atr" in bar.index else 0

            # Update trailing stop (ratchet up if new high)
            if current_high > pos["highest_price"]:
                pos["highest_price"] = current_high
                if current_atr > 0:
                    new_stop = current_high - (current_atr * 1.5)
                    pos["trailing_stop"] = max(pos["trailing_stop"], new_stop)

            # Check exit conditions
            exit_price = None
            exit_reason = None

            # 1. Stop hit (use low of bar)
            if current_low <= pos["trailing_stop"]:
                exit_price = pos["trailing_stop"]
                exit_reason = "trailing_stop"

            # 2. TP2 hit (full close)
            elif current_high >= pos["take_profit_2"]:
                exit_price = pos["take_profit_2"]
                exit_reason = "tp2"

            # 3. TP1 hit (partial — we simplify to full close at TP1 for backtesting)
            elif current_high >= pos["take_profit_1"] and not pos.get("tp1_hit"):
                exit_price = pos["take_profit_1"]
                exit_reason = "tp1"

            if exit_price is not None:
                symbols_to_close.append((symbol, exit_price, exit_reason, bar_date))

        # Execute closes
        for symbol, exit_price, exit_reason, date in symbols_to_close:
            self._close_position(symbol, exit_price, exit_reason, date)

        # Step 2: Look for new entries (only if we have capacity)
        if len(self.open_positions) >= self.max_positions:
            return

        for symbol, df in symbol_data.items():
            if symbol in self.open_positions:
                continue
            if len(self.open_positions) >= self.max_positions:
                break

            bar = self._get_bar(df, bar_date)
            if bar is None:
                continue

            score = float(bar.get(score_column, 0)) if score_column in bar.index else 0
            if score < min_score:
                continue

            atr = float(bar.get("atr", 0)) if "atr" in bar.index else 0
            close_price = float(bar.get("close", 0))

            if atr <= 0 or close_price <= 0:
                continue

            # Generate entry setup
            risk_per_share = atr * self.atr_stop_mult
            if risk_per_share >= close_price:
                continue

            stop_loss = close_price - risk_per_share
            tp1 = close_price + (TP1_MULTIPLIER * risk_per_share)
            tp2 = close_price + (TP2_MULTIPLIER * risk_per_share)
            rr_ratio = (tp1 - close_price) / risk_per_share if risk_per_share > 0 else 0

            if rr_ratio < self.min_rr_ratio:
                continue

            # Position sizing (2% rule)
            risk_dollars = self.account_balance * self.risk_per_trade
            shares = int(risk_dollars / risk_per_share) if risk_per_share > 0 else 0
            if shares <= 0:
                continue

            cost = shares * close_price
            if cost > self.account_balance:
                shares = int(self.account_balance / close_price)
                cost = shares * close_price
                if shares <= 0:
                    continue

            # Execute entry
            self.account_balance -= cost
            self.open_positions[symbol] = {
                "symbol": symbol,
                "shares": shares,
                "entry_price": close_price,
                "stop_loss": stop_loss,
                "trailing_stop": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "risk_per_share": risk_per_share,
                "highest_price": close_price,
                "entry_date": bar_date,
                "score": score,
                "tp1_hit": False,
            }

    def _close_position(self, symbol: str, exit_price: float, reason: str, date) -> None:
        """Close a position and record the trade."""
        if symbol not in self.open_positions:
            return

        pos = self.open_positions.pop(symbol)
        shares = pos["shares"]
        entry_price = pos["entry_price"]
        pnl = round((exit_price - entry_price) * shares, 2)

        self.account_balance += shares * exit_price

        self.trades.append({
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "shares": shares,
            "pnl": pnl,
            "pnl_percent": round((exit_price - entry_price) / entry_price * 100, 2),
            "exit_reason": reason,
            "entry_date": pos.get("entry_date"),
            "exit_date": date,
            "score": pos.get("score", 0),
        })

    def _close_all_remaining(self, last_date, symbol_data: dict[str, pd.DataFrame]) -> None:
        """Close all open positions at the last bar's close price."""
        for symbol in list(self.open_positions.keys()):
            df = symbol_data.get(symbol)
            if df is not None:
                bar = self._get_bar(df, last_date)
                close = float(bar.get("close", 0)) if bar is not None else 0
            else:
                close = self.open_positions[symbol]["entry_price"]  # Fallback

            if close > 0:
                self._close_position(symbol, close, "end_of_backtest", last_date)

    def _get_bar(self, df: pd.DataFrame, date) -> pd.Series | None:
        """Safely get a single bar (row) from a DataFrame by date."""
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                if date in df.index:
                    return df.loc[date]
            elif "date" in df.columns:
                mask = pd.to_datetime(df["date"]) == pd.Timestamp(date)
                matches = df[mask]
                if not matches.empty:
                    return matches.iloc[0]
        except Exception:
            pass
        return None

    def _calculate_equity(self, bar_date, symbol_data: dict[str, pd.DataFrame]) -> float:
        """Calculate total equity = cash + sum(open position market values)."""
        equity = self.account_balance
        for symbol, pos in self.open_positions.items():
            df = symbol_data.get(symbol)
            if df is not None:
                bar = self._get_bar(df, bar_date)
                price = float(bar.get("close", pos["entry_price"])) if bar is not None else pos["entry_price"]
            else:
                price = pos["entry_price"]
            equity += pos["shares"] * price
        return equity

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from the equity curve."""
        if not self.equity_curve:
            return 0.0

        equities = [e["equity"] for e in self.equity_curve]
        peak = equities[0]
        max_dd = 0.0

        for eq in equities:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd

        return round(max_dd, 2)


def _empty_backtest_results(initial_balance: float) -> dict:
    """Return zeroed results when no trades were executed."""
    return {
        "trades": [],
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "total_return": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "final_balance": initial_balance,
        "initial_balance": initial_balance,
    }
