from __future__ import annotations

from datetime import date

import pytest

from src.models.orchestrator_schemas import (
    IntentEnum,
    ReasonCode,
    ResponseStatus,
    TrendDataPayload,
)
from src.models.schemas import CriticalAlertSchema, TrendPointResponse, TrendResponse
from src.orchestrator import response_composer
from src.orchestrator.response_composer import build_final_response, deterministic_message_for


def _trend_payload(
    *,
    analyte: str,
    unit: str,
    values: list[tuple[date, float, str]],
    observed_direction: str | None,
    critical_alert: CriticalAlertSchema | None = None,
) -> TrendDataPayload:
    return TrendDataPayload(
        trend=TrendResponse(
            analyte_canonical=analyte,
            display_name=analyte,
            canonical_unit=unit,
            filter="latest5",
            result_count=len(values),
            trend_available=len(values) >= 3,
            points=[
                TrendPointResponse(
                    report_id=index,
                    test_date=test_date,
                    value=value,
                    assessment=assessment,
                )
                for index, (test_date, value, assessment) in enumerate(values, start=1)
            ],
            observed_direction=observed_direction,
            critical_alert=critical_alert,
        )
    )


def _message(payload: TrendDataPayload) -> str:
    return deterministic_message_for(
        ResponseStatus.SUCCESS,
        None,
        IntentEnum.ANALYZE_TREND,
        payload,
    )


def test_increasing_trend_preserves_exact_dates_values_unit_and_latest_assessment():
    message = _message(
        _trend_payload(
            analyte="WBC",
            unit="G/L",
            values=[
                (date(2026, 4, 15), 6.5, "normal"),
                (date(2026, 6, 15), 8.1, "normal"),
                (date(2026, 8, 15), 12.0, "high"),
            ],
            observed_direction="increasing",
        )
    )

    assert "WBC" in message
    assert "15/04/2026: 6.5 G/L" in message
    assert "15/06/2026: 8.1 G/L" in message
    assert "15/08/2026: 12.0 G/L" in message
    assert "tăng qua các lần đo được ghi nhận" in message
    assert "Giá trị gần nhất là 12.0 G/L" in message
    assert "CAO" in message


def test_decreasing_trend_preserves_exact_dates_values_and_percent_unit():
    message = _message(
        _trend_payload(
            analyte="HbA1c",
            unit="%",
            values=[
                (date(2026, 4, 15), 7.4, "high"),
                (date(2026, 6, 15), 7.1, "high"),
                (date(2026, 8, 15), 6.8, "high"),
            ],
            observed_direction="decreasing",
        )
    )

    assert "15/04/2026: 7.4%" in message
    assert "15/06/2026: 7.1%" in message
    assert "15/08/2026: 6.8%" in message
    assert "giảm qua các lần đo được ghi nhận" in message
    assert "Giá trị gần nhất là 6.8%" in message
    assert "CAO" in message


def test_null_direction_describes_mixed_observations_without_direction_claim():
    message = _message(
        _trend_payload(
            analyte="Creatinine",
            unit="µmol/L",
            values=[
                (date(2026, 4, 15), 82.0, "normal"),
                (date(2026, 6, 15), 88.0, "normal"),
                (date(2026, 8, 15), 84.0, "normal"),
            ],
            observed_direction=None,
        )
    )

    assert "15/04/2026: 82.0 µmol/L" in message
    assert "15/06/2026: 88.0 µmol/L" in message
    assert "15/08/2026: 84.0 µmol/L" in message
    assert "tăng" not in message.casefold()
    assert "giảm" not in message.casefold()
    assert "ổn định" not in message.casefold()


def test_latest_unknown_assessment_preserves_unknown_semantics():
    message = _message(
        _trend_payload(
            analyte="Creatinine",
            unit="µmol/L",
            values=[
                (date(2026, 4, 15), 82.0, "normal"),
                (date(2026, 6, 15), 88.0, "normal"),
                (date(2026, 8, 15), 84.0, "unknown"),
            ],
            observed_direction=None,
        )
    )

    assert "CHƯA XÁC ĐỊNH (UNKNOWN)" in message


def test_latest_high_without_critical_alert_does_not_claim_critical_or_emergency():
    message = _message(
        _trend_payload(
            analyte="WBC",
            unit="G/L",
            values=[
                (date(2026, 4, 15), 6.5, "normal"),
                (date(2026, 6, 15), 8.1, "normal"),
                (date(2026, 8, 15), 12.0, "high"),
            ],
            observed_direction="increasing",
        )
    )

    assert "CAO" in message
    assert "nguy kịch" not in message.casefold()
    assert "khẩn cấp" not in message.casefold()


def test_critical_alert_preserves_authoritative_message_prominently():
    alert_message = "Kali hiện ở ngưỡng cảnh báo theo bộ phát hiện hiện hành."
    message = _message(
        _trend_payload(
            analyte="Potassium",
            unit="mmol/L",
            values=[
                (date(2026, 4, 15), 4.9, "normal"),
                (date(2026, 6, 15), 5.8, "high"),
                (date(2026, 8, 15), 6.4, "high"),
            ],
            observed_direction="increasing",
            critical_alert=CriticalAlertSchema(
                indicator_name="Potassium",
                value=6.4,
                unit="mmol/L",
                message=alert_message,
            ),
        )
    )

    assert "⚠️ CẢNH BÁO" in message
    assert alert_message in message


@pytest.mark.parametrize(
    "forbidden_claim",
    ["cải thiện", "xấu đi", "tốt hơn", "điều trị hiệu quả", "% thay đổi", "độ dốc"],
)
def test_trend_message_does_not_add_forbidden_interpretation(forbidden_claim):
    message = _message(
        _trend_payload(
            analyte="HbA1c",
            unit="%",
            values=[
                (date(2026, 4, 15), 7.4, "high"),
                (date(2026, 6, 15), 7.1, "high"),
                (date(2026, 8, 15), 6.8, "high"),
            ],
            observed_direction="decreasing",
        )
    )

    assert forbidden_claim not in message.casefold()


def test_insufficient_data_message_remains_unchanged():
    payload = _trend_payload(
        analyte="WBC",
        unit="G/L",
        values=[
            (date(2026, 6, 15), 8.1, "normal"),
            (date(2026, 8, 15), 12.0, "high"),
        ],
        observed_direction=None,
    )

    assert deterministic_message_for(
        ResponseStatus.NEEDS_INPUT,
        ReasonCode.TREND_INSUFFICIENT_POINTS,
        IntentEnum.ANALYZE_TREND,
        payload,
    ) == "Chưa đủ dữ liệu để tạo xu hướng cho chỉ số này."


@pytest.mark.asyncio
async def test_successful_trend_response_is_deterministic_and_does_not_call_llm(monkeypatch):
    payload = _trend_payload(
        analyte="HbA1c",
        unit="%",
        values=[
            (date(2026, 4, 15), 7.4, "high"),
            (date(2026, 6, 15), 7.1, "high"),
            (date(2026, 8, 15), 6.8, "high"),
        ],
        observed_direction="decreasing",
    )
    calls = 0

    def counted_llm():
        nonlocal calls
        calls += 1
        raise AssertionError("Trend composition must remain deterministic")

    monkeypatch.setattr(response_composer, "get_llm", counted_llm)

    response = await build_final_response(
        intent=IntentEnum.ANALYZE_TREND,
        status=ResponseStatus.SUCCESS,
        data=payload,
    )

    assert calls == 0
    assert response.status == ResponseStatus.SUCCESS
    assert response.data == payload
    assert "15/08/2026: 6.8%" in response.message
    assert "giảm qua các lần đo được ghi nhận" in response.message
