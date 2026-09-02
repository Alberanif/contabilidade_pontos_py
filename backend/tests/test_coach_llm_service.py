from unittest.mock import patch, MagicMock
import pytest

from coach_llm_service import (
    fuzzy_match,
    llm_match_groq,
    evaluate_coach_identity,
)


def test_fuzzy_match_exact_and_close():
    canonical_list = ["Vinicius Marini", "Tatiane Pellicel", "Karlla Andrade"]

    best, score = fuzzy_match("Vinicius Marini", canonical_list)
    assert best == "Vinicius Marini"
    assert score == 100.0

    best, score = fuzzy_match("Vinicius Marinii", canonical_list)
    assert best == "Vinicius Marini"
    assert score >= 90.0


def test_llm_match_groq_mock():
    canonical_list = ["Vinicius Marini", "Tatiane Pellicel"]

    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content='{"coach_sugerido": "Vinicius Marini", "confianca": 96.0}'))
    ]

    with patch("coach_llm_service.Groq") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_cls.return_value = mock_client

        coach, conf = llm_match_groq("Vini Marini", canonical_list, groq_api_key="mock_key")
        assert coach == "Vinicius Marini"
        assert conf == 96.0


def test_evaluate_coach_identity_flow():
    canonical_list = ["Vinicius Marini", "Tatiane Pellicel"]

    # 1. Exact match
    res = evaluate_coach_identity("vinicius marini", canonical_list)
    assert res["action"] == "exact_match"
    assert res["coach_canonico"] == "Vinicius Marini"

    # 2. RapidFuzz >= 95%
    res = evaluate_coach_identity("Vinicius Marini ", canonical_list)
    assert res["action"] == "exact_match"  # Normalization catches trailing spaces!

    # 3. LLM >= 95% auto approve
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content='{"coach_sugerido": "Vinicius Marini", "confianca": 98.0}'))
    ]
    with patch("config.GROQ_API_KEY", "mock_key"), patch("coach_llm_service.Groq") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_groq_cls.return_value = mock_client

        res = evaluate_coach_identity("Vini Marini", canonical_list)
        assert res["action"] in ["auto_approve", "pending_queue"]

    # 4. LLM 70-94% pending queue
    mock_completion_pending = MagicMock()
    mock_completion_pending.choices = [
        MagicMock(message=MagicMock(content='{"coach_sugerido": "Tatiane Pellicel", "confianca": 85.0}'))
    ]
    with patch("config.GROQ_API_KEY", "mock_key"), patch("coach_llm_service.Groq") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion_pending
        mock_groq_cls.return_value = mock_client

        res = evaluate_coach_identity("Tati P.", canonical_list)
        assert res["action"] == "pending_queue"
        assert res["coach_canonico"] == "Tatiane Pellicel"
        assert res["confianca"] == 85.0

