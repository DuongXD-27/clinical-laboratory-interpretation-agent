from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.nodes.analyzer_node import _known_citations
from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.services.explanation_grounding import (
    evidence_has_numeric_conflict,
    validate_generated_supplement,
)
from src.services.medical_citations import MedicalCitationRepository
from src.services.safe_grounding import filter_safe_grounding_text


async def _check(name: str, value: float, unit: str = "mmol/L") -> dict:
    result = await reference_range_checker_node(
        {
            "raw_indicators": [{"name": name, "value": value, "unit": unit}],
            "patient_age": 35,
            "patient_gender": "male",
        }
    )
    return result["indicators"][0]


@pytest.mark.asyncio
async def test_a_ri_fact_envelope_total_protein() -> None:
    indicator = await _check("Total protein", 5, "g/L")

    assert indicator["rule_type"] == "RI"
    assert (indicator["reference_low"], indicator["reference_high"]) == (60, 80)
    assert indicator["status"] == "low"
    assert indicator["rule_id"] == "RRV2-0039"
    assert indicator["classification_provenance"]["source_url"].startswith("https://www.gloshospitals")


@pytest.mark.asyncio
async def test_b_band_specific_decision_is_not_collapsed_to_generic_high() -> None:
    indicator = await _check("Triglyceride", 6)

    assert indicator["status"] == "high"
    assert indicator["band_id"] == "very_high"
    assert indicator["band_label"] == "Rất cao"
    assert indicator["rule_id"] == "RRV2-0058"
    assert indicator["band_lower"] == 5.65
    assert indicator["lower_operator"] == ">="


@pytest.mark.asyncio
async def test_c_triglyceride_boundaries_follow_existing_audited_evaluator() -> None:
    expected = {
        1.699: "normal",
        1.7: "normal",
        2.26: "high",
        5.65: "very_high",
        5.651: "very_high",
    }
    for value, band in expected.items():
        indicator = await _check("Triglyceride", value)
        assert indicator["band_id"] == band


def _citation_entries() -> list[dict]:
    def source(source_id: str, url: str, *, description: str = "Mô tả", high_note: str | None = None) -> dict:
        return {
            "source_id": source_id,
            "source_title": source_id,
            "organization": source_id,
            "url": url,
            "publication_date": "2024",
            "description": description,
            "high_note": high_note,
        }

    return [
        {
            "canonical_name": "Synthetic",
            "sources": [
                source("SRC-X", "https://x.example", high_note="Ghi chú cao"),
                source("SRC-Y", "https://y.example"),
            ],
        }
    ]


def test_d_e_citations_dedupe_by_source_identity_not_chunk_or_note_count() -> None:
    repository = MedicalCitationRepository(_citation_entries())

    same_source = repository.resolve_many(
        analyte="Synthetic",
        sources=["https://x.example", "https://x.example", "https://x.example"],
    )
    distinct_sources = repository.resolve_many(
        analyte="Synthetic",
        sources=["https://x.example", "https://y.example", "https://x.example"],
    )

    assert len(same_source) == 1
    assert len(distinct_sources) == 2


@pytest.mark.asyncio
async def test_f_classification_and_explanation_provenance_are_separate() -> None:
    indicator = await _check("Triglyceride", 6)
    citations = _known_citations(
        analyte="Triglyceride",
        sources=[],
        chunks=[
            {
                "source_id": "SRC-NCEP-ATP3-TG",
                "source_url": "https://www.nhlbi.nih.gov/resources/third-report-expert-panel-detection-evaluation-and-treatment-high-blood-cholesterol-0",
                "note_type": "band_note",
            }
        ],
    )

    assert indicator["classification_provenance"]["source_url"] == "https://renal.testcatalog.org/show/LPSC1"
    assert [citation["source_id"] for citation in citations] == ["SRC-NCEP-ATP3-TG"]


@pytest.mark.asyncio
async def test_inactive_critical_registry_record_is_not_misattributed_as_threshold_authority() -> None:
    checked = await reference_range_checker_node(
        {
            "raw_indicators": [{"name": "Triglyceride", "value": 6, "unit": "mmol/L"}],
            "patient_age": 35,
            "patient_gender": "male",
        }
    )
    result = await detect_critical_values_node({**checked, "raw_indicators": [{"name": "Triglyceride", "value": 6, "unit": "mmol/L"}]})
    assert result["indicators"][0].get("critical_threshold_source") is None


def test_g_treatment_directive_is_removed_from_release_facing_grounding() -> None:
    unsafe = (
        "Mức rất cao làm gia tăng nguy cơ viêm tụy cấp, đòi hỏi can thiệp "
        "hạ mỡ máu khẩn trương bằng thuốc."
    )
    assert filter_safe_grounding_text(unsafe) == ""


def test_h_generated_numeric_override_is_rejected() -> None:
    text, reason = validate_generated_supplement("Ngưỡng đúng là 9.9 mmol/L.")
    assert text is None
    assert reason == "numeric_fact_in_generated_prose"


def test_i_generated_certainty_strengthening_is_rejected() -> None:
    text, reason = validate_generated_supplement("Tình trạng này do X gây ra.")
    assert text is None
    assert reason == "unsafe_or_unsupported_generated_prose"


def test_generated_claim_without_evidence_overlap_is_rejected() -> None:
    text, reason = validate_generated_supplement(
        "Kết quả này có thể liên quan đến tình trạng sức khỏe cần theo dõi.",
        evidence_text="Triglyceride là dạng chất béo trung tính dự trữ năng lượng.",
    )
    assert text is None
    assert reason == "insufficient_evidence_overlap"


@pytest.mark.asyncio
async def test_j_conversion_retains_raw_and_comparison_representations() -> None:
    indicator = await _check("Triglyceride", 500, "mg/dL")

    assert (indicator["raw_value"], indicator["raw_unit"]) == (500, "mg/dL")
    assert (indicator["comparison_value"], indicator["comparison_unit"]) == (5.65, "mmol/L")
    assert indicator["conversion_applied"] is True
    assert indicator["band_id"] == "very_high"


def test_multi_source_numeric_conflict_is_suppressed_deterministically() -> None:
    chunks = [
        {"source_id": "X", "note_type": "band_note", "text": "Ngưỡng 5.6 mmol/L."},
        {"source_id": "Y", "note_type": "band_note", "text": "Ngưỡng 7.0 mmol/L."},
    ]
    assert evidence_has_numeric_conflict(chunks) is True


def test_full_corpus_patient_safety_view_blocks_every_flagged_note() -> None:
    entries = json.loads(Path("data/reference/explanations.json").read_text(encoding="utf-8"))
    fields = (
        "description",
        "high_note",
        "low_note",
        "critical_high_note",
        "critical_low_note",
        "preanalytic_note",
        "limitation_note",
    )
    scanned = 0
    for entry in entries:
        for source in entry.get("sources", []):
            notes = [source.get(field) for field in fields]
            notes.extend((source.get("band_notes") or {}).values())
            for note in notes:
                if not note:
                    continue
                scanned += 1
                safe = filter_safe_grounding_text(note)
                assert "bằng thuốc" not in safe.casefold()
                assert "đòi hỏi can thiệp" not in safe.casefold()
    assert scanned == 199
