from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from eval.run_ragas import (
    APPROVED_ANALYTES,
    DatasetValidationError,
    build_ragas_dataset,
    inspect_metric_api,
    load_jsonl,
    main,
    validate_cases,
)

DATASET_PATH = Path("eval/datasets/ragas_v2_baseline.jsonl")
EXPECTED_CASE_COUNT = 27
FORBIDDEN_KEYS = {"OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "ANTHROPIC_API_KEY"}


def valid_cases() -> list[dict]:
    return load_jsonl(DATASET_PATH)


def test_r01_valid_jsonl_loads():
    assert len(valid_cases()) == EXPECTED_CASE_COUNT


def test_r02_malformed_json_line_produces_clear_failure(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"case_id": "RAGAS-V2-001"\n', encoding="utf-8")

    with pytest.raises(DatasetValidationError, match="Malformed JSON on line 1"):
        load_jsonl(path)


def test_r03_duplicate_case_id_rejected():
    cases = valid_cases()
    cases[1] = {**cases[1], "case_id": cases[0]["case_id"]}

    with pytest.raises(DatasetValidationError, match="case_id values must be unique"):
        validate_cases(cases)


def test_r04_unapproved_analyte_rejected():
    cases = valid_cases()
    cases[0] = {**cases[0], "analyte": "Troponin"}

    with pytest.raises(DatasetValidationError, match="outside the approved"):
        validate_cases(cases)


def test_r05_unpermitted_empty_context_rejected():
    cases = valid_cases()
    cases[0] = {**cases[0], "retrieved_contexts": []}

    with pytest.raises(DatasetValidationError, match="empty retrieved_contexts require missing_context"):
        validate_cases(cases)


def test_r06_valid_cases_convert_to_single_turn_samples():
    dataset = build_ragas_dataset(valid_cases())

    assert len(dataset.samples) == EXPECTED_CASE_COUNT
    assert all(sample.__class__.__name__ == "SingleTurnSample" for sample in dataset.samples)


def test_r07_evaluation_dataset_constructs_successfully():
    assert build_ragas_dataset(valid_cases()).__class__.__name__ == "EvaluationDataset"


def test_r08_faithfulness_class_import_succeeds():
    assert inspect_metric_api()["Faithfulness"] == "Faithfulness"


def test_r09_context_precision_class_import_succeeds():
    assert inspect_metric_api()["ContextPrecision"] == "ContextPrecision"


def test_r10_validate_only_returns_exit_code_0(capsys):
    exit_code = main(["--dataset", str(DATASET_PATH), "--validate-only"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Live evaluation executed: NO" in output


def test_r11_inspect_makes_no_network_call(monkeypatch, capsys):
    def fail_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    exit_code = main(["--dataset", str(DATASET_PATH), "--inspect"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Metric scores generated: NO" in output


def test_r12_live_flag_rejected(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--dataset", str(DATASET_PATH), "--validate-only", "--live"])
    error = capsys.readouterr().err

    assert exc_info.value.code == 2
    assert "not allowed with argument" in error


def test_r13_runner_does_not_read_api_key_environment_variables(monkeypatch):
    class GuardedEnviron(dict):
        def __getitem__(self, key):
            if key in FORBIDDEN_KEYS:
                raise AssertionError(f"forbidden key read: {key}")
            return super().__getitem__(key)

        def get(self, key, default=None):
            if key in FORBIDDEN_KEYS:
                raise AssertionError(f"forbidden key read: {key}")
            return super().get(key, default)

    monkeypatch.setattr(os, "environ", GuardedEnviron(os.environ))

    assert main(["--dataset", str(DATASET_PATH), "--validate-only"]) == 0


def test_r14_no_metric_score_fields_are_generated():
    score_keys = {"faithfulness", "context_precision", "hallucination", "hallucination_proxy", "score"}
    cases = valid_cases()
    metadata = json.loads(Path("eval/datasets/ragas_v2_baseline.meta.json").read_text(encoding="utf-8"))

    assert {case["analyte"] for case in cases} == APPROVED_ANALYTES
    assert all(score_keys.isdisjoint(case) for case in cases)
    assert score_keys.isdisjoint(metadata)
