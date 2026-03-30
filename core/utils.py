# =============================================================================
# core/utils.py — Market Data Fetching Pipeline
# =============================================================================
#
# PURPOSE:
#   Provides a clean interface for downloading stock market data from Yahoo
#   Finance using the yfinance library. All other modules that need price data
#   import from this file — it is the single data-access layer.
#
# KEY FUNCTIONS:
#   - get_stock_data(symbol, period, interval)
#       Downloads OHLCV data for a single stock symbol.
#
#   - get_multiple_stocks(symbols, period, interval)
#       Downloads OHLCV data for a list of symbols. Returns a dict of
#       {symbol: DataFrame} pairs. Handles errors gracefully per-symbol.
#
#   - load_watchlist(csv_path)
#       Reads a CSV file of stock symbols to build the scanning universe.
#
# DATA FORMAT:
#   All DataFrames returned contain these columns:
#       Open, High, Low, Close, Volume
#   Indexed by datetime (DatetimeIndex).
#
# USAGE:
#   from core.utils import get_stock_data, get_multiple_stocks, load_watchlist
#
#   df = get_stock_data("AAPL", period="3mo")
#   all_data = get_multiple_stocks(["AAPL", "MSFT", "GOOG"])
#   symbols = load_watchlist("data/watchlist.csv")
#
# =============================================================================

import os
import logging

import pandas as pd
import yfinance as yf

from config.settings import SCANNER_DATA_PERIOD, SCANNER_DATA_INTERVAL, WATCHLIST_PATH

# Configure module-level logger for data operations
logger = logging.getLogger(__name__)


def get_stock_data(
    symbol: str,
    period: str = SCANNER_DATA_PERIOD,
    interval: str = SCANNER_DATA_INTERVAL,
) -> pd.DataFrame:
    """
    Download OHLCV (Open, High, Low, Close, Volume) data for a single stock.

    Uses yfinance to fetch historical price data from Yahoo Finance.
    Returns an empty DataFrame if the symbol is invalid or data is unavailable.

    Args:
        symbol:   Stock ticker symbol (e.g., "AAPL", "XOM").
        period:   How far back to fetch data. Default from settings.
                  Valid values: "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"
        interval: Candle interval. Default from settings.
                  Valid values: "1d", "1h", "5m", "15m", "30m", "1wk"

    Returns:
        pd.DataFrame with columns [Open, High, Low, Close, Volume] and a
        DatetimeIndex. Returns empty DataFrame on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        # Validate that we received meaningful data
        if df.empty:
            logger.warning("No data returned for symbol '%s'.", symbol)
            return pd.DataFrame()

        # Keep only the essential OHLCV columns to ensure consistent schema
        required_columns = ["Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            logger.warning(
                "Symbol '%s' is missing columns: %s", symbol, missing
            )
            return pd.DataFrame()

        df = df[required_columns]

        logger.info(
            "Fetched %d rows of %s data for '%s'.", len(df), interval, symbol
        )
        return df

    except Exception as exc:
        # Catch broad exceptions from network errors, invalid tickers, etc.
        logger.error("Failed to fetch data for '%s': %s", symbol, exc)
        return pd.DataFrame()


def get_multiple_stocks(
    symbols: list[str],
    period: str = SCANNER_DATA_PERIOD,
    interval: str = SCANNER_DATA_INTERVAL,
) -> dict[str, pd.DataFrame]:
    """
    Download OHLCV data for a list of stock symbols.

    Iterates through each symbol and calls get_stock_data(). Symbols that
    fail to download are silently skipped (logged as warnings).

    Args:
        symbols:  List of ticker strings (e.g., ["AAPL", "MSFT", "XOM"]).
        period:   How far back to fetch data. Passed to get_stock_data().
        interval: Candle interval. Passed to get_stock_data().

    Returns:
        Dictionary mapping symbol strings to their OHLCV DataFrames.
        Only symbols with valid (non-empty) data are included.
    """
    stock_data: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        df = get_stock_data(symbol, period=period, interval=interval)
        if not df.empty:
            stock_data[symbol] = df
        else:
            logger.warning("Skipping '%s' — no valid data returned.", symbol)

    logger.info(
        "Successfully loaded data for %d / %d symbols.",
        len(stock_data),
        len(symbols),
    )
    return stock_data


def load_watchlist(csv_path: str = WATCHLIST_PATH) -> list[str]:
    """
    Load the stock universe from a CSV file.

    The CSV file should have a column named 'Symbol' containing ticker strings.
    Lines starting with '#' in the file are treated as comments (skipped).

    Args:
        csv_path: Absolute or relative path to the watchlist CSV file.

    Returns:
        List of uppercase ticker symbol strings (e.g., ["AAPL", "MSFT"]).

    Raises:
        FileNotFoundError: If the CSV file does not exist at the given path.
        KeyError: If the CSV file does not contain a 'Symbol' column.
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(
            f"Watchlist file not found: {csv_path}. "
            "Please create it with a 'Symbol' column."
        )

    df = pd.read_csv(csv_path, comment="#")

    if "Symbol" not in df.columns:
        raise KeyError(
            "Watchlist CSV must have a 'Symbol' column. "
            f"Found columns: {list(df.columns)}"
        )

    # Clean up: strip whitespace, convert to uppercase, drop blanks
    symbols = (
        df["Symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
        .loc[lambda s: s != ""]
        .tolist()
    )

    logger.info("Loaded %d symbols from watchlist '%s'.", len(symbols), csv_path)
    return symbols
