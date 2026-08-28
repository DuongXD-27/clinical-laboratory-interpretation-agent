"""Deterministic output guardrail shared by the canonical chat runtime."""

from __future__ import annotations

import re
import unicodedata

from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    DataPayload,
    DataType,
    IntentEnum,
    OrchestratorResponse,
    ReasonCode,
    ResponseStatus,
)
from src.services.medical_safety_validator import MedicalSafetyValidator


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", plain))


_UNGROUNDED_SYMPTOM_RE = re.compile(
    r"\b(?:ban|em|nguoi benh)\s+(?:co the\s+)?(?:(?:dang|cam thay|gap|bi|co|mac|xuat hien|trieu chung)\s+)*(?:kho tho|met moi|chong mat|dau nguc|hoa mat|buon non|sot|co giat|ngat|dau dau|tuc nguc|danh trong nguc)\b",
    re.IGNORECASE,
)
_UNGROUNDED_DIAGNOSIS_RE = re.compile(
    r"\b(?:ban|em|nguoi benh)\s+(?:co the\s+)?(?:(?:dang|chac chan|bi|mac|mac phai|chan doan|co nguy co|nguy co cao mac|nguy co|dau hieu cua)\s+)+(?:thieu mau|benh tim|tieu duong|dai thao duong|ung thu|suy than|suy gan|nhiem trung|tai bien|dot quy|viem gan|xo gan|da hong cau)\b",
    re.IGNORECASE,
)
_UNGROUNDED_PHYSIO_RE = re.compile(
    r"\b(?:"
    r"co the (?:ban|nguoi benh)?\s*(?:dang |duoc )?(?:cung cap oxy|thieu oxy|thieu mau|phuc hoi|hoi phuc|on dinh|khoe manh)"
    r"|khien co the (?:ban )?(?:bi )?(?:thieu|met|suy|giam|thieu oxy)"
    r"|lam co the (?:ban )?(?:bi )?(?:thieu|met|suy|giam|thieu oxy)"
    r"|chuc nang (?:gan|than|tim|phoi|tao mau|mien dich) cua ban"
    r"|cho thay (?:co the|suc khoe|ban) (?:dang |da )?(?:phuc hoi|tien trien tot|hoan toan khoe|khong co benh)"
    r"|(?:ban|nguoi benh) (?:hoan toan khoe manh|khong co benh)"
    r"|(?:ban|nguoi benh) (?:can|nen|phai) (?:uong|dung|tiem|bo sung|dieu tri|su dung thuoc|dung thuoc|mua thuoc|ngung thuoc)"
    r")\b",
    re.IGNORECASE,
)


def _validate_patient_grounding(message: str, user_message: str | None = None) -> bool:
    if not message:
        return True
    normalized_msg = _normalize(message)
    normalized_user = _normalize(user_message or "")
    if _UNGROUNDED_PHYSIO_RE.search(normalized_msg) or _UNGROUNDED_DIAGNOSIS_RE.search(normalized_msg):
        return False

    match_symptom = _UNGROUNDED_SYMPTOM_RE.search(normalized_msg)
    if match_symptom:
        symptom_keywords = (
            "kho tho",
            "met moi",
            "chong mat",
            "dau nguc",
            "hoa mat",
            "buon non",
            "sot",
            "co giat",
            "ngat",
            "dau dau",
            "tuc nguc",
            "danh trong nguc",
        )
        matched_tokens = [token for token in symptom_keywords if token in match_symptom.group(0)]
        if not all(symptom in normalized_user for symptom in matched_tokens):
            return False
    return True


def _message_contradicts_canonical_data(message: str, data: DataPayload) -> bool:
    normalized = _normalize(message)
    if not normalized or not isinstance(data, AnalysisDataPayload) or not data.indicators:
        return False

    critical_count = len(data.critical_alerts) + sum(
        1
        for indicator in data.indicators
        if getattr(indicator, "is_critical", False) or getattr(indicator, "critical_status", None)
    )
    abnormal_count = sum(
        1
        for indicator in data.indicators
        if str(indicator.status).casefold() in {"high", "low"}
        and not getattr(indicator, "is_critical", False)
        and not getattr(indicator, "critical_status", None)
    )
    normal_count = sum(
        1
        for indicator in data.indicators
        if str(indicator.status).casefold() == "normal" and not getattr(indicator, "is_critical", False)
    )
    total = len(data.indicators)

    if normal_count == total and any(
        term in normalized for term in ("nguy kich", "critical", "cao", "thap", "bat thuong")
    ):
        return True
    if normal_count == 0 and (abnormal_count > 0 or critical_count > 0):
        if "tat ca binh thuong" in normalized or "hoan toan binh thuong" in normalized:
            return True
        if "binh thuong" in normalized and not any(
            term in normalized for term in ("cao", "thap", "nguy kich", "bat thuong", "ngoai", "ngoai khoang")
        ):
            return True
    return bool(
        critical_count > 0 and ("hoan toan binh thuong" in normalized or "khong co gi bat thuong" in normalized)
    )


def _guardrail_blocked_response(
    intent: IntentEnum,
    message: str = "Nội dung phản hồi không vượt qua kiểm duyệt an toàn.",
) -> OrchestratorResponse:
    return OrchestratorResponse(
        intent=intent,
        status=ResponseStatus.BLOCKED,
        message=message,
        data_type=DataType.BLOCKED,
        data=BlockedPayload(
            safety_notice=message,
            disclaimer="Thông tin này chỉ mang tính giáo dục và không thay thế tư vấn y khoa.",
            reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        ),
        reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        suggested_actions=[],
        sources=[],
        safety_notice=message,
    )


def enforce_final_response(
    response: OrchestratorResponse,
    user_message: str | None = None,
) -> OrchestratorResponse:
    """Validate schema, medical safety, canonical facts, and patient grounding."""

    try:
        validated = OrchestratorResponse.model_validate(response.model_dump())
    except Exception:
        return _guardrail_blocked_response(response.intent)

    if MedicalSafetyValidator().validate(validated.message):
        return _guardrail_blocked_response(validated.intent)
    if _message_contradicts_canonical_data(validated.message, validated.data):
        return _guardrail_blocked_response(validated.intent)
    if not _validate_patient_grounding(validated.message, user_message):
        return _guardrail_blocked_response(validated.intent)
    return validated


__all__ = ["enforce_final_response"]
