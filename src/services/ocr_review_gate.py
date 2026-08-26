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

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal

from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.db import OCRReviewLifecycle
from src.models.ocr_schemas import (
    OCRIndicatorDraft,
    OCRReviewedIndicator,
)
from src.services.reference_repository import (
    ReferenceRepository,
    ReferenceRepositoryError,
)

_TOKEN_PURPOSE = "ocr-review"
OCR_REVIEW_PENDING = "PENDING"
OCR_REVIEW_CONSUMED = "CONSUMED"
OCR_REVIEW_EXPIRED = "EXPIRED"
OCRReviewStatus = Literal["PENDING", "CONSUMED", "EXPIRED", "INVALID", "NONE"]

AMBIGUOUS_ANALYTE_MESSAGE = (
    "Đã nhận diện đây là xét nghiệm Glucose, nhưng chưa đủ thông tin để xác định "
    "đây có phải glucose lúc đói hay không."
)


class OCRReviewGateError(ValueError):
    """OCR review evidence is invalid, incomplete, forged, or expired."""


@dataclass(frozen=True)
class OCRReviewState:
    review_id: str | None
    status: OCRReviewStatus
    pending: bool


@lru_cache(maxsize=1)
def _get_reference_repository() -> ReferenceRepository:
    return ReferenceRepository.from_default_files()


def _is_supported_analyte(name: str) -> bool:
    try:
        repository = _get_reference_repository()
    except ReferenceRepositoryError:
        return True

    canonical = repository.resolve_analyte(name)
    return canonical in repository.approved_analytes


def _unsupported_reason(name: str) -> str:
    try:
        resolution = _get_reference_repository().resolve_analyte_result(name)
    except ReferenceRepositoryError:
        return "Chỉ số này hiện tại chưa được hỗ trợ."
    if resolution.status == "AMBIGUOUS":
        return AMBIGUOUS_ANALYTE_MESSAGE
    return "Chỉ số này hiện tại chưa được hỗ trợ."


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def review_token_expires_at() -> datetime:
    settings = get_settings()
    return _utcnow() + timedelta(minutes=settings.ocr_review_token_expire_minutes)


def _identity_values(current_user: object) -> dict[str, object]:
    username = getattr(current_user, "username", None)
    role = getattr(current_user, "role", None)
    if not isinstance(username, str) or not username or not isinstance(role, str) or not role:
        raise OCRReviewGateError("Phiên đăng nhập không hợp lệ.")

    session_id = getattr(current_user, "session_id", None)
    account_key = getattr(current_user, "user_id", None)
    if role == "guest":
        if not isinstance(session_id, str) or not session_id:
            raise OCRReviewGateError("Phiên khách không hợp lệ.")
        account_key = None
    elif not isinstance(account_key, int):
        raise OCRReviewGateError("Phiên đăng nhập không hợp lệ.")
    else:
        session_id = None

    return {
        "owner_subject": username,
        "owner_role": role,
        "owner_user_id": account_key,
        "owner_session_id": session_id,
    }


def _owner_predicates(current_user: object) -> list:
    values = _identity_values(current_user)
    predicates = [
        OCRReviewLifecycle.owner_subject == values["owner_subject"],
        OCRReviewLifecycle.owner_role == values["owner_role"],
    ]
    if values["owner_role"] == "guest":
        predicates.append(OCRReviewLifecycle.owner_session_id == values["owner_session_id"])
    else:
        predicates.append(OCRReviewLifecycle.owner_user_id == values["owner_user_id"])
    return predicates


def create_review_lifecycle(
    db: Session,
    *,
    current_user: object,
    expires_at: datetime | None = None,
) -> OCRReviewLifecycle:
    values = _identity_values(current_user)
    lifecycle = OCRReviewLifecycle(
        review_id=secrets.token_urlsafe(32),
        expires_at=expires_at or review_token_expires_at(),
        status=OCR_REVIEW_PENDING,
        **values,
    )
    db.add(lifecycle)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(lifecycle)
    return lifecycle


def _effective_status(lifecycle: OCRReviewLifecycle, *, now: datetime | None = None) -> OCRReviewStatus:
    if lifecycle.status == OCR_REVIEW_CONSUMED:
        return OCR_REVIEW_CONSUMED
    current_time = now or _utcnow()
    if _as_aware_utc(lifecycle.expires_at) <= _as_aware_utc(current_time):
        return OCR_REVIEW_EXPIRED
    if lifecycle.status == OCR_REVIEW_PENDING:
        return OCR_REVIEW_PENDING
    return "INVALID"


def get_current_review_state(db: Session, *, current_user: object) -> OCRReviewState:
    lifecycle = db.scalar(
        select(OCRReviewLifecycle)
        .where(
            *_owner_predicates(current_user),
            OCRReviewLifecycle.status == OCR_REVIEW_PENDING,
        )
        .order_by(OCRReviewLifecycle.created_at.desc())
        .limit(1)
    )
    if lifecycle is None:
        return OCRReviewState(review_id=None, status="NONE", pending=False)

    status = _effective_status(lifecycle)
    return OCRReviewState(
        review_id=lifecycle.review_id,
        status=status,
        pending=status == OCR_REVIEW_PENDING,
    )


def has_pending_review(db: Session, *, current_user: object) -> bool:
    return get_current_review_state(db, current_user=current_user).pending


def _decode_review_payload(token: str, *, username: str) -> dict:
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

    if payload.get("purpose") != _TOKEN_PURPOSE:
        raise OCRReviewGateError(
            "Token không thuộc luồng xác nhận OCR."
        )

    if payload.get("sub") != username:
        raise OCRReviewGateError(
            "Phiên xác nhận OCR không thuộc người dùng hiện tại."
        )

    return payload


def verify_review_lifecycle(db: Session, *, token: str, current_user: object) -> OCRReviewLifecycle:
    payload = _decode_review_payload(token, username=str(getattr(current_user, "username", "")))
    review_id = payload.get("review_id")
    if not isinstance(review_id, str) or not review_id:
        raise OCRReviewGateError("Phiên xác nhận OCR không hợp lệ hoặc đã hết hạn.")

    lifecycle = db.scalar(
        select(OCRReviewLifecycle).where(
            OCRReviewLifecycle.review_id == review_id,
            *_owner_predicates(current_user),
        )
    )
    if lifecycle is None or _effective_status(lifecycle) != OCR_REVIEW_PENDING:
        raise OCRReviewGateError("Phiên xác nhận OCR không hợp lệ hoặc đã hết hạn.")
    return lifecycle


def consume_review_lifecycle(db: Session, *, token: str, current_user: object) -> OCRReviewLifecycle:
    lifecycle = verify_review_lifecycle(db, token=token, current_user=current_user)
    consumed_at = _utcnow()
    result = db.execute(
        update(OCRReviewLifecycle)
        .where(
            OCRReviewLifecycle.id == lifecycle.id,
            OCRReviewLifecycle.status == OCR_REVIEW_PENDING,
            OCRReviewLifecycle.consumed_at.is_(None),
            OCRReviewLifecycle.expires_at > consumed_at,
        )
        .values(status=OCR_REVIEW_CONSUMED, consumed_at=consumed_at)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise OCRReviewGateError("Phiên xác nhận OCR không hợp lệ hoặc đã hết hạn.")
    db.commit()
    db.refresh(lifecycle)
    return lifecycle


def prepare_review(
    drafts: list[OCRIndicatorDraft],
    *,
    username: str,
    source_image: str = "",
    review_id: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[list[OCRIndicatorDraft], str]:
    """Annotate OCR rows and issue a short-lived signed review token.

    The token preserves only server-observed provenance and review-control
    metadata. Medical values/name/unit remain editable by the user during
    manual review.
    """

    settings = get_settings()
    threshold = settings.ocr_low_confidence_threshold

    prepared = []
    for draft in drafts:
        supported = _is_supported_analyte(draft.name)
        prepared.append(
            draft.model_copy(
                update={
                    "needs_review": supported and draft.confidence < threshold,
                    "supported": supported,
                    "unsupported_reason": (
                        ""
                        if supported
                        else _unsupported_reason(draft.name)
                    ),
                }
            )
        )

    expires_at = expires_at or review_token_expires_at()

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
    if review_id is not None:
        payload["review_id"] = review_id

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

    payload = _decode_review_payload(token, username=username)

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

        supported = _is_supported_analyte(row.name)
        is_low_confidence = supported and confidence < float(threshold)

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
            supported=supported,
            unsupported_reason=(
                "" if supported else _unsupported_reason(row.name)
            ),
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
