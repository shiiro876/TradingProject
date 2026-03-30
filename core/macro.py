# =============================================================================
# core/macro.py — Sector Rotation & Macro Analysis Engine
# =============================================================================
#
# PURPOSE:
#   Tracks the performance of major sector ETFs to identify which sectors
#   are leading (hot) and which are lagging (cold).  Detects "sector
#   rotation" — the phenomenon where institutional money flows from one
#   sector into another — so the scanner can prioritise stocks from
#   sectors with momentum.
#
#   Example:  If Energy was ranked #5 last week but surged to #1 this week
#   while Tech dropped from #1 to #4, the module flags:
#       "SECTOR ROTATION DETECTED: Money moving from Technology → Energy"
#
# HOW IT WORKS:
#   1. Download recent OHLCV data for each sector ETF (XLE, XLK, etc.)
#      using the same yfinance pipeline that Module 1 uses.
#   2. Calculate percentage returns over two windows:
#        - 1-week  (5 trading days)
#        - 1-month (21 trading days)
#   3. Rank all sectors by 1-week return (primary sort).
#   4. Classify each sector as STRONG, NEUTRAL, or WEAK using configurable
#      thresholds (+2% / -2% by default).
#   5. Compare current rankings to a previous snapshot to detect rotation.
#   6. Return a structured result that downstream modules can merge with
#      scanner output to boost scores for stocks in strong sectors.
#
# KEY FUNCTIONS:
#   - calculate_sector_return(df, period_days)
#       Computes the percentage return over the last N trading days.
#
#   - rank_sectors(sector_data)
#       Downloads ETF data, calculates returns, ranks, and classifies.
#
#   - detect_sector_rotation(current_rankings, previous_rankings)
#       Compares two ranking snapshots and flags significant moves.
#
#   - get_sector_for_symbol(symbol, watchlist_path)
#       Looks up the sector for a stock from the watchlist CSV.
#
#   - run_macro_analysis(previous_rankings)
#       Full pipeline: fetch → rank → detect rotation → report.
#
#   - save_sector_results(results, output_dir)
#       Persists sector data to a dated CSV.
#
#   - print_sector_report(results)
#       Formatted console output of sector rankings.
#
# USAGE:
#   from core.macro import run_macro_analysis, print_sector_report
#
#   results = run_macro_analysis()
#   print_sector_report(results)
#
# =============================================================================

import os
import logging
from datetime import datetime

import pandas as pd

from config.settings import (
    SECTOR_ETFS,
    SECTOR_PERFORMANCE_PERIODS,
    SECTOR_STRONG_THRESHOLD,
    SECTOR_WEAK_THRESHOLD,
    SECTOR_ROTATION_MIN_CHANGE,
    DATA_DIR,
    WATCHLIST_PATH,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Return Calculation
# =============================================================================


def calculate_sector_return(df: pd.DataFrame, period_days: int) -> float | None:
    """
    Calculate the percentage return over the last *period_days* trading days.

    Uses the closing price from *period_days* ago vs. the latest close:
        return_pct = ((close_now - close_then) / close_then) × 100

    Args:
        df:          OHLCV DataFrame with a "Close" column and DatetimeIndex.
        period_days: Number of trading days to look back.

    Returns:
        Percentage return as a float (e.g., 3.45 for +3.45%), or None if
        there isn't enough data.
    """
    if df is None or df.empty or len(df) < period_days + 1:
        return None

    close_now = df["Close"].iloc[-1]
    close_then = df["Close"].iloc[-(period_days + 1)]

    if close_then == 0:
        return None

    return round(((close_now - close_then) / close_then) * 100, 2)


def classify_sector(return_pct: float | None) -> str:
    """
    Classify a sector as STRONG, WEAK, or NEUTRAL based on its return.

    Args:
        return_pct: The sector's percentage return over the analysis period.

    Returns:
        "STRONG" if return >= threshold, "WEAK" if <= negative threshold,
        otherwise "NEUTRAL".
    """
    if return_pct is None:
        return "NEUTRAL"

    if return_pct >= SECTOR_STRONG_THRESHOLD:
        return "STRONG"
    elif return_pct <= SECTOR_WEAK_THRESHOLD:
        return "WEAK"
    else:
        return "NEUTRAL"


# =============================================================================
# Sector Ranking
# =============================================================================


def rank_sectors(
    sector_data: dict[str, pd.DataFrame] | None = None,
) -> list[dict]:
    """
    Rank all sectors by their recent performance.

    For each sector ETF:
      1. Calculates 1-week and 1-month percentage returns.
      2. Classifies the sector as STRONG / NEUTRAL / WEAK.
      3. Ranks all sectors by 1-week return (descending).

    Args:
        sector_data: Optional pre-fetched dict mapping sector names to OHLCV
                     DataFrames.  If None, data is fetched live via yfinance.

    Returns:
        List of sector result dicts, sorted by 1-week return (best first).
        Each dict contains: sector, etf_symbol, return_1w, return_1m,
        classification, rank.
    """
    # If no data provided, fetch it live
    if sector_data is None:
        sector_data = _fetch_sector_data()

    results = []

    for sector_name, df in sector_data.items():
        etf_symbol = SECTOR_ETFS.get(sector_name, "?")

        return_1w = calculate_sector_return(
            df, SECTOR_PERFORMANCE_PERIODS["1_week"]
        )
        return_1m = calculate_sector_return(
            df, SECTOR_PERFORMANCE_PERIODS["1_month"]
        )

        classification = classify_sector(return_1w)

        results.append({
            "sector": sector_name,
            "etf_symbol": etf_symbol,
            "return_1w": return_1w,
            "return_1m": return_1m,
            "classification": classification,
        })

    # Sort by 1-week return descending; treat None as -infinity
    results.sort(key=lambda x: x["return_1w"] if x["return_1w"] is not None else -999, reverse=True)

    # Assign ranks (1 = best performing)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return results


def _fetch_sector_data() -> dict[str, pd.DataFrame]:
    """
    Download OHLCV data for all sector ETFs using the same yfinance pipeline.

    Returns:
        Dict mapping sector names to their OHLCV DataFrames.
    """
    from core.utils import get_stock_data

    sector_data: dict[str, pd.DataFrame] = {}

    for sector_name, etf_symbol in SECTOR_ETFS.items():
        df = get_stock_data(etf_symbol, period="3mo", interval="1d")
        if not df.empty:
            sector_data[sector_name] = df
        else:
            logger.warning("No data for sector ETF '%s' (%s).", sector_name, etf_symbol)

    logger.info(
        "Fetched sector data for %d / %d ETFs.",
        len(sector_data), len(SECTOR_ETFS),
    )
    return sector_data


# =============================================================================
# Sector Rotation Detection
# =============================================================================


def detect_sector_rotation(
    current_rankings: list[dict],
    previous_rankings: list[dict] | None = None,
) -> list[dict]:
    """
    Compare current sector rankings to previous rankings and flag rotation.

    Sector rotation is detected when a sector's rank changes by at least
    SECTOR_ROTATION_MIN_CHANGE positions between snapshots.

    Example output:
        "SECTOR ROTATION: Energy moved from rank #5 → #1 (+4 positions)"

    Args:
        current_rankings:   Latest ranking list from rank_sectors().
        previous_rankings:  Previous ranking list (e.g., from last week).
                            If None, no rotation detection is possible.

    Returns:
        List of rotation event dicts.  Each contains:
            sector     (str): Sector name.
            direction  (str): "UP" or "DOWN".
            old_rank   (int): Previous rank.
            new_rank   (int): Current rank.
            rank_change (int): Positions moved (positive = improved).
            message    (str): Human-readable description.
    """
    if previous_rankings is None or not previous_rankings:
        return []

    # Build lookup: sector → rank for previous snapshot
    prev_lookup = {r["sector"]: r["rank"] for r in previous_rankings}
    rotations = []

    for current in current_rankings:
        sector = current["sector"]
        new_rank = current["rank"]
        old_rank = prev_lookup.get(sector)

        if old_rank is None:
            continue  # Sector wasn't in previous snapshot

        rank_change = old_rank - new_rank  # Positive = moved up (improved)

        if abs(rank_change) >= SECTOR_ROTATION_MIN_CHANGE:
            direction = "UP" if rank_change > 0 else "DOWN"
            rotations.append({
                "sector": sector,
                "direction": direction,
                "old_rank": old_rank,
                "new_rank": new_rank,
                "rank_change": rank_change,
                "message": (
                    f"SECTOR ROTATION: {sector} moved from rank #{old_rank} → "
                    f"#{new_rank} ({'+' if rank_change > 0 else ''}{rank_change} positions)"
                ),
            })

    return rotations


# =============================================================================
# Sector Lookup for Individual Stocks
# =============================================================================


def get_sector_for_symbol(
    symbol: str,
    watchlist_path: str = WATCHLIST_PATH,
) -> str | None:
    """
    Look up the sector for a stock symbol from the watchlist CSV.

    The watchlist CSV should have columns: Symbol, Name, Sector.

    Args:
        symbol:         Stock ticker to look up.
        watchlist_path: Path to the watchlist CSV file.

    Returns:
        The sector name (e.g., "Energy") or None if not found.
    """
    try:
        df = pd.read_csv(watchlist_path)
        match = df.loc[df["Symbol"].str.upper() == symbol.upper(), "Sector"]
        if not match.empty:
            return match.iloc[0]
    except Exception as exc:
        logger.error("Error reading watchlist for sector lookup: %s", exc)

    return None


def get_sector_adjustment(
    symbol: str,
    sector_rankings: list[dict],
    watchlist_path: str = WATCHLIST_PATH,
) -> float:
    """
    Calculate a score adjustment for a stock based on its sector's strength.

    Stocks in STRONG sectors get a positive boost; stocks in WEAK sectors
    get penalised.  This allows the scanner to prioritise stocks from
    sectors with institutional momentum.

    Adjustments:
        STRONG sector → +1.0 points
        NEUTRAL sector → 0.0 points
        WEAK sector → -1.0 points

    Args:
        symbol:           Stock ticker.
        sector_rankings:  Current sector ranking list from rank_sectors().
        watchlist_path:   Path to the watchlist CSV.

    Returns:
        Float adjustment value to add to the scanner score.
    """
    sector = get_sector_for_symbol(symbol, watchlist_path)
    if sector is None:
        return 0.0

    for ranking in sector_rankings:
        if ranking["sector"] == sector:
            if ranking["classification"] == "STRONG":
                return 1.0
            elif ranking["classification"] == "WEAK":
                return -1.0
            return 0.0

    return 0.0


# =============================================================================
# Full Pipeline
# =============================================================================


def run_macro_analysis(
    previous_rankings: list[dict] | None = None,
    sector_data: dict[str, pd.DataFrame] | None = None,
) -> dict:
    """
    Execute the full macro/sector analysis pipeline.

    Steps:
      1. Rank all sectors by 1-week and 1-month performance.
      2. Detect sector rotation if previous rankings are provided.
      3. Identify strong and weak sectors.

    Args:
        previous_rankings: Optional previous ranking snapshot for rotation
                           detection (e.g., from last week's analysis).
        sector_data:       Optional pre-fetched sector ETF data (for testing).

    Returns:
        Dictionary containing:
            rankings     (list): Sorted sector rankings.
            strong       (list): Sector names classified as STRONG.
            weak         (list): Sector names classified as WEAK.
            rotations    (list): Detected rotation events.
            analysed_at  (str):  Timestamp of analysis.
    """
    rankings = rank_sectors(sector_data=sector_data)

    strong_sectors = [r["sector"] for r in rankings if r["classification"] == "STRONG"]
    weak_sectors = [r["sector"] for r in rankings if r["classification"] == "WEAK"]

    rotations = detect_sector_rotation(rankings, previous_rankings)

    logger.info(
        "Macro analysis complete. STRONG sectors: %s, WEAK sectors: %s, Rotations: %d.",
        strong_sectors or "none",
        weak_sectors or "none",
        len(rotations),
    )

    return {
        "rankings": rankings,
        "strong": strong_sectors,
        "weak": weak_sectors,
        "rotations": rotations,
        "analysed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# =============================================================================
# Persistence & Reporting
# =============================================================================


def save_sector_results(results: dict, output_dir: str = DATA_DIR) -> str:
    """
    Save sector ranking results to a dated CSV file.

    Creates data/sector_YYYY-MM-DD.csv and overwrites data/sector.csv
    as the "latest" reference.

    Args:
        results:    Full macro analysis result dict from run_macro_analysis().
        output_dir: Directory to write CSV files to.

    Returns:
        Path to the saved dated CSV file.
    """
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for r in results["rankings"]:
        rows.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "rank": r["rank"],
            "sector": r["sector"],
            "etf_symbol": r["etf_symbol"],
            "return_1w": r["return_1w"],
            "return_1m": r["return_1m"],
            "classification": r["classification"],
        })

    df = pd.DataFrame(rows)

    date_str = datetime.now().strftime("%Y-%m-%d")
    dated_path = os.path.join(output_dir, f"sector_{date_str}.csv")
    df.to_csv(dated_path, index=False)

    latest_path = os.path.join(output_dir, "sector.csv")
    df.to_csv(latest_path, index=False)

    logger.info("Sector results saved to '%s'.", dated_path)
    return dated_path


def print_sector_report(results: dict) -> None:
    """
    Print a formatted console report of sector rankings and rotation events.

    Args:
        results: Full macro analysis result dict from run_macro_analysis().
    """
    print("\n" + "=" * 80)
    print(f"  🌐 SECTOR ANALYSIS — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    rankings = results.get("rankings", [])
    if not rankings:
        print("  No sector data available.")
        print("=" * 80)
        return

    # Table header
    print(
        f"  {'Rank':<6} {'Sector':<25} {'ETF':<6} "
        f"{'1-Week':>8} {'1-Month':>9} {'Status':<10}"
    )
    print("-" * 80)

    for r in rankings:
        ret_1w = f"{r['return_1w']:+.2f}%" if r["return_1w"] is not None else "N/A"
        ret_1m = f"{r['return_1m']:+.2f}%" if r["return_1m"] is not None else "N/A"

        # Add emoji for visual classification
        status_icon = {"STRONG": "🟢", "WEAK": "🔴", "NEUTRAL": "⚪"}.get(
            r["classification"], "⚪"
        )

        print(
            f"  #{r['rank']:<5} {r['sector']:<25} {r['etf_symbol']:<6} "
            f"{ret_1w:>8} {ret_1m:>9} {status_icon} {r['classification']:<10}"
        )

    # Strong / weak summary
    strong = results.get("strong", [])
    weak = results.get("weak", [])
    if strong:
        print(f"\n  🟢 STRONG SECTORS: {', '.join(strong)}")
    if weak:
        print(f"  🔴 WEAK SECTORS:   {', '.join(weak)}")

    # Rotation events
    rotations = results.get("rotations", [])
    if rotations:
        print("\n  ⚠️  ROTATION EVENTS:")
        for rot in rotations:
            print(f"     {rot['message']}")

    print("=" * 80 + "\n")


# =============================================================================
# CLI Entry Point — Run macro analysis from the command line
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("🌐 Running Sector / Macro Analysis...")
    results = run_macro_analysis()
    save_sector_results(results)
    print_sector_report(results)
