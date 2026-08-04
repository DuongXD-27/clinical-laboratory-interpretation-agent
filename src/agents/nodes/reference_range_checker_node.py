import json
import logging
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

from src.agents.state import AgentState, IndicatorAssessment
from src.config import get_settings
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError

logger = logging.getLogger(__name__)

def load_explanations() -> dict:
    get_settings()
    config_path = Path("data/reference/explanations.json")
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
            return {item["indicator"].lower(): item for item in data}
    return {}

EXPLANATIONS_DB = load_explanations()


@lru_cache(maxsize=1)
def get_reference_repository() -> ReferenceRepository:
    return ReferenceRepository.from_default_files()


def _unknown_assessment(name: str, val, unit: str) -> IndicatorAssessment:
    return {
        "name": name,
        "value": val,
        "unit": unit,
        "reference_low": None,
        "reference_high": None,
        "status": "unknown",
        "is_abnormal": False,
        "is_critical": False,
        "explanation": "",
        "sources": [],
    }


def _parse_value(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_rule_bound(value) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _json_number_or_none(value: Decimal | None):
    if value is None:
        return None
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(format(normalized, "f"))


def _find_explanation(name: str, canonical_analyte: str | None) -> dict:
    candidates = [name.lower()]
    if canonical_analyte:
        candidates.append(canonical_analyte.lower())
    for key in candidates:
        if key in EXPLANATIONS_DB:
            return EXPLANATIONS_DB[key]
    return {}


def _sources_from_explanation_or_rule(explanation_info: dict, rule: dict) -> list[str]:
    sources = explanation_info.get("sources", [])
    if sources:
        return sources
    source_url = rule.get("source_url")
    return [source_url] if source_url else []


def _classify(value: Decimal, lower: Decimal | None, upper: Decimal | None) -> str:
    if lower is not None and upper is not None:
        if value < lower:
            return "low"
        if value > upper:
            return "high"
        return "normal"
    if lower is None and upper is not None:
        if value > upper:
            return "high"
        return "normal"
    if lower is not None and upper is None:
        if value < lower:
            return "low"
        return "normal"
    return "unknown"

async def reference_range_checker_node(state: AgentState) -> dict:
    """Kiểm tra giá trị chỉ số dựa trên khoảng tham chiếu để phân loại trạng thái."""
    raw_indicators = state.get("raw_indicators", [])
    patient_gender = state.get("patient_gender", "A")
    patient_age = state.get("patient_age")
    indicators: list[IndicatorAssessment] = []

    try:
        repository = get_reference_repository()
    except ReferenceRepositoryError as exc:
        logger.error("Reference repository unavailable: %s", exc)
        repository = None

    for ind in raw_indicators:
        name = ind.get("name", "")
        val = ind.get("value")
        unit = ind.get("unit", "")

        assessment = _unknown_assessment(name, val, unit)
        numeric_value = _parse_value(val)
        if repository is None or numeric_value is None:
            indicators.append(assessment)
            continue

        result = repository.select_rule(
            analyte=name,
            unit=unit,
            patient_gender=patient_gender,
            patient_age=patient_age,
        )
        if not result.matched or not result.rule:
            indicators.append(assessment)
            continue

        lower = _parse_rule_bound(result.rule.get("range_lower"))
        upper = _parse_rule_bound(result.rule.get("range_upper"))
        status = _classify(numeric_value, lower, upper)
        if status == "unknown":
            indicators.append(assessment)
            continue

        explanation_info = _find_explanation(name, result.canonical_analyte)
        assessment["reference_low"] = _json_number_or_none(lower)
        assessment["reference_high"] = _json_number_or_none(upper)
        assessment["status"] = status
        assessment["is_abnormal"] = status in {"low", "high"}
        assessment["explanation"] = explanation_info.get("simple_explanation", "")
        assessment["sources"] = _sources_from_explanation_or_rule(explanation_info, result.rule)

        indicators.append(assessment)

    return {
        "indicators": indicators
    }
