"""Server-side safety gate between OCR extraction and the analysis graph.

The signed token preserves the server-observed confidence for every OCR row.
Corrected medical values intentionally are not signed: manual correction is the
purpose of this gate. Only explicit review evidence controls admission.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from src.config import get_settings
from src.models.ocr_schemas import OCRIndicatorDraft, OCRReviewedIndicator

_TOKEN_PURPOSE = "ocr-review"


class OCRReviewGateError(ValueError):
    """The OCR review evidence is invalid, incomplete, or expired."""


def prepare_review(
    drafts: list[OCRIndicatorDraft],
    *,
    username: str,
) -> tuple[list[OCRIndicatorDraft], str]:
    """Annotate low-confidence rows and issue a short-lived signed review token."""
    settings = get_settings()
    threshold = settings.ocr_low_confidence_threshold
    prepared = [
        draft.model_copy(update={"needs_review": draft.confidence < threshold})
        for draft in drafts
    ]
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.ocr_review_token_expire_minutes
    )
    payload = {
        "purpose": _TOKEN_PURPOSE,
        "sub": username,
        "exp": expires_at,
        "threshold": threshold,
        "drafts": [
            {"draft_id": draft.draft_id, "confidence": draft.confidence}
            for draft in prepared
        ],
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return prepared, token


def validate_review(
    token: str,
    reviewed_indicators: list[OCRReviewedIndicator],
    *,
    username: str,
) -> tuple[list[OCRIndicatorDraft], list[dict]]:
    """Validate review evidence and return graph-safe drafts + included inputs."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise OCRReviewGateError("Phiên xác nhận OCR không hợp lệ hoặc đã hết hạn.") from exc

    if payload.get("purpose") != _TOKEN_PURPOSE:
        raise OCRReviewGateError("Token không thuộc luồng xác nhận OCR.")
    if payload.get("sub") != username:
        raise OCRReviewGateError("Phiên xác nhận OCR không thuộc người dùng hiện tại.")

    threshold = payload.get("threshold")
    signed_rows = payload.get("drafts")
    if not isinstance(threshold, (int, float)) or not isinstance(signed_rows, list):
        raise OCRReviewGateError("Token OCR thiếu dữ liệu kiểm chứng.")

    signed_by_id: dict[str, float] = {}
    for row in signed_rows:
        if not isinstance(row, dict):
            raise OCRReviewGateError("Token OCR có dữ liệu không hợp lệ.")
        draft_id = row.get("draft_id")
        confidence = row.get("confidence")
        if not isinstance(draft_id, str) or not isinstance(confidence, (int, float)):
            raise OCRReviewGateError("Token OCR có dữ liệu không hợp lệ.")
        if draft_id in signed_by_id:
            raise OCRReviewGateError("Token OCR chứa định danh trùng lặp.")
        signed_by_id[draft_id] = float(confidence)

    submitted_ids = [row.draft_id for row in reviewed_indicators]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise OCRReviewGateError("Danh sách xác nhận có dòng OCR trùng lặp.")
    if set(submitted_ids) != set(signed_by_id):
        raise OCRReviewGateError(
            "Phải kiểm tra mọi dòng OCR; không được thêm hoặc bỏ dòng ngoài phiên review."
        )

    drafts: list[OCRIndicatorDraft] = []
    included_inputs: list[dict] = []
    for row in reviewed_indicators:
        confidence = signed_by_id[row.draft_id]
        is_low_confidence = confidence < float(threshold)
        if not row.reviewed:
            raise OCRReviewGateError(f"Chỉ số {row.name} chưa được đối chiếu thủ công.")
        if row.included and is_low_confidence and not row.low_confidence_acknowledged:
            raise OCRReviewGateError(
                f"Chỉ số {row.name} có độ tin cậy thấp và cần xác nhận riêng."
            )

        draft = OCRIndicatorDraft(
            draft_id=row.draft_id,
            name=row.name,
            value=row.value,
            unit=row.unit,
            confidence=confidence,
            needs_review=is_low_confidence,
        )
        drafts.append(draft)
        if row.included:
            included_inputs.append(draft.to_indicator_input())

    if not included_inputs:
        raise OCRReviewGateError("Cần giữ lại ít nhất một chỉ số đã xác nhận để phân tích.")

    return drafts, included_inputs
