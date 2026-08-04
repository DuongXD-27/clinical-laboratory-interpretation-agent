from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.ragas_compat import import_ragas_api


DATASET_VERSION = "v2-baseline-1"
CASE_ID_PATTERN = re.compile(r"^RAGAS-V2-\d{3}$")
APPROVED_ANALYTES = {"WBC", "RBC", "Fasting plasma glucose", "Creatinine"}
PENDING_ANALYTES = {"HGB", "HDL-C", "HbA1c", "LDL-C", "Potassium"}
REQUIRED_FIELDS = {
    "case_id",
    "dataset_version",
    "analyte",
    "user_input",
    "response",
    "reference",
    "retrieved_contexts",
    "source_urls",
    "tags",
    "fixture_origin",
    "notes",
}
PROHIBITED_TEXT = {
    "chẩn đoán",
    "chan doan",
    "điều trị",
    "dieu tri",
    "thuốc",
    "toa thuốc",
    "patient id",
    "hospital number",
    "ngày sinh",
    "date of birth",
    "địa chỉ",
    "số điện thoại",
}
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{12,}"),
]


class DatasetValidationError(Exception):
    pass


@dataclass(frozen=True)
class ValidationSummary:
    dataset_version: str
    case_count: int
    approved_analytes: tuple[str, ...]
    pending_analytes_used: tuple[str, ...]
    pii_check_pass: bool
    metadata_case_count_matches: bool
    contains_real_patient_data: bool
    live_evaluation_status: str


def load_jsonl(path: Path) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    item = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise DatasetValidationError(f"Malformed JSON on line {line_number}: {exc.msg}") from exc
                if not isinstance(item, dict):
                    raise DatasetValidationError(f"Line {line_number} must contain a JSON object")
                cases.append(item)
    except FileNotFoundError as exc:
        raise DatasetValidationError(f"Dataset file not found: {path}") from exc
    return cases


def metadata_path_for(dataset_path: Path) -> Path:
    return dataset_path.with_suffix(".meta.json")


def load_metadata(dataset_path: Path) -> dict[str, Any]:
    path = metadata_path_for(dataset_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DatasetValidationError(f"Metadata file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"Malformed metadata JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise DatasetValidationError("Metadata must be a JSON object")
    return data


def project_source_urls() -> set[str]:
    urls: set[str] = set()
    explanations_path = Path("data/reference/explanations.json")
    if explanations_path.exists():
        for item in json.loads(explanations_path.read_text(encoding="utf-8")):
            urls.update(url for url in item.get("sources", []) if url)

    runtime_path = Path("data/reference/reference_ranges_v2.json")
    if runtime_path.exists():
        for item in json.loads(runtime_path.read_text(encoding="utf-8")):
            if item.get("source_url"):
                urls.add(str(item["source_url"]))

    quarantine_path = Path("data/reference/quarantine_v2.csv")
    if quarantine_path.exists():
        with quarantine_path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("source_url"):
                    urls.add(row["source_url"])
    return urls


def text_values(case: dict[str, object]) -> list[str]:
    values = [
        str(case.get("user_input", "")),
        str(case.get("response", "")),
        str(case.get("reference", "")),
        str(case.get("notes", "")),
    ]
    values.extend(str(item) for item in case.get("retrieved_contexts", []) if isinstance(item, str))
    return values


def validate_cases(cases: list[dict[str, object]]) -> ValidationSummary:
    errors: list[str] = []
    if len(cases) != 12:
        errors.append(f"expected 12 cases, found {len(cases)}")

    ids = [str(case.get("case_id", "")) for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("case_id values must be unique")
    if any(not CASE_ID_PATTERN.match(case_id) for case_id in ids):
        errors.append("case_id values must match RAGAS-V2-###")

    versions = {case.get("dataset_version") for case in cases}
    if versions != {DATASET_VERSION}:
        errors.append(f"dataset_version must be exactly {DATASET_VERSION}")

    analytes = {str(case.get("analyte", "")) for case in cases}
    pending_used = sorted(analytes & PENDING_ANALYTES)
    if not analytes <= APPROVED_ANALYTES:
        errors.append("dataset contains analytes outside the approved TIP-004A scope")
    if analytes != APPROVED_ANALYTES:
        errors.append("dataset must represent all four approved analytes")

    seen_payloads: set[str] = set()
    evidence_urls = project_source_urls()
    pii_check_pass = True
    for index, case in enumerate(cases, start=1):
        missing = REQUIRED_FIELDS - set(case)
        if missing:
            errors.append(f"case {index} missing fields: {', '.join(sorted(missing))}")

        for field in ("user_input", "response", "reference"):
            if not str(case.get(field, "")).strip():
                errors.append(f"{case.get('case_id')} has empty {field}")

        contexts = case.get("retrieved_contexts")
        tags = case.get("tags")
        source_urls = case.get("source_urls")
        if not isinstance(contexts, list) or not all(isinstance(item, str) for item in contexts):
            errors.append(f"{case.get('case_id')} retrieved_contexts must be a list of strings")
        if not isinstance(source_urls, list) or not all(isinstance(item, str) for item in source_urls):
            errors.append(f"{case.get('case_id')} source_urls must be a list of strings")
        elif any(not item.strip() for item in source_urls):
            errors.append(f"{case.get('case_id')} source_urls must not contain empty values")
        elif any(item not in evidence_urls for item in source_urls):
            errors.append(f"{case.get('case_id')} contains a source URL not present in project evidence")

        if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
            errors.append(f"{case.get('case_id')} tags must be a list of strings")
        elif len(tags) != len(set(tags)):
            errors.append(f"{case.get('case_id')} tags must be unique")

        if contexts == [] and (not isinstance(tags, list) or "missing_context" not in tags):
            errors.append(f"{case.get('case_id')} empty retrieved_contexts require missing_context tag")
        if contexts != [] and isinstance(tags, list) and "missing_context" in tags:
            errors.append(f"{case.get('case_id')} missing_context tag requires empty retrieved_contexts")

        payload = json.dumps({key: value for key, value in case.items() if key != "case_id"}, sort_keys=True)
        if payload in seen_payloads:
            errors.append(f"{case.get('case_id')} duplicates another case payload")
        seen_payloads.add(payload)

        combined = "\n".join(text_values(case)).casefold()
        if any(pattern.search(combined) for pattern in SECRET_PATTERNS):
            errors.append(f"{case.get('case_id')} contains a secret-like token")
        if any(term in combined for term in PROHIBITED_TEXT):
            pii_check_pass = False
            errors.append(f"{case.get('case_id')} contains prohibited PII, diagnosis, or treatment language")
        if any(analyte.casefold() in combined for analyte in PENDING_ANALYTES):
            errors.append(f"{case.get('case_id')} contains a pending-analyte range claim")

    cases_by_id = {case.get("case_id"): case for case in cases}
    case_008 = cases_by_id.get("RAGAS-V2-008", {})
    case_009 = cases_by_id.get("RAGAS-V2-009", {})
    if case_008.get("retrieved_contexts") != list(reversed(case_009.get("retrieved_contexts", []))):
        errors.append("cases 008 and 009 must contain the same logical contexts in opposite order")

    if errors:
        raise DatasetValidationError("; ".join(errors))

    return ValidationSummary(
        dataset_version=DATASET_VERSION,
        case_count=len(cases),
        approved_analytes=tuple(sorted(analytes)),
        pending_analytes_used=tuple(pending_used),
        pii_check_pass=pii_check_pass,
        metadata_case_count_matches=False,
        contains_real_patient_data=False,
        live_evaluation_status="unknown",
    )


def validate_metadata(cases: list[dict[str, object]], metadata: dict[str, Any]) -> ValidationSummary:
    summary = validate_cases(cases)
    errors: list[str] = []
    if metadata.get("case_count") != len(cases):
        errors.append("metadata case_count must equal JSONL case count")
    if metadata.get("contains_real_patient_data") is not False:
        errors.append("metadata contains_real_patient_data must be false")
    if metadata.get("live_evaluation_status") != "not_run":
        errors.append("metadata live_evaluation_status must remain not_run")
    if set(metadata.get("approved_analytes", [])) != APPROVED_ANALYTES:
        errors.append("metadata approved_analytes must match TIP-004A scope")
    if errors:
        raise DatasetValidationError("; ".join(errors))
    return ValidationSummary(
        dataset_version=summary.dataset_version,
        case_count=summary.case_count,
        approved_analytes=summary.approved_analytes,
        pending_analytes_used=summary.pending_analytes_used,
        pii_check_pass=summary.pii_check_pass,
        metadata_case_count_matches=True,
        contains_real_patient_data=False,
        live_evaluation_status="not_run",
    )


def build_ragas_dataset(cases: list[dict[str, object]]):
    api = import_ragas_api()
    samples = [
        api.SingleTurnSample(
            user_input=str(case["user_input"]),
            response=str(case["response"]),
            reference=str(case["reference"]),
            retrieved_contexts=list(case["retrieved_contexts"]),
        )
        for case in cases
    ]
    return api.EvaluationDataset(samples=samples)


def inspect_metric_api() -> dict[str, str]:
    api = import_ragas_api()
    return {
        "ragas_version": api.ragas_version,
        "compatibility_shim_applied": str(api.compatibility_shim_applied),
        "SingleTurnSample": api.SingleTurnSample.__name__,
        "EvaluationDataset": api.EvaluationDataset.__name__,
        "Faithfulness": api.Faithfulness.__name__,
        "ContextPrecision": api.ContextPrecision.__name__,
    }


def print_summary(summary: ValidationSummary, dataset_constructed: bool, metrics: dict[str, str]) -> None:
    print(f"Dataset: {summary.dataset_version}")
    print(f"Cases: {summary.case_count}")
    print(f"Approved analytes: {len(summary.approved_analytes)}")
    print(f"Pending analytes used: {len(summary.pending_analytes_used)}")
    print(f"PII check: {'PASS' if summary.pii_check_pass and not summary.contains_real_patient_data else 'FAIL'}")
    print(f"RAGAS dataset construction: {'PASS' if dataset_constructed else 'FAIL'}")
    print(f"Faithfulness API available: {'PASS' if metrics.get('Faithfulness') == 'Faithfulness' else 'FAIL'}")
    print(f"ContextPrecision API available: {'PASS' if metrics.get('ContextPrecision') == 'ContextPrecision' else 'FAIL'}")
    print("Live evaluation executed: NO")


def run_validate(dataset_path: Path, *, inspect: bool = False) -> int:
    cases = load_jsonl(dataset_path)
    metadata = load_metadata(dataset_path)
    summary = validate_metadata(cases, metadata)
    dataset = build_ragas_dataset(cases)
    metrics = inspect_metric_api()
    print_summary(summary, dataset_constructed=dataset is not None, metrics=metrics)
    if inspect:
        print(f"RAGAS version: {metrics['ragas_version']}")
        print(f"Compatibility shim applied: {metrics['compatibility_shim_applied']}")
        print(f"SingleTurnSample: {metrics['SingleTurnSample']}")
        print(f"EvaluationDataset: {metrics['EvaluationDataset']}")
        print(f"Faithfulness: {metrics['Faithfulness']}")
        print(f"ContextPrecision: {metrics['ContextPrecision']}")
        print("Metric scores generated: NO")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline RAGAS V2 dataset validator.")
    parser.add_argument("--dataset", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    parser.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.live:
        print("Live evaluation is prohibited in TIP-004A.", file=sys.stderr)
        return 3
    try:
        return run_validate(args.dataset, inspect=args.inspect)
    except DatasetValidationError as exc:
        print(f"Dataset validation failed: {exc}", file=sys.stderr)
        return 1
    except (ImportError, RuntimeError, ModuleNotFoundError) as exc:
        print(f"RAGAS API unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
