"""Build Chroma-ready chunks from the App Help markdown corpus.

Each source file under ``data/app_how_to_use/`` starts with a fenced
metadata block (``feature``/``role``/``route``/``section``) followed by a
series of ``##`` sections. Unlike the medical corpus (fixed 35-analyte
schema, see ``corpus_builder.py``), this corpus has no fixed content schema
— it is plain product documentation — so the builder only has to parse
front matter + split on ``##`` headings, not validate clinical rule bands.

One chunk is emitted per ``##`` section so retrieval can return a focused
answer (e.g. just "Điều kiện/giới hạn?") instead of a whole multi-topic
file.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Files in the corpus directory that are not part of the retrievable corpus
# itself (review/audit artifacts from Phase 1).
NON_CORPUS_FILES = {"FEATURE_INVENTORY.md", "PROVENANCE_REPORT.md"}

_FRONT_MATTER_RE = re.compile(r"^```\n(.*?)\n```\n*(.*)$", re.DOTALL)
_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


class AppHelpCorpusError(Exception):
    """Raised when a corpus source file is malformed."""


@dataclass(frozen=True)
class AppHelpChunk:
    chunk_id: str
    text: str
    feature: str
    role: str
    route: str
    section: str
    heading: str
    source_file: str


def _slugify(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_accents = without_accents.replace("đ", "d")
    slug = re.sub(r"[^a-z0-9]+", "-", without_accents).strip("-")
    return slug or "section"


def _parse_front_matter(raw: str, source_file: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(raw.strip() + "\n")
    if not match:
        raise AppHelpCorpusError(f"{source_file}: missing fenced metadata block at top of file")
    block, body = match.group(1), match.group(2)
    metadata: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise AppHelpCorpusError(f"{source_file}: malformed metadata line: {line!r}")
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()
    for required in ("feature", "role", "route", "section"):
        if required not in metadata or not metadata[required]:
            raise AppHelpCorpusError(f"{source_file}: metadata missing required key '{required}'")
    return metadata, body


def _split_sections(body: str) -> list[tuple[str, str]]:
    headings = list(_HEADING_RE.finditer(body))
    if not headings:
        raise AppHelpCorpusError("no '##' sections found in file body")
    sections: list[tuple[str, str]] = []
    for index, heading_match in enumerate(headings):
        heading = heading_match.group(1).strip()
        start = heading_match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        text = body[start:end].strip()
        sections.append((heading, text))
    return sections


def parse_file(path: Path) -> list[AppHelpChunk]:
    raw = path.read_text(encoding="utf-8")
    metadata, body = _parse_front_matter(raw, path.name)
    sections = _split_sections(body)
    chunks: list[AppHelpChunk] = []
    for heading, text in sections:
        if not text:
            continue
        chunk_id = f"{metadata['feature']}::{_slugify(heading)}"
        # Prepend the heading so the embedded text carries its own topic
        # label — needed since a section like "Không làm được gì?" read in
        # isolation would otherwise lose that framing.
        chunk_text = f"{heading}\n\n{text}"
        chunks.append(
            AppHelpChunk(
                chunk_id=chunk_id,
                text=chunk_text,
                feature=metadata["feature"],
                role=metadata["role"],
                route=metadata["route"],
                section=metadata["section"],
                heading=heading,
                source_file=path.name,
            )
        )
    return chunks


def build_corpus_chunks(corpus_dir: str | Path) -> list[AppHelpChunk]:
    directory = Path(corpus_dir)
    if not directory.is_dir():
        raise AppHelpCorpusError(f"corpus directory not found: {directory}")
    chunks: list[AppHelpChunk] = []
    seen_ids: set[str] = set()
    for path in sorted(directory.glob("*.md")):
        if path.name in NON_CORPUS_FILES:
            continue
        try:
            file_chunks = parse_file(path)
        except AppHelpCorpusError as exc:
            raise AppHelpCorpusError(f"{path.name}: {exc}") from exc
        for chunk in file_chunks:
            if chunk.chunk_id in seen_ids:
                raise AppHelpCorpusError(f"duplicate chunk_id across corpus: {chunk.chunk_id}")
            seen_ids.add(chunk.chunk_id)
        chunks.extend(file_chunks)
    if not chunks:
        raise AppHelpCorpusError(f"no corpus chunks found under {directory}")
    return chunks
