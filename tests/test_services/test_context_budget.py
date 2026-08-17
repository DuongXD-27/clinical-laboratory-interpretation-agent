"""Unit tests for the bounded-context helper."""

from __future__ import annotations

from src.services.context_budget import build_bounded_context


def _chunk(text: str, indicator_name: str = "WBC") -> dict:
    return {"indicator_name": indicator_name, "text": text}


def test_all_chunks_fit_within_budget():
    chunks = [_chunk("a" * 100), _chunk("b" * 100), _chunk("c" * 100)]

    result = build_bounded_context(chunks, max_chars=1000)

    assert result == ("a" * 100) + "\n\n" + ("b" * 100) + "\n\n" + ("c" * 100)
    assert len(result) <= 1000


def test_keeps_most_relevant_chunks_and_drops_overflow():
    chunks = [_chunk("first"), _chunk("second"), _chunk("third")]

    result = build_bounded_context(chunks, max_chars=14)

    assert result == "first\n\nsecond"
    assert "third" not in result


def test_first_chunk_is_never_dropped_even_when_it_exceeds_budget():
    chunks = [_chunk("x" * 500), _chunk("y" * 10)]

    result = build_bounded_context(chunks, max_chars=200)

    assert result == "x" * 500
    assert "y" not in result


def test_never_truncates_mid_chunk():
    chunks = [_chunk("a" * 30), _chunk("b" * 30), _chunk("c" * 30)]

    result = build_bounded_context(chunks, max_chars=45)

    assert result == "a" * 30
    assert "b" not in result


def test_empty_text_and_empty_chunks_are_ignored():
    assert build_bounded_context([_chunk("")], max_chars=100) == ""
    assert build_bounded_context([], max_chars=100) == ""
