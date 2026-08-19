from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.scripts.extract_explanation_reference_ranges import extract_supplemental_rules

BUILDER_VERSION = "v3"
DEFAULT_INPUT = "data/reference/source/adult_outpatient_laboratory_reference_map.csv"
DEFAULT_OUTPUT_DIR = "data/reference"
DEFAULT_SUPPLEMENTAL = "data/reference/explanations.json"

RUNTIME_CSV = "reference_ranges.csv"
RUNTIME_JSON = "reference_ranges.json"
QUARANTINE_CSV = "quarantine.csv"
BUILD_REPORT_JSON = "reference_build_report.json"

SUPPLEMENTAL_FIELDS = [
    "source_origin",
    "source_entry_id",
    "range_group",
    "range_note",
    "source_urls",
    "source_unit_original",
    "source_range_lower_original",
    "source_range_upper_original",
    "conversion_factor",
    "conversion_rounding",
]

# Analytes whose primary catalog rules are superseded by supplemental rules derived from explanations.json.
# Primary rules for these analytes are excluded from the final catalog (but still counted in runtime_accepted_rows).
SUPPLEMENTAL_REPLACEMENT_ANALYTES: frozenset[str] = frozenset()

# Source CSV section column -> canonical runtime key (ADR-010 CRIT-TREND-06).
SECTION_CSV_TO_CANONICAL: dict[str, str] = {
    "HEMATOLOGY ANALYTES": "hematology",
    "CHEMISTRY, RENAL, AND LIVER ANALYTES": "chemistry",
    "LIPIDS, HBA1C, AND DECISION-LIMIT ANALYTES": "lipids",
}

# Expert overrides for the per-analyte functional group. FPG's RI rule lives in the
# "Chemistry, renal, and liver analytes" section of the source CSV, but the product
# group "Mỡ máu & đường huyết" (Business Description) includes blood glucose, so FPG
# is grouped under lipids. Applies to every rule of the analyte.
SECTION_OVERRIDES: dict[str, str] = {
    "Fasting plasma glucose": "lipids",
}

STRUCTURAL_REASON_ORDER = [
    "missing_analyte",
    "invalid_sex",
    "missing_age_scope",
    "missing_unit",
    "missing_reference_type",
    "missing_range_bounds",
    "invalid_lower_bound",
    "invalid_upper_bound",
    "lower_greater_than_upper",
    "missing_upper_operator",
    "invalid_upper_operator",
]
REASON_ORDER = STRUCTURAL_REASON_ORDER

NULL_TOKENS = {"", "NA", "N/A", "NULL", "NONE"}
SOURCE_REQUIRED_FIELDS = [
    "analyte_canonical",
    "sex",
    "age_scope",
    "unit_machine",
    "unit_display_vn",
    "range_lower",
    "range_upper",
    "reference_type",
    "source_priority_tier",
    "confidence",
]

RUNTIME_FIELDS = [
    "rule_id",
    "source_row_number",
    "analyte_canonical",
    "section",
    "specimen",
    "fasting_required",
    "sex",
    "age_scope",
    "unit_machine",
    "unit_display_vn",
    "unit_raw",
    "unit_canonical",
    "value_type",
    "range_lower",
    "range_upper",
    "upper_operator",
    "reference_type",
    "source_priority_tier",
    "source_url",
    "confidence",
]


class BuildError(Exception):
    """Invalid input or output failure."""


class InvariantError(Exception):
    """Invariant or source-integrity failure."""


@dataclass(frozen=True)
class BuildResult:
    report: dict[str, Any]
    accepted: list[dict[str, Any]]
    quarantined: list[dict[str, Any]]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_repo_path(path_value: str | Path, root: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (root or repo_root()) / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize_for_compare(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_null(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.upper() in NULL_TOKENS:
        return None
    return text


def normalize_sex(value: Any) -> str | None:
    text = normalize_for_compare(value)
    if text in {"M", "MALE", "NAM"}:
        return "M"
    if text in {"F", "FEMALE", "NỮ", "NU"}:
        return "F"
    if text in {"A", "ALL", "ANY"}:
        return "A"
    return None


def normalize_section(value: Any) -> str | None:
    text = normalize_for_compare(value)
    if not text:
        return None
    return SECTION_CSV_TO_CANONICAL.get(text)


def normalize_unit(value: Any) -> str | None:
    text = normalize_null(value)
    if text is None:
        return None

    # Case-sensitive lookup: unit symbols are not case-equivalent.
    # G/L (hematology display shorthand) → 10^9/L  but  g/L (mass per volume) stays g/L.
    canonical_map = {
        "×10^9/L": "10^9/L",
        "10^9/L": "10^9/L",
        "×10^12/L": "10^12/L",
        "10^12/L": "10^12/L",
        "µmol/L": "umol/L",
        "μmol/L": "umol/L",
        "umol/L": "umol/L",
        "G/L": "10^9/L",
        "T/L": "10^12/L",
    }
    return canonical_map.get(text, text)


def parse_bound(value: Any) -> tuple[Decimal | None, str | None]:
    text = normalize_null(value)
    if text is None:
        return None, None
    try:
        return Decimal(text), None
    except InvalidOperation:
        return None, "invalid"


def decimal_to_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f")


def decimal_to_json(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(format(normalized, "f"))


def rule_id_for(source_row_number: int) -> str:
    return f"RRV2-{source_row_number:04d}"


def structural_result(row: dict[str, str]) -> tuple[list[str], dict[str, Any]]:
    reasons: list[str] = []
    normalized: dict[str, Any] = {}

    analyte = normalize_null(row.get("analyte_canonical"))
    if not analyte:
        reasons.append("missing_analyte")
    normalized["analyte_canonical"] = analyte

    sex = normalize_sex(row.get("sex"))
    if sex is None:
        reasons.append("invalid_sex")
    normalized["sex"] = sex

    age_scope = normalize_null(row.get("age_scope"))
    if not age_scope:
        reasons.append("missing_age_scope")
    normalized["age_scope"] = age_scope

    unit_machine = normalize_null(row.get("unit_machine"))
    unit_display_vn = normalize_null(row.get("unit_display_vn"))
    if not unit_machine and not unit_display_vn:
        reasons.append("missing_unit")
    unit_raw = unit_machine or unit_display_vn
    normalized["unit_machine"] = unit_machine
    normalized["unit_display_vn"] = unit_display_vn
    normalized["unit_raw"] = unit_raw
    normalized["unit_canonical"] = normalize_unit(unit_raw)

    reference_type = normalize_null(row.get("reference_type"))
    if not reference_type:
        reasons.append("missing_reference_type")
    normalized["reference_type"] = reference_type

    lower, lower_error = parse_bound(row.get("range_lower"))
    upper, upper_error = parse_bound(row.get("range_upper"))
    if lower_error:
        reasons.append("invalid_lower_bound")
    if upper_error:
        reasons.append("invalid_upper_bound")
    if lower is None and upper is None and not lower_error and not upper_error:
        reasons.append("missing_range_bounds")
    if lower is not None and upper is not None and lower > upper:
        reasons.append("lower_greater_than_upper")
    normalized["range_lower_decimal"] = lower
    normalized["range_upper_decimal"] = upper

    upper_op = normalize_null(row.get("upper_operator"))
    if reference_type == "ONE_SIDED_LIMIT":
        if not upper_op:
            reasons.append("missing_upper_operator")
        elif upper_op not in {"<", "<=", ">", ">="}:
            reasons.append("invalid_upper_operator")
    normalized["upper_operator"] = upper_op

    return [reason for reason in STRUCTURAL_REASON_ORDER if reason in reasons], normalized


def normalize_optional_source_value(value: Any) -> str | None:
    return normalize_null(value)


def make_runtime_record(
    row: dict[str, str],
    source_row_number: int,
    normalized: dict[str, Any],
    *,
    json_ready: bool = False,
) -> dict[str, Any]:
    lower = normalized["range_lower_decimal"]
    upper = normalized["range_upper_decimal"]
    lower_value: Any = decimal_to_json(lower) if json_ready else decimal_to_text(lower)
    upper_value: Any = decimal_to_json(upper) if json_ready else decimal_to_text(upper)

    return {
        "rule_id": rule_id_for(source_row_number),
        "source_row_number": source_row_number,
        "analyte_canonical": normalized["analyte_canonical"],
        "section": normalize_section(row.get("section")),
        "specimen": normalize_optional_source_value(row.get("specimen")),
        "fasting_required": normalize_optional_source_value(row.get("fasting_required")),
        "sex": normalized["sex"],
        "age_scope": normalized["age_scope"],
        "unit_machine": normalized["unit_machine"],
        "unit_display_vn": normalized["unit_display_vn"],
        "unit_raw": normalized["unit_raw"],
        "unit_canonical": normalized["unit_canonical"],
        "value_type": normalize_optional_source_value(row.get("value_type")),
        "range_lower": lower_value,
        "range_upper": upper_value,
        "upper_operator": normalized.get("upper_operator"),
        "reference_type": normalized["reference_type"],
        "source_priority_tier": normalize_for_compare(row.get("source_priority_tier")),
        "source_url": normalize_optional_source_value(row.get("source_url")),
        "confidence": normalize_for_compare(row.get("confidence")),
    }


def sort_runtime_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, int, str]:
    src_num = record.get("source_row_number")
    return (
        str(record.get("analyte_canonical") or ""),
        str(record.get("sex") or ""),
        str(record.get("age_scope") or ""),
        str(record.get("unit_canonical") or ""),
        str(record.get("reference_type") or ""),
        int(src_num) if src_num is not None else 99999,
        str(record.get("rule_id") or ""),
    )


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(v) for v in value)
    return value


def resolve_record_sections(
    records: list[dict[str, Any]],
    overrides: dict[str, str] | None = None,
) -> tuple[Counter[str], list[dict[str, str]]]:
    """Fill missing per-record ``section`` (supplemental rules have none) and apply
    the expert override map. Resolution precedence per record:
    SECTION_OVERRIDES[analyte] -> the record's own CSV section -> the analyte's
    section from any other record -> None (resolved to "other" at runtime)."""
    overrides = overrides or SECTION_OVERRIDES
    by_analyte: dict[str, str] = {}
    for rec in records:
        analyte = str(rec.get("analyte_canonical") or "")
        section = rec.get("section")
        if analyte and section and analyte not in by_analyte:
            by_analyte[analyte] = section

    applied_overrides: list[dict[str, str]] = []
    section_counts: Counter[str] = Counter()
    for rec in records:
        analyte = str(rec.get("analyte_canonical") or "")
        override = overrides.get(analyte)
        section = override or rec.get("section") or by_analyte.get(analyte)
        rec["section"] = section
        if override and rec.get("section") == override:
            applied_overrides.append({"analyte_canonical": analyte, "section": override})
        if section:
            section_counts[section] += 1
    return section_counts, applied_overrides


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def read_source_rows(input_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except FileNotFoundError as exc:
        raise BuildError(f"input file not found: {input_path}") from exc

    missing = [field for field in SOURCE_REQUIRED_FIELDS if field not in fieldnames]
    if missing:
        raise BuildError(f"input file missing required columns: {', '.join(missing)}")
    return rows, fieldnames


def build_reference_config(
    input_path: str | Path = DEFAULT_INPUT,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    root: Path | None = None,
    supplemental_path: str | Path | None = None,
) -> BuildResult:
    root = root or repo_root()
    input_file = resolve_repo_path(input_path, root)
    output_path = resolve_repo_path(output_dir, root)
    output_path.mkdir(parents=True, exist_ok=True)

    input_hash_before = sha256_file(input_file)
    input_size = input_file.stat().st_size
    rows, source_fieldnames = read_source_rows(input_file)

    accepted_working: list[tuple[dict[str, str], int, dict[str, Any]]] = []
    quarantined: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()
    structurally_eligible_rows = 0

    for index, row in enumerate(rows, start=2):
        reasons, normalized = structural_result(row)
        if not reasons:
            structurally_eligible_rows += 1
            accepted_working.append((row, index, normalized))
            continue

        ordered_reasons = [reason for reason in REASON_ORDER if reason in reasons]
        rejection_counts.update(ordered_reasons)
        quarantine_row = dict(row)
        quarantine_row.update(
            {
                "source_row_number": index,
                "rule_id": rule_id_for(index),
                "rejection_reasons": "|".join(ordered_reasons),
                "rejection_reason_count": len(ordered_reasons),
            }
        )
        quarantined.append(quarantine_row)

    accepted_csv = sorted(
        [
            make_runtime_record(row, source_row_number, normalized, json_ready=False)
            for row, source_row_number, normalized in accepted_working
        ],
        key=sort_runtime_key,
    )
    accepted_json = sorted(
        [
            make_runtime_record(row, source_row_number, normalized, json_ready=True)
            for row, source_row_number, normalized in accepted_working
        ],
        key=sort_runtime_key,
    )
    quarantined.sort(key=lambda record: int(record["source_row_number"]))

    input_rows = len(rows)
    runtime_accepted_rows = len(accepted_csv)
    quarantined_rows = len(quarantined)
    if input_rows != runtime_accepted_rows + quarantined_rows:
        raise InvariantError("input row count does not equal accepted + quarantined")
    if runtime_accepted_rows != structurally_eligible_rows:
        raise InvariantError("runtime accepted rows do not equal structurally eligible rows")

    runtime_csv_path = output_path / RUNTIME_CSV
    runtime_json_path = output_path / RUNTIME_JSON
    quarantine_csv_path = output_path / QUARANTINE_CSV
    build_report_path = output_path / BUILD_REPORT_JSON

    # --- Supplemental extraction ---
    supplemental_json: list[dict[str, Any]] = []
    supplemental_warnings: list[dict[str, Any]] = []
    if supplemental_path is not None:
        sup_file = resolve_repo_path(supplemental_path, root)
        if not sup_file.exists():
            raise BuildError(f"supplemental file not found: {sup_file}")
        primary_analytes = {str(row["analyte_canonical"]) for row in accepted_json if row.get("analyte_canonical")}
        # Exclude replacement analytes so extractor generates their rules from explanations.json instead
        primary_analytes -= SUPPLEMENTAL_REPLACEMENT_ANALYTES
        supplemental_json, supplemental_warnings = extract_supplemental_rules(sup_file, primary_analytes)

    # --- Write output files ---
    # Pre-compute catalog-accepted sets (exclude replacement analytes regardless of supplemental)
    catalog_accepted_json = [
        r for r in accepted_json if r.get("analyte_canonical") not in SUPPLEMENTAL_REPLACEMENT_ANALYTES
    ]
    catalog_accepted_csv = [
        r for r in accepted_csv if r.get("analyte_canonical") not in SUPPLEMENTAL_REPLACEMENT_ANALYTES
    ]

    if supplemental_json:
        catalog_fields = RUNTIME_FIELDS + SUPPLEMENTAL_FIELDS
        combined_json = sorted(catalog_accepted_json + supplemental_json, key=sort_runtime_key)
        section_counts, applied_overrides = resolve_record_sections(combined_json)
        # Build CSV-compatible copies of supplemental records (lists → pipe strings)
        supplemental_csv: list[dict[str, Any]] = []
        for rec in supplemental_json:
            csv_rec = dict(rec)
            csv_rec["source_urls"] = "|".join(str(u) for u in (rec.get("source_urls") or []))
            supplemental_csv.append(csv_rec)
        combined_csv = sorted(catalog_accepted_csv + supplemental_csv, key=sort_runtime_key)
        resolve_record_sections(combined_csv)
        write_csv(runtime_csv_path, combined_csv, catalog_fields)
        write_json(runtime_json_path, combined_json)
        catalog_rule_count = len(combined_json)
    else:
        section_counts, applied_overrides = resolve_record_sections(accepted_json)
        resolve_record_sections(accepted_csv)
        write_csv(runtime_csv_path, accepted_csv, RUNTIME_FIELDS)
        write_json(runtime_json_path, accepted_json)
        catalog_rule_count = len(accepted_json)

    write_csv(
        quarantine_csv_path,
        quarantined,
        source_fieldnames + ["source_row_number", "rule_id", "rejection_reasons", "rejection_reason_count"],
    )

    input_hash_after = sha256_file(input_file)
    if input_hash_after != input_hash_before:
        raise InvariantError("source hash changed during build")

    multiple_reason_rows = sum(1 for row in quarantined if int(row["rejection_reason_count"]) > 1)
    accepted_analytes = sorted({str(row["analyte_canonical"]) for row in accepted_csv if row.get("analyte_canonical")})
    quarantined_analytes = sorted(
        {str(row.get("analyte_canonical")) for row in quarantined if row.get("analyte_canonical")}
    )

    # Supplemental analytes grouped by analyte name for the report
    sup_analytes: list[str] = []
    if supplemental_json:
        seen: set[str] = set()
        for rec in supplemental_json:
            a = str(rec.get("analyte_canonical") or "")
            if a and a not in seen:
                seen.add(a)
                sup_analytes.append(a)
        sup_analytes.sort()

    report: dict[str, Any] = {
        "builder_version": BUILDER_VERSION,
        "input_file": relative_path(input_file, root),
        "input_sha256": input_hash_before,
        "input_sha256_after": input_hash_after,
        "input_size_bytes": input_size,
        "input_rows": input_rows,
        "structurally_eligible_rows": structurally_eligible_rows,
        "structurally_rejected_rows": input_rows - structurally_eligible_rows,
        "runtime_accepted_rows": runtime_accepted_rows,
        "quarantined_rows": quarantined_rows,
        "multiple_reason_rows": multiple_reason_rows,
        "rejection_reason_counts": {
            reason: rejection_counts[reason] for reason in REASON_ORDER if rejection_counts[reason]
        },
        "accepted_analytes": accepted_analytes,
        "quarantined_analytes": quarantined_analytes,
        "output_files": {
            "reference_ranges_csv": {
                "path": relative_path(runtime_csv_path, root),
                "sha256": sha256_file(runtime_csv_path),
            },
            "reference_ranges_json": {
                "path": relative_path(runtime_json_path, root),
                "sha256": sha256_file(runtime_json_path),
            },
            "quarantine_csv": {
                "path": relative_path(quarantine_csv_path, root),
                "sha256": sha256_file(quarantine_csv_path),
            },
        },
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_integrity_verified": True,
        "section_propagation": {
            "records_per_section": {k: v for k, v in sorted(section_counts.items())},
            "records_without_section": catalog_rule_count - sum(section_counts.values()),
            "overrides_applied": applied_overrides,
        },
    }

    if supplemental_path is not None:
        report["explanation_supplement"] = {
            "supplemental_file": relative_path(resolve_repo_path(supplemental_path, root), root),
            "entries_scanned": 9,
            "missing_analytes": len(sup_analytes),
            "supplemental_analytes": sup_analytes,
            "rules_added": len(supplemental_json),
            "boundary_warnings": supplemental_warnings,
        }
        report["catalog"] = {
            "total_rules": catalog_rule_count,
        }

    build_report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    return BuildResult(report=report, accepted=accepted_json, quarantined=quarantined)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reference catalog and structural-rejection artifacts.")
    parser.add_argument(
        "--input", default=DEFAULT_INPUT, help="Source CSV path, relative to repo root unless absolute."
    )
    parser.add_argument(
        "--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory, relative to repo root unless absolute."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_reference_config(
            args.input,
            args.output_dir,
            supplemental_path=DEFAULT_SUPPLEMENTAL,
        )
    except InvariantError as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 2
    except (BuildError, OSError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1

    report = result.report
    print(f"Input rows: {report['input_rows']}")
    print(f"Structurally eligible: {report['structurally_eligible_rows']}")
    print(f"Runtime accepted: {report['runtime_accepted_rows']}")
    print(f"Quarantined: {report['quarantined_rows']}")
    print("Source integrity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
