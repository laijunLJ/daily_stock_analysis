# -*- coding: utf-8 -*-
"""TradingView multi-timeframe technical-analysis rating fetcher.

Pulls TradingView's *aggregate technical-analysis recommendation*
(STRONG_BUY .. STRONG_SELL) across several timeframes via TradingView's
public scanner endpoint, using the unofficial ``tradingview-ta`` library.

Design contract (matches the rest of the pipeline's fail-open philosophy):

* **Fully isolated** — any failure (import error, network error, unknown
  symbol, malformed payload) returns ``None`` and never raises into the
  analysis pipeline. "Breaks" only this one signal.
* **No credentials / no login** — uses the same public data that powers the
  "Technical Analysis" widget on a TradingView symbol page.
* **US-first** — ``market="us"`` uses the ``america`` screener and resolves
  the exchange automatically (NASDAQ / NYSE / AMEX). HK / CN are best-effort.

The returned dict is consumed by ``GeminiAnalyzer._format_prompt`` and rendered
as an extra *external* technical-reference block in the per-stock LLM prompt.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Import the unofficial library defensively so importing this module never
# fails even if the dependency is missing in some environment.
try:  # pragma: no cover - exercised indirectly
    from tradingview_ta import get_multiple_analysis as _get_multiple_analysis

    _TV_AVAILABLE = True
except Exception:  # noqa: BLE001 - any import problem -> feature disabled
    _get_multiple_analysis = None  # type: ignore[assignment]
    _TV_AVAILABLE = False


# market region -> (scanner screener, candidate exchange prefixes)
_MARKET_MAP: Dict[str, Tuple[str, List[str]]] = {
    "us": ("america", ["NASDAQ", "NYSE", "AMEX"]),
    "hk": ("hongkong", ["HKEX"]),
    "cn": ("china", ["SSE", "SZSE"]),
}

# TradingView Interval constants are just these raw strings, so we can pass
# them directly to get_multiple_analysis without importing the Interval enum.
_DEFAULT_INTERVALS: List[str] = ["1W", "1d", "4h", "1h"]
_VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1W", "1M"}

_REC_ZH = {
    "STRONG_BUY": "强烈买入",
    "BUY": "买入",
    "NEUTRAL": "中性",
    "SELL": "卖出",
    "STRONG_SELL": "强烈卖出",
}

_DEFAULT_TIMEOUT = 8.0


def _intervals_from_env() -> List[str]:
    raw = os.getenv("TV_RATING_INTERVALS", "").strip()
    if not raw:
        return list(_DEFAULT_INTERVALS)
    parsed = [part.strip() for part in raw.split(",") if part.strip() in _VALID_INTERVALS]
    return parsed or list(_DEFAULT_INTERVALS)


def _timeout_from_env() -> float:
    raw = os.getenv("TV_RATING_TIMEOUT", "").strip()
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        value = float(raw)
        return value if value > 0 else _DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _normalize_summary(summary: Any) -> Optional[Dict[str, Any]]:
    """Normalize a tradingview_ta Analysis.summary into a flat dict."""
    if not isinstance(summary, dict):
        return None
    rec_raw = summary.get("RECOMMENDATION")
    rec = str(rec_raw).upper() if rec_raw not in (None, "") else None
    if rec is None:
        return None
    return {
        "recommendation": rec,
        "recommendation_zh": _REC_ZH.get(rec, rec),
        "buy": _to_int(summary.get("BUY")),
        "sell": _to_int(summary.get("SELL")),
        "neutral": _to_int(summary.get("NEUTRAL")),
    }


def _pick_first_valid(analyses: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """From a {symbol: Analysis|None} mapping, pick the first usable one."""
    if not isinstance(analyses, dict):
        return None
    for symbol, analysis in analyses.items():
        if analysis is None:
            continue
        normalized = _normalize_summary(getattr(analysis, "summary", None))
        if normalized is not None:
            return str(symbol), normalized
    return None


def fetch_tv_rating(
    code: str,
    market: Optional[str],
    intervals: Optional[List[str]] = None,
    timeout: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch TradingView multi-timeframe TA rating for one stock.

    Args:
        code: bare ticker (e.g. ``"NVDA"``); A-share/HK codes also accepted.
        market: ``"us" | "hk" | "cn" | None`` (from ``get_market_for_stock``).
        intervals: optional list of TradingView interval strings.
        timeout: per-request timeout in seconds.

    Returns:
        A normalized dict (see module docstring) or ``None`` on any problem.
    """
    if not _TV_AVAILABLE or _get_multiple_analysis is None:
        return None
    if not code or not isinstance(code, str):
        return None

    mapping = _MARKET_MAP.get((market or "").lower())
    if mapping is None:
        # Unknown / unsupported market -> skip silently (fail-open).
        return None
    screener, exchanges = mapping

    ticker = code.strip().upper()
    if not ticker:
        return None

    interval_list = [iv for iv in (intervals or _intervals_from_env()) if iv in _VALID_INTERVALS]
    if not interval_list:
        interval_list = list(_DEFAULT_INTERVALS)
    req_timeout = timeout if (timeout and timeout > 0) else _timeout_from_env()

    ratings: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    resolved_symbol: Optional[str] = None

    try:
        for interval in interval_list:
            # Once the exchange is resolved, reuse the exact symbol to avoid
            # redundant candidate lookups.
            if resolved_symbol:
                symbols = [resolved_symbol]
            else:
                symbols = [f"{ex}:{ticker}" for ex in exchanges]

            analyses = _get_multiple_analysis(
                screener=screener,
                interval=interval,
                symbols=symbols,
                timeout=req_timeout,
            )
            picked = _pick_first_valid(analyses)
            if picked is None:
                continue
            resolved_symbol = picked[0]
            ratings[interval] = picked[1]
            order.append(interval)
    except Exception as exc:  # noqa: BLE001 - never propagate into pipeline
        logger.debug("[tv_rating] fetch failed for %s (%s): %s", ticker, market, exc)
        return None

    if not ratings or resolved_symbol is None:
        return None

    return {
        "source": "TradingView (tradingview-ta)",
        "symbol": resolved_symbol,
        "screener": screener,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "intervals_order": order,
        "ratings": ratings,
    }
