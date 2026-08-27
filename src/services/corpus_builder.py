"""Fine-grained Corpus Chunk Builder and metadata normalizer."""

from __future__ import annotations

import logging
from typing import Any

from src.models.corpus_schemas import CorpusAnalyteRecord, CorpusChunk, CorpusSourceRecord, RuleType
from src.services.analyte_resolver import ANALYTE_RULE_TYPES, canonical_analyte_id

logger = logging.getLogger(__name__)


def generate_chunk_id(
    analyte_id: str,
    note_type: str,
    source_id: str,
    band_id: str | None = None,
) -> str:
    """Generate a deterministic, source-reorder safe chunk ID.

    Format:
        BAND note: {analyte_id}::band_note::{band_id}::{source_id}
        Other note: {analyte_id}::{note_type}::{source_id}
    """
    clean_aid = canonical_analyte_id(analyte_id)
    clean_sid = str(source_id).strip()
    clean_ntype = str(note_type).strip()

    if clean_ntype == "band_note":
        clean_bid = str(band_id or "").strip()
        return f"{clean_aid}::band_note::{clean_bid}::{clean_sid}"

    return f"{clean_aid}::{clean_ntype}::{clean_sid}"


def parse_source_record(raw_src: dict[str, Any], default_source_index: int = 0) -> CorpusSourceRecord:
    """Parse a source record supporting both structured and legacy schema."""
    url = str(raw_src.get("url") or "").strip()
    source_id = str(raw_src.get("source_id") or "").strip()
    if not source_id:
        # Backward compatibility fallback for legacy records missing explicit source_id
        source_id = f"SRC-LEGACY-{default_source_index:03d}"

    source_title = str(raw_src.get("source_title") or "").strip()
    organization = str(raw_src.get("organization") or "").strip()
    source_tier = str(raw_src.get("source_tier") or "TIER_1").strip()
    publication_date = str(raw_src.get("publication_date") or "").strip()
    section = str(raw_src.get("section") or "").strip()
    language = str(raw_src.get("language") or "vi").strip()

    description = str(raw_src.get("description")).strip() if raw_src.get("description") else None
    high_note = str(raw_src.get("high_note")).strip() if raw_src.get("high_note") else None
    low_note = str(raw_src.get("low_note")).strip() if raw_src.get("low_note") else None
    critical_high_note = str(raw_src.get("critical_high_note")).strip() if raw_src.get("critical_high_note") else None
    critical_low_note = str(raw_src.get("critical_low_note")).strip() if raw_src.get("critical_low_note") else None
    preanalytic_note = str(raw_src.get("preanalytic_note")).strip() if raw_src.get("preanalytic_note") else None
    limitation_note = str(raw_src.get("limitation_note")).strip() if raw_src.get("limitation_note") else None

    raw_band_notes = raw_src.get("band_notes", {})
    band_notes: dict[str, str] = {}
    if isinstance(raw_band_notes, dict):
        for k, v in raw_band_notes.items():
            if v and str(v).strip():
                band_notes[str(k).strip()] = str(v).strip()

    return CorpusSourceRecord(
        source_id=source_id,
        source_title=source_title,
        organization=organization,
        source_tier=source_tier if source_tier in {"TIER_1", "TIER_2", "TIER_3"} else "TIER_1",  # type: ignore
        publication_date=publication_date,
        url=url,
        section=section,
        language=language,
        description=description,
        high_note=high_note,
        low_note=low_note,
        band_notes=band_notes,
        critical_high_note=critical_high_note,
        critical_low_note=critical_low_note,
        preanalytic_note=preanalytic_note,
        limitation_note=limitation_note,
    )


def parse_analyte_record(raw_entry: dict[str, Any]) -> CorpusAnalyteRecord:
    """Parse an analyte entry supporting both structured and legacy schema."""
    canonical_name = str(raw_entry.get("canonical_name") or raw_entry.get("name") or "").strip()
    analyte_id = str(raw_entry.get("analyte_id") or canonical_analyte_id(canonical_name)).strip()
    rule_type_raw = str(raw_entry.get("rule_type") or ANALYTE_RULE_TYPES.get(analyte_id, "RI")).strip()
    rule_type: RuleType = rule_type_raw if rule_type_raw in {"RI", "BAND", "CDL", "ONE_SIDED_LIMIT"} else "RI"  # type: ignore
    canonical_unit = str(raw_entry.get("canonical_unit") or raw_entry.get("metric") or "").strip()

    raw_sources = raw_entry.get("sources", [])
    sources: list[CorpusSourceRecord] = []
    if isinstance(raw_sources, list):
        for idx, src in enumerate(raw_sources):
            if isinstance(src, dict):
                sources.append(parse_source_record(src, default_source_index=idx))

    return CorpusAnalyteRecord(
        canonical_name=canonical_name,
        analyte_id=analyte_id,
        rule_type=rule_type,
        canonical_unit=canonical_unit,
        sources=sources,
    )


def build_chunks_from_analyte(analyte: CorpusAnalyteRecord) -> list[CorpusChunk]:
    """Generate fine-grained normalized chunks from a single analyte record.

    Rule: Analyte × Source × Note Type -> 1 Chunk.
    """
    chunks: list[CorpusChunk] = []

    for source in analyte.sources:
        sid = source.source_id

        # Standard singular note fields
        notes: list[tuple[str, str | None, str | None]] = [
            ("description", source.description, None),
            ("high_note", source.high_note, None),
            ("low_note", source.low_note, None),
            ("critical_high_note", source.critical_high_note, None),
            ("critical_low_note", source.critical_low_note, None),
            ("preanalytic_note", source.preanalytic_note, None),
            ("limitation_note", source.limitation_note, None),
        ]

        for note_type, text_val, _ in notes:
            if text_val and text_val.strip():
                chunk_id = generate_chunk_id(
                    analyte_id=analyte.analyte_id,
                    note_type=note_type,
                    source_id=sid,
                )
                chunks.append(
                    CorpusChunk(
                        chunk_id=chunk_id,
                        text=text_val.strip(),
                        indicator=analyte.canonical_name,
                        analyte_id=analyte.analyte_id,
                        rule_type=analyte.rule_type,
                        note_type=note_type,  # type: ignore
                        band_id=None,
                        band_label=None,
                        source_id=sid,
                        source_title=source.source_title,
                        organization=source.organization,
                        source_url=source.url,
                        source_section=source.section,
                        source_tier=source.source_tier,
                        language=source.language,
                    )
                )

        # Multi-band notes
        if source.band_notes:
            for band_id, band_text in source.band_notes.items():
                if band_text and band_text.strip():
                    chunk_id = generate_chunk_id(
                        analyte_id=analyte.analyte_id,
                        note_type="band_note",
                        source_id=sid,
                        band_id=band_id,
                    )
                    chunks.append(
                        CorpusChunk(
                            chunk_id=chunk_id,
                            text=band_text.strip(),
                            indicator=analyte.canonical_name,
                            analyte_id=analyte.analyte_id,
                            rule_type=analyte.rule_type,
                            note_type="band_note",
                            band_id=band_id,
                            band_label=band_id.replace("_", " ").capitalize(),
                            source_id=sid,
                            source_title=source.source_title,
                            organization=source.organization,
                            source_url=source.url,
                            source_section=source.section,
                            source_tier=source.source_tier,
                            language=source.language,
                        )
                    )

    return chunks


def build_corpus_chunks(entries: list[dict[str, Any]] | list[CorpusAnalyteRecord]) -> list[CorpusChunk]:
    """Generate all fine-grained chunks from raw JSON entries or CorpusAnalyteRecords."""
    all_chunks: list[CorpusChunk] = []

    for entry in entries:
        if isinstance(entry, dict):
            analyte_rec = parse_analyte_record(entry)
        else:
            analyte_rec = entry
        all_chunks.extend(build_chunks_from_analyte(analyte_rec))

    return all_chunks
