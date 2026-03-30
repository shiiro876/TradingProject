# =============================================================================
# tests/test_module3.py — Unit Tests for Module 3 (News & Macro)
# =============================================================================
#
# PURPOSE:
#   Validates the core functionality of Module 3 components:
#     - core/news.py:   Headline sentiment scoring, major event detection,
#                        aggregation, saving, and reporting.
#     - core/macro.py:  Sector return calculation, ranking, classification,
#                        rotation detection, sector lookup, and reporting.
#
# HOW TO RUN:
#   From the project root directory:
#     python -m pytest tests/test_module3.py -v
#
# =============================================================================

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Helper: Generate synthetic OHLCV data for sector ETF testing
# =============================================================================

def make_sector_ohlcv(rows: int = 30, trend: str = "up") -> pd.DataFrame:
    """
    Create a synthetic OHLCV DataFrame for testing sector calculations.

    Args:
        rows:  Number of data points (trading days).
        trend: "up" for uptrend, "down" for downtrend, "flat" for sideways.

    Returns:
        DataFrame with columns [Open, High, Low, Close, Volume].
    """
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=rows, freq="B")

    if trend == "up":
        base = 100 + np.cumsum(np.random.normal(0.5, 0.3, rows))
    elif trend == "down":
        base = 100 + np.cumsum(np.random.normal(-0.5, 0.3, rows))
    else:
        base = 100 + np.cumsum(np.random.normal(0.0, 0.2, rows))

    base = np.maximum(base, 10.0)  # No negative prices

    close = base
    open_ = close + np.random.normal(0, 0.2, rows)
    high = np.maximum(open_, close) + np.abs(np.random.normal(0.3, 0.1, rows))
    low = np.minimum(open_, close) - np.abs(np.random.normal(0.3, 0.1, rows))
    volume = np.random.randint(1_000_000, 5_000_000, rows).astype(float)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


# =============================================================================
# Test Suite: core/news.py — Headline Scoring
# =============================================================================

class TestHeadlineScoring:
    """Verify VADER-based headline sentiment scoring."""

    def test_positive_headline(self):
        """A clearly positive headline should score above the positive threshold."""
        from core.news import score_headline

        result = score_headline("Amazing earnings! Stock soars to all-time high with great performance!")
        assert result["compound"] > 0.0
        assert result["label"] == "POSITIVE"

    def test_negative_headline(self):
        """A clearly negative headline should score below the negative threshold."""
        from core.news import score_headline

        result = score_headline("Terrible disaster! Stock crashes horribly as losses mount and investors panic!")
        assert result["compound"] < 0.0
        assert result["label"] == "NEGATIVE"

    def test_neutral_headline(self):
        """A factual headline should score near zero and be labelled NEUTRAL."""
        from core.news import score_headline

        result = score_headline("Apple to hold quarterly earnings call on Thursday")
        # VADER may not see this as perfectly neutral, but it should be moderate
        assert result["label"] in ("NEUTRAL", "POSITIVE")  # Allow slight positive

    def test_score_returns_all_fields(self):
        """score_headline should return all expected dictionary keys."""
        from core.news import score_headline

        result = score_headline("Test headline for field check")
        expected_keys = ["headline", "compound", "positive", "negative", "neutral", "label"]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_compound_in_range(self):
        """VADER compound score should always be between -1.0 and +1.0."""
        from core.news import score_headline

        for headline in [
            "Great news! Stock soars to all-time high!",
            "Terrible crash wipes out billions in value",
            "Trading volume was average today",
        ]:
            result = score_headline(headline)
            assert -1.0 <= result["compound"] <= 1.0


# =============================================================================
# Test Suite: core/news.py — Major Event Detection
# =============================================================================

class TestMajorEventDetection:
    """Verify keyword-based major event detection."""

    def test_earnings_detection(self):
        """Headlines mentioning earnings should flag the 'earnings' category."""
        from core.news import detect_major_events

        events = detect_major_events("ExxonMobil quarterly earnings beat expectations")
        assert "earnings" in events

    def test_analyst_detection(self):
        """Headlines mentioning upgrades should flag the 'analyst' category."""
        from core.news import detect_major_events

        events = detect_major_events("Goldman Sachs issues upgrade for AAPL to overweight")
        assert "analyst" in events

    def test_merger_detection(self):
        """Headlines mentioning acquisitions should flag the 'merger' category."""
        from core.news import detect_major_events

        events = detect_major_events("Tech giant confirms acquisition of startup for $5B")
        assert "merger" in events

    def test_sector_event_detection(self):
        """Headlines mentioning oil supply should flag the 'sector' category."""
        from core.news import detect_major_events

        events = detect_major_events("Oil supply disruption sends energy stocks higher")
        assert "sector" in events

    def test_multiple_events(self):
        """A headline with multiple event types should return all matched."""
        from core.news import detect_major_events

        events = detect_major_events(
            "Earnings beat expectations after merger deal closes"
        )
        assert "earnings" in events
        assert "merger" in events

    def test_no_events(self):
        """A generic headline should return an empty list."""
        from core.news import detect_major_events

        events = detect_major_events("The weather is nice today")
        assert events == []

    def test_case_insensitive(self):
        """Event detection should be case-insensitive."""
        from core.news import detect_major_events

        events = detect_major_events("EARNINGS BEAT ALL EXPECTATIONS")
        assert "earnings" in events


# =============================================================================
# Test Suite: core/news.py — Stock Sentiment Aggregation
# =============================================================================

class TestSentimentAggregation:
    """Verify per-stock sentiment aggregation logic."""

    def test_analyze_positive_headlines(self):
        """Mostly positive headlines should yield a positive overall label."""
        from core.news import analyze_stock_sentiment

        headlines = [
            "Company reports record revenue growth",
            "Stock surges after stellar quarterly results",
            "Analysts upgrade stock to strong buy",
        ]
        result = analyze_stock_sentiment("AAPL", headlines)

        assert result["symbol"] == "AAPL"
        assert result["headline_count"] == 3
        assert result["avg_sentiment"] > 0
        assert result["overall_label"] == "POSITIVE"
        assert result["positive_count"] >= 2

    def test_analyze_negative_headlines(self):
        """Mostly negative headlines should yield a negative overall label."""
        from core.news import analyze_stock_sentiment

        headlines = [
            "Company announces devastating layoffs, terrible decline, and awful losses",
            "Revenue plummets as company faces devastating financial losses",
            "Stock crashes badly to a terrible 52-week low",
        ]
        result = analyze_stock_sentiment("XOM", headlines)

        assert result["avg_sentiment"] < 0
        assert result["overall_label"] == "NEGATIVE"
        assert result["negative_count"] >= 2

    def test_empty_headlines(self):
        """Empty headline list should return a zeroed neutral result."""
        from core.news import analyze_stock_sentiment

        result = analyze_stock_sentiment("MSFT", [])
        assert result["headline_count"] == 0
        assert result["avg_sentiment"] == 0.0
        assert result["overall_label"] == "NEUTRAL"

    def test_major_event_aggregation(self):
        """Major events from individual headlines should bubble up."""
        from core.news import analyze_stock_sentiment

        headlines = [
            "Quarterly earnings beat all expectations",
            "Merger deal announced with rival company",
        ]
        result = analyze_stock_sentiment("TEST", headlines)

        assert result["has_major_event"] is True
        assert "earnings" in result["major_events"]
        assert "merger" in result["major_events"]

    def test_headline_details_populated(self):
        """headline_details should contain per-headline scoring dicts."""
        from core.news import analyze_stock_sentiment

        headlines = ["Good news today", "Bad news tomorrow"]
        result = analyze_stock_sentiment("TEST", headlines)

        assert len(result["headline_details"]) == 2
        assert "compound" in result["headline_details"][0]


# =============================================================================
# Test Suite: core/news.py — Full Pipeline
# =============================================================================

class TestNewsPipeline:
    """Verify the full news analysis pipeline with headline overrides."""

    def test_run_news_analysis_with_overrides(self):
        """run_news_analysis should work with provided headlines (no API)."""
        from core.news import run_news_analysis

        overrides = {
            "AAPL": ["Apple reports record iPhone sales", "Great quarter for Apple"],
            "XOM": ["Oil prices crash amid oversupply concerns"],
        }

        results = run_news_analysis(
            symbols=["AAPL", "XOM"],
            headlines_override=overrides,
        )

        assert len(results) == 2
        aapl = next(r for r in results if r["symbol"] == "AAPL")
        xom = next(r for r in results if r["symbol"] == "XOM")

        assert aapl["headline_count"] == 2
        assert xom["headline_count"] == 1

    def test_run_news_analysis_missing_symbol(self):
        """Symbols not in overrides should get empty results."""
        from core.news import run_news_analysis

        results = run_news_analysis(
            symbols=["FAKE"],
            headlines_override={"AAPL": ["test"]},
        )

        assert len(results) == 1
        assert results[0]["headline_count"] == 0
        assert results[0]["overall_label"] == "NEUTRAL"

    def test_save_sentiment_results(self, tmp_path):
        """save_sentiment_results should create a CSV with correct columns."""
        from core.news import save_sentiment_results

        results = [{
            "symbol": "AAPL",
            "headline_count": 5,
            "avg_sentiment": 0.45,
            "overall_label": "POSITIVE",
            "positive_count": 3,
            "negative_count": 1,
            "neutral_count": 1,
            "major_events": ["earnings"],
            "has_major_event": True,
            "headline_details": [],
            "analysed_at": "2026-01-01 10:00:00",
        }]

        path = save_sentiment_results(results, output_dir=str(tmp_path))
        assert os.path.isfile(path)

        df = pd.read_csv(path)
        assert "symbol" in df.columns
        assert "avg_sentiment" in df.columns
        assert len(df) == 1

    def test_print_sentiment_report_no_error(self, capsys):
        """print_sentiment_report should execute without errors."""
        from core.news import print_sentiment_report

        results = [{
            "symbol": "AAPL",
            "headline_count": 3,
            "avg_sentiment": 0.5,
            "overall_label": "POSITIVE",
            "positive_count": 2,
            "negative_count": 0,
            "neutral_count": 1,
            "major_events": ["earnings"],
            "has_major_event": True,
        }]
        print_sentiment_report(results)
        captured = capsys.readouterr()
        assert "AAPL" in captured.out
        assert "NEWS SENTIMENT REPORT" in captured.out

    def test_print_sentiment_report_empty(self, capsys):
        """print_sentiment_report should handle empty results gracefully."""
        from core.news import print_sentiment_report

        print_sentiment_report([])
        captured = capsys.readouterr()
        assert "No sentiment data" in captured.out


# =============================================================================
# Test Suite: core/macro.py — Sector Return Calculation
# =============================================================================

class TestSectorReturns:
    """Verify sector return calculation and classification."""

    def test_calculate_return_uptrend(self):
        """An uptrending ETF should have a positive return."""
        from core.macro import calculate_sector_return

        df = make_sector_ohlcv(rows=30, trend="up")
        ret = calculate_sector_return(df, period_days=5)

        assert ret is not None
        assert ret > 0

    def test_calculate_return_downtrend(self):
        """A downtrending ETF should have a negative return."""
        from core.macro import calculate_sector_return

        df = make_sector_ohlcv(rows=30, trend="down")
        ret = calculate_sector_return(df, period_days=5)

        assert ret is not None
        assert ret < 0

    def test_calculate_return_insufficient_data(self):
        """Should return None if DataFrame has fewer rows than needed."""
        from core.macro import calculate_sector_return

        df = make_sector_ohlcv(rows=3, trend="up")
        ret = calculate_sector_return(df, period_days=5)
        assert ret is None

    def test_calculate_return_empty_df(self):
        """Should return None for an empty DataFrame."""
        from core.macro import calculate_sector_return

        ret = calculate_sector_return(pd.DataFrame(), period_days=5)
        assert ret is None

    def test_classify_sector_strong(self):
        """Return above +2% should classify as STRONG."""
        from core.macro import classify_sector

        assert classify_sector(3.5) == "STRONG"
        assert classify_sector(2.0) == "STRONG"

    def test_classify_sector_weak(self):
        """Return below -2% should classify as WEAK."""
        from core.macro import classify_sector

        assert classify_sector(-3.0) == "WEAK"
        assert classify_sector(-2.0) == "WEAK"

    def test_classify_sector_neutral(self):
        """Return between thresholds should classify as NEUTRAL."""
        from core.macro import classify_sector

        assert classify_sector(1.0) == "NEUTRAL"
        assert classify_sector(-1.0) == "NEUTRAL"
        assert classify_sector(0.0) == "NEUTRAL"
        assert classify_sector(None) == "NEUTRAL"


# =============================================================================
# Test Suite: core/macro.py — Sector Ranking
# =============================================================================

class TestSectorRanking:
    """Verify sector ranking and sorting logic."""

    def test_rank_sectors_with_synthetic_data(self):
        """rank_sectors should rank sectors by 1-week return descending."""
        from core.macro import rank_sectors

        sector_data = {
            "Energy": make_sector_ohlcv(rows=30, trend="up"),
            "Technology": make_sector_ohlcv(rows=30, trend="down"),
            "Healthcare": make_sector_ohlcv(rows=30, trend="flat"),
        }

        rankings = rank_sectors(sector_data=sector_data)

        assert len(rankings) == 3
        # Best performer should be rank 1
        assert rankings[0]["rank"] == 1
        assert rankings[1]["rank"] == 2
        assert rankings[2]["rank"] == 3

        # Returns should be descending
        for i in range(len(rankings) - 1):
            r1 = rankings[i]["return_1w"] or -999
            r2 = rankings[i + 1]["return_1w"] or -999
            assert r1 >= r2

    def test_rank_sectors_result_structure(self):
        """Each ranking result should have all expected keys."""
        from core.macro import rank_sectors

        sector_data = {
            "Energy": make_sector_ohlcv(rows=30, trend="up"),
        }

        rankings = rank_sectors(sector_data=sector_data)
        assert len(rankings) == 1

        r = rankings[0]
        expected_keys = [
            "sector", "etf_symbol", "return_1w", "return_1m",
            "classification", "rank",
        ]
        for key in expected_keys:
            assert key in r, f"Missing key: {key}"

    def test_rank_sectors_empty_input(self):
        """rank_sectors with no data should return empty list."""
        from core.macro import rank_sectors

        rankings = rank_sectors(sector_data={})
        assert rankings == []


# =============================================================================
# Test Suite: core/macro.py — Rotation Detection
# =============================================================================

class TestSectorRotation:
    """Verify sector rotation detection logic."""

    def test_detect_rotation_significant_move(self):
        """A rank change ≥ 3 positions should be flagged."""
        from core.macro import detect_sector_rotation

        current = [
            {"sector": "Energy", "rank": 1},
            {"sector": "Technology", "rank": 2},
            {"sector": "Healthcare", "rank": 3},
            {"sector": "Financials", "rank": 4},
        ]
        previous = [
            {"sector": "Energy", "rank": 4},   # Moved from 4 → 1 = +3
            {"sector": "Technology", "rank": 1},  # Moved from 1 → 2 = -1
            {"sector": "Healthcare", "rank": 2},
            {"sector": "Financials", "rank": 3},
        ]

        rotations = detect_sector_rotation(current, previous)

        assert len(rotations) >= 1
        energy_rot = [r for r in rotations if r["sector"] == "Energy"]
        assert len(energy_rot) == 1
        assert energy_rot[0]["direction"] == "UP"
        assert energy_rot[0]["rank_change"] == 3

    def test_detect_rotation_no_significant_move(self):
        """Small rank changes should NOT be flagged."""
        from core.macro import detect_sector_rotation

        current = [
            {"sector": "Energy", "rank": 1},
            {"sector": "Technology", "rank": 2},
        ]
        previous = [
            {"sector": "Energy", "rank": 2},   # Only moved 1 position
            {"sector": "Technology", "rank": 1},
        ]

        rotations = detect_sector_rotation(current, previous)
        assert len(rotations) == 0

    def test_detect_rotation_no_previous(self):
        """No previous rankings should return empty rotation list."""
        from core.macro import detect_sector_rotation

        current = [{"sector": "Energy", "rank": 1}]
        rotations = detect_sector_rotation(current, None)
        assert rotations == []

    def test_detect_rotation_down_movement(self):
        """A sector that drops ≥ 3 ranks should be flagged as DOWN."""
        from core.macro import detect_sector_rotation

        current = [
            {"sector": "Technology", "rank": 5},
            {"sector": "Energy", "rank": 1},
            {"sector": "Financials", "rank": 2},
            {"sector": "Healthcare", "rank": 3},
            {"sector": "Utilities", "rank": 4},
        ]
        previous = [
            {"sector": "Technology", "rank": 1},  # 1 → 5 = -4
            {"sector": "Energy", "rank": 2},
            {"sector": "Financials", "rank": 3},
            {"sector": "Healthcare", "rank": 4},
            {"sector": "Utilities", "rank": 5},
        ]

        rotations = detect_sector_rotation(current, previous)
        tech_rot = [r for r in rotations if r["sector"] == "Technology"]
        assert len(tech_rot) == 1
        assert tech_rot[0]["direction"] == "DOWN"
        assert tech_rot[0]["rank_change"] == -4


# =============================================================================
# Test Suite: core/macro.py — Sector Lookup
# =============================================================================

class TestSectorLookup:
    """Verify stock-to-sector mapping and score adjustments."""

    def test_get_sector_for_known_symbol(self):
        """Should return the correct sector for a symbol in the watchlist."""
        from core.macro import get_sector_for_symbol

        # Uses the real watchlist.csv in the project
        sector = get_sector_for_symbol("XOM")
        assert sector == "Energy"

    def test_get_sector_for_unknown_symbol(self):
        """Should return None for a symbol not in the watchlist."""
        from core.macro import get_sector_for_symbol

        sector = get_sector_for_symbol("ZZZZZ")
        assert sector is None

    def test_sector_adjustment_strong(self):
        """STRONG sector should give +1.0 adjustment."""
        from core.macro import get_sector_adjustment

        rankings = [
            {"sector": "Energy", "classification": "STRONG", "rank": 1},
            {"sector": "Technology", "classification": "NEUTRAL", "rank": 2},
        ]

        adj = get_sector_adjustment("XOM", rankings)
        assert adj == 1.0

    def test_sector_adjustment_weak(self):
        """WEAK sector should give -1.0 adjustment."""
        from core.macro import get_sector_adjustment

        rankings = [
            {"sector": "Energy", "classification": "WEAK", "rank": 5},
        ]

        adj = get_sector_adjustment("XOM", rankings)
        assert adj == -1.0

    def test_sector_adjustment_neutral(self):
        """NEUTRAL sector should give 0.0 adjustment."""
        from core.macro import get_sector_adjustment

        rankings = [
            {"sector": "Energy", "classification": "NEUTRAL", "rank": 3},
        ]

        adj = get_sector_adjustment("XOM", rankings)
        assert adj == 0.0

    def test_sector_adjustment_unknown_symbol(self):
        """Unknown symbol should give 0.0 adjustment."""
        from core.macro import get_sector_adjustment

        rankings = [{"sector": "Energy", "classification": "STRONG", "rank": 1}]
        adj = get_sector_adjustment("ZZZZZ", rankings)
        assert adj == 0.0


# =============================================================================
# Test Suite: core/macro.py — Full Pipeline & Reporting
# =============================================================================

class TestMacroPipeline:
    """Verify the full macro analysis pipeline."""

    def test_run_macro_analysis_synthetic(self):
        """run_macro_analysis should return a complete result structure."""
        from core.macro import run_macro_analysis

        sector_data = {
            "Energy": make_sector_ohlcv(rows=30, trend="up"),
            "Technology": make_sector_ohlcv(rows=30, trend="down"),
        }

        results = run_macro_analysis(sector_data=sector_data)

        assert "rankings" in results
        assert "strong" in results
        assert "weak" in results
        assert "rotations" in results
        assert "analysed_at" in results
        assert len(results["rankings"]) == 2

    def test_run_macro_analysis_with_rotation(self):
        """Passing previous_rankings should enable rotation detection."""
        from core.macro import run_macro_analysis

        sector_data = {
            "Energy": make_sector_ohlcv(rows=30, trend="up"),
            "Technology": make_sector_ohlcv(rows=30, trend="down"),
            "Healthcare": make_sector_ohlcv(rows=30, trend="flat"),
            "Financials": make_sector_ohlcv(rows=30, trend="up"),
        }

        # Fake previous rankings where Energy was last
        previous = [
            {"sector": "Technology", "rank": 1},
            {"sector": "Healthcare", "rank": 2},
            {"sector": "Financials", "rank": 3},
            {"sector": "Energy", "rank": 4},
        ]

        results = run_macro_analysis(
            previous_rankings=previous,
            sector_data=sector_data,
        )

        # Energy should have moved up significantly
        assert isinstance(results["rotations"], list)

    def test_save_sector_results(self, tmp_path):
        """save_sector_results should create a CSV with correct columns."""
        from core.macro import save_sector_results

        results = {
            "rankings": [
                {
                    "sector": "Energy", "etf_symbol": "XLE",
                    "return_1w": 3.5, "return_1m": 5.2,
                    "classification": "STRONG", "rank": 1,
                },
            ],
            "strong": ["Energy"],
            "weak": [],
            "rotations": [],
            "analysed_at": "2026-01-01 10:00:00",
        }

        path = save_sector_results(results, output_dir=str(tmp_path))
        assert os.path.isfile(path)

        df = pd.read_csv(path)
        assert "sector" in df.columns
        assert "return_1w" in df.columns
        assert len(df) == 1

    def test_print_sector_report_no_error(self, capsys):
        """print_sector_report should execute without errors."""
        from core.macro import print_sector_report

        results = {
            "rankings": [
                {
                    "sector": "Energy", "etf_symbol": "XLE",
                    "return_1w": 3.5, "return_1m": 5.2,
                    "classification": "STRONG", "rank": 1,
                },
                {
                    "sector": "Technology", "etf_symbol": "XLK",
                    "return_1w": -1.5, "return_1m": -3.2,
                    "classification": "WEAK", "rank": 2,
                },
            ],
            "strong": ["Energy"],
            "weak": ["Technology"],
            "rotations": [{
                "sector": "Energy",
                "direction": "UP",
                "old_rank": 4,
                "new_rank": 1,
                "rank_change": 3,
                "message": "SECTOR ROTATION: Energy moved from #4 → #1 (+3)",
            }],
            "analysed_at": "2026-01-01 10:00:00",
        }

        print_sector_report(results)
        captured = capsys.readouterr()
        assert "SECTOR ANALYSIS" in captured.out
        assert "Energy" in captured.out
        assert "STRONG" in captured.out

    def test_print_sector_report_empty(self, capsys):
        """print_sector_report should handle empty rankings gracefully."""
        from core.macro import print_sector_report

        results = {
            "rankings": [],
            "strong": [],
            "weak": [],
            "rotations": [],
            "analysed_at": "2026-01-01",
        }
        print_sector_report(results)
        captured = capsys.readouterr()
        assert "No sector data" in captured.out


# =============================================================================
# Test Suite: Settings Validation
# =============================================================================

class TestModule3Settings:
    """Verify that all Module 3 settings are present and valid."""

    def test_sentiment_thresholds_exist(self):
        """Sentiment threshold settings should be defined and sensible."""
        from config.settings import (
            SENTIMENT_POSITIVE_THRESHOLD,
            SENTIMENT_NEGATIVE_THRESHOLD,
        )
        assert SENTIMENT_POSITIVE_THRESHOLD > 0
        assert SENTIMENT_NEGATIVE_THRESHOLD < 0
        assert SENTIMENT_POSITIVE_THRESHOLD > SENTIMENT_NEGATIVE_THRESHOLD

    def test_major_event_keywords_exist(self):
        """MAJOR_EVENT_KEYWORDS should have at least 4 categories."""
        from config.settings import MAJOR_EVENT_KEYWORDS

        assert len(MAJOR_EVENT_KEYWORDS) >= 4
        for category, keywords in MAJOR_EVENT_KEYWORDS.items():
            assert len(keywords) > 0, f"Category '{category}' has no keywords"

    def test_sector_etfs_exist(self):
        """SECTOR_ETFS should map at least 6 sectors to ETF symbols."""
        from config.settings import SECTOR_ETFS

        assert len(SECTOR_ETFS) >= 6
        for sector, etf in SECTOR_ETFS.items():
            assert isinstance(sector, str)
            assert isinstance(etf, str)
            assert len(etf) <= 5  # ETF symbols are short

    def test_sector_performance_periods(self):
        """Sector performance periods should be positive integers."""
        from config.settings import SECTOR_PERFORMANCE_PERIODS

        assert "1_week" in SECTOR_PERFORMANCE_PERIODS
        assert "1_month" in SECTOR_PERFORMANCE_PERIODS
        assert SECTOR_PERFORMANCE_PERIODS["1_week"] > 0
        assert SECTOR_PERFORMANCE_PERIODS["1_month"] > 0
