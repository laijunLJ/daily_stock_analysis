# -*- coding: utf-8 -*-
"""Tests for the backtest-derived calibration prompt section (daily-report ③)."""

from src.services.backtest_service import format_historical_calibration_prompt_section


def test_renders_rows_when_data_present():
    g = {"completed_count": 120, "direction_accuracy_pct": 58.0, "win_rate_pct": 52.0}
    s = {"completed_count": 14, "direction_accuracy_pct": 50.0, "win_rate_pct": 45.0}
    out = format_historical_calibration_prompt_section(g, s, code="AAOI", report_language="zh")
    assert "历史校准" in out
    assert "58.0%" in out and "样本 120" in out
    assert "AAOI" in out and "样本 14" in out
    assert "confidence_level" in out


def test_empty_when_no_history():
    assert format_historical_calibration_prompt_section(None, None, code="AAOI") == ""
    # zero samples should also be skipped
    assert format_historical_calibration_prompt_section(
        {"completed_count": 0, "direction_accuracy_pct": None},
        {"completed_count": 0, "direction_accuracy_pct": None},
        code="AAOI",
    ) == ""


def test_stock_only():
    s = {"total_evaluations": 9, "completed_count": 9, "direction_accuracy_pct": 66.7, "win_rate_pct": 55.0}
    out = format_historical_calibration_prompt_section(None, s, code="INTC", report_language="zh")
    assert "本股 INTC" in out and "66.7%" in out
    assert "全局历史" not in out


def test_english():
    g = {"completed_count": 40, "direction_accuracy_pct": 60.0, "win_rate_pct": 50.0}
    out = format_historical_calibration_prompt_section(g, None, code="INTC", report_language="en")
    assert "Historical calibration" in out
    assert "direction accuracy 60.0%" in out and "n=40" in out
