import sys, os, io, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from routers.desafio_import import preview, confirmar


class _FakeUploadFile:
    def __init__(self, content: bytes = b""):
        self.file = io.BytesIO(content)


def _config(desafio_id=None):
    return json.dumps({
        "nome": "Desafio Teste",
        "desafio_id": desafio_id,
        "data_inicio": "2026-05-11",
        "data_fim": "2026-06-30",
        "pontos_por_participacao": 10,
    })


class TestPreviewBloqueado:
    """A importação de CSV foi bloqueada (issue #17): a Google Sheet de desafios
    é a única fonte de verdade. /preview não processa mais nada — nem chega a
    tocar em google_sheets_client ou supabase_client."""

    def test_preview_retorna_410_sem_processar_nada(self):
        with patch("google_sheets_client.fetch_ranking") as mock_ranking, \
             patch("supabase_client.get_tokens_importados") as mock_tokens, \
             patch("supabase_client.get_coach_alias_map") as mock_alias:
            with pytest.raises(HTTPException) as exc_info:
                preview(
                    file=_FakeUploadFile(),
                    mapping=json.dumps({}),
                    config=_config(),
                )

        assert exc_info.value.status_code == 410
        mock_ranking.assert_not_called()
        mock_tokens.assert_not_called()
        mock_alias.assert_not_called()


class TestConfirmarBloqueado:
    """A confirmação de importação de CSV foi bloqueada (issue #17): nenhum
    registro de desafio ou de coach é mais criado/atualizado por este endpoint."""

    def test_confirmar_retorna_410_sem_persistir_nada(self):
        with patch("google_sheets_client.fetch_ranking") as mock_ranking, \
             patch("supabase_client.create_desafio") as mock_create_desafio, \
             patch("supabase_client.create_desafio_registro_coach") as mock_create_coach, \
             patch("supabase_client.add_delta_to_coach_total") as mock_delta_coach, \
             patch("supabase_client.add_delta_to_clan_total") as mock_delta_clan:
            with pytest.raises(HTTPException) as exc_info:
                confirmar(
                    file=_FakeUploadFile(),
                    mapping=json.dumps({}),
                    config=_config(),
                )

        assert exc_info.value.status_code == 410
        mock_ranking.assert_not_called()
        mock_create_desafio.assert_not_called()
        mock_create_coach.assert_not_called()
        mock_delta_coach.assert_not_called()
        mock_delta_clan.assert_not_called()
