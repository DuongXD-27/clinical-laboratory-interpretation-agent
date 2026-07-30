import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data" / "mock" / "generated"
UNITS_FILE = ROOT / "data" / "reference" / "units_metric.csv"
FILES = {
    "normal.json": GENERATED / "normal.json",
    "abnormal.json": GENERATED / "abnormal.json",
    "edge_case.json": GENERATED / "edge_case.json",
}
REPORT_FIELDS = {
    "report_id",
    "report_type",
    "patient_age",
    "patient_gender",
    "test_date",
    "status",
    "indicators",
}
INDICATOR_FIELDS = {"name", "value", "unit"}
REPORT_TYPES = {
    "cbc_with_differential",
    "glycemic_profile",
    "lipid_profile",
    "liver_function_basic",
    "renal_function_blood",
    "electrolytes_basic",
    "general_health_check",
}
STATUSES = {"draft", "final", "cancelled"}
GENDERS = {"male", "female", "other", "unknown"}


def fail(message):
    raise AssertionError(message)


def load_units():
    with UNITS_FILE.open(newline="", encoding="utf-8-sig") as file:
        return {
            (row["test_name"], row["standardized_unit"])
            for row in csv.DictReader(file)
        }


def load_reports():
    reports_by_file = {}
    for name, path in FILES.items():
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            fail(f"{name}: top-level JSON must be an array")
        if len(data) != 5:
            fail(f"{name}: expected 5 reports, got {len(data)}")
        reports_by_file[name] = data
    return reports_by_file


def validate_date(value, context):
    if not isinstance(value, str):
        fail(f"{context}: test_date must be a string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        fail(f"{context}: invalid YYYY-MM-DD date {value!r}: {exc}")
    if parsed.strftime("%Y-%m-%d") != value:
        fail(f"{context}: invalid canonical date {value!r}")


def validate_report(report, filename, index, units):
    context = f"{filename}[{index}]"
    if not isinstance(report, dict):
        fail(f"{context}: report must be an object")
    if set(report) != REPORT_FIELDS:
        fail(f"{context}: report fields mismatch: {sorted(report)}")
    if not isinstance(report["report_id"], str):
        fail(f"{context}: report_id must be a string")
    if report["report_type"] not in REPORT_TYPES:
        fail(f"{context}: invalid report_type {report['report_type']!r}")
    if report["status"] not in STATUSES:
        fail(f"{context}: invalid status {report['status']!r}")
    if not isinstance(report["patient_age"], int):
        fail(f"{context}: patient_age must be an integer")
    if report["patient_gender"] not in GENDERS:
        fail(f"{context}: invalid patient_gender {report['patient_gender']!r}")
    validate_date(report["test_date"], context)
    indicators = report["indicators"]
    if not isinstance(indicators, list):
        fail(f"{context}: indicators must be an array")
    if report["status"] == "final" and not indicators:
        fail(f"{context}: final report must have at least one indicator")
    if report["status"] == "cancelled" and indicators != []:
        fail(f"{context}: cancelled report must have empty indicators")

    names = set()
    for indicator_index, indicator in enumerate(indicators):
        indicator_context = f"{context}.indicators[{indicator_index}]"
        if not isinstance(indicator, dict):
            fail(f"{indicator_context}: indicator must be an object")
        if set(indicator) != INDICATOR_FIELDS:
            fail(f"{indicator_context}: indicator fields mismatch: {sorted(indicator)}")
        if not isinstance(indicator["name"], str):
            fail(f"{indicator_context}: name must be a string")
        if not isinstance(indicator["unit"], str):
            fail(f"{indicator_context}: unit must be a string")
        value = indicator["value"]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            fail(f"{indicator_context}: value must be a number")
        pair = (indicator["name"], indicator["unit"])
        if pair not in units:
            fail(f"{indicator_context}: name-unit pair is not in units_metric.csv: {pair}")
        if indicator["name"] in names:
            fail(f"{indicator_context}: duplicate indicator name {indicator['name']!r}")
        names.add(indicator["name"])


def validate():
    units = load_units()
    reports_by_file = load_reports()
    report_ids = []
    all_report_types = set()
    all_statuses = set()

    for filename, reports in reports_by_file.items():
        file_report_types = {report["report_type"] for report in reports}
        if len(file_report_types) < 4:
            fail(f"{filename}: expected at least 4 report_type values, got {sorted(file_report_types)}")
        if filename in {"normal.json", "abnormal.json"}:
            statuses = {report["status"] for report in reports}
            if "cancelled" in statuses:
                fail(f"{filename}: cancelled status is not allowed")
            if not {"draft", "final"}.issubset(statuses):
                fail(f"{filename}: must contain both draft and final")
        if filename == "edge_case.json":
            statuses = {report["status"] for report in reports}
            if not STATUSES.issubset(statuses):
                fail(f"{filename}: must contain draft, final, and cancelled")

        for index, report in enumerate(reports):
            validate_report(report, filename, index, units)
            report_ids.append(report["report_id"])
            all_report_types.add(report["report_type"])
            all_statuses.add(report["status"])

    duplicates = [report_id for report_id, count in Counter(report_ids).items() if count > 1]
    if duplicates:
        fail(f"duplicate report_id values: {duplicates}")
    if all_report_types != REPORT_TYPES:
        fail(f"all report types mismatch: {sorted(all_report_types)}")

    return reports_by_file, all_report_types, all_statuses


def main():
    reports_by_file, all_report_types, all_statuses = validate()

    print("Generated files:")
    for filename, reports in reports_by_file.items():
        print(f"- {FILES[filename].relative_to(ROOT)}: {len(reports)} reports")
        for report in reports:
            print(f"  - {report['report_id']}: {report['report_type']} / {report['status']}")
    print("All report_type values:", ", ".join(sorted(all_report_types)))
    print("All status values:", ", ".join(sorted(all_statuses)))
    print("Validation: passed")
    print("All indicator name-unit pairs match data/reference/units_metric.csv")
    print("No duplicate report_id values found")
    print("All cancelled reports have empty indicators")


if __name__ == "__main__":
    main()
