from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.scripts.build_reference_config import (
    DEFAULT_INPUT,
    SECTION_OVERRIDES,
    normalize_section,
)

DEFAULT_CATALOG = "data/reference/reference_ranges.json"


class AnnotateError(Exception):
    """Invalid catalog or source input."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_repo_path(path_value: str | Path, root: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (root or repo_root()) / path


def section_maps_by_source(input_path: Path) -> tuple[dict[int, str | None], dict[str, str]]:
    import csv

    by_row: dict[int, str | None] = {}
    by_analyte: dict[str, str] = {}
    with input_path.open("r", encoding="utf-8-sig", newline="") as file:
        for index, row in enumerate(csv.DictReader(file), start=2):
            section = normalize_section(row.get("section"))
            by_row[index] = section
            analyte = str(row.get("analyte_canonical") or "").strip()
            if analyte and section and analyte not in by_analyte:
                by_analyte[analyte] = section
    return by_row, by_analyte


def annotate_catalog_sections(
    catalog_path: str | Path = DEFAULT_CATALOG,
    input_path: str | Path = DEFAULT_INPUT,
    *,
    root: Path | None = None,
) -> tuple[int, int]:
    """Annotate the runtime catalog with per-rule functional ``section`` without
    regenerating it from sources.

    Background (ADR-010 CRIT-TREND-06): the committed catalog carries 20
    supplemental rules (source_origin=explanations.json) that provide the RI
    reference ranges for HbA1c, LDL-C, HDL-C and Potassium. The current
    explanations.json schema no longer carries ranges, so a full rebuild would
    silently drop those RI rules (a clinical regression). This script therefore
    annotates the existing catalog in place instead.

    Section resolution per rule:
      primary rules   -> SECTION_OVERRIDES[analyte] or the source CSV section of
                         the rule's source_row_number.
      supplemental    -> SECTION_OVERRIDES[analyte] or the section of that
                         analyte's primary rules or None.
    """
    root = root or repo_root()
    catalog_file = resolve_repo_path(catalog_path, root)
    input_file = resolve_repo_path(input_path, root)
    if not catalog_file.exists():
        raise AnnotateError(f"catalog not found: {catalog_file}")
    if not input_file.exists():
        raise AnnotateError(f"source CSV not found: {input_file}")

    rules = json.loads(catalog_file.read_text(encoding="utf-8"))
    by_source_row, by_analyte_from_csv = section_maps_by_source(input_file)

    primary_by_analyte: dict[str, str] = {}

    annotated = 0
    missing = 0
    for rule in rules:
        analyte = str(rule.get("analyte_canonical") or "")
        override = SECTION_OVERRIDES.get(analyte)
        if rule.get("source_origin") == "explanations.json":
            section = override or by_analyte_from_csv.get(analyte) or primary_by_analyte.get(analyte)
        else:
            section = override or by_source_row.get(int(rule.get("source_row_number") or 0))
            if not section:
                section = by_analyte_from_csv.get(analyte)
            if section and analyte not in primary_by_analyte:
                primary_by_analyte[analyte] = section
        if not section:
            missing += 1
        rule["section"] = section
        annotated += 1

    ordered: list[dict[str, object]] = []
    for rule in rules:
        reordered = {"rule_id": rule["rule_id"], "source_row_number": rule["source_row_number"]}
        for key, value in rule.items():
            if key not in reordered:
                reordered[key] = value
        ordered.append(reordered)

    catalog_file.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return annotated, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Annotate the committed runtime reference catalog with per-rule sections (in place)."
    )
    parser.add_argument(
        "--catalog", default=DEFAULT_CATALOG, help="Runtime catalog JSON path, relative to repo root unless absolute."
    )
    parser.add_argument(
        "--input", default=DEFAULT_INPUT, help="Source CSV path, relative to repo root unless absolute."
    )
    args = parser.parse_args(argv)
    try:
        annotated, missing = annotate_catalog_sections(args.catalog, args.input)
    except AnnotateError as exc:
        print(f"Annotate failed: {exc}", file=sys.stderr)
        return 1
    print(f"Annotated rules: {annotated}")
    print(f"Rules without section: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
