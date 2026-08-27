import logging
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from src.agents.state import AgentState, IndicatorAssessment
from src.services.analyte_catalog import AnalyteCatalogError, get_analyte_catalog
from src.services.measurement_conversion import validate_numeric_measurement
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError

logger = logging.getLogger(__name__)


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
        "rule_type": None,
        "band_id": None,
        "upper_operator": None,
        "evaluation_reason": None,
    }


def _parse_value(value) -> Decimal | None:
    try:
        return validate_numeric_measurement(value)
    except (ValueError, TypeError):
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


def _sources_from_catalog_or_rule(catalog_sources: tuple[str, ...], rule: dict) -> list[str]:
    if catalog_sources:
        return list(catalog_sources)
    source_url = rule.get("source_url")
    return [source_url] if source_url else []


def _classify(
    value: Decimal,
    lower: Decimal | None,
    upper: Decimal | None,
    rule_type: str | None = None,
    upper_operator: str | None = None,
) -> str:
    if value < Decimal("0"):
        return "unknown"
    if rule_type == "ONE_SIDED_LIMIT":
        if upper is None or upper_operator not in {"<", "<=", ">", ">="}:
            return "unknown"
        if upper_operator == "<":
            return "normal" if value < upper else "high"
        if upper_operator == "<=":
            return "normal" if value <= upper else "high"
        if upper_operator == ">":
            return "normal" if value > upper else "low"
        if upper_operator == ">=":
            return "normal" if value >= upper else "low"
        return "unknown"
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
    integrity_by_index = {
        int(result["index"]): result
        for result in state.get("input_integrity_results", [])
        if isinstance(result, dict) and "index" in result
    }

    try:
        repository = get_reference_repository()
    except ReferenceRepositoryError as exc:
        logger.error("Reference repository unavailable: %s", exc)
        repository = None
    try:
        catalog = get_analyte_catalog()
    except AnalyteCatalogError as exc:
        logger.error("Analyte catalog unavailable: %s", exc)
        catalog = None

    for index, ind in enumerate(raw_indicators):
        name = ind.get("name", "")
        val = ind.get("value")
        unit = ind.get("unit", "")

        assessment = _unknown_assessment(name, val, unit)
        integrity = integrity_by_index.get(index)
        if integrity is not None:
            assessment["input_integrity_status"] = integrity.get("status", "VALID")
            assessment["input_integrity_reason_code"] = integrity.get("reason_code")
            assessment["input_integrity_message"] = integrity.get("message", "")
            assessment["input_integrity_rule_id"] = integrity.get("rule_id")
            assessment["input_integrity_source_id"] = integrity.get("source_id")
            assessment["analyte_canonical"] = integrity.get("canonical_analyte")
            assessment["canonical_value"] = integrity.get("observed_value")
            assessment["canonical_unit"] = integrity.get("canonical_unit")
            if integrity.get("status") == "NEED_REVIEW":
                assessment["evaluation_reason"] = integrity.get("reason_code")
                assessment["explanation"] = integrity.get("message", "")
                indicators.append(assessment)
                continue
        numeric_value = _parse_value(val)
        if repository is None or numeric_value is None:
            indicators.append(assessment)
            continue

        result = repository.select_rule(
            analyte=name,
            unit=unit,
            value=numeric_value,
            patient_gender=patient_gender,
            patient_age=patient_age,
        )
        if not result.matched or not result.rule:
            assessment["evaluation_reason"] = result.reason
            indicators.append(assessment)
            continue

        lower = _parse_rule_bound(result.rule.get("range_lower"))
        upper = _parse_rule_bound(result.rule.get("range_upper"))
        ref_type = result.rule.get("reference_type")
        upper_op = result.rule.get("upper_operator")
        classification_value = (
            result.comparison_value
            if result.comparison_value is not None
            else numeric_value
        )
        status = _classify(
            classification_value,
            lower,
            upper,
            rule_type=ref_type,
            upper_operator=upper_op,
        )
        if status == "unknown":
            indicators.append(assessment)
            continue

        definition = (
            catalog.resolve(result.canonical_analyte or name)
            if catalog is not None
            else None
        )
        if definition is not None:
            assessment["analyte_id"] = definition.analyte_id
        assessment["reference_low"] = _json_number_or_none(lower)
        assessment["reference_high"] = _json_number_or_none(upper)
        assessment["status"] = status
        assessment["is_abnormal"] = status in {"low", "high"}
        assessment["explanation"] = definition.curated_explanation if definition else ""
        assessment["sources"] = _sources_from_catalog_or_rule(
            definition.sources if definition else (),
            result.rule,
        )
        assessment["rule_type"] = ref_type
        assessment["band_id"] = result.rule.get("band_id")
        assessment["upper_operator"] = upper_op
        source_url = str(result.rule.get("source_url") or "").strip()
        if source_url:
            assessment["reference_range_source"] = {
                "source_id": str(result.rule.get("rule_id") or ""),
                "title": str(result.rule.get("source_title") or ""),
                "organization": str(result.rule.get("source_organization") or ""),
                "url": source_url,
                "section_or_context": str(result.rule.get("source_section") or "").strip() or None,
                "analyte": str(result.canonical_analyte or name),
                "note_type": "reference_range",
            }

        indicators.append(assessment)

    return {
        "indicators": indicators
    }
