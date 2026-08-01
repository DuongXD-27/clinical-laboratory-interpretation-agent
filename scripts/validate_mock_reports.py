import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "data" / "mock" / "generated"
TEMPLATES = ROOT / "data" / "mock" / "templates"
UNITS_FILE = ROOT / "data" / "reference" / "units_metric.csv"
FILES = {
    "normal.json": GENERATED / "normal.json",
    "abnormal.json": GENERATED / "abnormal.json",
    "edge_case.json": GENERATED / "edge_case.json",
}
TEMPLATE_FILES = {
    "cbc_with_differential": TEMPLATES / "cbc_with_differential.mock.json",
    "glycemic_profile": TEMPLATES / "glycemic_profile.mock.json",
    "lipid_profile": TEMPLATES / "lipid_profile.mock.json",
    "liver_function_basic": TEMPLATES / "liver_function_basic.mock.json",
    "renal_function_blood": TEMPLATES / "renal_function_blood.mock.json",
    "electrolytes_basic": TEMPLATES / "electrolytes.mock.json",
    "general_health_check": TEMPLATES / "general_health_check.mock.json",
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
STRICT_FINAL_REPORT_TYPES = REPORT_TYPES - {"general_health_check"}
GENERAL_HEALTH_COMPLETE_GROUP_TYPES = {
    "cbc_with_differential",
    "glycemic_profile",
    "lipid_profile",
    "renal_function_blood",
}


def fail(message):
    raise AssertionError(message)


def load_units():
    with UNITS_FILE.open(newline="", encoding="utf-8-sig") as file:
        return {
            (row["test_name"], row["standardized_unit"])
            for row in csv.DictReader(file)
        }


def indicator_names(report):
    return [indicator["name"] for indicator in report["indicators"]]


def load_template_indicator_names():
    template_names = {}
    for report_type, path in TEMPLATE_FILES.items():
        with path.open(encoding="utf-8") as file:
            template = json.load(file)
        if template.get("report_type") != report_type:
            fail(
                f"{path.relative_to(ROOT)}: expected report_type "
                f"{report_type!r}, got {template.get('report_type')!r}"
            )
        template_names[report_type] = indicator_names(template)
    return template_names


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


def validate_exact_indicator_names(actual, expected, context):
    actual_names = set(actual)
    expected_names = set(expected)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing or extra:
        detail = []
        if missing:
            detail.append(f"missing={missing}")
        if extra:
            detail.append(f"extra={extra}")
        fail(f"{context}: final indicator names mismatch: {', '.join(detail)}")


def validate_general_health_check_indicator_names(report, context, template_names):
    actual = set(indicator_names(report))
    allowed = set(template_names["general_health_check"])
    extra = sorted(actual - allowed)
    if extra:
        fail(f"{context}: general_health_check has indicator names outside template: {extra}")

    complete_groups = []
    incomplete_groups = []
    for report_type in sorted(GENERAL_HEALTH_COMPLETE_GROUP_TYPES):
        group_names = set(template_names[report_type])
        present = actual & group_names
        if present == group_names:
            complete_groups.append(report_type)
        elif present:
            missing = sorted(group_names - present)
            incomplete_groups.append(f"{report_type} missing={missing}")

    if incomplete_groups:
        fail(f"{context}: incomplete general_health_check groups: {incomplete_groups}")
    if not complete_groups:
        fail(
            f"{context}: general_health_check final report must include at least "
            "one complete test group"
        )


def validate_date(value, context):
    if not isinstance(value, str):
        fail(f"{context}: test_date must be a string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        fail(f"{context}: invalid YYYY-MM-DD date {value!r}: {exc}")
    if parsed.strftime("%Y-%m-%d") != value:
        fail(f"{context}: invalid canonical date {value!r}")


def validate_report(report, filename, index, units, template_names):
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

    report_type = report["report_type"]
    if report["status"] == "final" and report_type in STRICT_FINAL_REPORT_TYPES:
        validate_exact_indicator_names(
            names,
            template_names[report_type],
            context,
        )
    if report["status"] == "final" and report_type == "general_health_check":
        validate_general_health_check_indicator_names(report, context, template_names)


def validate():
    units = load_units()
    template_names = load_template_indicator_names()
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
            validate_report(report, filename, index, units, template_names)
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
