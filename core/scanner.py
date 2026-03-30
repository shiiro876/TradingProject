# =============================================================================
# core/scanner.py — Market Scanner Engine
# =============================================================================
#
# PURPOSE:
#   Scans the stock universe (watchlist) each day, runs all technical
#   indicators on every stock, assigns a composite score (0–10), and returns
#   the top N ranked stocks with plain-English reasoning for each pick.
#
#   This replaces the manual process of checking charts one by one. The
#   scanner automates what a human trader does each morning: look at price,
#   volume, RSI, MACD, and moving averages to find the best setups.
#
# KEY FUNCTIONS:
#   - scan_stock(symbol, df)
#       Runs indicators on a single stock and returns its score + metadata.
#
#   - score_stock(indicators)
#       Converts raw indicator signals into a 0–10 score using weighted rules.
#
#   - generate_reason(indicators, score)
#       Builds a plain-English explanation of why a stock scored well/poorly.
#
#   - run_full_scan(symbols, period, interval)
#       Orchestrates the full scanning pipeline: fetch data → analyze →
#       score → rank → return top N results.
#
#   - save_scan_results(results, output_dir)
#       Persists the scan output to a dated CSV file for journaling.
#
#   - print_scan_report(results)
#       Prints a formatted console report of the scan results.
#
# USAGE:
#   from core.scanner import run_full_scan
#   results = run_full_scan()  # Uses default watchlist and settings
#   # results is a list of dicts, sorted by score descending, top N only
#
# =============================================================================

import os
import logging
from datetime import datetime

import pandas as pd

from config.settings import (
    SCANNER_TOP_N,
    SCANNER_DATA_PERIOD,
    SCANNER_DATA_INTERVAL,
    SCORE_WEIGHTS,
    DATA_DIR,
)
from core.utils import get_stock_data, get_multiple_stocks, load_watchlist
from core.indicators import calculate_all_indicators

logger = logging.getLogger(__name__)


def score_stock(indicators: dict) -> float:
    """
    Calculate a composite score (0–10) for a stock based on its indicator signals.

    Each bullish signal detected by the indicator engine adds weighted points
    to the total score. The weights are defined in config/settings.py under
    SCORE_WEIGHTS so they can be tuned without modifying this function.

    Scoring logic:
      - RSI oversold (rsi_bullish)       → +2.0 points
      - MACD bullish crossover           → +2.0 points
      - Price above both 50MA & 200MA    → +1.5 points
      - Bollinger Band breakout          → +1.5 points
      - Volume surge (≥ 2× average)      → +2.0 points
      - ATR within reasonable range      → +1.0 points

    Total possible score: 10.0

    Args:
        indicators: Dictionary from calculate_all_indicators() containing
                    all signal flags and values.

    Returns:
        Float score between 0.0 and 10.0 (higher = more bullish signals).
    """
    score = 0.0

    # RSI: Award points if RSI indicates oversold condition (bounce potential)
    if indicators.get("rsi_bullish"):
        score += SCORE_WEIGHTS["rsi_bullish"]

    # MACD: Award points if a bullish crossover was detected
    if indicators.get("macd_bullish"):
        score += SCORE_WEIGHTS["macd_bullish"]

    # Moving Averages: Award points if price is above both 50MA and 200MA
    if indicators.get("price_above_ma"):
        score += SCORE_WEIGHTS["price_above_ma"]

    # Bollinger Bands: Award points if price broke above upper band
    if indicators.get("bb_breakout"):
        score += SCORE_WEIGHTS["bollinger_breakout"]

    # Volume: Award points if volume is surging above average
    if indicators.get("volume_surge"):
        score += SCORE_WEIGHTS["volume_surge"]

    # ATR: Award points if ATR percentage is in a "favorable" range (1%–5%)
    # Too low ATR = no movement; too high ATR = excessive risk
    atr_pct = indicators.get("atr_percent")
    if atr_pct is not None and 1.0 <= atr_pct <= 5.0:
        score += SCORE_WEIGHTS["atr_favorable"]

    return round(score, 1)


def generate_reason(indicators: dict, score: float) -> str:
    """
    Generate a plain-English explanation of a stock's scanner score.

    Examines each indicator flag and builds a human-readable summary that
    explains WHY the stock received its score. This is critical for the
    trader to understand the reasoning behind each recommendation.

    Args:
        indicators: Dictionary from calculate_all_indicators().
        score:      The composite score from score_stock().

    Returns:
        A string like "Strong buy: RSI oversold + MACD crossover + high volume"
        or "Weak setup: No strong signals detected".
    """
    reasons = []

    # Collect all active bullish signals
    if indicators.get("rsi_bullish"):
        rsi_val = indicators.get("rsi_value", "?")
        reasons.append(f"RSI oversold ({rsi_val})")

    if indicators.get("macd_bullish"):
        reasons.append("MACD bullish crossover")

    if indicators.get("price_above_ma"):
        reasons.append("Price above 50MA & 200MA")
    elif indicators.get("price_above_short"):
        reasons.append("Price above 50MA")

    if indicators.get("bb_breakout"):
        reasons.append("Bollinger Band breakout")

    if indicators.get("volume_surge"):
        ratio = indicators.get("volume_ratio", "?")
        reasons.append(f"Volume surge ({ratio}x avg)")

    if indicators.get("golden_cross"):
        reasons.append("Golden cross (50MA > 200MA)")

    # Determine signal strength label based on score
    if score >= 7.0:
        strength = "Strong buy"
    elif score >= 5.0:
        strength = "Moderate buy"
    elif score >= 3.0:
        strength = "Weak setup"
    else:
        strength = "No signal"

    # Build the final reason string
    if reasons:
        return f"{strength}: {' + '.join(reasons)}"
    else:
        return f"{strength}: No strong signals detected"


def scan_stock(symbol: str, df: pd.DataFrame) -> dict:
    """
    Analyze a single stock: compute indicators, score, and reason.

    This is the per-stock processing step within the full scan pipeline.
    It takes pre-fetched OHLCV data and returns a complete analysis result.

    Args:
        symbol: The stock ticker symbol (e.g., "AAPL").
        df:     The stock's OHLCV DataFrame (from utils.get_stock_data).

    Returns:
        Dictionary containing:
            symbol       (str):   Ticker symbol.
            score        (float): Composite score 0–10.
            reason       (str):   Plain-English explanation.
            current_price (float): Latest closing price.
            rsi_value    (float): Current RSI reading.
            macd_signal  (str):   "Bullish" or "Neutral".
            volume_signal (str):  "Surge" or "Normal".
            indicators   (dict):  Full raw indicator dictionary.
    """
    # Run all technical indicators on this stock's data
    indicators = calculate_all_indicators(df)

    # Calculate composite score from indicator signals
    score = score_stock(indicators)

    # Generate human-readable reasoning
    reason = generate_reason(indicators, score)

    return {
        "symbol": symbol,
        "score": score,
        "reason": reason,
        "current_price": indicators.get("current_price"),
        "rsi_value": indicators.get("rsi_value"),
        "macd_signal": "Bullish" if indicators.get("macd_bullish") else "Neutral",
        "volume_signal": "Surge" if indicators.get("volume_surge") else "Normal",
        "atr_value": indicators.get("atr_value"),
        "indicators": indicators,
    }


def run_full_scan(
    symbols: list[str] | None = None,
    period: str = SCANNER_DATA_PERIOD,
    interval: str = SCANNER_DATA_INTERVAL,
    top_n: int = SCANNER_TOP_N,
) -> list[dict]:
    """
    Execute a full market scan: fetch data, analyze, score, rank, and return.

    This is the primary entry point for the scanner module. It:
      1. Loads the stock universe from the watchlist CSV (or uses provided list).
      2. Downloads OHLCV data for all symbols via yfinance.
      3. Runs all technical indicators on each stock.
      4. Scores each stock 0–10 based on bullish signal count.
      5. Sorts by score descending and returns the top N picks.
      6. Saves results to a dated CSV file in the data/ directory.

    Args:
        symbols:  Optional list of ticker symbols to scan. If None, loads
                  from the watchlist CSV file defined in settings.
        period:   Historical data period (default: "3mo").
        interval: Data interval (default: "1d").
        top_n:    Number of top-ranked stocks to return (default: 5).

    Returns:
        List of dictionaries (one per stock), sorted by score descending,
        limited to top_n results. Each dict contains symbol, score, reason,
        price, and all indicator values.
    """
    # Step 1: Load stock universe
    if symbols is None:
        symbols = load_watchlist()
    logger.info("Starting market scan for %d symbols...", len(symbols))

    # Step 2: Download OHLCV data for all symbols
    stock_data = get_multiple_stocks(symbols, period=period, interval=interval)
    logger.info("Data retrieved for %d / %d symbols.", len(stock_data), len(symbols))

    # Step 3 & 4: Analyze and score each stock
    results = []
    for symbol, df in stock_data.items():
        try:
            result = scan_stock(symbol, df)
            results.append(result)
        except Exception as exc:
            logger.error("Error scanning '%s': %s", symbol, exc)

    # Step 5: Sort by score (descending) and take top N
    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:top_n]

    logger.info(
        "Scan complete. Top %d stocks selected out of %d analyzed.",
        len(top_results),
        len(results),
    )

    # Step 6: Save results to CSV
    save_scan_results(top_results)

    return top_results


def save_scan_results(results: list[dict], output_dir: str = DATA_DIR) -> str:
    """
    Save scan results to a dated CSV file in the data/ directory.

    Creates a file named daily_scan_YYYY-MM-DD.csv with the scan output.
    Also overwrites data/daily_scan.csv as the "latest" scan reference.

    Args:
        results:    List of result dictionaries from run_full_scan().
        output_dir: Directory to save the CSV files to.

    Returns:
        Path to the saved CSV file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Prepare a clean DataFrame for CSV export (exclude raw indicators dict)
    rows = []
    for r in results:
        rows.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "symbol": r["symbol"],
            "score": r["score"],
            "current_price": r["current_price"],
            "rsi_value": r["rsi_value"],
            "macd_signal": r["macd_signal"],
            "volume_signal": r["volume_signal"],
            "atr_value": r["atr_value"],
            "reason": r["reason"],
        })

    df = pd.DataFrame(rows)

    # Save dated file for historical tracking
    date_str = datetime.now().strftime("%Y-%m-%d")
    dated_path = os.path.join(output_dir, f"daily_scan_{date_str}.csv")
    df.to_csv(dated_path, index=False)

    # Save as "latest" for other modules to reference
    latest_path = os.path.join(output_dir, "daily_scan.csv")
    df.to_csv(latest_path, index=False)

    logger.info("Scan results saved to '%s'.", dated_path)
    return dated_path


def print_scan_report(results: list[dict]) -> None:
    """
    Print a formatted console report of scan results.

    Displays a clean ASCII table with the top-ranked stocks, their scores,
    key indicator values, and the plain-English reasoning.

    Args:
        results: List of result dictionaries from run_full_scan().
    """
    print("\n" + "=" * 80)
    print(f"  📊 DAILY MARKET SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    if not results:
        print("  No stocks matched the scanning criteria today.")
        print("=" * 80)
        return

    # Table header
    print(
        f"  {'#':<3} {'Symbol':<8} {'Score':<7} {'Price':>10} "
        f"{'RSI':>6} {'MACD':<9} {'Volume':<8} {'Reason'}"
    )
    print("-" * 80)

    # Table rows
    for i, r in enumerate(results, 1):
        price_str = f"${r['current_price']:.2f}" if r["current_price"] else "N/A"
        rsi_str = f"{r['rsi_value']:.1f}" if r["rsi_value"] else "N/A"
        print(
            f"  {i:<3} {r['symbol']:<8} {r['score']:<7.1f} {price_str:>10} "
            f"{rsi_str:>6} {r['macd_signal']:<9} {r['volume_signal']:<8} "
            f"{r['reason']}"
        )

    print("=" * 80)
    print(f"  Scanned at {datetime.now().strftime('%H:%M:%S')} | "
          f"Top {len(results)} of watchlist shown")
    print("=" * 80 + "\n")


# =============================================================================
# CLI Entry Point — Run the scanner directly from the command line
# =============================================================================
if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("🔍 Starting Market Scanner...")
    top_picks = run_full_scan()
    print_scan_report(top_picks)
