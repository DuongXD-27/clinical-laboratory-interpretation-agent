"""Deterministic provenance snapshots for analysis facts and knowledge artifacts."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@lru_cache(maxsize=1)
def artifact_provenance() -> dict[str, Any]:
    """Return immutable versions/hashes used by the running analysis process."""
    root = Path(__file__).resolve().parents[2]
    config_path = root / "data/reference/reference_checker_config.json"
    ranges_path = root / "data/reference/reference_ranges.json"
    manifest_path = root / "data/reference/medical_kb_manifest.json"

    config = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "reference_config_version": str(config.get("config_version") or ""),
        "reference_config_sha256": _normalized_sha256(config_path),
        "reference_rules_sha256": _normalized_sha256(ranges_path),
        "corpus_version": str(manifest.get("corpus_version") or ""),
        "corpus_sha256": str(manifest.get("corpus_sha256") or ""),
        "corpus_schema_version": manifest.get("schema_version"),
    }


def classification_provenance(rule: dict[str, Any], canonical_analyte: str) -> dict[str, Any]:
    """Snapshot the exact deterministic rule authority without borrowing RAG metadata."""
    artifacts = artifact_provenance()
    return {
        "rule_id": str(rule.get("rule_id") or ""),
        "reference_type": str(rule.get("reference_type") or ""),
        "analyte": canonical_analyte,
        "source_id": str(rule.get("source_id") or "") or None,
        "source_title": str(rule.get("source_title") or "") or None,
        "source_organization": str(rule.get("source_organization") or "") or None,
        "source_url": str(rule.get("source_url") or "") or None,
        "source_date": str(rule.get("source_date") or "") or None,
        "source_revision": str(rule.get("source_revision") or "") or None,
        "source_section": str(rule.get("source_section") or "") or None,
        "reference_config_version": artifacts["reference_config_version"],
        "reference_config_sha256": artifacts["reference_config_sha256"],
        "reference_rules_sha256": artifacts["reference_rules_sha256"],
    }
