# =============================================================================
# learning/optimizer.py — Strategy Parameter Optimizer
# =============================================================================
#
# PURPOSE:
#   Searches for the best strategy parameters by running multiple backtests
#   with different configurations. This is how the system "self-improves" —
#   it finds the parameter combination (scoring weights, thresholds, ATR
#   multipliers) that would have produced the best historical results.
#
# HOW IT WORKS:
#   1. Define a parameter grid: ranges for each setting to test.
#   2. For each combination, configure a Backtester and run it on the data.
#   3. Score each run by a target metric (e.g., total return, profit factor).
#   4. Return the ranked results so the user can pick the best parameters.
#
# KEY CLASSES:
#   - StrategyOptimizer(symbol_data)
#       Manages parameter search and result ranking.
#
#   - optimize(param_grid, metric)  → Run grid search, return ranked results.
#   - get_best_params()             → Get the top-performing parameter set.
#   - get_optimization_results()    → Get all results sorted by metric.
#   - print_optimization_report()   → Formatted console output.
#
# USAGE:
#   from learning.optimizer import StrategyOptimizer
#   optimizer = StrategyOptimizer(symbol_data={"AAPL": df_aapl})
#   param_grid = {
#       "atr_stop_multiplier": [1.5, 2.0, 2.5],
#       "min_score": [4.0, 5.0, 6.0],
#   }
#   results = optimizer.optimize(param_grid, metric="total_return")
#   best = optimizer.get_best_params()
#
# =============================================================================

import logging
from itertools import product
from datetime import datetime

from learning.backtester import Backtester

logger = logging.getLogger(__name__)


class StrategyOptimizer:
    """
    Parameter optimizer that grid-searches strategy configurations.

    Runs multiple backtests with different parameter combinations and
    ranks them by a target metric. This allows the system to find the
    best settings for scoring thresholds, stop distances, risk sizing,
    and position limits.

    Attributes:
        symbol_data      (dict): Historical OHLCV data for backtesting.
        account_balance  (float): Starting capital for each backtest.
        results          (list): Ranked optimization results.
        best_params      (dict | None): Top-performing parameter set.
    """

    def __init__(
        self,
        symbol_data: dict,
        account_balance: float = 10000.0,
    ):
        """
        Initialize the optimizer.

        Args:
            symbol_data:    Dict mapping symbol → OHLCV DataFrame.
            account_balance: Starting capital for each backtest run.
        """
        self.symbol_data = symbol_data
        self.account_balance = account_balance
        self.results: list[dict] = []
        self.best_params: dict | None = None

        logger.info("StrategyOptimizer initialized with %d symbols.", len(symbol_data))

    def optimize(
        self,
        param_grid: dict[str, list],
        metric: str = "total_return",
        min_score: float = 5.0,
    ) -> list[dict]:
        """
        Run a grid search over parameter combinations.

        For each combination in the grid, configures a Backtester, runs it
        on the stored symbol_data, and records the performance. Results are
        sorted by the target metric (descending).

        Supported parameters in the grid:
          - atr_stop_multiplier (float): ATR multiplier for stop distance.
          - risk_per_trade (float): Fraction of account to risk (e.g., 0.02).
          - max_positions (int): Maximum simultaneous positions.
          - min_rr_ratio (float): Minimum R:R ratio for signal acceptance.
          - min_score (float): Minimum scanner score for entry signal.

        Supported metrics for ranking:
          - total_return: Percentage return over the backtest period.
          - total_pnl: Absolute dollar profit/loss.
          - profit_factor: Gross profit / |gross loss|.
          - win_rate: Percentage of winning trades.

        Args:
            param_grid: Dictionary mapping parameter names to lists of values.
                        Example: {"atr_stop_multiplier": [1.5, 2.0, 2.5]}
            metric:     Target metric to optimize (default "total_return").
            min_score:  Default minimum score if not in param_grid.

        Returns:
            List of result dicts sorted by metric (best first).
        """
        if not param_grid:
            logger.warning("Empty parameter grid. Nothing to optimize.")
            return []

        # Generate all combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))

        logger.info(
            "Starting optimization: %d combinations to test.",
            len(combinations),
        )

        self.results = []

        for combo in combinations:
            params = dict(zip(param_names, combo))

            # Extract backtester params (with defaults)
            bt_params = {
                "account_balance": self.account_balance,
                "max_positions": int(params.get("max_positions", 3)),
                "risk_per_trade": float(params.get("risk_per_trade", 0.02)),
                "min_rr_ratio": float(params.get("min_rr_ratio", 1.5)),
                "atr_stop_multiplier": float(params.get("atr_stop_multiplier", 2.0)),
            }
            run_min_score = float(params.get("min_score", min_score))

            # Run backtest with these params
            bt = Backtester(**bt_params)
            bt.run(self.symbol_data, min_score=run_min_score)
            bt_results = bt.get_results()

            # Record the result
            result_entry = {
                "params": params,
                "total_return": bt_results.get("total_return", 0.0),
                "total_pnl": bt_results.get("total_pnl", 0.0),
                "total_trades": bt_results.get("total_trades", 0),
                "win_rate": bt_results.get("win_rate", 0.0),
                "profit_factor": bt_results.get("profit_factor", 0.0),
                "max_drawdown": bt_results.get("max_drawdown", 0.0),
                "final_balance": bt_results.get("final_balance", self.account_balance),
            }
            self.results.append(result_entry)

        # Sort by target metric (descending)
        self.results.sort(
            key=lambda r: r.get(metric, 0), reverse=True
        )

        # Best params
        if self.results:
            self.best_params = self.results[0]["params"]
            logger.info(
                "Optimization complete. Best %s=%.2f with params=%s.",
                metric, self.results[0].get(metric, 0), self.best_params,
            )

        return self.results

    def get_best_params(self) -> dict | None:
        """
        Get the top-performing parameter set.

        Returns:
            Dictionary of parameter values, or None if no optimization run.
        """
        return self.best_params

    def get_optimization_results(self) -> list[dict]:
        """
        Get all optimization results sorted by the target metric.

        Returns:
            List of result dicts, each with params and performance metrics.
        """
        return list(self.results)

    def get_optimization_summary(self) -> dict:
        """
        Get a summary of the optimization run.

        Returns:
            Dictionary with run count, best params, and top/bottom results.
        """
        if not self.results:
            return {
                "total_runs": 0,
                "best_params": None,
                "best_result": None,
                "worst_result": None,
            }

        return {
            "total_runs": len(self.results),
            "best_params": self.best_params,
            "best_result": self.results[0] if self.results else None,
            "worst_result": self.results[-1] if self.results else None,
        }

    def print_optimization_report(self, top_n: int = 5) -> None:
        """
        Print a formatted optimization results report.

        Args:
            top_n: Number of top results to show (default 5).
        """
        print("\n" + "=" * 80)
        print("  ⚡ STRATEGY OPTIMIZATION RESULTS")
        print("=" * 80)

        if not self.results:
            print("  No optimization results. Run optimize() first.")
            print("=" * 80)
            return

        print(f"  Total Combinations Tested: {len(self.results)}")
        print(f"  Best Parameters: {self.best_params}")
        print("-" * 80)

        # Header
        print(
            f"  {'Rank':<6} {'Return':>8} {'P&L':>10} {'Trades':>7} "
            f"{'Win%':>6} {'PF':>6} {'MaxDD':>8}  Parameters"
        )
        print("-" * 80)

        # Top N results
        for i, result in enumerate(self.results[:top_n], 1):
            params_str = ", ".join(
                f"{k}={v}" for k, v in result["params"].items()
            )
            print(
                f"  {i:<6} {result['total_return']:>+7.2f}% "
                f"${result['total_pnl']:>+8.2f} "
                f"{result['total_trades']:>7} "
                f"{result['win_rate']:>5.1f}% "
                f"{result['profit_factor']:>5.2f} "
                f"${result['max_drawdown']:>7.2f}  "
                f"{params_str}"
            )

        print("=" * 80 + "\n")
