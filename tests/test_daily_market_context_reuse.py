# -*- coding: utf-8 -*-
"""Regression tests for same-day market-review reuse across stock analyses.

Bug: in US pre-/post-market, an individual stock analysis computes target_date =
effective trading session (e.g. last close 06-16), while a freshly generated
market review's wall-clock created_at is the next calendar day (06-17). With no
authoritative date stamped on the record, reuse matching fell back to
created_date == target_date, which never held in pre-market -> a brand new market
review was regenerated on EVERY individual analysis (wasted tokens).

Fix: stamp the analysis target_date onto the persisted record
(context_snapshot["market_review_target_date"]) and match against it.
"""

from datetime import date, datetime

from src.services.daily_market_context import _record_matches_target_date


class _FakeRecord:
    def __init__(self, *, context_snapshot, created_at, query_id=None):
        self.context_snapshot = context_snapshot
        self.created_at = created_at
        self.query_id = query_id


def test_premarket_reuse_with_target_date_stamp():
    """Pre-market: stamped target_date matches the analysis session -> reuse."""
    record = _FakeRecord(
        context_snapshot={
            "report_language": "zh",
            "market_review_target_date": "2026-06-16",
        },
        created_at=datetime(2026, 6, 17, 7, 40),  # next-day wall clock (pre-market)
    )
    assert _record_matches_target_date(
        record=record,
        payload={},  # no trade_date in payload
        region="us",
        target_date=date(2026, 6, 16),
        report_language="zh",
    ) is True


def test_different_session_does_not_reuse():
    """A stamped review for an older session must NOT be reused for a new one."""
    record = _FakeRecord(
        context_snapshot={
            "report_language": "zh",
            "market_review_target_date": "2026-06-16",
        },
        created_at=datetime(2026, 6, 16, 16, 5),
    )
    assert _record_matches_target_date(
        record=record,
        payload={},
        region="us",
        target_date=date(2026, 6, 17),
        report_language="zh",
    ) is False


def test_legacy_record_without_stamp_falls_back_to_payload_date():
    """Records persisted before the stamp still match via payload trade_date."""
    record = _FakeRecord(
        context_snapshot={"report_language": "zh"},  # no stamp
        created_at=datetime(2026, 6, 17, 7, 40),
    )
    assert _record_matches_target_date(
        record=record,
        payload={"trade_date": "2026-06-16"},
        region="us",
        target_date=date(2026, 6, 16),
        report_language="zh",
    ) is True


def test_language_mismatch_blocks_reuse():
    record = _FakeRecord(
        context_snapshot={
            "report_language": "en",
            "market_review_target_date": "2026-06-16",
        },
        created_at=datetime(2026, 6, 17, 7, 40),
    )
    assert _record_matches_target_date(
        record=record,
        payload={},
        region="us",
        target_date=date(2026, 6, 16),
        report_language="zh",
    ) is False


def test_query_id_match_still_reuses_regardless_of_date():
    record = _FakeRecord(
        context_snapshot={"report_language": "zh"},
        created_at=datetime(2026, 6, 10, 9, 0),
        query_id="q-123",
    )
    assert _record_matches_target_date(
        record=record,
        payload={},
        region="us",
        target_date=date(2026, 6, 16),
        current_query_id="q-123",
        report_language="zh",
    ) is True
