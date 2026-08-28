"""Deterministic catalog for supported analytes and curated safe fallbacks.

This module deliberately performs key lookup only. Reference ranges, units and
critical thresholds are authoritative structured data and must never depend on
semantic retrieval or an embedding model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.services.analyte_name_resolution import normalize_analyte_lookup_key
from src.services.analyte_resolver import canonical_analyte_id


class AnalyteCatalogError(Exception):
    """Raised when the curated analyte catalog cannot be loaded safely."""


VALID_RUNTIME_STATUSES = frozenset({"APPROVED", "HOLD", "UNSUPPORTED"})


@dataclass(frozen=True)
class AnalyteCatalogEntry:
    analyte_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    group: str
    canonical_unit: str
    runtime_status: str


class AnalyteCatalogContract:
    """Canonical identity contract for analyte metadata.

    The contract is intentionally limited to identity, aliases, grouping,
    canonical unit metadata and runtime support status. Reference ranges,
    critical thresholds and medical narrative remain in their dedicated files.
    """

    def __init__(self, *, entries: list[AnalyteCatalogEntry]) -> None:
        if not entries:
            raise AnalyteCatalogError("analyte catalog contract is empty")

        self._entries = tuple(entries)
        self._by_id: dict[str, AnalyteCatalogEntry] = {}
        self._by_name: dict[str, AnalyteCatalogEntry] = {}
        self._by_key: dict[str, AnalyteCatalogEntry] = {}

        for entry in entries:
            self._register(entry.analyte_id, entry, self._by_id, "analyte_id")
            self._register(entry.canonical_name, entry, self._by_name, "canonical_name")

            for value in (entry.analyte_id, entry.canonical_name, *entry.aliases):
                key = _lookup_key(value)
                existing = self._by_key.get(key)
                if existing is not None and existing.canonical_name != entry.canonical_name:
                    raise AnalyteCatalogError(
                        f"alias {value!r} maps to both {existing.canonical_name!r} and {entry.canonical_name!r}"
                    )
                if key:
                    self._by_key[key] = entry

    @staticmethod
    def _register(
        key: str,
        entry: AnalyteCatalogEntry,
        target: dict[str, AnalyteCatalogEntry],
        label: str,
    ) -> None:
        if not key:
            raise AnalyteCatalogError(f"catalog entry {entry!r} has empty {label}")
        if key in target:
            raise AnalyteCatalogError(f"duplicate {label}: {key}")
        target[key] = entry

    @classmethod
    def from_file(cls, path: str | Path) -> AnalyteCatalogContract:
        catalog_path = Path(path)
        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AnalyteCatalogError(f"missing analyte catalog contract: {catalog_path}") from exc
        except json.JSONDecodeError as exc:
            raise AnalyteCatalogError(f"invalid analyte catalog contract JSON: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
            raise AnalyteCatalogError("analyte catalog contract must contain an entries list")

        entries: list[AnalyteCatalogEntry] = []
        for index, item in enumerate(payload["entries"]):
            if not isinstance(item, dict):
                raise AnalyteCatalogError(f"catalog entry at index {index} must be an object")
            entry = AnalyteCatalogEntry(
                analyte_id=str(item.get("analyte_id") or "").strip(),
                canonical_name=str(item.get("canonical_name") or "").strip(),
                aliases=tuple(str(alias).strip() for alias in item.get("aliases", []) if str(alias).strip()),
                group=str(item.get("group") or "").strip(),
                canonical_unit=str(item.get("canonical_unit") or "").strip(),
                runtime_status=str(item.get("runtime_status") or "").strip().upper(),
            )
            missing = [
                field_name
                for field_name in ("analyte_id", "canonical_name", "group", "canonical_unit", "runtime_status")
                if not getattr(entry, field_name)
            ]
            if missing:
                raise AnalyteCatalogError(
                    f"catalog entry at index {index} missing required fields: {', '.join(missing)}"
                )
            if entry.runtime_status not in VALID_RUNTIME_STATUSES:
                raise AnalyteCatalogError(
                    f"{entry.canonical_name} has unsupported runtime_status {entry.runtime_status!r}"
                )
            entries.append(entry)

        return cls(entries=entries)

    @classmethod
    def from_default_file(cls) -> AnalyteCatalogContract:
        root = Path(__file__).resolve().parents[2]
        return cls.from_file(root / "data/reference/analyte_catalog.json")

    @property
    def entries(self) -> tuple[AnalyteCatalogEntry, ...]:
        return self._entries

    @property
    def approved_entries(self) -> tuple[AnalyteCatalogEntry, ...]:
        return tuple(entry for entry in self._entries if entry.runtime_status == "APPROVED")

    @property
    def approved_names(self) -> tuple[str, ...]:
        return tuple(entry.canonical_name for entry in self.approved_entries)

    def runtime_alias_map(self) -> dict[str, str]:
        """Raw alias -> canonical name for runtime-approved analytes only."""
        aliases: dict[str, str] = {}
        for entry in self.approved_entries:
            for alias in (entry.canonical_name, *entry.aliases):
                aliases[alias] = entry.canonical_name
        return aliases

    def runtime_status_for(self, value: Any) -> str | None:
        entry = self.resolve(value)
        return entry.runtime_status if entry is not None else None

    def get(self, analyte_id: str) -> AnalyteCatalogEntry | None:
        return self._by_id.get(str(analyte_id).strip())

    def resolve(self, value: Any) -> AnalyteCatalogEntry | None:
        return self._by_key.get(_lookup_key(value))


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
    band_notes: dict[str, str] = field(default_factory=dict)
    preanalytic_note: str = ""
    limitation_note: str = ""

    @property
    def description(self) -> str:
        return self.curated_explanation

    def explanation_for_status(
        self,
        status: str,
        critical_status: str | None = None,
        band_id: str | None = None,
    ) -> str:
        """Deterministic status-aware explanation selection.

        Selection policy:
        CRITICAL_HIGH: critical_high_note -> high_note -> description
        CRITICAL_LOW: critical_low_note -> low_note -> description
        BAND: exact band_note[band_id] -> description
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
        if band_id and band_id in self.band_notes:
            return self.band_notes[band_id]
        if effective_status == "high":
            return self.high_note or self.curated_explanation
        if effective_status == "low":
            return self.low_note or self.curated_explanation
        # normal, unknown, etc. return neutral description only
        return self.curated_explanation


def _lookup_key(value: Any) -> str:
    return normalize_analyte_lookup_key(value)


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
            if not isinstance(item, dict):
                raise AnalyteCatalogError(f"analyte definition at index {index} must be an object")
            indicator = str(item.get("canonical_name") or item.get("name") or "").strip()
            if not indicator:
                raise AnalyteCatalogError(f"analyte definition at index {index} requires 'canonical_name' or 'name'")
            # Use authoritative shared resolver
            analyte_id = str(item.get("analyte_id") or canonical_analyte_id(indicator)).strip()

            raw_sources = item.get("sources", [])
            source_urls: list[str] = []
            descriptions: list[str] = []
            high_notes: list[str] = []
            low_notes: list[str] = []
            crit_high_notes: list[str] = []
            crit_low_notes: list[str] = []
            all_band_notes: dict[str, str] = {}
            preanalytic_notes: list[str] = []
            limitation_notes: list[str] = []

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
                pan = str(src.get("preanalytic_note") or "").strip()
                if pan:
                    preanalytic_notes.append(pan)
                lim = str(src.get("limitation_note") or "").strip()
                if lim:
                    limitation_notes.append(lim)
                if isinstance(src.get("band_notes"), dict):
                    for b_id, b_text in src["band_notes"].items():
                        if b_text and str(b_text).strip() and b_id not in all_band_notes:
                            all_band_notes[str(b_id).strip()] = str(b_text).strip()

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
                    band_notes=all_band_notes,
                    preanalytic_note=preanalytic_notes[0] if preanalytic_notes else "",
                    limitation_note=limitation_notes[0] if limitation_notes else "",
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


@lru_cache(maxsize=1)
def get_analyte_catalog_contract() -> AnalyteCatalogContract:
    return AnalyteCatalogContract.from_default_file()
