"""Conservative lexical resolution primitives for locked analyte names.

This module handles presentation noise only. It never infers analyte identity
from values, units, reference intervals, or medical similarity.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

ResolutionStatus = Literal["RESOLVED", "AMBIGUOUS", "UNSUPPORTED"]

# Identity-only aliases verified as exact lexical equivalents. Clinical rules
# and source data remain unchanged.
SAFE_RUNTIME_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "Triglycerid": "Triglyceride",
    }
)

# Labels whose analyte family is recognizable but whose locked canonical rule
# requires a qualifier absent from the source label.
AMBIGUOUS_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "glucose": "Fasting plasma glucose",
        "glucose mau": "Fasting plasma glucose",
        "duong huyet": "Fasting plasma glucose",
    }
)

_HOSPITAL_PREFIXES = (
    "dinh luong",
    "xet nghiem",
)
_ANNOTATION_RE = re.compile(r"[\[(]([^\])]+)[\])]", re.IGNORECASE)
_SAFE_SPECIMEN_ANNOTATIONS = frozenset({"mau", "blood"})


@dataclass(frozen=True)
class AnalyteNameResolution:
    status: ResolutionStatus
    raw_name: str
    normalized_name: str
    lookup_key: str
    canonical_name: str | None
    specimen_annotations: tuple[str, ...] = ()
    reason: str = ""


def normalize_analyte_lookup_key(value: Any) -> str:
    """Normalize safe lexical variation without adding medical semantics."""
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.replace("đ", "d").replace("%", " percent ")
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens = [{"percentage": "percent", "absolute": "abs"}.get(token, token) for token in tokens]
    if len(tokens) >= 2 and all(len(token) == 1 and token.isalpha() for token in tokens):
        return "".join(tokens)
    return " ".join(tokens)


def _structural_candidate(value: Any) -> tuple[str, tuple[str, ...]]:
    raw_name = str(value or "").strip()
    annotations: list[str] = []

    def remove_safe_annotation(match: re.Match[str]) -> str:
        annotation = normalize_analyte_lookup_key(match.group(1))
        if annotation in _SAFE_SPECIMEN_ANNOTATIONS:
            annotations.append(annotation)
            return " "
        return match.group(0)

    without_safe_annotations = _ANNOTATION_RE.sub(remove_safe_annotation, raw_name)
    candidate = normalize_analyte_lookup_key(without_safe_annotations)
    for prefix in _HOSPITAL_PREFIXES:
        if candidate == prefix:
            candidate = ""
            break
        if candidate.startswith(f"{prefix} "):
            candidate = candidate[len(prefix) + 1 :]
            break
    return candidate, tuple(dict.fromkeys(annotations))


def analyte_lookup_candidates(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return exact-first lookup candidates and preserved specimen annotations."""
    exact = normalize_analyte_lookup_key(value)
    structural, annotations = _structural_candidate(value)
    candidates = tuple(dict.fromkeys(key for key in (exact, structural) if key))
    return candidates, annotations


def resolve_analyte_name(
    value: Any,
    alias_map: Mapping[str, str],
) -> AnalyteNameResolution:
    """Resolve exact/approved lexical forms, then fail closed on ambiguity."""
    raw_name = str(value or "").strip()
    candidates, annotations = analyte_lookup_candidates(raw_name)
    for candidate in candidates:
        canonical = alias_map.get(candidate)
        if canonical:
            return AnalyteNameResolution(
                status="RESOLVED",
                raw_name=raw_name,
                normalized_name=candidate,
                lookup_key=candidate,
                canonical_name=canonical,
                specimen_annotations=annotations,
                reason="approved_exact_or_lexical_match",
            )

    for candidate in reversed(candidates):
        possible_canonical = AMBIGUOUS_LABELS.get(candidate)
        if possible_canonical:
            return AnalyteNameResolution(
                status="AMBIGUOUS",
                raw_name=raw_name,
                normalized_name=candidate,
                lookup_key=candidate,
                canonical_name=None,
                specimen_annotations=annotations,
                reason=f"missing required qualifier for {possible_canonical}",
            )

    key = candidates[-1] if candidates else ""
    return AnalyteNameResolution(
        status="UNSUPPORTED",
        raw_name=raw_name,
        normalized_name=key,
        lookup_key=key,
        canonical_name=None,
        specimen_annotations=annotations,
        reason="no approved deterministic alias",
    )
