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
        config_path = root / "data/reference/reference_checker_v2_config.json"
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
            # "sources" is now a list of objects; extract the "url" field from each.
            raw_sources = item.get("sources", [])
            source_urls: tuple[str, ...] = tuple(
                str(src["url"]).strip()
                for src in raw_sources
                if isinstance(src, dict) and str(src.get("url", "")).strip()
            )
            definitions.append(
                AnalyteDefinition(
                    analyte_id=analyte_id,
                    indicator=indicator,
                    display_name=indicator,
                    vietnamese_name="",
                    curated_explanation="",
                    sources=source_urls,
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
