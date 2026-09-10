import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from routers.desafios import excluir_desafio


class TestExcluirDesafioBloqueadoNaoDescontaCoach:
    """A lógica de desconto de pontos de coach ao excluir um desafio (antigo
    `desafio_registros_coach`) foi removida junto com o bloqueio do endpoint
    (issue #17): o handler agora só levanta HTTP 410, sem tocar em nenhuma
    tabela de clã/coach."""

    def test_excluir_desafio_bloqueado_nao_chama_nenhuma_funcao_de_pontos(self):
        with patch("supabase_client.get_desafio") as mock_get, \
             patch("supabase_client.list_desafio_registros") as mock_list_clan, \
             patch("supabase_client.add_delta_to_clan_total") as mock_delta_clan, \
             patch("supabase_client.list_desafio_registros_coach") as mock_list_coach, \
             patch("supabase_client.add_delta_to_coach_total") as mock_delta_coach, \
             patch("supabase_client.delete_desafio") as mock_delete:
            with pytest.raises(HTTPException) as exc_info:
                excluir_desafio(42)

        assert exc_info.value.status_code == 410
        mock_get.assert_not_called()
        mock_list_clan.assert_not_called()
        mock_delta_clan.assert_not_called()
        mock_list_coach.assert_not_called()
        mock_delta_coach.assert_not_called()
        mock_delete.assert_not_called()
