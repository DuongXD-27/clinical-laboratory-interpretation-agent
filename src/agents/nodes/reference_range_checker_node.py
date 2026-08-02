import json
from pathlib import Path

from src.agents.state import AgentState, IndicatorAssessment
from src.config import get_settings


def load_explanations() -> dict:
    get_settings()
    config_path = Path("data/reference/explanations.json")
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
            return {item["indicator"].lower(): item for item in data}
    return {}

EXPLANATIONS_DB = load_explanations()

def get_gender_code(gender_str: str) -> str:
    g = (gender_str or "").lower()
    if g in ["male", "nam", "m"]:
        return "M"
    elif g in ["female", "nữ", "f"]:
        return "F"
    return "A"

async def reference_range_checker_node(state: AgentState) -> dict:
    """Kiểm tra giá trị chỉ số dựa trên khoảng tham chiếu để phân loại trạng thái."""
    raw_indicators = state.get("raw_indicators", [])
    patient_gender = state.get("patient_gender", "A")

    gender_code = get_gender_code(patient_gender)

    indicators: list[IndicatorAssessment] = []

    for ind in raw_indicators:
        name = ind.get("name", "")
        val = ind.get("value")
        unit = ind.get("unit", "")

        assessment: IndicatorAssessment = {
            "name": name,
            "value": val,
            "unit": unit,
            "reference_low": None,
            "reference_high": None,
            "status": "unknown",
            "is_abnormal": False,
            "is_critical": False,
            "explanation": "",
            "sources": []
        }

        name_lower = name.lower()
        if name_lower in EXPLANATIONS_DB and val is not None:
            indicator_info = EXPLANATIONS_DB[name_lower]
            ranges = indicator_info.get("reference_ranges", [])

            matched_group = "unknown"
            for r in ranges:
                r_gender = r.get("gender", "A")
                if r_gender != "A" and r_gender != gender_code:
                    continue

                low = r.get("low")
                high = r.get("high")

                if low is not None and val < low:
                    continue
                # Some ranges use exclusive high bound, some inclusive. We use >= high for exclusive, or > if inclusive.
                # In typical JSON definitions like "fasting_prediabetes" (5.6 to 6.9), let's assume < high is safe.
                # If high is None, it's open ended.
                if high is not None and val > high:
                    continue

                matched_group = r.get("group", "unknown")
                if matched_group in ["normal", "optimal", "average"]:
                    assessment["reference_low"] = low
                    assessment["reference_high"] = high

                break

            assessment["status"] = matched_group
            if matched_group not in ["normal", "optimal", "average", "unknown"]:
                assessment["is_abnormal"] = True

        indicators.append(assessment)

    return {
        "indicators": indicators
    }
