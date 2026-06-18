# -*- coding: utf-8 -*-
"""Unit tests for the TradingView multi-timeframe TA rating feature.

Covers:
* ``data_provider.tradingview_ta_fetcher.fetch_tv_rating`` — exchange
  resolution, summary normalization, and fail-open behavior. The fetcher is a
  dependency-light leaf module, so it is loaded in isolation (without importing
  the whole ``data_provider`` package) to keep the test fast and hermetic.
* ``src.tv_rating_prompt.format_tv_rating_section`` — prompt rendering and its
  fail-open contract.
"""

import importlib.util
import os
import unittest

from src.tv_rating_prompt import (
    format_tv_rating_section,
    format_tv_rating_report_section,
)


def _load_fetcher():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "data_provider", "tradingview_ta_fetcher.py")
    spec = importlib.util.spec_from_file_location("tv_ta_fetcher_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeAnalysis:
    def __init__(self, summary):
        self.summary = summary


class FetchTvRatingTest(unittest.TestCase):
    def setUp(self):
        self.f = _load_fetcher()
        self.f._TV_AVAILABLE = True

    def test_resolves_exchange_once_then_reuses(self):
        calls = []

        def fake_gma(screener, interval, symbols, timeout=None):
            calls.append((interval, list(symbols)))
            return {
                s: (
                    _FakeAnalysis(
                        {"RECOMMENDATION": "STRONG_BUY", "BUY": 18, "SELL": 2, "NEUTRAL": 6}
                    )
                    if s == "NASDAQ:NVDA"
                    else None
                )
                for s in symbols
            }

        self.f._get_multiple_analysis = fake_gma
        out = self.f.fetch_tv_rating("nvda", "us", intervals=["1W", "1d", "4h"], timeout=5)

        self.assertIsNotNone(out)
        self.assertEqual(out["symbol"], "NASDAQ:NVDA")
        self.assertEqual(out["screener"], "america")
        self.assertEqual(out["intervals_order"], ["1W", "1d", "4h"])
        self.assertEqual(out["ratings"]["1W"]["recommendation"], "STRONG_BUY")
        self.assertEqual(out["ratings"]["1W"]["recommendation_zh"], "强烈买入")
        self.assertEqual(out["ratings"]["1W"]["buy"], 18)
        # First call tries all candidate exchanges; later calls reuse the match.
        self.assertEqual(calls[0][1], ["NASDAQ:NVDA", "NYSE:NVDA", "AMEX:NVDA"])
        self.assertEqual(calls[1][1], ["NASDAQ:NVDA"])
        self.assertEqual(calls[2][1], ["NASDAQ:NVDA"])

    def test_unknown_market_returns_none(self):
        self.f._get_multiple_analysis = lambda *a, **k: {}
        self.assertIsNone(self.f.fetch_tv_rating("NVDA", None))
        self.assertIsNone(self.f.fetch_tv_rating("NVDA", "jp"))

    def test_no_match_returns_none(self):
        self.f._get_multiple_analysis = lambda screener, interval, symbols, timeout=None: {
            s: None for s in symbols
        }
        self.assertIsNone(self.f.fetch_tv_rating("ZZZZ", "us"))

    def test_library_error_is_fail_open(self):
        def boom(*a, **k):
            raise RuntimeError("network down")

        self.f._get_multiple_analysis = boom
        self.assertIsNone(self.f.fetch_tv_rating("NVDA", "us"))

    def test_library_unavailable_returns_none(self):
        self.f._TV_AVAILABLE = False
        self.f._get_multiple_analysis = None
        self.assertIsNone(self.f.fetch_tv_rating("NVDA", "us"))

    def test_normalize_summary_rejects_missing_recommendation(self):
        self.assertIsNone(self.f._normalize_summary({"BUY": 1}))
        self.assertIsNone(self.f._normalize_summary(None))
        norm = self.f._normalize_summary(
            {"RECOMMENDATION": "sell", "BUY": "3", "SELL": "9", "NEUTRAL": "8"}
        )
        self.assertEqual(norm["recommendation"], "SELL")
        self.assertEqual(norm["recommendation_zh"], "卖出")
        self.assertEqual((norm["buy"], norm["sell"], norm["neutral"]), (3, 9, 8))


class FormatTvRatingSectionTest(unittest.TestCase):
    def _sample(self):
        return {
            "source": "TradingView (tradingview-ta)",
            "symbol": "NASDAQ:NVDA",
            "screener": "america",
            "intervals_order": ["1W", "1d", "4h"],
            "ratings": {
                "1W": {"recommendation": "STRONG_BUY", "recommendation_zh": "强烈买入", "buy": 18, "sell": 2, "neutral": 6},
                "1d": {"recommendation": "BUY", "recommendation_zh": "买入", "buy": 12, "sell": 4, "neutral": 10},
                "4h": {"recommendation": "NEUTRAL", "recommendation_zh": "中性", "buy": 8, "sell": 7, "neutral": 11},
            },
        }

    def test_zh_render(self):
        out = format_tv_rating_section(self._sample(), "zh")
        self.assertIn("### TradingView 多周期技术评级", out)
        self.assertIn("NASDAQ:NVDA", out)
        self.assertIn("| 周线 | 强烈买入(STRONG_BUY) | 18/2/6 |", out)
        self.assertIn("| 日线 | 买入(BUY) | 12/4/10 |", out)
        self.assertIn("信号矛盾", out)

    def test_en_render(self):
        out = format_tv_rating_section(self._sample(), "en")
        self.assertIn("TradingView Multi-Timeframe TA Rating", out)
        self.assertIn("| Weekly | Strong Buy | 18/2/6 |", out)
        self.assertIn("signal conflict", out)

    def test_fail_open_empty_inputs(self):
        self.assertEqual(format_tv_rating_section(None), "")
        self.assertEqual(format_tv_rating_section({}), "")
        self.assertEqual(format_tv_rating_section({"ratings": {}}), "")
        self.assertEqual(format_tv_rating_section({"ratings": {"1d": "bad"}}), "")

    def test_missing_counts_render_as_na(self):
        tv = {
            "symbol": "NYSE:DOCN",
            "intervals_order": ["1d"],
            "ratings": {"1d": {"recommendation": "BUY", "buy": None, "sell": None, "neutral": None}},
        }
        out = format_tv_rating_section(tv, "zh")
        self.assertIn("N/A/N/A/N/A", out)



class FormatTvRatingReportSectionTest(unittest.TestCase):
    def _sample(self):
        return {
            "symbol": "NASDAQ:MRVL",
            "intervals_order": ["1W", "1d", "4h", "1h"],
            "ratings": {
                "1W": {"recommendation": "BUY", "recommendation_zh": "买入", "buy": 14, "sell": 3, "neutral": 9},
                "1d": {"recommendation": "BUY", "recommendation_zh": "买入", "buy": 14, "sell": 2, "neutral": 10},
                "4h": {"recommendation": "BUY", "recommendation_zh": "买入", "buy": 13, "sell": 3, "neutral": 10},
                "1h": {"recommendation": "SELL", "recommendation_zh": "卖出", "buy": 6, "sell": 10, "neutral": 10},
            },
        }

    def test_zh_report_render(self):
        out = format_tv_rating_report_section(self._sample(), "zh")
        self.assertIn("### 📐 TradingView 多周期技术评级", out)
        self.assertIn("NASDAQ:MRVL", out)
        self.assertIn("| 周线 | 买入(BUY) | 14/3/9 |", out)
        self.assertIn("| 1小时 | 卖出(SELL) | 6/10/10 |", out)
        # Report variant must NOT carry the prompt-only instruction text.
        self.assertNotIn("不要据此单独给出确定性买卖点", out)

    def test_en_report_render(self):
        out = format_tv_rating_report_section(self._sample(), "en")
        self.assertIn("TradingView Multi-Timeframe TA Rating", out)
        self.assertIn("| Weekly | Buy | 14/3/9 |", out)

    def test_report_fail_open(self):
        self.assertEqual(format_tv_rating_report_section(None), "")
        self.assertEqual(format_tv_rating_report_section({"ratings": {}}), "")

if __name__ == "__main__":
    unittest.main()
