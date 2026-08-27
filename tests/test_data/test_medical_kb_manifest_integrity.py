from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.scripts.ingest_kb import corpus_sha256

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLANATIONS_PATH = REPO_ROOT / "data/reference/explanations.json"
MANIFEST_PATH = REPO_ROOT / "data/reference/medical_kb_manifest.json"
ACCEPTED_CORPUS_HASH = "5397a9777eec2057e34648b3912e68a8bd00e8da5f5568c10f3e37a2d27a6944"


def _sha256(data: bytes) -> str:
    """Hash byte da chuan hoa dong, giong het `corpus_sha256()` cua ingest_kb.

    Hash byte tho phu thuoc vao `core.autocrlf` cua may checkout chu khong phu
    thuoc noi dung: cung mot commit ra LF tren Linux va CRLF tren Windows, nen
    pin se xanh tren CI va do tren moi may Windows du du lieu y het.
    """

    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def test_medical_kb_manifest_matches_accepted_explanations_blob():
    corpus_bytes = EXPLANATIONS_PATH.read_bytes()
    corpus = json.loads(corpus_bytes)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    digest = _sha256(corpus_bytes)

    assert digest == ACCEPTED_CORPUS_HASH
    assert manifest["corpus_sha256"] == ACCEPTED_CORPUS_HASH
    assert manifest["source_corpus_sha256"] == ACCEPTED_CORPUS_HASH
    assert manifest["analyte_count"] == len(corpus)
    assert manifest["source_record_count"] == sum(len(item.get("sources", [])) for item in corpus)


def test_medical_kb_manifest_hash_changes_when_semantic_corpus_changes():
    corpus = json.loads(EXPLANATIONS_PATH.read_text(encoding="utf-8"))
    changed = json.loads(json.dumps(corpus))
    changed[0]["sources"][0]["description"] = f"{changed[0]['sources'][0]['description']} changed"

    changed_bytes = json.dumps(changed, ensure_ascii=False, indent=2).encode("utf-8")

    assert changed != corpus
    assert _sha256(changed_bytes) != ACCEPTED_CORPUS_HASH


def test_producer_and_pin_agree_on_the_same_hash():
    """`ingest_kb.corpus_sha256()` ghi manifest, test nay doc no — hai ben phai
    tinh giong nhau, neu khong manifest vua ghi xong da lam do suite."""

    assert corpus_sha256(EXPLANATIONS_PATH) == ACCEPTED_CORPUS_HASH
