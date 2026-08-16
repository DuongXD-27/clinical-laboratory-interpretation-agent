"""Deterministic catalog for supported analytes and curated safe fallbacks.

This module deliberately performs key lookup only. Reference ranges, units and
critical thresholds are authoritative structured data and must never depend on
semantic retrieval or an embedding model.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


class AnalyteCatalogError(Exception):
    """Raised when the curated analyte catalog cannot be loaded safely."""


@dataclass(frozen=True)
class AnalyteDefinition:
    analyte_id: str
    indicator: str
    display_name: str
    vietnamese_name: str
    curated_explanation: str
    sources: tuple[str, ...]
    high_note: str = ""
    low_note: str = ""
    critical_high_note: str = ""
    critical_low_note: str = ""

    @property
    def description(self) -> str:
        return self.curated_explanation

    def explanation_for_status(
        self,
        status: str,
        critical_status: str | None = None,
    ) -> str:
        """Deterministic status-aware explanation selection.

        Selection policy:
        CRITICAL_HIGH: critical_high_note -> high_note -> description
        CRITICAL_LOW: critical_low_note -> low_note -> description
        HIGH: high_note -> description
        LOW: low_note -> description
        NORMAL / UNKNOWN / other: neutral description
        """
        normalized_status = (status or "").lower().strip()
        normalized_critical = (critical_status or "").lower().strip()
        effective_status = normalized_critical or normalized_status

        if effective_status == "critical_high":
            return self.critical_high_note or self.high_note or self.curated_explanation
        if effective_status == "critical_low":
            return self.critical_low_note or self.low_note or self.curated_explanation
        if effective_status == "high":
            return self.high_note or self.curated_explanation
        if effective_status == "low":
            return self.low_note or self.curated_explanation
        # normal, unknown, etc. return neutral description only
        return self.curated_explanation


def _lookup_key(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


class AnalyteCatalog:
    def __init__(
        self,
        *,
        definitions: list[AnalyteDefinition],
        aliases: dict[str, str] | None = None,
    ) -> None:
        if not definitions:
            raise AnalyteCatalogError("analyte catalog is empty")

        self._by_id = {definition.analyte_id: definition for definition in definitions}
        self._by_key: dict[str, AnalyteDefinition] = {}
        for definition in definitions:
            for value in (
                definition.analyte_id,
                definition.indicator,
                definition.display_name,
                definition.vietnamese_name,
            ):
                key = _lookup_key(value)
                if key:
                    self._by_key[key] = definition

        # The reference config maps input aliases to its canonical range name.
        # Bind both sides to the same deterministic catalog record.
        for alias, canonical in (aliases or {}).items():
            definition = self._by_key.get(_lookup_key(alias))
            if definition is None:
                definition = self._by_key.get(_lookup_key(canonical))
            if definition is not None:
                self._by_key[_lookup_key(alias)] = definition
                self._by_key[_lookup_key(canonical)] = definition

    @classmethod
    def from_default_files(cls) -> AnalyteCatalog:
        root = Path(__file__).resolve().parents[2]
        explanations_path = root / "data/reference/explanations.json"
        config_path = root / "data/reference/reference_checker_config.json"
        try:
            explanations = json.loads(explanations_path.read_text(encoding="utf-8"))
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AnalyteCatalogError(f"missing analyte catalog file: {exc.filename}") from exc
        except json.JSONDecodeError as exc:
            raise AnalyteCatalogError(f"invalid analyte catalog JSON: {exc}") from exc

        definitions: list[AnalyteDefinition] = []
        for index, item in enumerate(explanations):
            # New schema: "name" is the indicator field; "id" is derived from it.
            if not isinstance(item, dict) or not item.get("name"):
                raise AnalyteCatalogError(
                    f"analyte definition at index {index} requires 'name'"
                )
            indicator = str(item["name"]).strip()
            # Derive a stable lowercase id from the name (e.g. "WBC" → "wbc")
            analyte_id = indicator.lower().replace("-", "_").replace(" ", "_")
            # "sources" is a list of objects; extract URLs and notes.
            raw_sources = item.get("sources", [])
            source_urls: list[str] = []
            descriptions: list[str] = []
            high_notes: list[str] = []
            low_notes: list[str] = []
            crit_high_notes: list[str] = []
            crit_low_notes: list[str] = []

            for src in raw_sources:
                if not isinstance(src, dict):
                    continue
                url = str(src.get("url", "")).strip()
                if url:
                    source_urls.append(url)
                desc = str(src.get("description") or "").strip()
                if desc:
                    descriptions.append(desc)
                hn = str(src.get("high_note") or "").strip()
                if hn:
                    high_notes.append(hn)
                ln = str(src.get("low_note") or "").strip()
                if ln:
                    low_notes.append(ln)
                chn = str(src.get("critical_high_note") or "").strip()
                if chn:
                    crit_high_notes.append(chn)
                cln = str(src.get("critical_low_note") or "").strip()
                if cln:
                    crit_low_notes.append(cln)

            definitions.append(
                AnalyteDefinition(
                    analyte_id=analyte_id,
                    indicator=indicator,
                    display_name=indicator,
                    vietnamese_name="",
                    curated_explanation=descriptions[0] if descriptions else "",
                    sources=tuple(source_urls),
                    high_note=high_notes[0] if high_notes else "",
                    low_note=low_notes[0] if low_notes else "",
                    critical_high_note=crit_high_notes[0] if crit_high_notes else "",
                    critical_low_note=crit_low_notes[0] if crit_low_notes else "",
                )
            )

        aliases = config.get("analyte_aliases", {}) if isinstance(config, dict) else {}
        return cls(definitions=definitions, aliases=aliases)

    def resolve(self, value: Any) -> AnalyteDefinition | None:
        """Resolve an ID/name/alias using exact normalized-key lookup."""

        return self._by_key.get(_lookup_key(value))

    def get(self, analyte_id: str) -> AnalyteDefinition | None:
        return self._by_id.get(str(analyte_id).strip())


@lru_cache(maxsize=1)
def get_analyte_catalog() -> AnalyteCatalog:
    return AnalyteCatalog.from_default_files()
