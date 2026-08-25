from __future__ import annotations

import pytest

from src.services.app_help_corpus_builder import (
    AppHelpCorpusError,
    build_corpus_chunks,
    parse_file,
)

CORPUS_DIR = "data/app_how_to_use"


def test_real_corpus_builds_without_error():
    chunks = build_corpus_chunks(CORPUS_DIR)
    assert len(chunks) > 0
    ids = [chunk.chunk_id for chunk in chunks]
    assert len(ids) == len(set(ids)), "chunk_ids must be unique across the whole corpus"


def test_every_chunk_has_required_metadata():
    chunks = build_corpus_chunks(CORPUS_DIR)
    for chunk in chunks:
        assert chunk.feature
        assert chunk.role in {"patient", "doctor", "patient,doctor", "doctor,patient"}
        assert chunk.route
        assert chunk.heading
        assert chunk.source_file.endswith(".md")
        assert chunk.text.strip()


def test_non_corpus_files_are_excluded():
    chunks = build_corpus_chunks(CORPUS_DIR)
    source_files = {chunk.source_file for chunk in chunks}
    assert "FEATURE_INVENTORY.md" not in source_files
    assert "PROVENANCE_REPORT.md" not in source_files


def test_missing_front_matter_raises(tmp_path):
    bad_file = tmp_path / "broken.md"
    bad_file.write_text("## Chỉ có heading, không có metadata\n\nNội dung.\n", encoding="utf-8")
    with pytest.raises(AppHelpCorpusError):
        parse_file(bad_file)


def test_missing_required_metadata_key_raises(tmp_path):
    bad_file = tmp_path / "broken.md"
    bad_file.write_text(
        "```\nfeature: x\nrole: patient\n```\n\n## Heading\n\nBody.\n",
        encoding="utf-8",
    )
    with pytest.raises(AppHelpCorpusError):
        parse_file(bad_file)


def test_empty_corpus_dir_raises(tmp_path):
    with pytest.raises(AppHelpCorpusError):
        build_corpus_chunks(tmp_path)
