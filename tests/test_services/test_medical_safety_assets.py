"""Unit tests for the shared medical-safety assets module."""

from __future__ import annotations

import pytest

from src.services.medical_safety_assets import (
    GENERATION_SAFETY_CONTRACT,
    STATUS_QUALIFIERS,
    ensure_reference_qualification,
)


@pytest.mark.parametrize(
    ("status", "unqualified", "expected"),
    [
        ("normal", "Chỉ số này được phân loại normal.", "nằm trong khoảng tham chiếu"),
        ("high", "Chỉ số này được phân loại high.", "cao so với khoảng tham chiếu"),
        ("low", "Chỉ số này được phân loại low.", "thấp so với khoảng tham chiếu"),
        ("critical_high", "Trạng thái critical_high.", "vượt ngưỡng cảnh báo nguy kịch"),
        ("critical_low", "Trạng thái critical_low.", "vượt ngưỡng cảnh báo nguy kịch"),
    ],
)
def test_status_is_reference_or_threshold_qualified(status, unqualified, expected):
    result = ensure_reference_qualification(unqualified, status)

    assert expected in result
    assert result.endswith(unqualified)


def test_existing_reference_qualification_is_not_duplicated():
    explanation = "Giá trị này cao so với khoảng tham chiếu được hệ thống sử dụng."

    assert ensure_reference_qualification(explanation, "high") == explanation


def test_critical_qualifier_wins_when_is_critical():
    explanation = "Chỉ số này cao bất thường."
    result = ensure_reference_qualification(
        explanation,
        "high",
        critical_status="critical_high",
        is_critical=True,
    )

    assert result.startswith(STATUS_QUALIFIERS["critical_high"])
    assert "vượt ngưỡng cảnh báo nguy kịch" in result


def test_generation_contract_covers_actual_failures():
    assert "NORMAL chỉ có nghĩa là giá trị nằm trong khoảng tham chiếu" in GENERATION_SAFETY_CONTRACT
    assert 'Không gọi giá trị là "mức tối ưu"' in GENERATION_SAFETY_CONTRACT
    assert "không khẳng định tim, gan, thận, miễn dịch" in GENERATION_SAFETY_CONTRACT
    assert "Context không nêu thì phải bỏ" in GENERATION_SAFETY_CONTRACT


def test_status_qualifiers_cover_all_classified_statuses():
    assert set(STATUS_QUALIFIERS) == {
        "normal",
        "low",
        "high",
        "critical_low",
        "critical_high",
    }
