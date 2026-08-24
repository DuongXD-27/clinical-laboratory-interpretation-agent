"""Medical knowledge corpus domain schemas and runtime chunk representations."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

SourceTier = Literal["TIER_1", "TIER_2", "TIER_3"]
RuleType = Literal["RI", "BAND", "CDL", "ONE_SIDED_LIMIT"]
NoteType = Literal[
    "description",
    "high_note",
    "low_note",
    "band_note",
    "critical_high_note",
    "critical_low_note",
    "preanalytic_note",
    "limitation_note",
]


class CorpusSourceRecord(BaseModel):
    """Source-backed medical reference knowledge container."""

    source_id: str = Field(..., description="Stable internal identifier e.g. SRC-NLA-NCEP-2014")
    source_title: str = Field(default="", description="Title of the source publication")
    organization: str = Field(default="", description="Publishing body or institution")
    source_tier: SourceTier = Field(default="TIER_1", description="Governance tier")
    publication_date: str = Field(default="", description="Publication date or year")
    url: str = Field(default="", description="Canonical source URL")
    section: str = Field(default="", description="Table/Section reference")
    language: str = Field(default="vi", description="Content language code")

    # Explanatory notes
    description: str | None = None
    high_note: str | None = None
    low_note: str | None = None
    band_notes: dict[str, str] = Field(default_factory=dict)
    critical_high_note: str | None = None
    critical_low_note: str | None = None
    preanalytic_note: str | None = None
    limitation_note: str | None = None


class CorpusAnalyteRecord(BaseModel):
    """Analyte-level knowledge container in explanations.json."""

    canonical_name: str
    analyte_id: str
    rule_type: RuleType
    canonical_unit: str = ""
    sources: list[CorpusSourceRecord] = Field(default_factory=list)


class CorpusChunk(BaseModel):
    """Fine-grained normalized chunk for vector embedding and retrieval."""

    chunk_id: str
    text: str

    indicator: str
    analyte_id: str

    rule_type: RuleType
    note_type: NoteType

    band_id: str | None = None
    band_label: str | None = None

    source_id: str
    source_url: str = ""
    source_tier: str = "TIER_1"

    language: str = "vi"

    def to_chroma_metadata(self) -> dict[str, str]:
        """Convert chunk metadata to flat scalars for ChromaDB compatibility."""
        # ``ChromaMedicalKnowledgeRetriever._metadata_chunk`` restores chunk
        # provenance from this key (JSON string list). Use the authoritative
        # source_url when present, otherwise the source_id. Never fabricated.
        provenance = self.source_url or self.source_id
        return {
            "sources": json.dumps([provenance] if provenance else []),
            "indicator": str(self.indicator),
            "analyte_id": str(self.analyte_id),
            "rule_type": str(self.rule_type),
            "note_type": str(self.note_type),
            "band_id": str(self.band_id or ""),
            "band_label": str(self.band_label or ""),
            "source_id": str(self.source_id),
            "source_tier": str(self.source_tier),
            "source_url": str(self.source_url),
            "language": str(self.language),
        }
