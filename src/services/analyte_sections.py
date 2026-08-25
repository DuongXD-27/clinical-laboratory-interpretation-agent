from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.services.analyte_catalog import get_analyte_catalog_contract

logger = logging.getLogger(__name__)

# Canonical functional sections (ADR-010 CRIT-TREND-06). Keys match the
# ``section`` values propagated into data/reference/reference_ranges.json.
HEMATOLOGY = "hematology"
CHEMISTRY = "chemistry"
LIPIDS = "lipids"
OTHER = "other"

KNOWN_SECTIONS: tuple[str, ...] = (HEMATOLOGY, CHEMISTRY, LIPIDS, OTHER)

SECTION_LABELS: dict[str, str] = {
    HEMATOLOGY: "Huyết học",
    CHEMISTRY: "Sinh hóa thận - gan",
    LIPIDS: "Mỡ máu & đường huyết",
    OTHER: "Khác",
}

DEFAULT_REFERENCE_RANGES_PATH = "data/reference/reference_ranges.json"

CANONICAL_TO_LEGACY_SECTION: dict[str, str] = {
    "hematology": HEMATOLOGY,
    "electrolytes": CHEMISTRY,
    "glucose": LIPIDS,
    "renal": CHEMISTRY,
    "liver": CHEMISTRY,
    "lipids": LIPIDS,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _load_sections_by_analyte() -> dict[str, str]:
    """Analyte canonical -> legacy functional section.

    Canonical group metadata comes from analyte_catalog.json. The legacy
    section keys stay unchanged for existing callers, and reference ranges only
    define which analytes previously had an externally visible section.
    """
    path = _repo_root() / DEFAULT_REFERENCE_RANGES_PATH
    try:
        rules: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("reference ranges not found: %s", path)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("reference ranges unparseable %s: %s", path, exc)
        return {}

    known_analytes: set[str] = set()
    for rule in rules:
        analyte = str(rule.get("analyte_canonical") or "").strip()
        if analyte:
            known_analytes.add(analyte)

    sections: dict[str, str] = {}
    catalog = get_analyte_catalog_contract()
    for analyte in known_analytes:
        entry = catalog.resolve(analyte)
        if entry is None:
            continue
        sections[analyte] = CANONICAL_TO_LEGACY_SECTION.get(entry.group, OTHER)
    return sections


def analyte_section(analyte_canonical: str) -> str | None:
    """Canonical section key for an analyte, or None if the analyte is unknown."""
    return _load_sections_by_analyte().get(analyte_canonical)


def section_label(section: str | None) -> str | None:
    if not section:
        return None
    return SECTION_LABELS.get(section, SECTION_LABELS[OTHER])
