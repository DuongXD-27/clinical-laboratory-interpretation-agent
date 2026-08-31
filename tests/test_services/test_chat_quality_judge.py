from __future__ import annotations

import pytest

from src.services import chat_quality_judge


def test_judge_parser_accepts_three_scores_and_safety_flag():
    result = chat_quality_judge._parse(
        'prefix {"groundedness": 0.8, "faithfulness": 0.7, "relevance": 0.9, "safety_violation": true}'
    )
    assert result == {
        "groundedness": 0.8,
        "faithfulness": 0.7,
        "relevance": 0.9,
        "safety_violation": True,
    }


def test_judge_parser_clamps_scores():
    result = chat_quality_judge._parse(
        '{"groundedness": 2, "faithfulness": -1, "relevance": 0.5, "safety_violation": false}'
    )
    assert result["groundedness"] == 1.0
    assert result["faithfulness"] == 0.0


def test_judge_parser_rejects_non_json():
    with pytest.raises(ValueError, match="judge_json_missing"):
        chat_quality_judge._parse("not json")
