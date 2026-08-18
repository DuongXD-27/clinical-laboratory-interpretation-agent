import logging

from src.agents.nodes.reference_range_checker_node import get_reference_repository
from src.agents.state import AgentState, CriticalAlert, IndicatorAssessment

# `_compare_critical`, `glucose_mmol_l_to_mg_dl` và `load_critical_thresholds` không
# còn gọi trực tiếp trong file này nữa (logic đã chuyển vào critical_value_service),
# nhưng tests/test_agents/test_critical_detector_node.py monkeypatch/gọi đúng các tên
# này trên module `critical_detector` để chứng minh converter/so sánh không bị gọi
# trong các nhánh fail-closed và để load lại config trong test. Xoá các import này
# (kể cả khi lint báo "unused") sẽ làm AttributeError ở test, không phải làm test đó
# bớt cần thiết.
from src.services.critical_value_service import (
    CRITICAL_THRESHOLDS,
    evaluate_critical,
    load_critical_thresholds,  # noqa: F401
)
from src.services.critical_value_service import (
    compare_critical as _compare_critical,  # noqa: F401
)
from src.services.critical_value_service import (
    parse_numeric as _parse_numeric,
)
from src.services.measurement_conversion import glucose_mmol_l_to_mg_dl  # noqa: F401
from src.services.reference_repository import ReferenceRepositoryError

logger = logging.getLogger(__name__)


async def detect_critical_values_node(state: AgentState) -> dict:
    """Phát hiện các chỉ số ở mức nguy kịch (critical) bằng rule-based an toàn đơn vị và định danh."""
    raw_indicators = state.get("raw_indicators", [])

    # Check if indicators were already populated by upstream node (e.g. reference_range_checker)
    has_upstream_indicators = bool(state.get("indicators"))
    indicators: list[IndicatorAssessment] = state.get("indicators", [])

    if not indicators and raw_indicators:
        indicators = [
            {
                "name": ind["name"],
                "value": ind["value"],
                "unit": ind.get("unit", ""),
                "reference_low": None,
                "reference_high": None,
                "status": "unknown",
                "is_abnormal": False,
                "is_critical": False,
            }
            for ind in raw_indicators
        ]

    # Tạo bản sao list mới thay vì dùng reference để tránh lỗi Duplicate Alerts
    critical_alerts: list[CriticalAlert] = list(state.get("critical_alerts", []))
    has_critical = state.get("has_critical_values", False)

    try:
        repository = get_reference_repository()
    except ReferenceRepositoryError as exc:
        logger.error("Reference repository unavailable in critical detector: %s", exc)
        repository = None

    updated_indicators = []

    for ind in indicators:
        # Copy dictionary để không ảnh hưởng trực tiếp đến state reference
        new_ind = dict(ind)
        name = new_ind.get("name", "")
        val = new_ind.get("value")
        input_unit = str(new_ind.get("unit", "")).strip()
        current_status = new_ind.get("status")

        numeric_val = _parse_numeric(val)
        if numeric_val is None or not name:
            updated_indicators.append(new_ind)
            continue

        # Blocker 02: If upstream Reference Range Checker already evaluated and returned 'unknown',
        # do NOT overwrite unknown with critical_low / critical_high.
        if has_upstream_indicators and current_status == "unknown":
            logger.debug(
                "Critical evaluation skipped for '%s': upstream status is 'unknown'",
                name,
            )
            updated_indicators.append(new_ind)
            continue

        # Blocker 01: Canonicalization via ReferenceRepository.
        # Canonicalization failure MUST NOT fall back to raw name lookup in CRITICAL_THRESHOLDS.
        if repository is None:
            logger.warning(
                "Critical evaluation skipped for '%s': ReferenceRepository unavailable",
                name,
            )
            updated_indicators.append(new_ind)
            continue

        canonical_analyte = repository.resolve_analyte(name)
        if not canonical_analyte:
            logger.debug(
                "Critical evaluation skipped for '%s': analyte not resolvable by ReferenceRepository",
                name,
            )
            updated_indicators.append(new_ind)
            continue

        # Look up threshold strictly by canonical analyte name (lowercase)
        canonical_key = canonical_analyte.lower()
        if canonical_key not in CRITICAL_THRESHOLDS:
            # Not a critical-registered analyte
            updated_indicators.append(new_ind)
            continue

        evaluation = evaluate_critical(
            canonical_analyte,
            val,
            input_unit,
            display_name=name,
            thresholds=CRITICAL_THRESHOLDS.get(canonical_key),
        )

        if evaluation.is_critical:
            new_ind["is_abnormal"] = True
            new_ind["is_critical"] = True
            new_ind["critical_status"] = evaluation.critical_status
            has_critical = True
            # Chống trùng lặp (nếu đồ thị chạy lại / retry)
            if not any(a.get("indicator_name") == name for a in critical_alerts):
                critical_alerts.append(
                    {
                        "indicator_name": name,
                        "value": val,
                        "unit": input_unit,
                        "message": evaluation.alert_message or "",
                    }
                )
        elif evaluation.evaluated:
            new_ind["is_critical"] = False
            new_ind["critical_status"] = None

        # Giữ lại indicator đã xử lý
        updated_indicators.append(new_ind)

    return {
        "indicators": updated_indicators,
        "critical_alerts": critical_alerts,
        "has_critical_values": has_critical,
    }
