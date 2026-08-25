"""Corpus Validator for Development and Release Gating."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.services.analyte_resolver import (
    ANALYTE_RULE_TYPES,
    FROZEN_CLINICAL_RULE_BANDS,
    LOCKED_35_ANALYTES,
    VALID_NOTE_TYPES,
    canonical_analyte_id,
)
from src.services.corpus_builder import build_corpus_chunks

PROHIBITED_PLACEHOLDERS = (
    "TODO",
    "TBD",
    "COMING SOON",
    "CHƯA CÓ DỮ LIỆU",
    "CHUA CO DU LIEU",
    "ĐANG CẬP NHẬT",
    "DANG CAP NHAT",
    "PLACEHOLDER",
)


@dataclass
class ValidationReport:
    is_valid: bool
    mode: str
    analyte_count: int
    chunk_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    covered_analytes: list[str] = field(default_factory=list)
    missing_analytes: list[str] = field(default_factory=list)


class CorpusValidator:
    """Validates medical knowledge corpus structure against frozen contracts."""

    @classmethod
    def validate(
        cls,
        entries: list[dict[str, Any]],
        *,
        mode: str = "development",
    ) -> ValidationReport:
        """Validate corpus entries in 'development' or 'release' mode."""
        errors: list[str] = []
        warnings: list[str] = []

        seen_analyte_ids: set[str] = set()
        seen_canonical_names: set[str] = set()

        # 1. Analyte-level validation
        for idx, entry in enumerate(entries):
            canonical_name = str(entry.get("canonical_name") or entry.get("name") or "").strip()
            if not canonical_name:
                errors.append(f"Entry #{idx} missing 'canonical_name' or 'name'")
                continue

            analyte_id = str(entry.get("analyte_id") or canonical_analyte_id(canonical_name)).strip()
            expected_aid = canonical_analyte_id(canonical_name)

            # Gate 1: Belongs to locked 35
            if canonical_name not in LOCKED_35_ANALYTES:
                errors.append(f"Entry '{canonical_name}' (id: '{analyte_id}') is not in the LOCKED 35 registry")

            # Gate 2: Slug matches canonical resolver output
            if analyte_id != expected_aid:
                errors.append(
                    f"Analyte '{canonical_name}' has mismatched analyte_id '{analyte_id}' (expected '{expected_aid}')"
                )

            # Gate 3: Rule type check
            expected_rule_type = ANALYTE_RULE_TYPES.get(analyte_id)
            actual_rule_type = entry.get("rule_type")
            if actual_rule_type and expected_rule_type and actual_rule_type != expected_rule_type:
                errors.append(
                    f"Analyte '{canonical_name}' rule_type '{actual_rule_type}' contradicts frozen medical contract '{expected_rule_type}'"
                )

            if analyte_id in seen_analyte_ids:
                errors.append(f"Duplicate analyte entry detected for '{analyte_id}'")
            seen_analyte_ids.add(analyte_id)
            seen_canonical_names.add(canonical_name)

        # Build chunks
        try:
            chunks = build_corpus_chunks(entries)
        except Exception as exc:
            errors.append(f"Failed to build chunks from corpus: {exc}")
            chunks = []

        # 2. Chunk-level validation
        seen_chunk_ids: set[str] = set()

        for chunk in chunks:
            # Gate 4: Valid note_type
            if chunk.note_type not in VALID_NOTE_TYPES:
                errors.append(f"Chunk '{chunk.chunk_id}' has illegal note_type '{chunk.note_type}'")

            # Gate 5 & 6 & 7: Band notes validation
            if chunk.note_type == "band_note":
                if not chunk.band_id:
                    errors.append(f"Chunk '{chunk.chunk_id}' is a band_note but missing 'band_id'")
                else:
                    if chunk.rule_type not in {"BAND", "CDL"}:
                        errors.append(
                            f"Analyte '{chunk.analyte_id}' has rule_type '{chunk.rule_type}' but defines band_note '{chunk.band_id}' (prohibited)"
                        )
                    allowed_bands = FROZEN_CLINICAL_RULE_BANDS.get(chunk.analyte_id, ())
                    if chunk.band_id not in allowed_bands:
                        errors.append(
                            f"Analyte '{chunk.analyte_id}' uses unknown band_id '{chunk.band_id}' (allowed: {allowed_bands})"
                        )

            # Gate 8: Source ID presence
            if not chunk.source_id or not chunk.source_id.strip():
                errors.append(f"Chunk '{chunk.chunk_id}' has empty source_id")

            # Gate 9: Chunk ID uniqueness
            if chunk.chunk_id in seen_chunk_ids:
                errors.append(f"Duplicate chunk_id detected: '{chunk.chunk_id}'")
            seen_chunk_ids.add(chunk.chunk_id)

            # Gate 10: Non-empty text
            if not chunk.text or not chunk.text.strip():
                errors.append(f"Chunk '{chunk.chunk_id}' contains empty text")

            # Gate 11: Placeholder rejection
            text_upper = chunk.text.upper()
            for placeholder in PROHIBITED_PLACEHOLDERS:
                if placeholder in text_upper:
                    errors.append(f"Chunk '{chunk.chunk_id}' contains prohibited placeholder text: '{placeholder}'")
                    break

            # Gate 12: Flat Chroma metadata scalar validation
            meta = chunk.to_chroma_metadata()
            for k, v in meta.items():
                if not isinstance(v, (str, int, float, bool)):
                    errors.append(
                        f"Chunk '{chunk.chunk_id}' metadata key '{k}' has unsupported type '{type(v).__name__}' (must be scalar)"
                    )

        # 3. Release mode checks
        covered = [name for name in LOCKED_35_ANALYTES if name in seen_canonical_names]
        missing = [name for name in LOCKED_35_ANALYTES if name not in seen_canonical_names]

        if mode.lower() == "release":
            if len(covered) != 35 or missing:
                errors.append(
                    f"Release validation failed: Exactly 35 analytes required, found {len(covered)}/35. Missing: {missing}"
                )

        return ValidationReport(
            is_valid=len(errors) == 0,
            mode=mode,
            analyte_count=len(seen_analyte_ids),
            chunk_count=len(chunks),
            errors=errors,
            warnings=warnings,
            covered_analytes=covered,
            missing_analytes=missing,
        )
