# 📦 Module 1 — Market Scanner (Phase 1)

**Status:** ✅ Complete  
**Phase:** 1 of 7  
**Files:** `core/utils.py`, `core/indicators.py`, `core/scanner.py`  
**Tests:** `tests/test_module1.py` (24 tests)

---

## Overview

Module 1 is the Market Scanner — it scans 50+ stocks every day, runs technical analysis on each one, scores them based on bullish signals, and returns the top 5 stocks to watch with plain-English reasoning.

This module replaces the manual process of checking charts one by one. It automates what a trader does each morning: evaluate price action, volume, momentum indicators, and trend direction to find the best trade candidates.

---

## Components

### `core/utils.py` — Market Data Pipeline

The data access layer that interfaces with Yahoo Finance via the `yfinance` library.

| Function | Description |
|----------|-------------|
| `get_stock_data(symbol, period, interval)` | Downloads OHLCV data for a single stock |
| `get_multiple_stocks(symbols, period, interval)` | Batch downloads for a list of symbols |
| `load_watchlist(csv_path)` | Reads stock symbols from a CSV file |

**Data Format:** All DataFrames contain columns `[Open, High, Low, Close, Volume]` indexed by `DatetimeIndex`.

### `core/indicators.py` — Technical Analysis Engine

Calculates 6 technical indicators on each stock's OHLCV data using the `pandas-ta` library:

| Indicator | Function | What It Detects | Bullish Signal |
|-----------|----------|-----------------|----------------|
| **RSI (14)** | `calculate_rsi(df)` | Overbought/oversold | RSI ≤ 30 |
| **MACD (12/26/9)** | `calculate_macd(df)` | Momentum crossovers | MACD > signal line |
| **50 & 200 SMA** | `calculate_moving_averages(df)` | Trend direction | Price above both MAs |
| **Bollinger Bands** | `calculate_bollinger_bands(df)` | Volatility breakouts | Price > upper band |
| **Volume Analysis** | `calculate_volume_signal(df)` | Unusual activity | Volume ≥ 2× average |
| **ATR (14)** | `calculate_atr(df)` | Volatility for stops | ATR% in 1–5% range |

The entry point is `calculate_all_indicators(df)` which runs all six and returns a flat dictionary.

### `core/scanner.py` — Scanning & Scoring Engine

Orchestrates the full scanning pipeline:

1. **Load** stock universe from `data/watchlist.csv`
2. **Fetch** 3 months of daily OHLCV data for all 50 stocks
3. **Analyze** each stock with all 6 technical indicators
4. **Score** each stock 0–10 based on weighted bullish signals
5. **Rank** and return the top 5 stocks with reasoning
6. **Save** results to `data/daily_scan_YYYY-MM-DD.csv`

| Function | Description |
|----------|-------------|
| `score_stock(indicators)` | Converts signals to 0–10 score |
| `generate_reason(indicators, score)` | Builds plain-English explanation |
| `scan_stock(symbol, df)` | Full per-stock analysis |
| `run_full_scan(symbols, period, interval, top_n)` | End-to-end scan pipeline |
| `save_scan_results(results, output_dir)` | Saves to dated CSV |
| `print_scan_report(results)` | Formatted console output |

**Scoring Weights:**

| Signal | Weight |
|--------|--------|
| RSI oversold | +2.0 |
| MACD crossover | +2.0 |
| Price above MAs | +1.5 |
| Bollinger breakout | +1.5 |
| Volume surge | +2.0 |
| Favorable ATR | +1.0 |
| **Total** | **10.0** |

### `data/watchlist.csv` — Stock Universe

50 diversified S&P 500 stocks across 8 sectors:

- **Technology (10):** AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, AMD, INTC
- **Energy (7):** XOM, CVX, HAL, SLB, COP, OXY, MRO
- **Healthcare (7):** JNJ, UNH, PFE, ABBV, MRK, LLY, TMO
- **Financials (6):** JPM, V, MA, BAC, GS, WFC
- **Industrials (7):** CAT, DE, BA, HON, UNP, CMC, GE, LMT
- **Consumer Staples (5):** PG, KO, PEP, WMT, COST
- **Utilities (4):** NEE, DUK, SO, AEP
- **Communication Services (4):** T, VZ, DIS, NFLX

---

## Usage

```bash
# Run the scanner from the project root
python -m core.scanner
```

**Example Output:**
```
📊 DAILY MARKET SCAN — 2026-03-30 10:00
================================================================================
  #   Symbol   Score   Price       RSI   MACD      Volume   Reason
--------------------------------------------------------------------------------
  1   XOM      8.0     $112.50    28.5   Bullish   Surge    Strong buy: RSI oversold + MACD crossover + Volume surge
  2   HAL      7.5     $38.20     32.1   Bullish   Surge    Strong buy: MACD crossover + Volume surge + Price above 50MA
  3   CVX      6.0     $158.90    45.2   Bullish   Normal   Moderate buy: MACD crossover + Price above 50MA & 200MA
================================================================================
```

---

## Tests

24 unit tests in `tests/test_module1.py`, organized into 4 classes:

| Class | Tests | What It Covers |
|-------|-------|----------------|
| `TestSettings` | 4 | Configuration constants and safety parameters |
| `TestUtils` | 4 | Data loading, watchlist parsing, edge cases |
| `TestIndicators` | 8 | All 6 indicators + combined + insufficient data |
| `TestScanner` | 8 | Scoring, reasoning, pipeline, CSV output, reporting |

```bash
python -m pytest tests/test_module1.py -v
```
