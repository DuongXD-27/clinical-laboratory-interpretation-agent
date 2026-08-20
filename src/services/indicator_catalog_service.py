"""Unified read facade for the approved indicator configuration.

The reference repository remains authoritative for rule selection.  This
service combines its canonical name/aliases/units/reference rules with the
functional section and trend policy so callers do not reassemble indicator
metadata from unrelated files.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from src.services.analyte_sections import analyte_section
from src.services.reference_repository import ReferenceRepository


class IndicatorConfigurationError(ValueError):
    """Raised when the declared catalog cannot safely describe an approved analyte."""


@dataclass(frozen=True)
class IndicatorConfiguration:
    canonical_name: str
    canonical_unit: str
    aliases: tuple[str, ...]
    section: str
    max_gap_days: int | None


class IndicatorConfigurationService:
    """Resolve all runtime indicator metadata from one validated configuration API."""

    def __init__(self, repository: ReferenceRepository) -> None:
        self._repository = repository
        approved = set(repository.approved_analytes)
        if set(repository.trend_max_gap_days) != approved:
            raise IndicatorConfigurationError(
                "trend_max_gap_days must declare exactly the approved analytes"
            )

        self._entries: dict[str, IndicatorConfiguration] = {}
        for canonical in approved:
            unit = repository.canonical_unit_for(canonical)
            if unit is None:
                raise IndicatorConfigurationError(
                    f"{canonical} must have exactly one approved canonical unit"
                )
            section = analyte_section(canonical)
            if section is None:
                raise IndicatorConfigurationError(f"{canonical} has no functional section")
            max_gap_days = repository.trend_max_gap_days[canonical]
            self._entries[canonical] = IndicatorConfiguration(
                canonical_name=canonical,
                canonical_unit=unit,
                aliases=repository.aliases_for(canonical),
                section=section,
                max_gap_days=max_gap_days,
            )

    def resolve(self, analyte: str) -> IndicatorConfiguration | None:
        canonical = self._repository.resolve_analyte(analyte)
        if canonical is None:
            return None
        return self._entries.get(canonical)

    def get(self, canonical_name: str) -> IndicatorConfiguration | None:
        return self._entries.get(canonical_name)


@lru_cache(maxsize=1)
def get_indicator_configuration_service() -> IndicatorConfigurationService:
    return IndicatorConfigurationService(ReferenceRepository.from_default_files())
