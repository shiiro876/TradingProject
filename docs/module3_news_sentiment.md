# 📦 Module 3 — News & Sentiment Analysis + Macro Sector Rotation (Phase 3)

**Status:** ✅ Complete  
**Phase:** 3 of 7  
**Files:** `core/news.py`, `core/macro.py`  
**Tests:** `tests/test_module3.py` (51 tests)

---

## Overview

Module 3 adds **news intelligence** to the trading system.  It gives the bot the ability to "read the news and understand market impact" — two capabilities that separate amateur from professional systems.

1. **News Sentiment Engine** (`core/news.py`) — Fetches financial news headlines for watchlist stocks, scores them using VADER sentiment analysis, classifies each as POSITIVE / NEGATIVE / NEUTRAL, and detects major events (earnings, analyst upgrades, mergers, geopolitical events).

2. **Macro Sector Detector** (`core/macro.py`) — Tracks sector ETF performance, ranks sectors by 1-week and 1-month returns, classifies them as STRONG / NEUTRAL / WEAK, and detects **sector rotation** — when institutional money flows from one sector to another.

**Week 5 Milestone:** The system reads news, detects major events, and knows which sectors are hot — enabling smarter signal prioritisation.

---

## Components

### `core/news.py` — News & Sentiment Engine

Uses the VADER (Valence Aware Dictionary and sEntiment Reasoner) analyzer to score headlines without the overhead of heavyweight transformer models.

**Pipeline:**
```
1. Fetch headlines via NewsAPI → list of headline strings
2. Score each headline with VADER → compound score (-1.0 to +1.0)
3. Classify → POSITIVE (> +0.20) / NEGATIVE (< -0.20) / NEUTRAL
4. Detect major events → earnings, analyst, merger, sector keywords
5. Aggregate → per-stock sentiment summary
6. Save → data/sentiment_YYYY-MM-DD.csv
```

| Function | Description |
|----------|-------------|
| `score_headline(headline)` | VADER scoring for a single headline → compound + label |
| `detect_major_events(headline)` | Keyword matching for earnings, analyst, merger, sector events |
| `fetch_news_for_symbol(symbol, api_key)` | Calls NewsAPI to get recent headlines (graceful fallback if no key) |
| `analyze_stock_sentiment(symbol, headlines)` | Aggregates all headline scores into a per-stock summary |
| `run_news_analysis(symbols, api_key, headlines_override)` | Full pipeline: fetch → score → aggregate for all symbols |
| `save_sentiment_results(results, output_dir)` | Saves to dated CSV + latest CSV |
| `print_sentiment_report(results)` | Formatted console table with sentiment scores and events |

**Major Event Detection Categories:**

| Category | Example Keywords | Meaning |
|----------|-----------------|---------|
| `earnings` | quarterly results, EPS, revenue beat/miss | Earnings announcements |
| `analyst` | upgrade, downgrade, price target, overweight | Analyst actions |
| `merger` | acquisition, takeover, buyout, joint venture | M&A activity |
| `sector` | oil supply, interest rate, inflation, tariff | Macro/geopolitical |

**Example Output:**
```
📰 NEWS SENTIMENT REPORT — 2026-03-30 10:00
=====================================================================================
  Symbol   Score    Label       +    -    ~   Headlines  Major Events
-------------------------------------------------------------------------------------
  AAPL     +0.5432  POSITIVE    3    0    1          4   earnings
  XOM      -0.3218  NEGATIVE    0    2    1          3  ⚠️ sector
  NVDA     +0.1024  NEUTRAL     1    0    2          3   —
=====================================================================================
```

### `core/macro.py` — Sector Rotation & Macro Analysis

Tracks 10 sector ETFs to identify institutional money flows across sectors.

**Sector ETFs Tracked:**

| Sector | ETF | Description |
|--------|-----|-------------|
| Energy | XLE | Oil, gas, energy services |
| Technology | XLK | Software, hardware, semiconductors |
| Industrials | XLI | Manufacturing, construction, aerospace |
| Consumer Staples | XLP | Food, beverages, household products |
| Healthcare | XLV | Pharma, biotech, medical devices |
| Utilities | XLU | Electric, gas, water utilities |
| Financials | XLF | Banks, insurance, asset management |
| Consumer Discretionary | XLY | Retail, autos, media |
| Communication Services | XLC | Telecom, internet, entertainment |
| Materials | XLB | Mining, chemicals, construction materials |

| Function | Description |
|----------|-------------|
| `calculate_sector_return(df, period_days)` | Percentage return over N trading days |
| `classify_sector(return_pct)` | Labels sector as STRONG (>+2%), WEAK (<-2%), or NEUTRAL |
| `rank_sectors(sector_data)` | Ranks all sectors by 1-week performance |
| `detect_sector_rotation(current, previous)` | Flags sectors that moved ≥3 rank positions |
| `get_sector_for_symbol(symbol)` | Looks up a stock's sector from the watchlist |
| `get_sector_adjustment(symbol, rankings)` | Returns +1.0 (STRONG), 0.0 (NEUTRAL), or -1.0 (WEAK) |
| `run_macro_analysis(previous_rankings, sector_data)` | Full pipeline with rotation detection |
| `save_sector_results(results, output_dir)` | Saves to dated CSV |
| `print_sector_report(results)` | Formatted console table with rankings and rotation events |

**Sector Rotation Detection:**

When a sector changes rank by ≥3 positions between analysis snapshots, the module flags it:

```
⚠️ SECTOR ROTATION: Energy moved from rank #5 → #1 (+4 positions)
```

This is exactly how the system would have caught the March 2026 energy trade automatically.

**Example Output:**
```
🌐 SECTOR ANALYSIS — 2026-03-30 10:00
================================================================================
  Rank   Sector                    ETF    1-Week   1-Month   Status
--------------------------------------------------------------------------------
  #1     Energy                    XLE     +4.20%    +8.50%  🟢 STRONG
  #2     Industrials               XLI     +2.10%    +3.20%  🟢 STRONG
  #3     Healthcare                XLV     +0.80%    +1.50%  ⚪ NEUTRAL
  ...
  #10    Technology                XLK     -3.20%    -5.10%  🔴 WEAK

  🟢 STRONG SECTORS: Energy, Industrials
  🔴 WEAK SECTORS: Technology

  ⚠️ ROTATION EVENTS:
     SECTOR ROTATION: Energy moved from #5 → #1 (+4 positions)
================================================================================
```

---

## Configuration Added (config/settings.py)

### News & Sentiment Settings
```python
SENTIMENT_POSITIVE_THRESHOLD = 0.20    # VADER compound > 0.20 = POSITIVE
SENTIMENT_NEGATIVE_THRESHOLD = -0.20   # VADER compound < -0.20 = NEGATIVE
NEWS_MAX_HEADLINES = 10                # Headlines per stock from NewsAPI

MAJOR_EVENT_KEYWORDS = {
    "earnings": [...],  # quarterly results, EPS, guidance
    "analyst":  [...],  # upgrade, downgrade, price target
    "merger":   [...],  # acquisition, takeover, buyout
    "sector":   [...],  # oil supply, interest rate, tariff
}
```

### Macro / Sector Settings
```python
SECTOR_ETFS = {
    "Energy": "XLE", "Technology": "XLK", "Industrials": "XLI",
    "Consumer Staples": "XLP", "Healthcare": "XLV", "Utilities": "XLU",
    "Financials": "XLF", "Consumer Discretionary": "XLY",
    "Communication Services": "XLC", "Materials": "XLB",
}

SECTOR_PERFORMANCE_PERIODS = {"1_week": 5, "1_month": 21}
SECTOR_STRONG_THRESHOLD = 2.0     # Return > +2% = STRONG
SECTOR_WEAK_THRESHOLD = -2.0      # Return < -2% = WEAK
SECTOR_ROTATION_MIN_CHANGE = 3    # Must move ≥3 ranks to flag
```

---

## Usage

### Run News Sentiment Analysis
```bash
# Requires NEWS_API_KEY in config/.env
python -m core.news
```

### Run Sector/Macro Analysis
```bash
python -m core.macro
```

### Use in Code
```python
from core.news import run_news_analysis, print_sentiment_report
from core.macro import run_macro_analysis, print_sector_report, get_sector_adjustment

# Sentiment analysis
news_results = run_news_analysis(["AAPL", "XOM", "NVDA"])
print_sentiment_report(news_results)

# Sector analysis
macro_results = run_macro_analysis()
print_sector_report(macro_results)

# Boost scanner scores with sector strength
for symbol in ["AAPL", "XOM"]:
    adj = get_sector_adjustment(symbol, macro_results["rankings"])
    print(f"{symbol} sector adjustment: {adj:+.1f}")
```

### Offline Testing (No API Key Required)
```python
# Use headlines_override to test without NewsAPI
results = run_news_analysis(
    symbols=["AAPL"],
    headlines_override={
        "AAPL": ["Apple beats earnings expectations!", "Stock surges on strong demand"],
    },
)
```

---

## Dependencies Added

| Package | Version | Purpose |
|---------|---------|---------|
| `vaderSentiment` | ≥3.3.2 | VADER lexicon-based sentiment analysis |
| `requests` | ≥2.31.0 | HTTP requests for NewsAPI calls |

---

## Tests

51 unit tests in `tests/test_module3.py`, organised into 9 test classes:

| Class | Tests | What It Covers |
|-------|-------|----------------|
| `TestHeadlineScoring` | 5 | VADER scoring, labels, compound range |
| `TestMajorEventDetection` | 7 | All 4 event categories + multi-match + case sensitivity |
| `TestSentimentAggregation` | 5 | Positive/negative/empty/major event aggregation |
| `TestNewsPipeline` | 5 | Full pipeline with overrides, saving, reporting |
| `TestSectorReturns` | 7 | Return calculation, classification thresholds, edge cases |
| `TestSectorRanking` | 3 | Ranking with synthetic data, structure, empty input |
| `TestSectorRotation` | 4 | UP/DOWN rotation, no-change, no-previous |
| `TestSectorLookup` | 6 | Watchlist lookup, sector adjustments (+1/0/-1) |
| `TestMacroPipeline` | 5 | Full pipeline, rotation, saving, reporting |
| `TestModule3Settings` | 4 | Settings validation for all new config values |

```bash
python -m pytest tests/test_module3.py -v
```

---

## How Module 3 Connects to Other Modules

```
Module 1 (Scanner)         Module 3 (News + Macro)
┌──────────────┐          ┌───────────────────────────┐
│  scanner.py  │          │  news.py                   │
│  watchlist   │─symbols─▶│  ├─ fetch headlines        │
│              │          │  ├─ VADER sentiment         │
└──────────────┘          │  ├─ major event detection   │
                          │  └─ per-stock sentiment     │
                          │                             │
Module 2 (Signals)        │  macro.py                   │
┌──────────────┐          │  ├─ sector ETF performance  │
│  signals.py  │◀─boost──▶│  ├─ rank & classify         │
│  score adj   │          │  ├─ sector rotation         │
└──────────────┘          │  └─ sector score adjustment │
                          └───────────────────────────┘
                                       │
                                       ▼
                          Module 5 (Execution) — future
                          Module 7 (Dashboard) — future
```

**Integration points:**
- `news.py` takes symbols from the watchlist (same as scanner)
- `macro.py`'s `get_sector_adjustment()` returns ±1.0 to boost/dampen scanner scores
- `news.py`'s major event flags can enhance signal strength classification
- Both modules save CSV data that the future dashboard (Module 7) can visualise
