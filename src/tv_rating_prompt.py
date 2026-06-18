# -*- coding: utf-8 -*-
"""Prompt rendering for the TradingView multi-timeframe TA rating.

Kept dependency-light (stdlib + typing only) so it is fully unit-testable in
isolation and so a problem here can only affect this one prompt section.

The input ``tv_rating`` dict is produced by
``data_provider.tradingview_ta_fetcher.fetch_tv_rating``. Rendering is
fail-open: any missing / malformed input returns ``""`` (no section emitted).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


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


def format_tv_rating_section(
    tv_rating: Optional[Dict[str, Any]],
    report_language: str = "zh",
) -> str:
    """Render the TradingView multi-timeframe TA rating as a prompt section.

    Returns an empty string when no usable rating is present, so a missing or
    failed fetch simply produces no section.
    """
    if not isinstance(tv_rating, dict):
        return ""
    ratings = tv_rating.get("ratings")
    if not isinstance(ratings, dict) or not ratings:
        return ""
    order = tv_rating.get("intervals_order") or list(ratings.keys())
    is_en = str(report_language).lower().startswith("en")
    label_map = _TV_INTERVAL_LABEL_EN if is_en else _TV_INTERVAL_LABEL_ZH

    rows = []
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
        return ""

    symbol = tv_rating.get("symbol") or ""
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
