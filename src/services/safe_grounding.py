"""Build a patient-facing-safe view of approved retrieval grounding.

The source corpus remains immutable. This module only creates copied chunks
whose prose has been filtered with the existing medical safety policy before
the text is sent to an explanation or rewrite model.
"""

from __future__ import annotations

import re
from typing import cast

from src.agents.state import RetrievedChunk
from src.services.medical_safety_validator import MedicalSafetyValidator

_SEGMENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")


def filter_safe_grounding_text(
    text: str,
    *,
    validator: MedicalSafetyValidator | None = None,
) -> str:
    """Remove unsafe complete prose segments without inventing replacements."""
    active_validator = validator or MedicalSafetyValidator()
    segments = [
        segment.strip()
        for segment in _SEGMENT_BOUNDARY.split(str(text or "").strip())
        if segment.strip()
    ]
    return " ".join(
        segment for segment in segments if not active_validator.validate(segment)
    )


def build_safe_grounding_view(
    chunks: list[RetrievedChunk],
    *,
    validator: MedicalSafetyValidator | None = None,
) -> list[RetrievedChunk]:
    """Copy chunks with safe text while preserving all provenance metadata."""
    active_validator = validator or MedicalSafetyValidator()
    safe_chunks: list[RetrievedChunk] = []
    for chunk in chunks:
        safe_text = filter_safe_grounding_text(
            str(chunk.get("text", "")),
            validator=active_validator,
        )
        if not safe_text:
            continue
        safe_chunks.append(cast(RetrievedChunk, {**chunk, "text": safe_text}))
    return safe_chunks
