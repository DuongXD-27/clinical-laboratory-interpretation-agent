import json
from pathlib import Path

from src.agents.state import AgentState, CriticalAlert, IndicatorAssessment
from src.config import get_settings


def load_critical_thresholds() -> dict:
    settings = get_settings()
    config_path = Path(settings.critical_thresholds_path)
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
            # Chuyển tất cả keys sang lowercase để fix lỗi Case-Sensitivity
            return {k.lower(): v for k, v in data.items()}
    return {}

CRITICAL_THRESHOLDS = load_critical_thresholds()

async def detect_critical_values_node(state: AgentState) -> dict:
    """Phát hiện các chỉ số ở mức nguy kịch (critical) bằng rule-based đơn giản."""
    raw_indicators = state.get("raw_indicators", [])

    # Nếu node reference_range_checker chưa chạy, ta khởi tạo từ raw_indicators.
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

    updated_indicators = []

    for ind in indicators:
        # Copy dictionary để không ảnh hưởng trực tiếp đến state reference
        new_ind = dict(ind)
        name = new_ind.get("name", "")
        val = new_ind.get("value")

        # So sánh chữ thường (case-insensitive)
        name_lower = name.lower() if name else ""

        if name_lower in CRITICAL_THRESHOLDS and val is not None:
            thresholds = CRITICAL_THRESHOLDS[name_lower]
            low_val = thresholds.get("low")
            high_val = thresholds.get("high")
            unit_str = new_ind.get("unit") or thresholds.get("unit", "")

            if low_val is not None and low_val >= 0 and val <= low_val:
                new_ind["status"] = "critical_low"
                new_ind["is_abnormal"] = True
                new_ind["is_critical"] = True
                has_critical = True
                # Chống trùng lặp (nếu đồ thị chạy lại / retry)
                if not any(a.get("indicator_name") == name for a in critical_alerts):
                    critical_alerts.append({
                        "indicator_name": name,
                        "value": val,
                        "unit": unit_str,
                        "message": f"CẢNH BÁO: {name} giảm tới ngưỡng nguy kịch ({val} <= {low_val} {unit_str}). Yêu cầu can thiệp y tế."
                    })
            elif high_val is not None and high_val >= 0 and val >= high_val:
                new_ind["status"] = "critical_high"
                new_ind["is_abnormal"] = True
                new_ind["is_critical"] = True
                has_critical = True
                # Chống trùng lặp
                if not any(a.get("indicator_name") == name for a in critical_alerts):
                    critical_alerts.append({
                        "indicator_name": name,
                        "value": val,
                        "unit": unit_str,
                        "message": f"CẢNH BÁO: {name} tăng tới ngưỡng nguy kịch ({val} >= {high_val} {unit_str}). Yêu cầu can thiệp y tế."
                    })

        # Dòng này phải NẰM NGOÀI khối if để giữ lại tất cả indicators
        updated_indicators.append(new_ind)

    return {
        "indicators": updated_indicators,
        "critical_alerts": critical_alerts,
        "has_critical_values": has_critical
    }
