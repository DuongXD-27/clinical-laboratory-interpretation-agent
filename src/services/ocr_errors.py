"""Stable, privacy-safe OCR failure taxonomy for API/UI handling."""

from __future__ import annotations

from typing import Final

OCR_ERROR_HEADER: Final = "X-OCR-Error-Code"

UNSUPPORTED_FILE: Final = "UNSUPPORTED_FILE"
FILE_TOO_LARGE: Final = "FILE_TOO_LARGE"
IMAGE_UNREADABLE: Final = "IMAGE_UNREADABLE"
NO_INDICATORS_FOUND: Final = "NO_INDICATORS_FOUND"
PROVIDER_UNAVAILABLE: Final = "PROVIDER_UNAVAILABLE"
REVIEW_REQUIRED: Final = "REVIEW_REQUIRED"
NO_SUPPORTED_ANALYTES: Final = "NO_SUPPORTED_ANALYTES"
OCR_EXTRACTION_FAILED: Final = "OCR_EXTRACTION_FAILED"


def headers(reason_code: str) -> dict[str, str]:
    return {OCR_ERROR_HEADER: reason_code}


def image_processor_reason(message: str) -> str:
    normalized = message.casefold()
    if "vượt giới hạn" in normalized:
        return FILE_TOO_LARGE
    if "định dạng không hỗ trợ" in normalized:
        return UNSUPPORTED_FILE
    return IMAGE_UNREADABLE
