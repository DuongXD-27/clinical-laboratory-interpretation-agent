"""Authoritative citation metadata lookup for patient-facing explanations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MedicalCitation:
    source_id: str
    title: str
    organization: str
    url: str
    section_or_context: str | None
    analyte: str
    note_type: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class MedicalCitationRepository:
    """Index corpus-owned metadata; never synthesize fields with an LLM."""

    NOTE_FIELDS = (
        "description",
        "high_note",
        "low_note",
        "critical_high_note",
        "critical_low_note",
        "preanalytic_note",
        "limitation_note",
    )

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._by_url_and_analyte: dict[tuple[str, str], list[MedicalCitation]] = {}
        self._by_id_and_analyte: dict[tuple[str, str], list[MedicalCitation]] = {}
        for entry in entries:
            analyte = str(entry.get("canonical_name") or entry.get("name") or "").strip()
            for source in entry.get("sources", []):
                if not isinstance(source, dict):
                    continue
                note_types = [field for field in self.NOTE_FIELDS if str(source.get(field) or "").strip()]
                if isinstance(source.get("band_notes"), dict) and source["band_notes"]:
                    note_types.append("band_note")
                for note_type in note_types:
                    citation = MedicalCitation(
                        source_id=str(source.get("source_id") or "").strip(),
                        title=str(source.get("source_title") or "").strip(),
                        organization=str(source.get("organization") or "").strip(),
                        url=str(source.get("url") or "").strip(),
                        section_or_context=str(source.get("section") or "").strip() or None,
                        analyte=analyte,
                        note_type=note_type,
                    )
                    self._by_url_and_analyte.setdefault((citation.url, analyte.casefold()), []).append(citation)
                    self._by_id_and_analyte.setdefault((citation.source_id, analyte.casefold()), []).append(citation)

    @classmethod
    def from_default_file(cls) -> MedicalCitationRepository:
        path = Path(__file__).resolve().parents[2] / "data/reference/explanations.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def resolve(
        self,
        *,
        analyte: str,
        url: str = "",
        source_id: str = "",
        note_type: str | None = None,
    ) -> MedicalCitation | None:
        key_analyte = analyte.strip().casefold()
        candidates = (
            self._by_id_and_analyte.get((source_id.strip(), key_analyte), [])
            if source_id.strip()
            else self._by_url_and_analyte.get((url.strip(), key_analyte), [])
        )
        if note_type:
            exact = next((item for item in candidates if item.note_type == note_type), None)
            if exact is not None:
                return exact
        return candidates[0] if candidates else None

    def resolve_many(self, *, analyte: str, sources: list[str]) -> list[MedicalCitation]:
        citations: list[MedicalCitation] = []
        seen: set[tuple[str, str]] = set()
        for source in sources:
            citation = self.resolve(analyte=analyte, url=str(source))
            if citation is None:
                continue
            key = (citation.source_id, citation.note_type)
            if key not in seen:
                seen.add(key)
                citations.append(citation)
        return citations


@lru_cache(maxsize=1)
def get_medical_citation_repository() -> MedicalCitationRepository:
    return MedicalCitationRepository.from_default_file()
