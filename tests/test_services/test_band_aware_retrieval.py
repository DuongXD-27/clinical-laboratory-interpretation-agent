"""GRQ-004 Fix 1/2 - band-aware retrieval candidates and provenance packaging.

Covers:
- R3:  banded analyte retrieval without an incoming band_id obtains a
       deterministic compatible band note (via ReferenceRepository.resolve_band).
- R3b: incompatible sibling-band notes can never be admitted, regardless of
       embedding similarity (metadata equality filter in BOTH prongs).
- R2:  CorpusChunk.to_chroma_metadata emits parseable ``sources``;
       _metadata_chunk restores source/sources; fusion dedups per source.
- R4:  weak/irrelevant chunks still fail the relevance gate.
"""

from __future__ import annotations

import json

import pytest

from src.models.corpus_schemas import CorpusChunk
from src.services.analyte_resolver import canonical_analyte_id
from src.services.medical_knowledge_retriever import ChromaMedicalKnowledgeRetriever
from src.services.reference_repository import ReferenceRepository
from tests.test_embed import FakeEmbeddingProvider


def _long(text: str) -> str:
    # metadata_min_chunk_length is 30; keep comfortably above the thin-chunk cut
    return text + " " + "Nội dung giáo dục được duyệt cho mục đích giải thích chỉ số xét nghiệm."


@pytest.fixture(scope="module")
def repository() -> ReferenceRepository:
    return ReferenceRepository.from_default_files()


# ---------------------------------------------------------------------------
# R3 - deterministic band resolution from authoritative bounds
# ---------------------------------------------------------------------------


def test_resolve_band_hba1c_matrix(repository):
    def resolve(value):
        return repository.resolve_band(
            analyte="HbA1c", value=value, unit="%", patient_gender="male", patient_age=35
        )
    # Boundary-consistent with the Reference Checker:
    # 5.7 is NOT strictly above the baseline upper bound -> checker NORMAL.
    assert resolve(4.5) == "normal_glycemia"
    assert resolve(5.7) == "normal_glycemia"
    assert resolve(5.71) == "prediabetes_high_risk"
    assert resolve(6.8) == "diabetes_diagnostic_threshold"


def test_resolve_band_other_banded_analytes(repository):
    assert (
        repository.resolve_band(
            analyte="Fasting plasma glucose",
            value=4.0,
            unit="mmol/L",
            patient_gender="male",
            patient_age=35,
        )
        == "normal"
    )
    assert (
        repository.resolve_band(
            analyte="Fasting plasma glucose",
            value=6.2,
            unit="mmol/L",
            patient_gender="male",
            patient_age=35,
        )
        == "impaired_fasting_glucose"
    )
    assert (
        repository.resolve_band(
            analyte="HDL-C", value=1.2, unit="mmol/L", patient_gender="male", patient_age=35
        )
        == "intermediate"
    )
    assert (
        repository.resolve_band(
            analyte="LDL-C", value=5.2, unit="mmol/L", patient_gender="male", patient_age=35
        )
        == "very_high"
    )


def test_resolve_band_fail_closed(repository):
    # Non-banded / unsupported analytes never receive a band hint.
    assert (
        repository.resolve_band(
            analyte="WBC", value=12.0, unit="G/L", patient_gender="male", patient_age=35
        )
        is None
    )
    assert (
        repository.resolve_band(
            analyte="Totally Unknown Analyte",
            value=1.0,
            unit="u/L",
            patient_gender="male",
            patient_age=35,
        )
        is None
    )
    # Unparseable values fail closed instead of guessing.
    assert (
        repository.resolve_band(
            analyte="HbA1c", value="not-a-number", unit="%", patient_gender="male", patient_age=35
        )
        is None
    )


def test_resolve_band_alignment_covers_every_frozen_banded_analyte(repository):
    from src.services.analyte_resolver import FROZEN_CLINICAL_RULE_BANDS

    for aid, bands in FROZEN_CLINICAL_RULE_BANDS.items():
        canonical = next(
            (c for c in repository.approved_analytes if canonical_analyte_id(c) == aid),
            None,
        )
        if canonical is None:
            continue  # analyte not approved for lookup yet; resolver must skip it
        rules = [
            rule
            for rule in repository._rules_by_analyte.get(canonical, ())
            if str(rule.get("reference_type")) in {"CDL", "BAND"}
        ]
        assert len(rules) == len(bands), f"{aid}: rule/band count mismatch"


# ---------------------------------------------------------------------------
# R2 - provenance packaging round-trip
# ---------------------------------------------------------------------------


def _chunk(source_url: str, source_id: str, text: str, band_id=None, note_type="description") -> CorpusChunk:
    return CorpusChunk(
        chunk_id=f"hba1c::{note_type}::{source_id}" + (f"::{band_id}" if band_id else ""),
        text=text,
        indicator="HbA1c",
        analyte_id="hba1c",
        rule_type="CDL",
        note_type=note_type,
        band_id=band_id,
        source_id=source_id,
        source_url=source_url,
        language="vi",
    )


def test_to_chroma_metadata_emits_parseable_sources():
    meta = _chunk("https://example.test/a", "SRC-A", "text").to_chroma_metadata()
    assert json.loads(meta["sources"]) == ["https://example.test/a"]

    meta_no_url = _chunk("", "SRC-B", "text").to_chroma_metadata()
    assert json.loads(meta_no_url["sources"]) == ["SRC-B"]

    meta_empty = _chunk("", "", "text").to_chroma_metadata()
    assert json.loads(meta_empty["sources"]) == []


def test_metadata_chunk_restores_source_and_sources():
    from src.services.medical_knowledge_retriever import ChromaMedicalKnowledgeRetriever

    restored = ChromaMedicalKnowledgeRetriever._metadata_chunk(
        None,
        "some grounded text",
        {"indicator": "HbA1c", "note_type": "band_note", "sources": json.dumps(["https://example.test/a"])},
        analyte_id="hba1c",
        score=1.0,
    )
    assert restored["source"] == "https://example.test/a"
    assert restored["sources"] == ["https://example.test/a"]

    empty = ChromaMedicalKnowledgeRetriever._metadata_chunk(
        None,
        "some text",
        {"sources": "[]"},
        analyte_id="hba1c",
        score=1.0,
    )
    assert empty["source"] == ""
    assert empty["sources"] == []


# ---------------------------------------------------------------------------
# R3/R3b/R4 - end-to-end retrieval over an ingested tmp collection
# ---------------------------------------------------------------------------

NORMAL_BAND_TEXT = _long(
    "Mức HbA1c bình thường dưới 5.7% phản ánh kiểm soát đường huyết ổn định ở người không mắc đái tháo đường."
)
DIABETES_BAND_TEXT = _long(
    "Ngưỡng chẩn đoán đái tháo đường từ 6.5%. Với người chưa từng được chẩn đoán, kết quả cần được làm lại bằng mẫu máu mới."
)
GENERIC_DESCRIPTION = _long("HbA1c phản ánh nồng độ đường huyết trung bình của cơ thể trong khoảng 2 đến 3 tháng gần nhất.")
JUNK_DESCRIPTION = "vector chroma vector chroma vector chroma vector chroma vector chroma junk content entirely off topic."


def _ingest(tmp_path, chunks):
    from src.services.vector_store import VectorStore

    store = VectorStore(
        persist_dir=str(tmp_path),
        collection_name="medical_kb_grq004_test",
        corpus_version="medical-kb-v4",
        embedding_provider=FakeEmbeddingProvider(),
    )
    store.add_documents(
        texts=[chunk.text for chunk in chunks],
        metadatas=[chunk.to_chroma_metadata() for chunk in chunks],
        ids=[chunk.chunk_id for chunk in chunks],
    )
    return ChromaMedicalKnowledgeRetriever(store)


def _hba1c_chunks() -> list[CorpusChunk]:
    return [
        _chunk("https://src.test/normal", "SRC-NORMAL", NORMAL_BAND_TEXT, band_id="normal_glycemia", note_type="band_note"),
        _chunk("https://src.test/diabetes", "SRC-DIABETES", DIABETES_BAND_TEXT, band_id="diabetes_diagnostic_threshold", note_type="band_note"),
        _chunk("https://src.test/desc-a", "SRC-DESC-A", GENERIC_DESCRIPTION),
    ]


def test_compatible_band_note_selected_and_sibling_excluded(tmp_path):
    retriever = _ingest(tmp_path, _hba1c_chunks())

    selected = retriever.retrieve(
        query="Ý nghĩa xét nghiệm HbA1c khi kết quả ở mức high",
        analyte_id="hba1c",
        status="high",
        band_id="diabetes_diagnostic_threshold",
        limit=3,
    )

    texts = [str(chunk.get("text", "")) for chunk in selected]
    assert any(DIABETES_BAND_TEXT[:40] in text for text in texts), texts
    # R3b: incompatible sibling band must be absent regardless of embeddings.
    assert all(NORMAL_BAND_TEXT[:40] not in text for text in texts), texts
    # R2/R8: provenance restored on retrieved chunks.
    diabetes_chunk = next(c for c in selected if DIABETES_BAND_TEXT[:40] in str(c.get("text", "")))
    assert diabetes_chunk["sources"] == ["https://src.test/diabetes"]
    assert diabetes_chunk["source"] == "https://src.test/diabetes"


def test_fusion_dedup_skips_duplicate_source_but_refills_with_others(tmp_path):
    chunks = _hba1c_chunks()
    # Give the generic description the SAME source as the primary band note;
    # per-source diversity must prefer different-source descriptions.
    chunks[2] = _chunk("https://src.test/diabetes", "SRC-DIABETES", GENERIC_DESCRIPTION)
    chunks.append(
        _chunk("https://src.test/limitation", "SRC-LIMITATION", _long(
            "Kết quả HbA1c có thể bị ảnh hưởng bởi các tình trạng thay đổi đời sống hồng cầu cần được lưu ý khi đánh giá."
        ))
    )
    retriever = _ingest(tmp_path, chunks)

    selected = retriever.retrieve(
        query="Ý nghĩa xét nghiệm HbA1c khi kết quả ở mức high",
        analyte_id="hba1c",
        status="high",
        band_id="diabetes_diagnostic_threshold",
        limit=2,
    )

    assert len(selected) == 2
    first_text = str(selected[0].get("text", ""))
    assert DIABETES_BAND_TEXT[:40] in first_text  # primary note wins
    second_text = str(selected[1].get("text", ""))
    assert GENERIC_DESCRIPTION[:40] not in second_text  # duplicate source skipped


def test_weak_offtopic_chunks_fail_relevance_gate(tmp_path):
    chunks = _hba1c_chunks() + [
        _chunk("https://src.test/junk", "SRC-JUNK", JUNK_DESCRIPTION),
    ]
    retriever = _ingest(tmp_path, chunks)

    selected = retriever.retrieve(
        query="Ý nghĩa xét nghiệm HbA1c khi kết quả ở mức high",
        analyte_id="hba1c",
        status="high",
        band_id="diabetes_diagnostic_threshold",
        limit=5,
    )

    texts = [str(chunk.get("text", "")) for chunk in selected]
    assert all(JUNK_DESCRIPTION[:40] not in text for text in texts), texts


# ---------------------------------------------------------------------------
# Exact-boundary equality: Reference Checker vs resolve_band
# ---------------------------------------------------------------------------


BOUNDARY_TABLE = {
    "HbA1c": {
        "unit": "%",
        "boundaries": [5.7, 6.5],
        # value: (expected_checker_status, expected_band_or_None)
        5.69: ("normal", "normal_glycemia"),
        5.7: ("normal", "normal_glycemia"),
        5.71: ("high", "prediabetes_high_risk"),
        6.49: ("high", "prediabetes_high_risk"),
        6.5: ("high", "diabetes_diagnostic_threshold"),
        6.51: ("high", "diabetes_diagnostic_threshold"),
    },
    "Fasting plasma glucose": {
        "unit": "mmol/L",
        "boundaries": [5.6, 7.0],
        5.59: ("normal", "normal"),
        5.6: ("normal", "normal"),
        5.61: ("high", "impaired_fasting_glucose"),
        6.99: ("high", "impaired_fasting_glucose"),
        7.0: ("high", "provisional_diabetes"),
        7.01: ("high", "provisional_diabetes"),
    },
    "Total cholesterol": {
        "unit": "mmol/L",
        "boundaries": [5.18, 6.19],
        5.17: (None, None),
        5.18: (None, None),
        5.19: (None, None),
        6.18: (None, None),
        6.19: (None, None),
        6.2: (None, None),
    },
    "Triglyceride": {
        "unit": "mmol/L",
        "boundaries": [1.7, 2.26, 5.65],
        1.69: (None, None),
        1.7: (None, None),
        1.71: (None, None),
        2.25: (None, None),
        2.26: (None, None),
        2.27: (None, None),
        5.64: (None, None),
        5.65: (None, None),
        5.66: (None, None),
    },
    "HDL-C": {
        "unit": "mmol/L",
        "boundaries": [1.04, 1.55],
        1.03: ("low", "low"),
        1.04: ("normal", "intermediate"),
        1.05: ("normal", "intermediate"),
        1.54: ("normal", "intermediate"),
        1.55: ("normal", "intermediate"),
        1.56: ("high", "optimal"),
    },
    "LDL-C": {
        "unit": "mmol/L",
        "boundaries": [2.59, 3.36, 4.14, 4.91],
        2.58: ("normal", "optimal"),
        2.59: ("normal", "optimal"),
        2.6: ("high", "near_optimal"),
        3.35: ("high", "near_optimal"),
        3.36: ("high", "borderline_high"),
        3.37: ("high", "borderline_high"),
        4.13: ("high", "borderline_high"),
        4.14: ("high", "high"),
        4.15: ("high", "high"),
        4.9: ("high", "high"),
        4.91: ("high", "very_high"),
        4.92: ("high", "very_high"),
    },
}

EPSILON = 0.01


def _epsilon_grid(bounds):
    values = []
    for bound in bounds:
        values.extend([round(bound - EPSILON, 2), bound, round(bound + EPSILON, 2)])
    return sorted(set(values))


@pytest.mark.asyncio
async def test_checker_and_resolve_band_agree_at_every_boundary(repository):
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    for analyte, spec in BOUNDARY_TABLE.items():
        unit = spec["unit"]
        for value in _epsilon_grid(spec["boundaries"]):
            state = {
                "patient_age": 35,
                "patient_gender": "male",
                "test_date": "2026-08-15",
                "raw_indicators": [{"name": analyte, "value": value, "unit": unit}],
            }
            checked = await reference_range_checker_node(state)
            checker_status = checked["indicators"][0]["status"]
            if checker_status == "unknown":
                checker_status = None

            expected_status, expected_band = spec[value]
            assert checker_status == expected_status, (
                f"{analyte} {value}: checker status {checker_status!r} != audited {expected_status!r}"
            )

            band = repository.resolve_band(
                analyte=analyte,
                value=value,
                unit=unit,
                patient_gender="male",
                patient_age=35,
            )
            assert band == expected_band, (
                f"{analyte} {value}: band {band!r} != audited {expected_band!r} "
                f"(checker status {checker_status!r})"
            )


def test_gap_value_resolves_to_none_and_no_band_note(monkeypatch, repository):
    import copy

    from src.services import reference_repository as repo_module

    real_rules = repository._rules_by_analyte.get("HbA1c", ())
    template_low = copy.deepcopy(real_rules[0])   # (None, 5.7)-style row
    template_high = copy.deepcopy(real_rules[2])  # (6.5, None)-style row
    template_low["range_upper"] = 5.0
    template_high["range_lower"] = 9.0
    gapped = [template_low, template_high]

    patched_rules = dict(repository._rules_by_analyte)
    patched_rules["HbA1c"] = gapped
    monkeypatch.setattr(repository, "_rules_by_analyte", patched_rules)
    monkeypatch.setattr(
        repo_module,
        "FROZEN_CLINICAL_RULE_BANDS",
        {"hba1c": ("gap_low", "gap_high")},
    )

    resolve = lambda value: repository.resolve_band(  # noqa: E731
        analyte="HbA1c", value=value, unit="%", patient_gender="male", patient_age=35
    )
    assert resolve(3.0) == "gap_low"
    assert resolve(9.5) == "gap_high"
    # Literal uncovered gap -> fail closed -> no band hint -> no band_note retrieval.
    assert resolve(7.0) is None
