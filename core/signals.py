# =============================================================================
# core/signals.py — Trade Signal Generator
# =============================================================================
#
# PURPOSE:
#   Takes the top-ranked stocks from the scanner (Module 1) and generates
#   complete trade setups for each one. A "trade setup" includes everything
#   a trader needs to execute a trade: entry price, stop loss, profit targets,
#   risk:reward ratio, and signal strength classification.
#
#   This module bridges the gap between "this stock looks good" (scanner) and
#   "here is exactly how to trade it" (execution). It uses the ATR (Average
#   True Range) indicator to dynamically calculate stop-loss distances and
#   profit targets, ensuring each setup respects the market's current
#   volatility for that stock.
#
# TRADE SETUP FORMULA:
#   Entry Price  = current closing price (or last close)
#   Stop Loss    = entry - (ATR × ATR_STOP_MULTIPLIER)   [default: 2× ATR]
#   Risk (R)     = entry - stop_loss
#   Take Profit 1 = entry + (2 × R)    → close 50% of position
#   Take Profit 2 = entry + (3 × R)    → close remaining 50%
#   Risk:Reward   = (TP1_distance / R)  → must be >= MIN_RR_RATIO (1.5)
#
# KEY FUNCTIONS:
#   - generate_trade_setup(scan_result)
#       Converts a single scanner result dict into a full trade setup.
#
#   - generate_all_signals(scan_results)
#       Processes a list of scanner results, filters by R:R, returns signals.
#
#   - classify_signal_strength(score, rr_ratio)
#       Labels signal as STRONG / MEDIUM / WEAK based on score and R:R.
#
#   - save_signals(signals, output_dir)
#       Saves generated signals to data/signals.csv.
#
#   - print_signals_report(signals)
#       Prints a formatted console table of all trade setups.
#
# USAGE:
#   from core.signals import generate_all_signals, print_signals_report
#   from core.scanner import run_full_scan
#
#   scan_results = run_full_scan()
#   signals = generate_all_signals(scan_results)
#   print_signals_report(signals)
#
# =============================================================================

import os
import logging
from datetime import datetime

import pandas as pd

from config.settings import (
    ATR_STOP_MULTIPLIER,
    MIN_RR_RATIO,
    DATA_DIR,
)

logger = logging.getLogger(__name__)


def generate_trade_setup(scan_result: dict) -> dict | None:
    """
    Convert a single scanner result into a complete trade setup.

    Uses the ATR value from the scanner's indicator output to calculate
    dynamic stop-loss and take-profit levels. This ensures that stops and
    targets adapt to each stock's volatility — a volatile stock gets wider
    stops, a calm stock gets tighter stops.

    Formula:
        risk_per_share = ATR × ATR_STOP_MULTIPLIER (default 2.0)
        stop_loss      = entry - risk_per_share
        take_profit_1  = entry + (2 × risk_per_share)  → 2:1 R:R
        take_profit_2  = entry + (3 × risk_per_share)  → 3:1 R:R

    Args:
        scan_result: A dictionary from scanner.scan_stock() containing at
                     minimum: symbol, score, current_price, atr_value,
                     indicators, and reason.

    Returns:
        A trade setup dictionary with all entry/exit levels, or None if the
        setup is invalid (missing ATR, zero price, etc.).
    """
    symbol = scan_result.get("symbol")
    entry_price = scan_result.get("current_price")
    atr_value = scan_result.get("atr_value")
    score = scan_result.get("score", 0.0)
    reason = scan_result.get("reason", "")

    # Validate required fields — cannot generate a setup without price and ATR
    if entry_price is None or entry_price <= 0:
        logger.warning("Cannot generate setup for '%s': invalid price.", symbol)
        return None

    if atr_value is None or atr_value <= 0:
        logger.warning("Cannot generate setup for '%s': invalid ATR.", symbol)
        return None

    # Calculate risk per share using ATR (the "R" value)
    risk_per_share = round(atr_value * ATR_STOP_MULTIPLIER, 4)

    # Prevent risk from being larger than the entry price itself
    if risk_per_share >= entry_price:
        logger.warning(
            "Risk per share ($%.2f) >= entry price ($%.2f) for '%s'. Skipping.",
            risk_per_share, entry_price, symbol,
        )
        return None

    # Calculate stop loss and take profit levels
    stop_loss = round(entry_price - risk_per_share, 2)
    take_profit_1 = round(entry_price + (2 * risk_per_share), 2)
    take_profit_2 = round(entry_price + (3 * risk_per_share), 2)

    # Calculate Risk:Reward ratio (using TP1 as the primary target)
    rr_ratio = round((take_profit_1 - entry_price) / risk_per_share, 2)

    # Classify signal strength based on scanner score and R:R
    strength = classify_signal_strength(score, rr_ratio)

    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_per_share": round(risk_per_share, 2),
        "rr_ratio": rr_ratio,
        "signal_strength": strength,
        "scanner_score": score,
        "reason": reason,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def classify_signal_strength(score: float, rr_ratio: float) -> str:
    """
    Classify a trade signal as STRONG, MEDIUM, or WEAK.

    Classification criteria:
        STRONG: Scanner score >= 7.0 AND R:R >= 2.0
                (Multiple bullish indicators aligning with good R:R)
        MEDIUM: Scanner score >= 5.0 AND R:R >= 1.5
                (Decent setup with acceptable R:R)
        WEAK:   Everything else
                (Few signals or poor R:R — trade with caution)

    Args:
        score:    The composite scanner score (0–10).
        rr_ratio: The risk:reward ratio for the trade setup.

    Returns:
        One of "STRONG", "MEDIUM", or "WEAK".
    """
    if score >= 7.0 and rr_ratio >= 2.0:
        return "STRONG"
    elif score >= 5.0 and rr_ratio >= 1.5:
        return "MEDIUM"
    else:
        return "WEAK"


def generate_all_signals(
    scan_results: list[dict],
    min_rr: float = MIN_RR_RATIO,
) -> list[dict]:
    """
    Process all scanner results and generate filtered trade signals.

    Iterates through each scanner result, generates a trade setup, and
    filters out any setup with a Risk:Reward ratio below the minimum
    threshold (default 1.5). This ensures we only output actionable signals
    that have acceptable risk characteristics.

    Args:
        scan_results: List of dictionaries from scanner.run_full_scan().
        min_rr:       Minimum acceptable R:R ratio. Setups below this are
                      excluded. Default from settings.MIN_RR_RATIO.

    Returns:
        List of trade setup dictionaries, filtered and sorted by signal
        strength (STRONG first, then MEDIUM, then WEAK).
    """
    signals = []

    for result in scan_results:
        setup = generate_trade_setup(result)

        if setup is None:
            continue

        # Filter: only include signals with R:R above the minimum threshold
        if setup["rr_ratio"] < min_rr:
            logger.info(
                "Excluding '%s': R:R ratio %.2f below minimum %.2f.",
                setup["symbol"], setup["rr_ratio"], min_rr,
            )
            continue

        signals.append(setup)

    # Sort by strength priority: STRONG > MEDIUM > WEAK
    strength_order = {"STRONG": 0, "MEDIUM": 1, "WEAK": 2}
    signals.sort(key=lambda s: (strength_order.get(s["signal_strength"], 3), -s["scanner_score"]))

    logger.info(
        "Generated %d actionable signals from %d scanner results.",
        len(signals), len(scan_results),
    )

    return signals


def save_signals(signals: list[dict], output_dir: str = DATA_DIR) -> str:
    """
    Save generated trade signals to a dated CSV file.

    Creates data/signals_YYYY-MM-DD.csv and overwrites data/signals.csv
    as the "latest" reference for downstream modules (execution engine).

    Args:
        signals:    List of trade setup dictionaries from generate_all_signals().
        output_dir: Directory to write CSV files to.

    Returns:
        Path to the saved dated CSV file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Prepare rows excluding complex nested data
    rows = []
    for s in signals:
        rows.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "symbol": s["symbol"],
            "entry_price": s["entry_price"],
            "stop_loss": s["stop_loss"],
            "take_profit_1": s["take_profit_1"],
            "take_profit_2": s["take_profit_2"],
            "risk_per_share": s["risk_per_share"],
            "rr_ratio": s["rr_ratio"],
            "signal_strength": s["signal_strength"],
            "scanner_score": s["scanner_score"],
            "reason": s["reason"],
        })

    df = pd.DataFrame(rows)

    # Save dated file for history
    date_str = datetime.now().strftime("%Y-%m-%d")
    dated_path = os.path.join(output_dir, f"signals_{date_str}.csv")
    df.to_csv(dated_path, index=False)

    # Save as "latest" for other modules
    latest_path = os.path.join(output_dir, "signals.csv")
    df.to_csv(latest_path, index=False)

    logger.info("Signals saved to '%s'.", dated_path)
    return dated_path


def print_signals_report(signals: list[dict]) -> None:
    """
    Print a formatted console report of generated trade signals.

    Displays a table showing each signal's entry, stop loss, targets,
    risk:reward ratio, and signal strength. This gives the trader a
    complete at-a-glance view of all actionable trade setups.

    Args:
        signals: List of trade setup dicts from generate_all_signals().
    """
    print("\n" + "=" * 90)
    print(f"  📈 TRADE SIGNALS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 90)

    if not signals:
        print("  No actionable signals generated today.")
        print("=" * 90)
        return

    # Table header
    print(
        f"  {'Symbol':<8} {'Strength':<9} {'Entry':>9} {'Stop':>9} "
        f"{'TP1':>9} {'TP2':>9} {'R:R':>5} {'Score':>6} {'Reason'}"
    )
    print("-" * 90)

    # Table rows
    for s in signals:
        print(
            f"  {s['symbol']:<8} {s['signal_strength']:<9} "
            f"${s['entry_price']:>7.2f} ${s['stop_loss']:>7.2f} "
            f"${s['take_profit_1']:>7.2f} ${s['take_profit_2']:>7.2f} "
            f"{s['rr_ratio']:>5.2f} {s['scanner_score']:>5.1f}  "
            f"{s['reason']}"
        )

    print("=" * 90)
    strong_count = sum(1 for s in signals if s["signal_strength"] == "STRONG")
    medium_count = sum(1 for s in signals if s["signal_strength"] == "MEDIUM")
    weak_count = sum(1 for s in signals if s["signal_strength"] == "WEAK")
    print(
        f"  Total: {len(signals)} signals | "
        f"STRONG: {strong_count} | MEDIUM: {medium_count} | WEAK: {weak_count}"
    )
    print("=" * 90 + "\n")


# =============================================================================
# CLI Entry Point — Generate signals from the latest scan
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from core.scanner import run_full_scan

    print("🔍 Running market scan...")
    scan_results = run_full_scan()

    print("📈 Generating trade signals...")
    signals = generate_all_signals(scan_results)
    save_signals(signals)
    print_signals_report(signals)
