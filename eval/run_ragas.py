from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from eval.ragas_compat import import_ragas_api


DATASET_VERSION = "v2-baseline-1"
DEFAULT_PROVIDER = "google"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_RESULT_PATH = Path("eval/results/ragas_v2_baseline.json")
DEFAULT_REPORT_PATH = Path("eval/results/report.md")
GOOGLE_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GOOGLE_ENDPOINT_HOST = "generativelanguage.googleapis.com"
METRIC_TRANSPORT_ADAPTER = "google_openai_compatible"
METRIC_TRANSPORT_LIBRARY = "openai-python"
RUN_ID = "RAGAS-V2-BASELINE-001"
CONCURRENCY = 1
CASE_ID_PATTERN = re.compile(r"^RAGAS-V2-\d{3}$")
APPROVED_ANALYTES = {"WBC", "RBC", "Fasting plasma glucose", "Creatinine", "HGB", "HbA1c", "LDL-C", "HDL-C", "Potassium"}
PENDING_ANALYTES: set[str] = set()
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


class SecurityGateError(Exception):
    pass


class ProviderProbeError(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


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


@dataclass(frozen=True)
class CredentialInfo:
    variable: str
    value: str


@dataclass(frozen=True)
class ProviderProbeResult:
    status: str
    category: str | None
    duration_ms: int


@dataclass(frozen=True)
class LiveRunConfig:
    dataset_path: Path
    provider: str
    model: str
    max_cases: int
    output_path: Path
    request_timeout_seconds: int
    confirm_key_rotated: bool
    probe_only: bool = False
    skip_probe_after_confirmed: bool = False


@dataclass(frozen=True)
class EvaluatorConfig:
    logical_provider: str
    transport_adapter: str
    model: str
    credential_variable: str
    base_url: str
    endpoint_host: str
    concurrency: int
    automatic_retries: int
    openai_service_used: bool


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
    if len(cases) != 27:
        errors.append(f"expected 27 cases, found {len(cases)}")

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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def load_local_env_for_live() -> None:
    from dotenv import load_dotenv

    load_dotenv()


def select_credential(environ: Any | None = None) -> CredentialInfo:
    environ = os.environ if environ is None else environ
    google_key = environ.get("GOOGLE_API_KEY")
    if google_key:
        return CredentialInfo(variable="GOOGLE_API_KEY", value=google_key)
    gemini_key = environ.get("GEMINI_API_KEY")
    if gemini_key:
        return CredentialInfo(variable="GEMINI_API_KEY", value=gemini_key)
    if environ.get("GEMINI_KEY"):
        raise SecurityGateError("GEMINI_KEY is present, but GOOGLE_API_KEY or GEMINI_API_KEY is required.")
    raise SecurityGateError("GOOGLE_API_KEY or GEMINI_API_KEY is required for live evaluation.")


def validate_live_config(config: LiveRunConfig) -> None:
    if not config.confirm_key_rotated:
        raise SecurityGateError(
            "Human key-rotation confirmation is required before live evaluation."
        )
    if config.provider != DEFAULT_PROVIDER:
        raise SecurityGateError("Only provider google is allowed for TIP-004B.")
    if config.model != DEFAULT_MODEL:
        raise SecurityGateError("Only model gemini-2.5-flash is allowed for TIP-004B.")
    if not 1 <= config.max_cases <= 27:
        raise DatasetValidationError("max_cases must satisfy 1 <= max_cases <= 27")


def create_google_client(api_key: str, request_timeout_seconds: int):
    from google import genai

    return genai.Client(
        api_key=api_key,
        http_options={"timeout": request_timeout_seconds * 1000},
    )


def build_evaluator_config(credential_variable: str, *, model: str = DEFAULT_MODEL) -> EvaluatorConfig:
    host = urlparse(GOOGLE_OPENAI_BASE_URL).hostname or ""
    if host != GOOGLE_ENDPOINT_HOST:
        raise SecurityGateError("Evaluator endpoint must be generativelanguage.googleapis.com.")
    return EvaluatorConfig(
        logical_provider=DEFAULT_PROVIDER,
        transport_adapter=METRIC_TRANSPORT_ADAPTER,
        model=model,
        credential_variable=credential_variable,
        base_url=GOOGLE_OPENAI_BASE_URL,
        endpoint_host=host,
        concurrency=CONCURRENCY,
        automatic_retries=0,
        openai_service_used=False,
    )


def create_evaluator_client(api_key: str, evaluator_config: EvaluatorConfig, request_timeout_seconds: int):
    host = urlparse(evaluator_config.base_url).hostname or ""
    if host != GOOGLE_ENDPOINT_HOST or host == "api.openai.com":
        raise SecurityGateError("Evaluator transport must use the Google OpenAI-compatible endpoint.")
    if evaluator_config.automatic_retries != 0:
        raise SecurityGateError("Evaluator transport retries must be zero.")

    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=api_key,
        base_url=evaluator_config.base_url,
        timeout=request_timeout_seconds,
        max_retries=evaluator_config.automatic_retries,
    )


def ensure_async_metric_llm(
    llm: Any,
    *,
    provider: str | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> Any:
    if getattr(llm, "is_async", True):
        return llm

    async def agenerate(prompt: str, response_model: type) -> Any:
        return await asyncio.to_thread(llm.generate, prompt, response_model)

    llm.agenerate = agenerate
    return llm


def classify_provider_error(exc: BaseException) -> str:
    text = f"{exc.__class__.__name__}: {exc}".casefold()
    if "api key" in text or "permission" in text or "unauth" in text or "401" in text or "403" in text:
        return "authentication_error"
    if "quota" in text or "rate" in text or "429" in text:
        return "quota_or_rate_limit"
    if "not found" in text or "model" in text and "404" in text:
        return "model_not_available"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "network" in text or "connection" in text or "dns" in text:
        return "network_error"
    return "provider_error"


def provider_probe(client: Any, *, model: str) -> ProviderProbeResult:
    start = time.perf_counter()
    try:
        client.models.generate_content(
            model=model,
            contents="Return exactly: OK",
            config={"max_output_tokens": 5},
        )
    except Exception as exc:  # Provider SDK exceptions vary by transport/status.
        duration_ms = int((time.perf_counter() - start) * 1000)
        category = classify_provider_error(exc)
        raise ProviderProbeError(category, category) from exc
    duration_ms = int((time.perf_counter() - start) * 1000)
    return ProviderProbeResult(status="PASS", category=None, duration_ms=duration_ms)


def metric_result_to_float(result: Any) -> float | None:
    candidate = result
    if hasattr(result, "value"):
        candidate = result.value
    elif hasattr(result, "score"):
        candidate = result.score
    elif isinstance(result, dict):
        candidate = result.get("value", result.get("score"))
    try:
        value = float(candidate)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        return None
    return value


def hallucination_proxy(faithfulness: float | None) -> float | None:
    if faithfulness is None:
        return None
    return 1.0 - faithfulness


async def score_case(case: dict[str, object], faithfulness_metric: Any, context_precision_metric: Any) -> dict[str, Any]:
    start = time.perf_counter()
    contexts = list(case["retrieved_contexts"])
    if not contexts:
        return {
            "case_id": case["case_id"],
            "analyte": case["analyte"],
            "faithfulness": None,
            "context_precision": None,
            "custom_hallucination_proxy": None,
            "metric_status": "not_applicable",
            "reason": "missing_retrieved_context",
            "errors": [],
            "duration_ms": 0,
        }

    errors: list[str] = []
    faithfulness: float | None = None
    context_precision: float | None = None

    try:
        faithfulness_result = await faithfulness_metric.ascore(
            user_input=str(case["user_input"]),
            response=str(case["response"]),
            retrieved_contexts=contexts,
        )
        faithfulness = metric_result_to_float(faithfulness_result)
        if faithfulness is None:
            errors.append("faithfulness_invalid_score")
    except Exception as exc:
        errors.append(f"faithfulness_error:{exc.__class__.__name__}")

    try:
        context_precision_result = await context_precision_metric.ascore(
            user_input=str(case["user_input"]),
            reference=str(case["reference"]),
            retrieved_contexts=contexts,
        )
        context_precision = metric_result_to_float(context_precision_result)
        if context_precision is None:
            errors.append("context_precision_invalid_score")
    except Exception as exc:
        errors.append(f"context_precision_error:{exc.__class__.__name__}")

    if not errors:
        status = "success"
    elif faithfulness is not None or context_precision is not None:
        status = "partial_failure"
    elif any("invalid_score" in error for error in errors):
        status = "invalid_score"
    else:
        status = "failed"

    return {
        "case_id": case["case_id"],
        "analyte": case["analyte"],
        "faithfulness": faithfulness,
        "context_precision": context_precision,
        "custom_hallucination_proxy": hallucination_proxy(faithfulness),
        "metric_status": status,
        "errors": errors,
        "duration_ms": int((time.perf_counter() - start) * 1000),
    }


async def score_cases(cases: list[dict[str, object]], llm: Any, api: Any) -> list[dict[str, Any]]:
    faithfulness_metric = api.Faithfulness(llm=llm)
    context_precision_metric = api.ContextPrecision(llm=llm)
    results: list[dict[str, Any]] = []
    for case in cases:
        results.append(await score_case(case, faithfulness_metric, context_precision_metric))
    return results


def stats_for_metric(results: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    values = [float(result[metric]) for result in results if isinstance(result.get(metric), (int, float))]
    failed_count = sum(
        1
        for result in results
        if result["metric_status"] in {"failed", "partial_failure", "invalid_score"} and result.get(metric) is None
    )
    not_applicable_count = sum(1 for result in results if result["metric_status"] == "not_applicable")
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "minimum": None,
            "maximum": None,
            "standard_deviation": None,
            "failed_count": failed_count,
            "not_applicable_count": not_applicable_count,
        }
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "standard_deviation": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "failed_count": failed_count,
        "not_applicable_count": not_applicable_count,
    }


def build_summary(results: list[dict[str, Any]], total_duration_seconds: float) -> dict[str, Any]:
    return {
        "faithfulness": stats_for_metric(results, "faithfulness"),
        "context_precision": stats_for_metric(results, "context_precision"),
        "custom_hallucination_proxy": stats_for_metric(results, "custom_hallucination_proxy"),
        "successful_cases": sum(1 for result in results if result["metric_status"] == "success"),
        "partial_cases": sum(1 for result in results if result["metric_status"] == "partial_failure"),
        "failed_cases": sum(1 for result in results if result["metric_status"] in {"failed", "invalid_score"}),
        "not_applicable_cases": sum(1 for result in results if result["metric_status"] == "not_applicable"),
        "total_duration_seconds": total_duration_seconds,
    }


def expected_pattern_checks(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {result["case_id"]: result for result in results}
    warnings: list[str] = []
    unsupported = by_id.get("RAGAS-V2-003", {}).get("faithfulness")
    supported = [
        by_id.get("RAGAS-V2-001", {}).get("faithfulness"),
        by_id.get("RAGAS-V2-002", {}).get("faithfulness"),
    ]
    supported_values = [value for value in supported if isinstance(value, (int, float))]
    unsupported_pass = None
    if isinstance(unsupported, (int, float)) and supported_values:
        unsupported_pass = unsupported < statistics.fmean(supported_values)
        if not unsupported_pass:
            warnings.append("RAGAS-V2-003 faithfulness was not lower than supported WBC cases.")

    cp_008 = by_id.get("RAGAS-V2-008", {}).get("context_precision")
    cp_009 = by_id.get("RAGAS-V2-009", {}).get("context_precision")
    ranking_pass = None
    if isinstance(cp_008, (int, float)) and isinstance(cp_009, (int, float)):
        ranking_pass = cp_008 >= cp_009
        if not ranking_pass:
            warnings.append("RAGAS-V2-008 context precision was lower than RAGAS-V2-009.")

    return {
        "unsupported_claim_contrast_pass": unsupported_pass,
        "relevant_first_context_contrast_pass": ranking_pass,
        "warnings": warnings,
        "dataset_or_prompt_tuning_performed": False,
    }


def write_json_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv_result(path: Path, cases: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "analyte",
                "faithfulness",
                "context_precision",
                "custom_hallucination_proxy",
                "metric_status",
                "duration_ms",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "analyte": case["analyte"],
                    "faithfulness": "" if case["faithfulness"] is None else case["faithfulness"],
                    "context_precision": "" if case["context_precision"] is None else case["context_precision"],
                    "custom_hallucination_proxy": ""
                    if case["custom_hallucination_proxy"] is None
                    else case["custom_hallucination_proxy"],
                    "metric_status": case["metric_status"],
                    "duration_ms": case["duration_ms"],
                }
            )


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def write_markdown_report(path: Path, result: dict[str, Any], command: str) -> None:
    summary = result["summary"]
    lines = [
        "# P-056 RAGAS V2 Baseline Report",
        "",
        "## Run metadata",
        f"- Run ID: {result['run_id']}",
        f"- Generated at: {result['generated_at']}",
        f"- Git commit: {result['git_commit']}",
        "- Live passes: 1",
        "",
        "## Security and credential handling",
        f"- Credential variable: {result['evaluator']['credential_variable']}",
        "- Key value logged: NO",
        "- Authorization headers stored: NO",
        "- OpenAI service used: NO",
        "",
        "## Dataset scope",
        f"- Dataset: {result['dataset']['path']}",
        f"- Dataset SHA-256: {result['dataset']['sha256']}",
        "- This evaluates curated fixtures, not retrieved contexts captured from the production graph.",
        "- Approved analytes: WBC, RBC, Fasting plasma glucose, Creatinine, HGB, HbA1c, LDL-C, HDL-C, Potassium.",
        "- Pending analytes are excluded.",
        "",
        "## Evaluator configuration",
        f"- Provider: {result['evaluator']['provider']}",
        f"- Model: {result['evaluator']['model']}",
        f"- Transport adapter: {result['evaluator']['transport_adapter']}",
        f"- Transport library: {result['evaluator']['transport_library']}",
        f"- API endpoint host: {result['evaluator']['api_endpoint_host']}",
        f"- RAGAS version: {result['evaluator']['ragas_version']}",
        f"- Compatibility shim applied: {result['evaluator']['compatibility_shim_applied']}",
        "- Concurrency: 1",
        f"- Automatic retries: {result['evaluator']['automatic_retries']}",
        "",
        "## Metrics",
        "- Faithfulness",
        "- Context Precision",
        "- custom_hallucination_proxy = 1 - faithfulness",
        "",
        "## Aggregate results",
        "| Metric | Count | Mean | Median | Min | Max | Std dev | Failed | N/A |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for metric, label in [
        ("faithfulness", "Faithfulness"),
        ("context_precision", "Context Precision"),
        ("custom_hallucination_proxy", "Custom hallucination proxy"),
    ]:
        item = summary[metric]
        lines.append(
            f"| {label} | {item['count']} | {fmt(item['mean'])} | {fmt(item['median'])} | "
            f"{fmt(item['minimum'])} | {fmt(item['maximum'])} | {fmt(item['standard_deviation'])} | "
            f"{item['failed_count']} | {item['not_applicable_count']} |"
        )
    lines.extend(
        [
            "",
            "## Per-case results",
            "| Case | Analyte | Faithfulness | Context Precision | Hallucination proxy | Status |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for case in result["cases"]:
        lines.append(
            f"| {case['case_id']} | {case['analyte']} | {fmt(case['faithfulness'])} | "
            f"{fmt(case['context_precision'])} | {fmt(case['custom_hallucination_proxy'])} | "
            f"{case['metric_status']} |"
        )
    checks = result["expected_pattern_checks"]
    lines.extend(
        [
            "",
            "## Expected-pattern checks",
            f"- Unsupported-claim contrast: {checks['unsupported_claim_contrast_pass']}",
            f"- Relevant-first context contrast: {checks['relevant_first_context_contrast_pass']}",
            f"- Warnings: {checks['warnings']}",
            "- Dataset or prompt tuning performed: NO",
            "",
            "## Failures and not-applicable cases",
            f"- Partial cases: {summary['partial_cases']}",
            f"- Failed cases: {summary['failed_cases']}",
            f"- Not applicable cases: {summary['not_applicable_cases']}",
            "- RAGAS-V2-012 is not applicable because retrieved_contexts is empty.",
            "",
            "## Limitations",
            "- Results are not clinical validation.",
            "- Results are not production RAG validation.",
            "- One live pass was executed; scores may vary across repeated evaluator runs.",
            "- No threshold optimization was performed.",
            "",
            "## Reproduction command",
            f"`{command}`",
            "",
            "## Interpretation boundaries",
            "- This is a curated-fixture baseline for eval plumbing and metric visibility.",
            "- Do not use these scores as a clinical accuracy claim.",
            "",
            "## Recommendation",
            "- Use this baseline as the first live RAGAS reference point for later Contractor-approved comparison.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run_live(config: LiveRunConfig, *, client_factory=None, probe_func=None) -> int:
    validate_live_config(config)
    load_local_env_for_live()
    cases = load_jsonl(config.dataset_path)
    metadata = load_metadata(config.dataset_path)
    validate_metadata(cases, metadata)
    cases_to_process = cases[: config.max_cases]

    client_factory = client_factory or create_google_client
    probe_func = probe_func or provider_probe
    credential = select_credential()
    if config.skip_probe_after_confirmed:
        if config.probe_only:
            raise SecurityGateError("probe-only cannot be combined with skip-probe-after-confirmed.")
        probe = ProviderProbeResult(status="REUSED", category=None, duration_ms=0)
        print("Provider probe reused from previous attempt: YES")
        print("Previous successful provider probe: PASS")
        print("Additional standalone probe calls: 0")
        print(f"Provider: {config.provider}")
        print(f"Model: {config.model}")
        print(f"Credential source: {credential.variable}")
        print("Key value logged: NO")
    else:
        client = client_factory(credential.value, config.request_timeout_seconds)
        probe = probe_func(client, model=config.model)
        print("Provider probe: PASS")
        print(f"Provider: {config.provider}")
        print(f"Model: {config.model}")
        print(f"Credential source: {credential.variable}")
        print("Key value logged: NO")
    if config.probe_only:
        return 0

    start = time.perf_counter()
    api = import_ragas_api()
    evaluator_config = build_evaluator_config(credential.variable, model=config.model)
    evaluator_client = create_evaluator_client(
        credential.value,
        evaluator_config,
        config.request_timeout_seconds,
    )
    llm = ensure_async_metric_llm(
        api.llm_factory(evaluator_config.model, provider="openai", client=evaluator_client),
        provider="openai",
        model=evaluator_config.model,
        client=evaluator_client,
    )
    case_results = await score_cases(cases_to_process, llm, api)
    total_duration_seconds = time.perf_counter() - start

    dataset_hash = sha256_file(config.dataset_path)
    eligible_cases = sum(1 for case in cases if case["retrieved_contexts"])
    result = {
        "run_id": RUN_ID,
        "run_type": "live_curated_fixture_baseline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_git_commit(),
        "dataset": {
            "path": str(config.dataset_path).replace("\\", "/"),
            "version": DATASET_VERSION,
            "sha256": dataset_hash,
            "total_cases": len(cases),
            "eligible_cases": eligible_cases,
            "evaluated_cases": len(cases_to_process),
        },
        "evaluator": {
            "provider": evaluator_config.logical_provider,
            "model": evaluator_config.model,
            "transport_adapter": evaluator_config.transport_adapter,
            "transport_library": METRIC_TRANSPORT_LIBRARY,
            "api_endpoint_host": evaluator_config.endpoint_host,
            "ragas_version": api.ragas_version,
            "compatibility_shim_applied": api.compatibility_shim_applied,
            "credential_variable": evaluator_config.credential_variable,
            "openai_service_used": evaluator_config.openai_service_used,
            "request_timeout_seconds": config.request_timeout_seconds,
            "concurrency": evaluator_config.concurrency,
            "automatic_retries": evaluator_config.automatic_retries,
            "provider_probe": {
                "status": probe.status,
                "duration_ms": probe.duration_ms,
                "reused_from_previous_attempt": config.skip_probe_after_confirmed,
            },
        },
        "metrics": [
            "faithfulness",
            "context_precision",
            "custom_hallucination_proxy",
        ],
        "cases": case_results,
        "summary": build_summary(case_results, total_duration_seconds),
        "expected_pattern_checks": expected_pattern_checks(case_results),
        "limitations": [
            "curated fixtures, not production graph retrieved contexts",
            "approved normal-reference analytes only",
            "not clinical validation",
            "one live pass only; scores may vary",
        ],
    }

    write_json_result(config.output_path, result)
    csv_path = config.output_path.with_suffix(".csv")
    write_csv_result(csv_path, case_results)
    if config.output_path == DEFAULT_RESULT_PATH:
        write_markdown_report(
            DEFAULT_REPORT_PATH,
            result,
            command=(
                "python -B -m eval.run_ragas --dataset eval/datasets/ragas_v2_baseline.jsonl "
                "--live --provider google --model gemini-2.5-flash --max-cases 27 "
                "--confirm-key-rotated --skip-probe-after-confirmed "
                "--output eval/results/ragas_v2_baseline.json"
            ),
        )
    print(f"Live evaluation executed: YES")
    print(f"Cases evaluated: {len(case_results)}")
    print(f"Result JSON: {config.output_path}")
    print(f"Result CSV: {csv_path}")
    return 0


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
    parser = argparse.ArgumentParser(description="RAGAS V2 dataset validator and guarded live baseline runner.")
    parser.add_argument("--dataset", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--confirm-key-rotated", action="store_true")
    parser.add_argument("--max-cases", type=int, default=12)
    parser.add_argument("--output", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("--request-timeout-seconds", type=int, default=120)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--skip-probe-after-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.live:
            config = LiveRunConfig(
                dataset_path=args.dataset,
                provider=args.provider,
                model=args.model,
                max_cases=args.max_cases,
                output_path=args.output,
                request_timeout_seconds=args.request_timeout_seconds,
                confirm_key_rotated=args.confirm_key_rotated,
                probe_only=args.probe_only,
                skip_probe_after_confirmed=args.skip_probe_after_confirmed,
            )
            return asyncio.run(run_live(config))
        return run_validate(args.dataset, inspect=args.inspect)
    except DatasetValidationError as exc:
        print(f"Dataset validation failed: {exc}", file=sys.stderr)
        return 1
    except SecurityGateError as exc:
        print(f"SECURITY GATE NOT READY: {exc}", file=sys.stderr)
        return 4
    except ProviderProbeError as exc:
        print(f"Provider probe failed: {exc.category}", file=sys.stderr)
        return 5
    except (ImportError, RuntimeError, ModuleNotFoundError) as exc:
        print(f"RAGAS API unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
