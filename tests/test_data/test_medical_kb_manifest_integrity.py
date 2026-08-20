from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLANATIONS_PATH = REPO_ROOT / "data/reference/explanations.json"
MANIFEST_PATH = REPO_ROOT / "data/reference/medical_kb_manifest.json"
ACCEPTED_CORPUS_HASH = "a26e050e91122a4615990c56176aa2eb53e80be9e2250bacf05700a7ac45a0f4"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
