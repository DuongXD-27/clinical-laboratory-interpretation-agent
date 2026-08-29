"""Deterministic release gate for LLM-authored explanation supplements."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any

from src.services.patient_explanation import filter_patient_education_text

_NUMERIC_FACT = re.compile(r"(?:[<>]=?|[≤≥])?\s*\d+(?:[.,]\d+)?")
_GROUNDING_STOPWORDS = frozenset(
    {"va", "co", "the", "duoc", "cua", "trong", "mot", "nay", "cho", "voi", "khi"}
)


def _content_tokens(text: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(character for character in decomposed if not unicodedata.combining(character)).replace("đ", "d")
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 2 and token not in _GROUNDING_STOPWORDS
    }


def evidence_has_numeric_conflict(chunks: list[dict[str, Any]]) -> bool:
    """Detect incompatible numeric claims for the same note type across sources.

    This intentionally does not attempt medical entailment. It catches the
    deterministic conflict class we can prove locally: two distinct sources
    provide different numeric facts for the same explanatory role.
    """
    claims: dict[str, dict[str, frozenset[str]]] = defaultdict(dict)
    for chunk in chunks:
        source_id = str(chunk.get("source_id") or chunk.get("source_url") or "").strip()
        note_type = str(chunk.get("note_type") or "").strip()
        numeric = frozenset(match.replace(" ", "").replace(",", ".") for match in _NUMERIC_FACT.findall(str(chunk.get("text") or "")))
        if source_id and note_type and numeric:
            claims[note_type][source_id] = numeric
    return any(len(set(by_source.values())) > 1 for by_source in claims.values() if len(by_source) > 1)


def validate_generated_supplement(
    text: str,
    *,
    evidence_text: str = "",
) -> tuple[str | None, str | None]:
    """Accept only non-numeric, locally safe educational prose.

    Values, thresholds, units, status and band labels are rendered from the
    immutable fact envelope, so an LLM has no legitimate reason to restate a
    number. Unsafe or certainty-strengthened segments are removed by the same
    patient education filter used by deterministic fallbacks.
    """
    candidate = str(text or "").strip()
    if not candidate:
        return None, "empty_output"
    if _NUMERIC_FACT.search(candidate):
        return None, "numeric_fact_in_generated_prose"
    filtered = filter_patient_education_text(candidate)
    if not filtered:
        return None, "unsafe_or_unsupported_generated_prose"
    if evidence_text:
        generated_tokens = _content_tokens(filtered)
        evidence_tokens = _content_tokens(evidence_text)
        if generated_tokens and len(generated_tokens & evidence_tokens) / len(generated_tokens) < 0.7:
            return None, "insufficient_evidence_overlap"
    return filtered, ("sanitized_generated_prose" if filtered != candidate else None)
