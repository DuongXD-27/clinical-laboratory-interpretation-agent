"""Comprehensive test suite for medical knowledge corpus and status/band/critical-aware RAG infrastructure."""

from __future__ import annotations

from pathlib import Path

from src.scripts.ingest_kb import ingest, load_corpus
from src.services.analyte_resolver import (
    CANONICAL_ANALYTE_ID_MAP,
    LOCKED_35_ANALYTES,
    canonical_analyte_id,
)
from src.services.corpus_builder import (
    build_corpus_chunks,
    generate_chunk_id,
)
from src.services.corpus_validator import CorpusValidator
from src.services.medical_knowledge_retriever import ChromaMedicalKnowledgeRetriever
from src.services.vector_store import VectorStore

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-embedding"
    dimension = 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


# ---------------------------------------------------------------------------
# 1. Shared Canonical Analyte Resolver Tests
# ---------------------------------------------------------------------------
def test_canonical_analyte_id_convention():
    assert canonical_analyte_id("LDL-C") == "ldl_c"
    assert canonical_analyte_id("HDL-C") == "hdl_c"
    assert canonical_analyte_id("Fasting plasma glucose") == "fasting_plasma_glucose"
    assert canonical_analyte_id("RDW-CV") == "rdw_cv"
    assert canonical_analyte_id("Total cholesterol") == "total_cholesterol"
    assert canonical_analyte_id("Neutrophils %") == "neutrophils_%"
    assert canonical_analyte_id("Neutrophils abs") == "neutrophils_abs"
    assert canonical_analyte_id("WBC") == "wbc"


def test_locked_35_analytes_complete_mapping():
    assert len(LOCKED_35_ANALYTES) == 35
    assert len(CANONICAL_ANALYTE_ID_MAP) == 35
    for name in LOCKED_35_ANALYTES:
        aid = CANONICAL_ANALYTE_ID_MAP[name]
        assert aid == canonical_analyte_id(name)


# ---------------------------------------------------------------------------
# 2. Fine-Grained Chunk Generation & Determinism Tests
# ---------------------------------------------------------------------------
def test_generate_chunk_id_format():
    assert (
        generate_chunk_id("wbc", "description", "SRC-001")
        == "wbc::description::SRC-001"
    )
    assert (
        generate_chunk_id("ldl_c", "band_note", "SRC-NCEP", band_id="very_high")
        == "ldl_c::band_note::very_high::SRC-NCEP"
    )
    assert (
        generate_chunk_id("potassium", "critical_low_note", "SRC-NHS")
        == "potassium::critical_low_note::SRC-NHS"
    )


def test_source_reorder_stability():
    source_a = {
        "source_id": "SRC-A",
        "url": "https://source-a.org",
        "description": "Description from source A",
        "high_note": "High note from source A",
    }
    source_b = {
        "source_id": "SRC-B",
        "url": "https://source-b.org",
        "description": "Description from source B",
        "low_note": "Low note from source B",
    }

    entry_order_1 = {
        "canonical_name": "WBC",
        "analyte_id": "wbc",
        "rule_type": "RI",
        "sources": [source_a, source_b],
    }
    entry_order_2 = {
        "canonical_name": "WBC",
        "analyte_id": "wbc",
        "rule_type": "RI",
        "sources": [source_b, source_a],
    }

    chunks_1 = {c.chunk_id: c.text for c in build_corpus_chunks([entry_order_1])}
    chunks_2 = {c.chunk_id: c.text for c in build_corpus_chunks([entry_order_2])}

    assert set(chunks_1.keys()) == set(chunks_2.keys())
    for cid in chunks_1:
        assert chunks_1[cid] == chunks_2[cid]


def test_band_chunk_generation_and_metadata_flattening():
    entry = {
        "canonical_name": "LDL-C",
        "analyte_id": "ldl_c",
        "rule_type": "BAND",
        "sources": [
            {
                "source_id": "SRC-NLA-2014",
                "source_title": "LDL guidance",
                "organization": "National Lipid Association",
                "section": "Recommendations",
                "source_tier": "TIER_1",
                "url": "https://nla.org/ldl",
                "description": "LDL cholesterol overview",
                "band_notes": {
                    "optimal": "Optimal level < 2.6 mmol/L",
                    "very_high": "Very high level >= 4.9 mmol/L",
                },
                "limitation_note": "Requires ASCVD risk calculation",
            }
        ],
    }

    chunks = build_corpus_chunks([entry])
    assert len(chunks) == 4

    chunk_ids = {c.chunk_id for c in chunks}
    assert "ldl_c::description::SRC-NLA-2014" in chunk_ids
    assert "ldl_c::band_note::optimal::SRC-NLA-2014" in chunk_ids
    assert "ldl_c::band_note::very_high::SRC-NLA-2014" in chunk_ids
    assert "ldl_c::limitation_note::SRC-NLA-2014" in chunk_ids

    # Validate Chroma metadata is flat scalar
    for chunk in chunks:
        meta = chunk.to_chroma_metadata()
        assert meta["source_title"] == "LDL guidance"
        assert meta["organization"] == "National Lipid Association"
        assert meta["source_section"] == "Recommendations"
        for k, v in meta.items():
            assert isinstance(v, (str, int, float, bool)), f"Non-scalar metadata: {k}={v}"


# ---------------------------------------------------------------------------
# 3. Corpus Validator Tests
# ---------------------------------------------------------------------------
def test_development_validation_passes_on_current_repo_corpus():
    raw_data = load_corpus()
    report = CorpusValidator.validate(raw_data, mode="development")
    assert report.is_valid, f"Validation errors: {report.errors}"
    assert report.analyte_count == 35
    assert report.chunk_count > 0


def test_release_validation_passes_on_full_35_corpus():
    raw_data = load_corpus()
    report = CorpusValidator.validate(raw_data, mode="release")
    assert report.is_valid, f"Validation errors: {report.errors}"
    assert report.analyte_count == 35


def test_release_validation_fails_on_partial_corpus():
    raw_data = load_corpus()[:9]
    report = CorpusValidator.validate(raw_data, mode="release")
    assert not report.is_valid
    assert any("Exactly 35 analytes required" in err for err in report.errors)


def test_validator_rejects_placeholders():
    bad_entry = {
        "canonical_name": "WBC",
        "analyte_id": "wbc",
        "rule_type": "RI",
        "sources": [
            {
                "source_id": "SRC-001",
                "description": "TODO: add description later",
            }
        ],
    }
    report = CorpusValidator.validate([bad_entry], mode="development")
    assert not report.is_valid
    assert any("placeholder" in err for err in report.errors)


def test_validator_rejects_unknown_band_id():
    bad_entry = {
        "canonical_name": "LDL-C",
        "analyte_id": "ldl_c",
        "rule_type": "BAND",
        "sources": [
            {
                "source_id": "SRC-001",
                "band_notes": {
                    "extremely_severe": "Unknown band text",
                },
            }
        ],
    }
    report = CorpusValidator.validate([bad_entry], mode="development")
    assert not report.is_valid
    assert any("unknown band_id" in err for err in report.errors)


def test_validator_rejects_non_band_defining_band_notes():
    bad_entry = {
        "canonical_name": "WBC",
        "analyte_id": "wbc",
        "rule_type": "RI",
        "sources": [
            {
                "source_id": "SRC-001",
                "band_notes": {
                    "high": "Invalid band note on RI",
                },
            }
        ],
    }
    report = CorpusValidator.validate([bad_entry], mode="development")
    assert not report.is_valid
    assert any("prohibited" in err for err in report.errors)


def test_validator_rejects_incomplete_or_invalid_source_metadata():
    entry = {
        "canonical_name": "WBC",
        "analyte_id": "wbc",
        "rule_type": "RI",
        "sources": [{"source_id": "SRC-BAD", "url": "ftp://invalid", "description": "Overview"}],
    }
    report = CorpusValidator.validate([entry], mode="development")
    assert any("missing source_title" in error for error in report.errors)
    assert any("missing organization" in error for error in report.errors)
    assert any("invalid URL schema" in error for error in report.errors)


def test_validator_rejects_duplicate_source_id_and_source_without_note():
    source = {
        "source_id": "SRC-DUP",
        "source_title": "Title",
        "organization": "Organization",
        "url": "https://example.org/source",
    }
    entries = [
        {"canonical_name": "WBC", "analyte_id": "wbc", "rule_type": "RI", "sources": [source]},
        {
            "canonical_name": "RBC",
            "analyte_id": "rbc",
            "rule_type": "RI",
            "sources": [{**source, "description": "RBC overview"}],
        },
    ]
    report = CorpusValidator.validate(entries, mode="development")
    assert any("Duplicate source_id" in error for error in report.errors)
    assert any("has no analyte note type" in error for error in report.errors)


def test_current_corpus_duplicate_urls_are_reported_as_maintenance_warnings():
    report = CorpusValidator.validate(load_corpus(), mode="development")
    assert report.is_valid
    assert any("Duplicate exact URL" in warning for warning in report.warnings)


# ---------------------------------------------------------------------------
# 4. Ingestion & VectorStore Idempotency Tests
# ---------------------------------------------------------------------------
def test_ingestion_and_idempotency(tmp_path):
    store = VectorStore(
        persist_dir=str(tmp_path),
        collection_name="medical_kb_v4",
        corpus_version="medical-kb-v4",
        embedding_provider=FakeEmbeddingProvider(),
    )

    # manifest_path phai tro vao tmp_path. Mac dinh cua ingest() la
    # data/reference/medical_kb_manifest.json — mot file DUOC TRACK, nen chay
    # test se ghi de len no bang hash cua corpus dang co tren dia. Hau qua that:
    # working tree ban sau moi lan chay suite, va manifest tu "chua lanh" chinh
    # no nen pin toan ven khong con phat hien duoc corpus bi doi.
    manifest = tmp_path / "medical_kb_manifest.json"

    doc_count_1 = ingest(
        json_path="data/reference/explanations.json",
        validation_mode="development",
        vector_store=store,
        manifest_path=manifest,
    )
    assert doc_count_1 > 0
    assert store.get_collection().count() == doc_count_1

    # Idempotent re-ingestion: total document count remains unchanged
    doc_count_2 = ingest(
        json_path="data/reference/explanations.json",
        validation_mode="development",
        vector_store=store,
        manifest_path=manifest,
    )
    assert doc_count_2 == doc_count_1
    assert store.get_collection().count() == doc_count_1


# ---------------------------------------------------------------------------
# 5. Status-Gated, Band-Aware & Critical-Decoupled Retrieval Tests
# ---------------------------------------------------------------------------
def test_retriever_status_and_critical_decoupling(tmp_path):
    store = VectorStore(
        persist_dir=str(tmp_path),
        collection_name="medical_kb_v4_test",
        corpus_version="medical-kb-v4",
        embedding_provider=FakeEmbeddingProvider(),
    )

    # Ingest test fixture with RI, BAND, and Critical notes
    test_entries = [
        {
            "canonical_name": "Potassium",
            "analyte_id": "potassium",
            "rule_type": "RI",
            "sources": [
                {
                    "source_id": "SRC-K",
                    "description": "Kali là cation chủ lực nội bào.",
                    "high_note": "Tăng kali máu nhẹ.",
                    "low_note": "Hạ kali máu nhẹ.",
                    "critical_high_note": "Nguy kịch: Tăng kali ác tính ngừng tim.",
                    "critical_low_note": "Nguy kịch: Hạ kali ác tính liệt cơ.",
                }
            ],
        },
        {
            "canonical_name": "Triglyceride",
            "analyte_id": "triglyceride",
            "rule_type": "BAND",
            "sources": [
                {
                    "source_id": "SRC-TG",
                    "description": "Triglyceride là chất béo trung tính.",
                    "band_notes": {
                        "normal": "Mức bình thường < 1.7 mmol/L.",
                        "very_high": "Mức rất cao >= 5.7 mmol/L nguy cơ viêm tụy cấp.",
                    },
                    "critical_high_note": "Fake critical alert note.",
                }
            ],
        },
    ]

    chunks = build_corpus_chunks(test_entries)
    texts = [c.text for c in chunks]
    metadatas = [c.to_chroma_metadata() for c in chunks]
    ids = [c.chunk_id for c in chunks]
    store.add_documents(texts=texts, metadatas=metadatas, ids=ids)

    retriever = ChromaMedicalKnowledgeRetriever(store)

    # 1. Potassium Normal -> returns description
    res_normal = retriever.retrieve(
        query="Kali bình thường",
        analyte_id="potassium",
        status="normal",
        critical_status="none",
    )
    assert len(res_normal) >= 1
    assert "cation chủ lực" in res_normal[0]["text"]

    # 2. Potassium Critical Low -> prioritizes critical_low_note
    res_crit_low = retriever.retrieve(
        query="Kali thấp nguy kịch",
        analyte_id="potassium",
        status="low",
        critical_status="critical_low",
    )
    assert len(res_crit_low) >= 1
    assert "Nguy kịch: Hạ kali" in res_crit_low[0]["text"]

    # 3. Triglyceride very_high with critical_status="none"
    # ABSOLUTE CRITICAL DECOUPLING: Must retrieve band_note::very_high, NEVER critical_high_note!
    res_tg = retriever.retrieve(
        query="Triglyceride rất cao",
        analyte_id="triglyceride",
        status="high",
        band_id="very_high",
        critical_status="none",
    )
    assert len(res_tg) >= 1
    assert "Mức rất cao" in res_tg[0]["text"]
    for chunk in res_tg:
        assert "Fake critical" not in chunk["text"], "CRITICAL NOTE WAS LEAKED INTO NON-CRITICAL BAND RETRIEVAL!"


def test_ingest_never_writes_the_tracked_manifest(tmp_path):
    """ingest() chi duoc ghi vao manifest_path duoc truyen vao.

    Truoc day duong dan manifest bi hardcode trong ingest(), nen moi lan chay
    suite la data/reference/medical_kb_manifest.json — file duoc track — bi ghi
    de bang hash cua corpus dang co tren dia. Hai hau qua: working tree ban sau
    moi lan chay test, va pin toan ven tu chuan lai theo corpus hien tai nen no
    khong the phat hien corpus bi doi nua. Do la mot guard tu vo hieu hoa chinh
    minh.
    """

    tracked = REPO_ROOT / "data/reference/medical_kb_manifest.json"
    before = tracked.read_bytes()

    store = VectorStore(
        persist_dir=str(tmp_path / "chroma"),
        collection_name="medical_kb_v4",
        corpus_version="medical-kb-v4",
        embedding_provider=FakeEmbeddingProvider(),
    )
    target = tmp_path / "manifest.json"

    ingest(
        json_path="data/reference/explanations.json",
        validation_mode="development",
        vector_store=store,
        manifest_path=target,
    )

    assert target.exists(), "manifest phai duoc ghi vao duong dan truyen vao"
    assert tracked.read_bytes() == before, "ingest() vua ghi de len file duoc track"
