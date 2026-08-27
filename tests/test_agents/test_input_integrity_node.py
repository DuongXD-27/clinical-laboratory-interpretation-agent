import pytest

from src.agents import graph as graph_module
from src.agents.nodes import analyzer_node as analyzer_module
from src.agents.nodes import input_integrity_node as integrity_module
from src.services.input_integrity import InputIntegrityEvaluator, PlausibilityRepository
from src.services.reference_repository import ReferenceRepository


def _active_fixture_evaluator() -> InputIntegrityEvaluator:
    return InputIntegrityEvaluator(
        PlausibilityRepository.from_dict(
            {
                "config_version": "test-only",
                "rules": [
                    {
                        "rule_id": "TEST-ONLY-POTASSIUM-BOUND",
                        "analyte": "Potassium",
                        "canonical_unit": "mmol/L",
                        "lower_bound": 0,
                        "lower_operator": ">=",
                        "upper_bound": 10,
                        "upper_operator": "<=",
                        "source_id": "TEST-FIXTURE-NON-MEDICAL",
                        "source": "Synthetic test fixture",
                        "source_section": "test-only",
                        "reason": "Exercise pipeline stop behavior only",
                        "status": "ACTIVE",
                    }
                ],
            }
        )
    )


@pytest.mark.asyncio
async def test_need_review_skips_reference_critical_and_analyzer_llm(monkeypatch):
    monkeypatch.setattr(
        integrity_module,
        "get_input_integrity_evaluator",
        _active_fixture_evaluator,
    )

    def forbidden_reference_classification(*_args, **_kwargs):
        raise AssertionError("reference classifier must not run for NEED_REVIEW")

    monkeypatch.setattr(ReferenceRepository, "select_rule", forbidden_reference_classification)
    monkeypatch.setattr(
        analyzer_module,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("analyzer LLM must not be initialized")),
    )

    result = await graph_module.build_graph().ainvoke(
        {
            "patient_age": 35,
            "patient_gender": "male",
            "language": "vi",
            "raw_indicators": [{"name": "Potassium", "value": 500, "unit": "mmol/L"}],
        },
        {"configurable": {"thread_id": "integrity-stop-test"}},
    )

    indicator = result["indicators"][0]
    assert indicator["value"] == 500
    assert indicator["input_integrity_status"] == "NEED_REVIEW"
    assert indicator["status"] == "unknown"
    assert indicator["is_critical"] is False
    assert result["critical_alerts"] == []
    assert result["has_critical_values"] is False
    assert result["explanations"] == []


@pytest.mark.asyncio
async def test_no_active_rule_preserves_existing_reference_and_critical_flow(monkeypatch):
    monkeypatch.setattr(
        integrity_module,
        "get_input_integrity_evaluator",
        lambda: InputIntegrityEvaluator(PlausibilityRepository.from_dict({"rules": []})),
    )
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: None)

    result = await graph_module.build_graph().ainvoke(
        {
            "patient_age": 35,
            "patient_gender": "male",
            "language": "vi",
            "raw_indicators": [{"name": "Potassium", "value": 6.5, "unit": "mmol/L"}],
        },
        {"configurable": {"thread_id": "integrity-backcompat-test"}},
    )

    indicator = result["indicators"][0]
    assert indicator["input_integrity_status"] == "VALID"
    assert indicator["status"] == "high"
    assert indicator["critical_status"] == "critical_high"
    assert result["has_critical_values"] is True
