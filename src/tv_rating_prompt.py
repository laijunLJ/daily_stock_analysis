# -*- coding: utf-8 -*-
"""Markdown rendering for the TradingView multi-timeframe TA rating.

Kept dependency-light (stdlib + typing only) so it is fully unit-testable in
isolation and so a problem here can only affect this one section.

Two renderers share the same table builder:
* ``format_tv_rating_section``        -> the per-stock *analysis prompt* (model input)
* ``format_tv_rating_report_section`` -> the *visible report* (drawer / markdown)

Both are fail-open: any missing / malformed input returns ``""``.
The ``tv_rating`` dict is produced by
``data_provider.tradingview_ta_fetcher.fetch_tv_rating``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


_TV_INTERVAL_LABEL_ZH = {
    "1M": "月线", "1W": "周线", "1d": "日线", "4h": "4小时", "2h": "2小时",
    "1h": "1小时", "30m": "30分钟", "15m": "15分钟", "5m": "5分钟", "1m": "1分钟",
}
_TV_INTERVAL_LABEL_EN = {
    "1M": "Monthly", "1W": "Weekly", "1d": "Daily", "4h": "4H", "2h": "2H",
    "1h": "1H", "30m": "30m", "15m": "15m", "5m": "5m", "1m": "1m",
}
_TV_REC_ZH = {
    "STRONG_BUY": "强烈买入", "BUY": "买入", "NEUTRAL": "中性",
    "SELL": "卖出", "STRONG_SELL": "强烈卖出",
}


def _build_rows(tv_rating: Any, is_en: bool) -> Optional[Tuple[List[str], str]]:
    """Return (markdown_rows, symbol) or None when there is no usable rating."""
    if not isinstance(tv_rating, dict):
        return None
    ratings = tv_rating.get("ratings")
    if not isinstance(ratings, dict) or not ratings:
        return None
    order = tv_rating.get("intervals_order") or list(ratings.keys())
    label_map = _TV_INTERVAL_LABEL_EN if is_en else _TV_INTERVAL_LABEL_ZH

    rows: List[str] = []
    for interval in order:
        item = ratings.get(interval)
        if not isinstance(item, dict):
            continue
        rec = item.get("recommendation") or "N/A"
        if is_en:
            rec_text = str(rec).replace("_", " ").title()
        else:
            rec_text = (
                f"{item.get('recommendation_zh') or _TV_REC_ZH.get(str(rec).upper(), rec)}"
                f"({rec})"
            )
        period = label_map.get(interval, interval)
        counts = "/".join(
            "N/A" if item.get(key) is None else str(item.get(key))
            for key in ("buy", "sell", "neutral")
        )
        rows.append(f"| {period} | {rec_text} | {counts} |")
    if not rows:
        return None
    return rows, (tv_rating.get("symbol") or "")


def format_tv_rating_section(
    tv_rating: Optional[Dict[str, Any]],
    report_language: str = "zh",
) -> str:
    """Render the rating as a section of the per-stock *analysis prompt* (model input)."""
    is_en = str(report_language).lower().startswith("en")
    built = _build_rows(tv_rating, is_en)
    if built is None:
        return ""
    rows, symbol = built
    table = "\n".join(rows)
    sym_suffix = f" · {symbol}" if symbol else ""

    if is_en:
        return (
            f"\n### TradingView Multi-Timeframe TA Rating "
            f"(source: TradingView aggregate technicals{sym_suffix})\n"
            f"| Timeframe | Rating | Buy/Sell/Neutral (indicator count) |\n"
            f"|------|------|------|\n{table}\n\n"
            "> Note: this is TradingView's mechanical aggregate of ~26 oscillators and "
            "moving averages for each timeframe. Treat it as ONE external technical "
            "reference signal only (no fundamentals/news). When it conflicts with the "
            "other technical signals or the trend analysis above, treat it as a signal "
            "conflict and lower confidence accordingly; do not derive a standalone "
            "buy/sell point from it.\n"
        )
    return (
        f"\n### TradingView 多周期技术评级"
        f"（数据出处：TradingView 综合技术指标汇总{sym_suffix}）\n"
        f"| 周期 | 评级 | 买/卖/中性(指标数) |\n"
        f"|------|------|------|\n{table}\n\n"
        "> 说明：该评级是 TradingView 基于约 26 项振荡指标与均线对各周期的**机械汇总**，"
        "仅作为技术面的**外部参考信号之一**（不含基本面/新闻判断）。与上文其他技术信号或趋势分析"
        "冲突时，按“信号矛盾”处理并相应下调置信度，**不要据此单独给出确定性买卖点**。\n"
    )


def format_tv_rating_report_section(
    tv_rating: Optional[Dict[str, Any]],
    report_language: str = "zh",
) -> str:
    """Render the rating as a *visible* section for the analysis report (drawer/markdown)."""
    is_en = str(report_language).lower().startswith("en")
    built = _build_rows(tv_rating, is_en)
    if built is None:
        return ""
    rows, symbol = built
    table = "\n".join(rows)
    sym_part = f" ｜ {symbol}" if symbol else ""

    if is_en:
        sym_part_en = f" | {symbol}" if symbol else ""
        return (
            "### 📐 TradingView Multi-Timeframe TA Rating\n"
            f"> Source: TradingView aggregate technicals "
            f"(~26 oscillators + moving averages; technical reference only){sym_part_en}\n\n"
            "| Timeframe | Rating | Buy/Sell/Neutral |\n"
            "|------|------|------|\n"
            f"{table}\n"
        )
    return (
        "### 📐 TradingView 多周期技术评级\n"
        f"> 数据来源：TradingView 综合技术指标（约 26 项振荡指标 + 均线机械汇总，仅技术面参考）{sym_part}\n\n"
        "| 周期 | 评级 | 买/卖/中性 |\n"
        "|------|------|------|\n"
        f"{table}\n"
    )
