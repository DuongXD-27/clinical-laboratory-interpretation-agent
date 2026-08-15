"""Small, evidence-only runner for the VMEC-05 G2 evaluation.

This script calls the running API over HTTP. It never records bearer tokens or
provider API keys. Product code and product configuration are not modified.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"
SERVER_LOG = Path(
    os.environ.get(
        "G2_SERVER_LOG",
        str(ROOT / "eval" / "raw" / "g2_server_stderr.log"),
    )
)
TIMING_PREFIX = "request_timing "


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def guest_headers(client: httpx.Client) -> dict[str, str]:
    response = client.post(f"{BASE_URL}/api/v1/auth/guest")
    response.raise_for_status()
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def parse_server_timings() -> dict[str, dict[str, Any]]:
    if not SERVER_LOG.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        marker = line.find(TIMING_PREFIX)
        if marker < 0:
            continue
        raw = line[marker + len(TIMING_PREFIX) :].strip()
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        request_id = str(record.get("request_id", ""))
        if request_id:
            records[request_id] = record
    return records


def wait_for_timing(request_id: str, timeout_seconds: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        record = parse_server_timings().get(request_id)
        if record:
            return record
        time.sleep(0.1)
    return {}


def event_evidence(timing: dict[str, Any], indicator_count: int) -> dict[str, Any]:
    events = timing.get("events") or []
    llm_events = [event for event in events if event.get("name") == "llm-explanation-call"]
    attempted = bool(llm_events)
    succeeded = attempted and all(event.get("outcome") == "success" for event in llm_events)
    successful_count = sum(event.get("outcome") == "success" for event in llm_events)
    fallback = (
        any(event.get("outcome") != "success" for event in llm_events)
        or successful_count < indicator_count
    )
    return {
        "provider": "OpenAI-compatible/ChatOpenAI",
        "model": "gpt-4o-mini",
        "call_attempted": attempted,
        "call_success": succeeded,
        "fallback_used": fallback,
        "successful_call_count": successful_count,
        "indicator_count": indicator_count,
        "request_id": timing.get("request_id"),
        "events": llm_events,
    }


def call_analyze(
    client: httpx.Client,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.post(f"{BASE_URL}/api/v1/analyze", headers=headers, json=payload)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    request_id = response.headers.get("x-request-id", "")
    timing = wait_for_timing(request_id)
    try:
        body: Any = response.json()
    except ValueError:
        body = {"raw_text": response.text}
    return {
        "timestamp": utc_now(),
        "request": payload,
        "status_code": response.status_code,
        "request_id": request_id,
        "server_timing_header": response.headers.get("server-timing", ""),
        "http_total_ms": elapsed_ms,
        "actual_response": body,
        "timing_record": timing,
        "llm_evidence": event_evidence(timing, len(payload.get("indicators") or [])),
    }


def smoke() -> None:
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-08-15",
        "language": "vi",
        "indicators": [{"name": "WBC", "value": 7.0, "unit": "10^9/L"}],
    }
    with httpx.Client(timeout=120.0) as client:
        result = call_analyze(client, guest_headers(client), payload)
    write_json(ROOT / "eval" / "raw" / "llm_smoke.json", result)
    evidence = result["llm_evidence"]
    print(f"SMOKE_HTTP_STATUS={result['status_code']}")
    print(f"SMOKE_REQUEST_ID={result['request_id']}")
    print(f"LLM_CALL_ATTEMPTED={str(evidence['call_attempted']).upper()}")
    print(f"LLM_CALL_SUCCESS={str(evidence['call_success']).upper()}")
    print(f"LLM_FALLBACK_USED={str(evidence['fallback_used']).upper()}")


def manual(output_dir: str = "manual") -> None:
    common = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-08-15",
        "language": "vi",
    }
    cases = [
        (
            "TC-G2-01",
            "Normal supported flow",
            {"name": "Potassium", "value": 4.5, "unit": "mmol/L"},
            {"ri_status": "normal", "critical": False},
        ),
        (
            "TC-G2-02",
            "Abnormal, non-critical",
            {"name": "Potassium", "value": 5.8, "unit": "mmol/L"},
            {"ri_status": "high", "critical": False},
        ),
        (
            "TC-G2-03",
            "Critical high",
            {"name": "Potassium", "value": 6.5, "unit": "mmol/L"},
            {
                "ri_status": "high",
                "response_status": "critical_high",
                "critical": True,
                "critical_direction": "high",
            },
        ),
        (
            "TC-G2-04",
            "Critical low fasting plasma glucose",
            {"name": "Fasting plasma glucose", "value": 3.05, "unit": "mmol/L"},
            {
                "ri_status": "low",
                "response_status": "critical_low",
                "critical": True,
                "critical_direction": "low",
            },
        ),
        (
            "TC-G2-05",
            "Generic Glucose fails closed",
            {"name": "Glucose", "value": 5.2, "unit": "mmol/L"},
            {"ri_status": "unknown", "critical": False, "reference_bounds": None},
        ),
    ]
    with httpx.Client(timeout=120.0) as client:
        headers = guest_headers(client)
        for test_id, purpose, indicator, expected in cases:
            payload = {**common, "indicators": [indicator]}
            raw = call_analyze(client, headers, payload)
            response = raw["actual_response"] if isinstance(raw["actual_response"], dict) else {}
            actual_indicator = (response.get("indicators") or [{}])[0]
            actual_status = str(actual_indicator.get("status", "")).lower()
            status_ok = actual_status == expected.get("response_status", expected["ri_status"])
            critical_ok = bool(response.get("has_critical_values")) == expected["critical"]
            if expected.get("reference_bounds") is None and test_id == "TC-G2-05":
                bounds_ok = actual_indicator.get("reference_low") is None and actual_indicator.get("reference_high") is None
            else:
                bounds_ok = True
            llm_ok = raw["llm_evidence"]["call_success"] and not raw["llm_evidence"]["fallback_used"]
            llm_requirement_ok = (
                not raw["llm_evidence"]["call_attempted"]
                if test_id == "TC-G2-05"
                else llm_ok
            )
            verdict = "PASS" if raw["status_code"] == 200 and status_ok and critical_ok and bounds_ok and llm_requirement_ok else "FAIL"
            artifact = {
                "test_id": test_id,
                "purpose": purpose,
                "timestamp": raw["timestamp"],
                "request": raw["request"],
                "expected": expected,
                "actual_response": raw["actual_response"],
                "llm_evidence": raw["llm_evidence"],
                "latency_ms": raw["http_total_ms"],
                "request_id": raw["request_id"],
                "status_code": raw["status_code"],
                "server_timing_header": raw["server_timing_header"],
                "verdict": verdict,
            }
            write_json(ROOT / "eval" / output_dir / f"{test_id}.json", artifact)
            print(f"{test_id}={verdict};REQUEST_ID={raw['request_id']}")


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def extract_metric(timing: dict[str, Any], name: str) -> float | None:
    metrics = timing.get("metrics_ms") or {}
    raw = metrics.get(name)
    if isinstance(raw, (int, float)):
        return float(raw)
    events = timing.get("events") or []
    matching = [event.get("duration_ms") for event in events if event.get("name") == name]
    numeric = [float(value) for value in matching if isinstance(value, (int, float))]
    return sum(numeric) if numeric else None


def summarize(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "mean_ms": round(statistics.fmean(values), 3),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(percentile_nearest_rank(values, 0.95), 3),
        "min_ms": round(min(values), 3),
        "max_ms": round(max(values), 3),
    }


def latency(count: int) -> None:
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-08-15",
        "language": "vi",
        "indicators": [{"name": "WBC", "value": 7.0, "unit": "10^9/L"}],
    }
    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        headers = guest_headers(client)
        for index in range(1, count + 1):
            raw = call_analyze(client, headers, payload)
            timing = raw["timing_record"]
            llm_ms = extract_metric(timing, "llm-explanation-call")
            rag_ms = extract_metric(timing, "rag-call")
            guardrail_ms = extract_metric(timing, "guardrail-rewrite-call")
            evidence = raw["llm_evidence"]
            row = {
                "sequence": index,
                "timestamp": raw["timestamp"],
                "request_id": raw["request_id"],
                "http_total_ms": raw["http_total_ms"],
                "llm_explanation_call_ms": llm_ms,
                "rag_call_ms": rag_ms,
                "guardrail_rewrite_ms": guardrail_ms,
                "status_code": raw["status_code"],
                "success": raw["status_code"] == 200 and evidence["call_success"] and not evidence["fallback_used"],
            }
            rows.append(row)
            print(f"LATENCY_{index:02d}_SUCCESS={str(row['success']).upper()};HTTP_MS={row['http_total_ms']}")
    http_values = [row["http_total_ms"] for row in rows]
    llm_values = [row["llm_explanation_call_ms"] for row in rows if row["llm_explanation_call_ms"] is not None]
    artifact = {
        "generated_at": utc_now(),
        "configuration": {
            "input": payload,
            "real_llm": True,
            "provider": "OpenAI-compatible/ChatOpenAI",
            "model": "gpt-4o-mini",
            "rag_enabled": True,
        },
        "N": len(rows),
        "successful_N": sum(1 for row in rows if row["success"]),
        "http_total": summarize(http_values),
        "llm_explanation_call": summarize(llm_values),
        "requests": rows,
    }
    write_json(ROOT / "eval" / "performance" / "latency_20_requests.json", artifact)


def ocr() -> None:
    samples = ["normal", "blur", "lowlight", "skew"]
    with httpx.Client(timeout=180.0) as client:
        headers = guest_headers(client)
        for condition in samples:
            image = ROOT / "data" / "ocr_samples" / condition / "report.png"
            started = time.perf_counter()
            with image.open("rb") as handle:
                response = client.post(
                    f"{BASE_URL}/api/v1/ocr/upload",
                    headers=headers,
                    data={"consent_acknowledged": "true"},
                    files={"file": (f"{condition}_report.png", handle, "image/png")},
                )
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            try:
                body: Any = response.json()
            except ValueError:
                body = {"raw_text": response.text}
            if isinstance(body, dict):
                body.pop("review_token", None)
            artifact = {
                "condition": condition,
                "timestamp": utc_now(),
                "image": str(image.relative_to(ROOT)).replace("\\", "/"),
                "status_code": response.status_code,
                "request_id": response.headers.get("x-request-id", ""),
                "latency_ms": elapsed_ms,
                "actual_response": body,
            }
            write_json(ROOT / "eval" / "ocr" / "raw_outputs" / f"{condition}_report.json", artifact)
            print(f"OCR_{condition.upper()}_STATUS={response.status_code};REQUEST_ID={artifact['request_id']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["smoke", "manual", "latency", "ocr"])
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--output-dir", default="manual")
    args = parser.parse_args()
    if args.mode == "smoke":
        smoke()
    elif args.mode == "manual":
        manual(args.output_dir)
    elif args.mode == "latency":
        latency(args.count)
    else:
        ocr()


if __name__ == "__main__":
    main()
