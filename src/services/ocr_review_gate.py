"""Server-side safety gate between OCR extraction and the analysis graph.

The signed token preserves server-observed OCR provenance:
- confidence
- raw_text
- source_image filename

Corrected medical values intentionally are NOT signed because manual correction
is the purpose of this review gate. Only explicit review evidence controls
admission to the analysis graph.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from src.config import get_settings
from src.models.ocr_schemas import (
    OCRIndicatorDraft,
    OCRReviewedIndicator,
)

_TOKEN_PURPOSE = "ocr-review"


class OCRReviewGateError(ValueError):
    """OCR review evidence is invalid, incomplete, forged, or expired."""


def prepare_review(
    drafts: list[OCRIndicatorDraft],
    *,
    username: str,
    source_image: str = "",
) -> tuple[list[OCRIndicatorDraft], str]:
    """Annotate OCR rows and issue a short-lived signed review token.

    The token preserves only server-observed provenance and review-control
    metadata. Medical values/name/unit remain editable by the user during
    manual review.
    """

    settings = get_settings()
    threshold = settings.ocr_low_confidence_threshold

    prepared = [
        draft.model_copy(
            update={
                "needs_review": draft.confidence < threshold,
            }
        )
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

        # Tên file do server thấy ở bước upload.
        # Không phải path và không chứa image bytes.
        "source_image": source_image,

        "drafts": [
            {
                "draft_id": draft.draft_id,

                # Confidence phải giữ nguyên giá trị Vision server trả về.
                "confidence": draft.confidence,

                # Raw OCR text cũng là provenance server-observed.
                # User được sửa name/value/unit nhưng không được giả raw_text.
                "raw_text": draft.raw_text,
            }
            for draft in prepared
        ],
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return prepared, token


def validate_review(
    token: str,
    reviewed_indicators: list[OCRReviewedIndicator],
    *,
    username: str,
) -> tuple[
    list[OCRIndicatorDraft],
    list[dict],
    str,
]:
    """Validate review evidence.

    Returns:
        drafts:
            OCR drafts after user review, while preserving signed confidence
            and raw_text from the original server OCR result.

        included_inputs:
            Only rows the user explicitly kept for analysis.

        source_image:
            Signed source filename originating from /ocr/upload.
    """

    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise OCRReviewGateError(
            "Phiên xác nhận OCR không hợp lệ hoặc đã hết hạn."
        ) from exc

    # ------------------------------------------------------------------
    # Token identity / purpose
    # ------------------------------------------------------------------

    if payload.get("purpose") != _TOKEN_PURPOSE:
        raise OCRReviewGateError(
            "Token không thuộc luồng xác nhận OCR."
        )

    if payload.get("sub") != username:
        raise OCRReviewGateError(
            "Phiên xác nhận OCR không thuộc người dùng hiện tại."
        )

    # ------------------------------------------------------------------
    # Signed review metadata
    # ------------------------------------------------------------------

    threshold = payload.get("threshold")
    signed_rows = payload.get("drafts")
    source_image = payload.get("source_image", "")

    if (
        not isinstance(threshold, (int, float))
        or not isinstance(signed_rows, list)
    ):
        raise OCRReviewGateError(
            "Token OCR thiếu dữ liệu kiểm chứng."
        )

    if not isinstance(source_image, str):
        raise OCRReviewGateError(
            "Token OCR chứa thông tin nguồn không hợp lệ."
        )

    # draft_id ->
    # {
    #     confidence: float,
    #     raw_text: str,
    # }
    signed_by_id: dict[str, dict[str, float | str]] = {}

    for signed_row in signed_rows:
        if not isinstance(signed_row, dict):
            raise OCRReviewGateError(
                "Token OCR có dữ liệu không hợp lệ."
            )

        draft_id = signed_row.get("draft_id")
        confidence = signed_row.get("confidence")

        # Backward-compatible default cho token/test cũ.
        raw_text = signed_row.get("raw_text", "")

        if (
            not isinstance(draft_id, str)
            or not isinstance(confidence, (int, float))
            or not isinstance(raw_text, str)
        ):
            raise OCRReviewGateError(
                "Token OCR có dữ liệu không hợp lệ."
            )

        if draft_id in signed_by_id:
            raise OCRReviewGateError(
                "Token OCR chứa định danh trùng lặp."
            )

        signed_by_id[draft_id] = {
            "confidence": float(confidence),
            "raw_text": raw_text,
        }

    # ------------------------------------------------------------------
    # Ensure client reviewed exactly the rows issued by server
    # ------------------------------------------------------------------

    submitted_ids = [
        row.draft_id
        for row in reviewed_indicators
    ]

    if len(submitted_ids) != len(set(submitted_ids)):
        raise OCRReviewGateError(
            "Danh sách xác nhận có dòng OCR trùng lặp."
        )

    if set(submitted_ids) != set(signed_by_id):
        raise OCRReviewGateError(
            "Phải kiểm tra mọi dòng OCR; không được thêm hoặc bỏ dòng "
            "ngoài phiên review."
        )

    # ------------------------------------------------------------------
    # Build graph-safe drafts
    # ------------------------------------------------------------------

    drafts: list[OCRIndicatorDraft] = []
    included_inputs: list[dict] = []

    for row in reviewed_indicators:
        signed = signed_by_id[row.draft_id]

        confidence = float(signed["confidence"])
        raw_text = str(signed["raw_text"])

        is_low_confidence = (
            confidence < float(threshold)
        )

        if not row.reviewed:
            raise OCRReviewGateError(
                f"Chỉ số {row.name} chưa được đối chiếu thủ công."
            )

        if (
            row.included
            and is_low_confidence
            and not row.low_confidence_acknowledged
        ):
            raise OCRReviewGateError(
                f"Chỉ số {row.name} có độ tin cậy thấp "
                "và cần xác nhận riêng."
            )

        # name/value/unit lấy từ dữ liệu người dùng đã review.
        #
        # confidence/raw_text lấy từ signed server provenance,
        # client không thể thay đổi.
        draft = OCRIndicatorDraft(
            draft_id=row.draft_id,
            name=row.name,
            value=row.value,
            unit=row.unit,
            confidence=confidence,
            raw_text=raw_text,
            needs_review=is_low_confidence,
        )

        drafts.append(draft)

        if row.included:
            included_inputs.append(
                draft.to_indicator_input()
            )

    if not included_inputs:
        raise OCRReviewGateError(
            "Cần giữ lại ít nhất một chỉ số đã xác nhận để phân tích."
        )

    return (
        drafts,
        included_inputs,
        source_image,
    )
