import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.desafios import excluir_desafio


class TestExcluirDesafioDescontaCoach:

    def test_desconta_pontos_de_coach_ao_excluir(self):
        desafio = {"id": 42, "nome": "Desafio G", "contabilizar_pontos": True, "origem": "csv_import"}
        registros_clan = [{"clan": "CLÃ 1", "total_pontos": 20}]
        registros_coach = [
            {"coach": "Ana Albertim", "total_pontos": 10},
            {"coach": "Gustavo Imhof", "total_pontos": 10},
        ]
        with patch("supabase_client.get_desafio", return_value=desafio), \
             patch("supabase_client.list_desafio_registros", return_value=registros_clan), \
             patch("supabase_client.add_delta_to_clan_total") as mock_delta_clan, \
             patch("supabase_client.list_desafio_registros_coach", return_value=registros_coach), \
             patch("supabase_client.add_delta_to_coach_total") as mock_delta_coach, \
             patch("supabase_client.delete_desafio", return_value=desafio) as mock_delete:
            resultado = excluir_desafio(42)

        mock_delta_clan.assert_called_once_with("CLÃ 1", -20)
        mock_delta_coach.assert_any_call("Ana Albertim", -10)
        mock_delta_coach.assert_any_call("Gustavo Imhof", -10)
        mock_delete.assert_called_once_with(42)
        assert resultado == {"mensagem": "Desafio 'Desafio G' excluído com sucesso."}

    def test_contabilizar_pontos_false_nao_desconta_nada(self):
        desafio = {"id": 42, "nome": "Desafio Manual", "contabilizar_pontos": False, "origem": "manual"}
        with patch("supabase_client.get_desafio", return_value=desafio), \
             patch("supabase_client.list_desafio_registros") as mock_list_clan, \
             patch("supabase_client.list_desafio_registros_coach") as mock_list_coach, \
             patch("supabase_client.add_delta_to_clan_total") as mock_delta_clan, \
             patch("supabase_client.add_delta_to_coach_total") as mock_delta_coach, \
             patch("supabase_client.delete_desafio", return_value=desafio):
            excluir_desafio(42)

        mock_list_clan.assert_not_called()
        mock_list_coach.assert_not_called()
        mock_delta_clan.assert_not_called()
        mock_delta_coach.assert_not_called()
