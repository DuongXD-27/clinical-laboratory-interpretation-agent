from __future__ import annotations

import json
import math
import os
import socket
from pathlib import Path

import pytest

from eval import run_ragas
from eval.run_ragas import (
    CONCURRENCY,
    LiveRunConfig,
    ProviderProbeError,
    ProviderProbeResult,
    build_summary,
    ensure_async_metric_llm,
    hallucination_proxy,
    main,
    metric_result_to_float,
    run_live,
    score_case,
    select_credential,
)

DATASET_PATH = Path("eval/datasets/ragas_v2_baseline.jsonl")


class Score:
    def __init__(self, value):
        self.value = value


class FakeFaithfulness:
    calls = 0

    def __init__(self, llm):
        self.llm = llm

    async def ascore(self, **kwargs):
        type(self).calls += 1
        return Score(0.75)


class FakeContextPrecision:
    calls = 0

    def __init__(self, llm):
        self.llm = llm

    async def ascore(self, **kwargs):
        type(self).calls += 1
        return Score(0.5)


class FakeApi:
    ragas_version = "0.4.3"
    compatibility_shim_applied = True
    Faithfulness = FakeFaithfulness
    ContextPrecision = FakeContextPrecision

    @staticmethod
    def llm_factory(model, provider, client):
        return {"model": model, "provider": provider, "client": client}


def fake_client_factory(api_key, request_timeout_seconds):
    return {"timeout": request_timeout_seconds}


def fake_probe(client, *, model):
    return ProviderProbeResult(status="PASS", category=None, duration_ms=1)


def config(output_path: Path, *, max_cases: int = 12, confirm: bool = True, probe_only: bool = False) -> LiveRunConfig:
    return LiveRunConfig(
        dataset_path=DATASET_PATH,
        provider="google",
        model="gemini-2.5-flash",
        max_cases=max_cases,
        output_path=output_path,
        request_timeout_seconds=120,
        confirm_key_rotated=confirm,
        probe_only=probe_only,
    )


@pytest.mark.asyncio
async def test_sync_google_llm_is_bridged_for_async_metrics():
    class SyncLLM:
        is_async = False

        def __init__(self):
            self.calls = 0

        def generate(self, prompt, response_model):
            self.calls += 1
            return {"prompt": prompt, "response_model": response_model}

    llm = SyncLLM()
    bridged = ensure_async_metric_llm(llm)

    assert bridged is llm
    assert await bridged.agenerate("prompt", dict) == {"prompt": "prompt", "response_model": dict}
    assert llm.calls == 1


def test_live_01_security_confirmation_required_before_credential_access(monkeypatch, tmp_path: Path):
    class GuardedEnviron(dict):
        def get(self, key, default=None):
            if key in {"GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_KEY"}:
                raise AssertionError(f"credential access attempted before confirmation: {key}")
            return super().get(key, default)

    monkeypatch.setattr(os, "environ", GuardedEnviron())

    exit_code = main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--live",
            "--provider",
            "google",
            "--model",
            "gemini-2.5-flash",
            "--output",
            str(tmp_path / "result.json"),
        ]
    )

    assert exit_code == 4


def test_live_02_standard_key_priority(monkeypatch):
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": "google-secret", "GEMINI_API_KEY": "gemini-secret"})

    assert select_credential().variable == "GOOGLE_API_KEY"


def test_live_03_missing_key(monkeypatch):
    monkeypatch.setattr(os, "environ", {})

    with pytest.raises(run_ragas.SecurityGateError, match="GOOGLE_API_KEY or GEMINI_API_KEY"):
        select_credential()


def test_live_04_gemini_key_rejected(monkeypatch):
    monkeypatch.setattr(os, "environ", {"GEMINI_KEY": "legacy-secret"})

    with pytest.raises(run_ragas.SecurityGateError, match="GEMINI_KEY is present"):
        select_credential()


def test_live_05_openai_key_not_read(monkeypatch):
    class GuardedEnviron(dict):
        def get(self, key, default=None):
            if key == "OPENAI_API_KEY":
                raise AssertionError("OPENAI_API_KEY read")
            return super().get(key, default)

    monkeypatch.setattr(os, "environ", GuardedEnviron({"GOOGLE_API_KEY": "google-secret"}))

    assert select_credential().variable == "GOOGLE_API_KEY"


@pytest.mark.parametrize("max_cases", [0, 28])
def test_live_06_maximum_cases_rejected(max_cases, tmp_path: Path):
    exit_code = main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--live",
            "--provider",
            "google",
            "--model",
            "gemini-2.5-flash",
            "--max-cases",
            str(max_cases),
            "--confirm-key-rotated",
            "--output",
            str(tmp_path / "result.json"),
        ]
    )

    assert exit_code == 1


def test_live_07_no_parallel_execution():
    assert CONCURRENCY == 1


def test_live_08_provider_probe_failure_prevents_metric_execution_and_result_creation(monkeypatch, tmp_path: Path):
    output = tmp_path / "result.json"
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": "google-secret"})
    monkeypatch.setattr(run_ragas, "create_google_client", fake_client_factory)

    def fail_probe(client, *, model):
        raise ProviderProbeError("authentication_error", "authentication_error")

    monkeypatch.setattr(run_ragas, "provider_probe", fail_probe)

    exit_code = main(
        [
            "--dataset",
            str(DATASET_PATH),
            "--live",
            "--provider",
            "google",
            "--model",
            "gemini-2.5-flash",
            "--max-cases",
            "1",
            "--confirm-key-rotated",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 5
    assert not output.exists()


@pytest.mark.asyncio
async def test_live_09_missing_context_skips_evaluator_invocation():
    case = {
        "case_id": "RAGAS-V2-012",
        "analyte": "WBC",
        "user_input": "q",
        "response": "r",
        "reference": "ref",
        "retrieved_contexts": [],
    }
    FakeFaithfulness.calls = 0
    FakeContextPrecision.calls = 0

    result = await score_case(case, FakeFaithfulness(None), FakeContextPrecision(None))

    assert result["metric_status"] == "not_applicable"
    assert result["faithfulness"] is None
    assert result["context_precision"] is None
    assert FakeFaithfulness.calls == 0
    assert FakeContextPrecision.calls == 0


@pytest.mark.parametrize("value", [-0.1, 1.1, math.nan, math.inf, "bad"])
def test_live_10_numeric_score_validation(value):
    assert metric_result_to_float(Score(value)) is None


def test_live_11_hallucination_proxy():
    assert hallucination_proxy(0.75) == 0.25


def test_live_12_null_propagation():
    assert hallucination_proxy(None) is None


def test_live_13_aggregate_statistics_only_valid_scores():
    summary = build_summary(
        [
            {"faithfulness": 1.0, "context_precision": 0.5, "custom_hallucination_proxy": 0.0, "metric_status": "success"},
            {"faithfulness": None, "context_precision": None, "custom_hallucination_proxy": None, "metric_status": "failed"},
            {"faithfulness": None, "context_precision": None, "custom_hallucination_proxy": None, "metric_status": "not_applicable"},
        ],
        total_duration_seconds=1.0,
    )

    assert summary["faithfulness"]["count"] == 1
    assert summary["faithfulness"]["failed_count"] == 1
    assert summary["faithfulness"]["not_applicable_count"] == 1


@pytest.mark.asyncio
async def test_live_14_partial_failure_keeps_successful_metric():
    class FailingFaithfulness(FakeFaithfulness):
        async def ascore(self, **kwargs):
            raise RuntimeError("metric failed")

    case = {
        "case_id": "RAGAS-V2-001",
        "analyte": "WBC",
        "user_input": "q",
        "response": "r",
        "reference": "ref",
        "retrieved_contexts": ["ctx"],
    }

    result = await score_case(case, FailingFaithfulness(None), FakeContextPrecision(None))

    assert result["metric_status"] == "partial_failure"
    assert result["faithfulness"] is None
    assert result["context_precision"] == 0.5


@pytest.mark.asyncio
async def test_live_15_no_credential_persistence(monkeypatch, tmp_path: Path):
    output = tmp_path / "ragas_v2_baseline.json"
    report = tmp_path / "report.md"
    secret = "google-secret-value"
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": secret})
    monkeypatch.setattr(run_ragas, "import_ragas_api", lambda: FakeApi())
    monkeypatch.setattr(run_ragas, "DEFAULT_RESULT_PATH", output)
    monkeypatch.setattr(run_ragas, "DEFAULT_REPORT_PATH", report)

    await run_live(config(output), client_factory=fake_client_factory, probe_func=fake_probe)

    csv_path = output.with_suffix(".csv")
    assert secret not in output.read_text(encoding="utf-8")
    assert secret not in csv_path.read_text(encoding="utf-8")
    assert secret not in report.read_text(encoding="utf-8")
    assert "authorization" not in output.read_text(encoding="utf-8").casefold()


@pytest.mark.asyncio
async def test_live_16_result_schema(monkeypatch, tmp_path: Path):
    output = tmp_path / "result.json"
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": "google-secret"})
    monkeypatch.setattr(run_ragas, "import_ragas_api", lambda: FakeApi())

    await run_live(config(output, max_cases=1), client_factory=fake_client_factory, probe_func=fake_probe)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["run_id"] == "RAGAS-V2-BASELINE-001"
    assert data["evaluator"]["provider"] == "google"
    assert data["evaluator"]["model"] == "gemini-2.5-flash"
    assert data["cases"][0]["metric_status"] == "success"


@pytest.mark.asyncio
async def test_live_17_csv_schema(monkeypatch, tmp_path: Path):
    output = tmp_path / "result.json"
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": "google-secret"})
    monkeypatch.setattr(run_ragas, "import_ragas_api", lambda: FakeApi())

    await run_live(config(output, max_cases=1), client_factory=fake_client_factory, probe_func=fake_probe)
    header = output.with_suffix(".csv").read_text(encoding="utf-8").splitlines()[0]

    assert header == "case_id,analyte,faithfulness,context_precision,custom_hallucination_proxy,metric_status,duration_ms"


@pytest.mark.asyncio
async def test_live_18_reproducibility_metadata(monkeypatch, tmp_path: Path):
    output = tmp_path / "result.json"
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": "google-secret"})
    monkeypatch.setattr(run_ragas, "import_ragas_api", lambda: FakeApi())

    await run_live(config(output, max_cases=1), client_factory=fake_client_factory, probe_func=fake_probe)
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["git_commit"]
    assert data["dataset"]["sha256"]
    assert data["evaluator"]["ragas_version"] == "0.4.3"
    assert data["evaluator"]["concurrency"] == 1


@pytest.mark.asyncio
async def test_live_19_one_pass_no_retry(monkeypatch, tmp_path: Path):
    class CountingFailure(FakeFaithfulness):
        calls = 0

        async def ascore(self, **kwargs):
            type(self).calls += 1
            raise RuntimeError("single failure")

    class OnePassApi(FakeApi):
        Faithfulness = CountingFailure

    output = tmp_path / "result.json"
    monkeypatch.setattr(os, "environ", {"GOOGLE_API_KEY": "google-secret"})
    monkeypatch.setattr(run_ragas, "import_ragas_api", lambda: OnePassApi())

    await run_live(config(output, max_cases=1), client_factory=fake_client_factory, probe_func=fake_probe)

    assert CountingFailure.calls == 1


def test_live_20_existing_offline_modes_network_free(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    assert main(["--dataset", str(DATASET_PATH), "--validate-only"]) == 0
    assert main(["--dataset", str(DATASET_PATH), "--inspect"]) == 0
