from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _load_sections_by_analyte() -> dict[str, str]:
    """Analyte canonical -> functional section, derived from the runtime catalog.

    RI rules are authoritative for grouping; an analyte with no RI rule falls back
    to any rule's section. Analytes absent from the catalog resolve to ``other``.
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

    by_analyte: dict[str, str] = {}
    ri_first: dict[str, str] = {}
    for rule in rules:
        analyte = str(rule.get("analyte_canonical") or "").strip()
        section = rule.get("section")
        if not analyte or not section:
            continue
        if rule.get("reference_type") == "RI" and analyte not in ri_first:
            ri_first[analyte] = section
        by_analyte.setdefault(analyte, section)
    return {analyte: ri_first.get(analyte, by_analyte.get(analyte, OTHER)) for analyte in by_analyte}


def analyte_section(analyte_canonical: str) -> str | None:
    """Canonical section key for an analyte, or None if the analyte is unknown."""
    return _load_sections_by_analyte().get(analyte_canonical)


def section_label(section: str | None) -> str | None:
    if not section:
        return None
    return SECTION_LABELS.get(section, SECTION_LABELS[OTHER])
