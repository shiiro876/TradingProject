# =============================================================================
# core/news.py — News & Sentiment Analysis Engine
# =============================================================================
#
# PURPOSE:
#   Fetches financial news headlines for stocks in the watchlist and scores
#   their sentiment using the VADER (Valence Aware Dictionary and sEntiment
#   Reasoner) analyzer.  VADER is specifically tuned for social media and
#   financial text, making it ideal for quick headline-level scoring without
#   the overhead of a full transformer model.
#
#   The module also detects "major events" — earnings announcements, analyst
#   upgrades/downgrades, mergers, and sector-wide geopolitical news — and
#   flags them for special attention.
#
# HOW IT WORKS:
#   1. Fetch headlines via NewsAPI (or use a provided list for testing).
#   2. Score each headline with VADER → compound score (-1.0 to +1.0).
#   3. Classify: POSITIVE (> +0.20), NEGATIVE (< -0.20), or NEUTRAL.
#   4. Aggregate all headline scores into a per-stock sentiment summary.
#   5. Detect major events by keyword matching against headline text.
#   6. Return enriched results that downstream modules can merge with
#      scanner output to boost or dampen trade signals.
#
# KEY FUNCTIONS:
#   - score_headline(headline)
#       Returns VADER compound score and sentiment label for a single headline.
#
#   - detect_major_events(headline)
#       Scans headline text for major event keywords; returns matched categories.
#
#   - fetch_news_for_symbol(symbol, api_key)
#       Calls NewsAPI to retrieve recent headlines for a given stock ticker.
#
#   - analyze_stock_sentiment(symbol, headlines)
#       Scores all headlines and returns an aggregated sentiment summary.
#
#   - run_news_analysis(symbols, api_key)
#       Full pipeline: fetch + score + aggregate for an entire watchlist.
#
#   - save_sentiment_results(results, output_dir)
#       Persists sentiment data to a dated CSV file.
#
#   - print_sentiment_report(results)
#       Formatted console output of sentiment analysis results.
#
# USAGE:
#   from core.news import run_news_analysis, print_sentiment_report
#
#   results = run_news_analysis(["AAPL", "XOM", "NVDA"])
#   print_sentiment_report(results)
#
# =============================================================================

import os
import logging
from datetime import datetime

import pandas as pd
import requests
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config.settings import (
    NEWS_API_KEY,
    NEWS_MAX_HEADLINES,
    SENTIMENT_POSITIVE_THRESHOLD,
    SENTIMENT_NEGATIVE_THRESHOLD,
    MAJOR_EVENT_KEYWORDS,
    DATA_DIR,
)

logger = logging.getLogger(__name__)

# Initialise the VADER analyzer once at module level (it's stateless)
_vader = SentimentIntensityAnalyzer()


# =============================================================================
# Headline-Level Analysis
# =============================================================================


def score_headline(headline: str) -> dict:
    """
    Score a single news headline using VADER sentiment analysis.

    VADER returns four scores: positive, negative, neutral, and a
    *compound* score that normalises all three into a single value
    between -1.0 (most negative) and +1.0 (most positive).

    Classification:
        compound >=  SENTIMENT_POSITIVE_THRESHOLD  → "POSITIVE"
        compound <= SENTIMENT_NEGATIVE_THRESHOLD    → "NEGATIVE"
        otherwise                                   → "NEUTRAL"

    Args:
        headline: The news headline text to analyse.

    Returns:
        Dictionary containing:
            headline  (str):   The original headline text.
            compound  (float): VADER compound score (-1.0 to +1.0).
            positive  (float): Proportion of positive sentiment (0–1).
            negative  (float): Proportion of negative sentiment (0–1).
            neutral   (float): Proportion of neutral sentiment (0–1).
            label     (str):   "POSITIVE", "NEGATIVE", or "NEUTRAL".
    """
    scores = _vader.polarity_scores(headline)
    compound = scores["compound"]

    if compound >= SENTIMENT_POSITIVE_THRESHOLD:
        label = "POSITIVE"
    elif compound <= SENTIMENT_NEGATIVE_THRESHOLD:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"

    return {
        "headline": headline,
        "compound": round(compound, 4),
        "positive": round(scores["pos"], 4),
        "negative": round(scores["neg"], 4),
        "neutral": round(scores["neu"], 4),
        "label": label,
    }


def detect_major_events(headline: str) -> list[str]:
    """
    Detect major financial events by scanning headline text for keywords.

    Checks the headline against pre-defined keyword lists for four event
    categories:
        - earnings:  Quarterly results, EPS, guidance
        - analyst:   Upgrades, downgrades, price target changes
        - merger:    Mergers, acquisitions, takeovers
        - sector:    Oil supply, interest rates, tariffs, Fed actions

    The search is case-insensitive.

    Args:
        headline: The news headline text to scan.

    Returns:
        List of matched event category strings (e.g., ["earnings", "analyst"]).
        Empty list if no major events detected.
    """
    matched_categories = []
    headline_lower = headline.lower()

    for category, keywords in MAJOR_EVENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in headline_lower:
                matched_categories.append(category)
                break  # One match per category is sufficient

    return matched_categories


# =============================================================================
# News Fetching (NewsAPI)
# =============================================================================


def fetch_news_for_symbol(
    symbol: str,
    api_key: str = NEWS_API_KEY,
    max_headlines: int = NEWS_MAX_HEADLINES,
) -> list[str]:
    """
    Fetch recent news headlines for a stock symbol using NewsAPI.

    Uses the /v2/everything endpoint to search for articles mentioning
    the stock symbol.  Returns only headline strings — we don't need
    the full article body for sentiment scoring.

    If the API key is missing or the request fails, returns an empty list
    so the pipeline can degrade gracefully.

    Args:
        symbol:        Stock ticker (e.g., "AAPL").
        api_key:       NewsAPI key. Default from config/settings.py.
        max_headlines: Maximum number of headlines to return.

    Returns:
        List of headline strings (may be empty on failure).
    """
    if not api_key:
        logger.warning(
            "NEWS_API_KEY not set — skipping news fetch for '%s'. "
            "Set it in config/.env to enable live news.",
            symbol,
        )
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": symbol,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": max_headlines,
        "apiKey": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        headlines = [
            article["title"]
            for article in data.get("articles", [])
            if article.get("title")
        ]

        logger.info("Fetched %d headlines for '%s'.", len(headlines), symbol)
        return headlines[:max_headlines]

    except requests.RequestException as exc:
        logger.error("NewsAPI request failed for '%s': %s", symbol, exc)
        return []


# =============================================================================
# Stock-Level Sentiment Aggregation
# =============================================================================


def analyze_stock_sentiment(
    symbol: str,
    headlines: list[str],
) -> dict:
    """
    Analyse all headlines for a single stock and produce an aggregated result.

    Scores each headline individually, then computes:
      - Average compound score across all headlines
      - Overall sentiment label (POSITIVE / NEGATIVE / NEUTRAL)
      - Count of positive, negative, and neutral headlines
      - Any major events detected in the headlines

    Args:
        symbol:    Stock ticker (e.g., "AAPL").
        headlines: List of headline strings to analyse.

    Returns:
        Dictionary containing:
            symbol              (str):   Ticker symbol.
            headline_count      (int):   Number of headlines analysed.
            avg_sentiment       (float): Mean compound score (-1.0 to +1.0).
            overall_label       (str):   Aggregated sentiment label.
            positive_count      (int):   Headlines with POSITIVE label.
            negative_count      (int):   Headlines with NEGATIVE label.
            neutral_count       (int):   Headlines with NEUTRAL label.
            major_events        (list):  Unique major event categories detected.
            has_major_event     (bool):  True if any major event was detected.
            headline_details    (list):  Per-headline score dicts.
            analysed_at         (str):   ISO-format timestamp.
    """
    if not headlines:
        return _empty_sentiment_result(symbol)

    scored = []
    all_events: set[str] = set()

    for hl in headlines:
        score_dict = score_headline(hl)
        events = detect_major_events(hl)
        score_dict["major_events"] = events
        scored.append(score_dict)
        all_events.update(events)

    # Aggregate scores
    compounds = [s["compound"] for s in scored]
    avg_compound = round(sum(compounds) / len(compounds), 4)

    if avg_compound >= SENTIMENT_POSITIVE_THRESHOLD:
        overall = "POSITIVE"
    elif avg_compound <= SENTIMENT_NEGATIVE_THRESHOLD:
        overall = "NEGATIVE"
    else:
        overall = "NEUTRAL"

    pos_count = sum(1 for s in scored if s["label"] == "POSITIVE")
    neg_count = sum(1 for s in scored if s["label"] == "NEGATIVE")
    neu_count = sum(1 for s in scored if s["label"] == "NEUTRAL")

    return {
        "symbol": symbol,
        "headline_count": len(scored),
        "avg_sentiment": avg_compound,
        "overall_label": overall,
        "positive_count": pos_count,
        "negative_count": neg_count,
        "neutral_count": neu_count,
        "major_events": sorted(all_events),
        "has_major_event": len(all_events) > 0,
        "headline_details": scored,
        "analysed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _empty_sentiment_result(symbol: str) -> dict:
    """Return a zeroed sentiment result when no headlines are available."""
    return {
        "symbol": symbol,
        "headline_count": 0,
        "avg_sentiment": 0.0,
        "overall_label": "NEUTRAL",
        "positive_count": 0,
        "negative_count": 0,
        "neutral_count": 0,
        "major_events": [],
        "has_major_event": False,
        "headline_details": [],
        "analysed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# =============================================================================
# Full Pipeline
# =============================================================================


def run_news_analysis(
    symbols: list[str],
    api_key: str = NEWS_API_KEY,
    headlines_override: dict[str, list[str]] | None = None,
) -> list[dict]:
    """
    Execute the full news sentiment pipeline for a list of stock symbols.

    For each symbol:
      1. Fetch headlines (or use provided overrides for testing).
      2. Score headlines with VADER.
      3. Aggregate into a per-stock sentiment summary.

    Args:
        symbols:            List of stock tickers to analyse.
        api_key:            NewsAPI key (passed to fetch_news_for_symbol).
        headlines_override: Optional dict mapping symbols to headline lists.
                            Used in testing to avoid live API calls.

    Returns:
        List of sentiment result dicts, one per symbol.
    """
    results = []

    for symbol in symbols:
        # Use overrides if provided (for testing), otherwise fetch live
        if headlines_override and symbol in headlines_override:
            headlines = headlines_override[symbol]
        else:
            headlines = fetch_news_for_symbol(symbol, api_key=api_key)

        result = analyze_stock_sentiment(symbol, headlines)
        results.append(result)

    logger.info(
        "News analysis complete for %d symbols. %d with major events.",
        len(results),
        sum(1 for r in results if r["has_major_event"]),
    )

    return results


# =============================================================================
# Persistence & Reporting
# =============================================================================


def save_sentiment_results(
    results: list[dict],
    output_dir: str = DATA_DIR,
) -> str:
    """
    Save sentiment analysis results to a dated CSV file.

    Creates data/sentiment_YYYY-MM-DD.csv and overwrites data/sentiment.csv
    as the "latest" reference for downstream modules.

    Args:
        results:    List of sentiment result dicts from run_news_analysis().
        output_dir: Directory to write CSV files to.

    Returns:
        Path to the saved dated CSV file.
    """
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for r in results:
        rows.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "symbol": r["symbol"],
            "headline_count": r["headline_count"],
            "avg_sentiment": r["avg_sentiment"],
            "overall_label": r["overall_label"],
            "positive_count": r["positive_count"],
            "negative_count": r["negative_count"],
            "neutral_count": r["neutral_count"],
            "major_events": ", ".join(r["major_events"]) if r["major_events"] else "",
            "has_major_event": r["has_major_event"],
        })

    df = pd.DataFrame(rows)

    date_str = datetime.now().strftime("%Y-%m-%d")
    dated_path = os.path.join(output_dir, f"sentiment_{date_str}.csv")
    df.to_csv(dated_path, index=False)

    latest_path = os.path.join(output_dir, "sentiment.csv")
    df.to_csv(latest_path, index=False)

    logger.info("Sentiment results saved to '%s'.", dated_path)
    return dated_path


def print_sentiment_report(results: list[dict]) -> None:
    """
    Print a formatted console report of news sentiment analysis results.

    Displays a table showing each stock's sentiment score, label, headline
    count, and any major events detected.

    Args:
        results: List of sentiment result dicts from run_news_analysis().
    """
    print("\n" + "=" * 85)
    print(f"  📰 NEWS SENTIMENT REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 85)

    if not results:
        print("  No sentiment data available.")
        print("=" * 85)
        return

    # Table header
    print(
        f"  {'Symbol':<8} {'Score':>7} {'Label':<10} "
        f"{'+':<4} {'-':<4} {'~':<4} {'Headlines':>9}  {'Major Events'}"
    )
    print("-" * 85)

    for r in results:
        events_str = ", ".join(r["major_events"]) if r["major_events"] else "—"
        flag = "⚠️" if r["has_major_event"] else "  "

        print(
            f"  {r['symbol']:<8} {r['avg_sentiment']:>+7.4f} {r['overall_label']:<10} "
            f"{r['positive_count']:<4} {r['negative_count']:<4} {r['neutral_count']:<4} "
            f"{r['headline_count']:>9}  {flag} {events_str}"
        )

    print("=" * 85)

    # Summary line
    major_count = sum(1 for r in results if r["has_major_event"])
    avg_all = (
        sum(r["avg_sentiment"] for r in results) / len(results)
        if results else 0.0
    )
    print(
        f"  Market mood: {avg_all:+.4f} | "
        f"{major_count} stock(s) with major events | "
        f"{len(results)} symbols analysed"
    )
    print("=" * 85 + "\n")


# =============================================================================
# CLI Entry Point — Run news analysis from the command line
# =============================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from core.utils import load_watchlist

    print("📰 Running News Sentiment Analysis...")
    symbols = load_watchlist()
    results = run_news_analysis(symbols)
    save_sentiment_results(results)
    print_sentiment_report(results)
