import pytest

from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node


@pytest.mark.asyncio
async def test_fpg_reference_and_critical_sources_are_distinct_claim_categories():
    state = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Fasting plasma glucose", "value": 30, "unit": "mmol/L"}
        ],
    }
    ranged = await reference_range_checker_node(state)
    detected = await detect_critical_values_node({**state, **ranged})
    indicator = detected["indicators"][0]

    reference = indicator["reference_range_source"]
    critical = indicator["critical_threshold_source"]
    assert reference["note_type"] == "reference_range"
    assert critical["note_type"] == "critical_threshold"
    assert reference["source_id"] != critical["source_id"]
    assert reference["url"] != critical["url"]
