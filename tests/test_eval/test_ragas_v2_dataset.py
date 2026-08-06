from __future__ import annotations

import csv
import json
from pathlib import Path

from eval.run_ragas import APPROVED_ANALYTES, PENDING_ANALYTES, load_jsonl, load_metadata, validate_metadata


DATASET_PATH = Path("eval/datasets/ragas_v2_baseline.jsonl")
MANIFEST_PATH = Path("docs/version-handoff/v2_analyte_manifest.json")


def cases() -> list[dict]:
    return load_jsonl(DATASET_PATH)


def metadata() -> dict:
    return load_metadata(DATASET_PATH)


def project_source_urls() -> set[str]:
    urls: set[str] = set()
    for item in json.loads(Path("data/reference/explanations.json").read_text(encoding="utf-8")):
        urls.update(url for url in item.get("sources", []) if url)
    for item in json.loads(Path("data/reference/reference_ranges_v2.json").read_text(encoding="utf-8")):
        if item.get("source_url"):
            urls.add(item["source_url"])
    with Path("data/reference/quarantine_v2.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("source_url"):
                urls.add(row["source_url"])
    return urls


def test_d01_exactly_12_valid_cases():
    summary = validate_metadata(cases(), metadata())

    assert summary.case_count == 12


def test_d02_unique_sequential_case_ids():
    ids = [case["case_id"] for case in cases()]

    assert ids == [f"RAGAS-V2-{index:03d}" for index in range(1, 13)]
    assert len(ids) == len(set(ids))


def test_d03_only_approved_analytes():
    assert {case["analyte"] for case in cases()} <= APPROVED_ANALYTES


def test_d04_all_approved_analytes_represented():
    assert {case["analyte"] for case in cases()} == APPROVED_ANALYTES


def test_d05_missing_context_policy_enforced():
    empty_context_cases = [case for case in cases() if case["retrieved_contexts"] == []]

    assert [case["case_id"] for case in empty_context_cases] == ["RAGAS-V2-012"]
    assert "missing_context" in empty_context_cases[0]["tags"]


def test_d06_case_008_and_009_have_reversed_context_ranking():
    by_id = {case["case_id"]: case for case in cases()}

    assert by_id["RAGAS-V2-008"]["retrieved_contexts"] == list(
        reversed(by_id["RAGAS-V2-009"]["retrieved_contexts"])
    )


def test_d07_unsupported_claim_case_tagged():
    case = next(item for item in cases() if item["case_id"] == "RAGAS-V2-003")

    assert "expected_low_faithfulness" in case["tags"]
    assert "unsupported_claim" in case["tags"]


def test_d08_no_pending_analytes():
    assert {case["analyte"] for case in cases()}.isdisjoint(PENDING_ANALYTES)


def test_d09_no_real_patient_data_marker():
    assert metadata()["contains_real_patient_data"] is False


def test_d10_metadata_and_jsonl_agree():
    data = cases()
    meta = metadata()

    assert meta["case_count"] == len(data)
    assert meta["dataset_version"] == {case["dataset_version"] for case in data}.pop()


def test_d11_source_urls_come_from_project_reference_evidence():
    evidence_urls = project_source_urls()

    for case in cases():
        assert all(url in evidence_urls for url in case["source_urls"])


def test_d12_manifest_ragas_flags_agree_with_dataset_coverage():
    manifest = {
        record["analyte"]: record
        for record in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    }
    dataset_analytes = {case["analyte"] for case in cases()}

    assert {analyte for analyte, record in manifest.items() if record["ragas_case_available"]} == dataset_analytes
    assert dataset_analytes == APPROVED_ANALYTES


def test_dataset_contains_no_metric_scores():
    score_keys = {"faithfulness", "context_precision", "hallucination", "hallucination_proxy", "score"}

    for case in cases():
        assert score_keys.isdisjoint(case)
    assert score_keys.isdisjoint(metadata())
