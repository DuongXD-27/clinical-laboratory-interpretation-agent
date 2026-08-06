from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

BUILDER_VERSION = "v2"
DEFAULT_INPUT = "adult_outpatient_laboratory_reference_map.csv"
DEFAULT_OUTPUT_DIR = "data/reference"

RUNTIME_CSV = "reference_ranges_v2.csv"
RUNTIME_JSON = "reference_ranges_v2.json"
QUARANTINE_CSV = "quarantine_v2.csv"
BUILD_REPORT_JSON = "reference_build_report.json"

QUALITY_REASON_ORDER = [
    "range_flag_not_ok",
    "confidence_not_high",
    "unsupported_source_tier",
]
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
]
REASON_ORDER = QUALITY_REASON_ORDER + STRUCTURAL_REASON_ORDER

NULL_TOKENS = {"", "NA", "N/A", "NULL", "NONE"}
SUPPORTED_TIERS = {"T1", "T2"}

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
    "range_flag",
]

RUNTIME_FIELDS = [
    "rule_id",
    "source_row_number",
    "analyte_canonical",
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
    "reference_type",
    "source_priority_tier",
    "source_url",
    "confidence",
    "range_flag",
]


class BuildFailure(Exception):
    """Invalid input or output failure."""


class InvariantFailure(Exception):
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


def normalize_unit(value: Any) -> str | None:
    text = normalize_null(value)
    if text is None:
        return None

    canonical_map = {
        "×10^9/L": "10^9/L",
        "10^9/L": "10^9/L",
        "×10^12/L": "10^12/L",
        "10^12/L": "10^12/L",
        "µMOL/L": "umol/L",
        "ΜMOL/L": "umol/L",
        "UMOL/L": "umol/L",
        "G/L": "10^9/L",
        "T/L": "10^12/L",
    }
    upper_text = text.upper()
    if upper_text in canonical_map:
        return canonical_map[upper_text]
    return text


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


def quality_reasons(row: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    if normalize_for_compare(row.get("range_flag")) != "OK":
        reasons.append("range_flag_not_ok")
    if normalize_for_compare(row.get("confidence")) != "HIGH":
        reasons.append("confidence_not_high")
    if normalize_for_compare(row.get("source_priority_tier")) not in SUPPORTED_TIERS:
        reasons.append("unsupported_source_tier")
    return reasons


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
        "reference_type": normalized["reference_type"],
        "source_priority_tier": normalize_for_compare(row.get("source_priority_tier")),
        "source_url": normalize_optional_source_value(row.get("source_url")),
        "confidence": normalize_for_compare(row.get("confidence")),
        "range_flag": normalize_for_compare(row.get("range_flag")),
    }


def sort_runtime_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, int]:
    return (
        str(record.get("analyte_canonical") or ""),
        str(record.get("sex") or ""),
        str(record.get("age_scope") or ""),
        str(record.get("unit_canonical") or ""),
        str(record.get("reference_type") or ""),
        int(record["source_row_number"]),
    )


def csv_value(value: Any) -> Any:
    return "" if value is None else value


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
        raise BuildFailure(f"input file not found: {input_path}") from exc

    missing = [field for field in SOURCE_REQUIRED_FIELDS if field not in fieldnames]
    if missing:
        raise BuildFailure(f"input file missing required columns: {', '.join(missing)}")
    return rows, fieldnames


def build_reference_config(
    input_path: str | Path = DEFAULT_INPUT,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    root: Path | None = None,
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
    strict_quality_eligible_rows = 0
    md_analytes: set[str] = set()

    for index, row in enumerate(rows, start=2):
        analyte = row.get("analyte_canonical", "")
        if normalize_for_compare(row.get("range_flag")) == "MD" and analyte:
            md_analytes.add(analyte)

        reasons = quality_reasons(row)
        if not reasons:
            strict_quality_eligible_rows += 1
            structural_reasons, normalized = structural_result(row)
            reasons.extend(structural_reasons)
            if not reasons:
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
        raise InvariantFailure("input row count does not equal accepted + quarantined")
    if runtime_accepted_rows > strict_quality_eligible_rows:
        raise InvariantFailure("runtime accepted rows exceed strict quality eligible rows")
    if strict_quality_eligible_rows > input_rows:
        raise InvariantFailure("strict quality eligible rows exceed input rows")

    runtime_csv_path = output_path / RUNTIME_CSV
    runtime_json_path = output_path / RUNTIME_JSON
    quarantine_csv_path = output_path / QUARANTINE_CSV
    build_report_path = output_path / BUILD_REPORT_JSON

    write_csv(runtime_csv_path, accepted_csv, RUNTIME_FIELDS)
    write_json(runtime_json_path, accepted_json)
    write_csv(
        quarantine_csv_path,
        quarantined,
        source_fieldnames + ["source_row_number", "rule_id", "rejection_reasons", "rejection_reason_count"],
    )

    input_hash_after = sha256_file(input_file)
    if input_hash_after != input_hash_before:
        raise InvariantFailure("source hash changed during build")

    multiple_reason_rows = sum(1 for row in quarantined if int(row["rejection_reason_count"]) > 1)
    accepted_analytes = sorted({str(row["analyte_canonical"]) for row in accepted_csv if row.get("analyte_canonical")})
    quarantined_analytes = sorted(
        {str(row.get("analyte_canonical")) for row in quarantined if row.get("analyte_canonical")}
    )

    report = {
        "builder_version": BUILDER_VERSION,
        "input_file": relative_path(input_file, root),
        "input_sha256": input_hash_before,
        "input_sha256_after": input_hash_after,
        "input_size_bytes": input_size,
        "input_rows": input_rows,
        "strict_quality_eligible_rows": strict_quality_eligible_rows,
        "strict_quality_rejected_rows": input_rows - strict_quality_eligible_rows,
        "runtime_accepted_rows": runtime_accepted_rows,
        "quarantined_rows": quarantined_rows,
        "multiple_reason_rows": multiple_reason_rows,
        "rejection_reason_counts": {reason: rejection_counts[reason] for reason in REASON_ORDER if rejection_counts[reason]},
        "accepted_analytes": accepted_analytes,
        "quarantined_analytes": quarantined_analytes,
        "md_analytes": sorted(md_analytes),
        "output_files": {
            "reference_ranges_v2_csv": {
                "path": relative_path(runtime_csv_path, root),
                "sha256": sha256_file(runtime_csv_path),
            },
            "reference_ranges_v2_json": {
                "path": relative_path(runtime_json_path, root),
                "sha256": sha256_file(runtime_json_path),
            },
            "quarantine_v2_csv": {
                "path": relative_path(quarantine_csv_path, root),
                "sha256": sha256_file(quarantine_csv_path),
            },
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_integrity_verified": True,
    }

    build_report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    return BuildResult(report=report, accepted=accepted_json, quarantined=quarantined)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build V2 reference whitelist and quarantine files.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Source CSV path, relative to repo root unless absolute.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory, relative to repo root unless absolute.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = build_reference_config(args.input, args.output_dir)
    except InvariantFailure as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 2
    except (BuildFailure, OSError, ValueError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1

    report = result.report
    print(f"Input rows: {report['input_rows']}")
    print(f"Strict quality eligible: {report['strict_quality_eligible_rows']}")
    print(f"Runtime accepted: {report['runtime_accepted_rows']}")
    print(f"Quarantined: {report['quarantined_rows']}")
    print("Source integrity: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
