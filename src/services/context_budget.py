"""Helpers for bounding the amount of retrieved context sent to an LLM.

Retrieved chunks are ordered by relevance; we always keep the first (most
relevant) chunk and then append further chunks only while they fit inside the
configured budget. A chunk is never truncated mid-sentence, so the LLM always
receives complete, grounded statements.
"""

from __future__ import annotations

from src.agents.state import RetrievedChunk


def build_bounded_context(chunks: list[RetrievedChunk], *, max_chars: int) -> str:
    """Join chunk texts up to ``max_chars`` without cutting inside a chunk.

    The first (most relevant) chunk is always kept even if it alone exceeds
    the budget, so grounding never collapses to an empty context.
    """
    parts: list[str] = []
    total = 0
    for index, chunk in enumerate(chunks):
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        if index == 0 or total + len(text) <= max_chars:
            parts.append(text)
            total += len(text)
        else:
            break
    return "\n\n".join(parts)
