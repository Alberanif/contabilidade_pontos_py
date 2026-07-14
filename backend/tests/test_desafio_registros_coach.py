import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
import supabase_client


def _mock_client(returned_rows):
    result = MagicMock()
    result.data = returned_rows
    chain = MagicMock()
    chain.execute.return_value = result
    for m in ("table", "select", "insert", "update", "eq", "order"):
        getattr(chain, m).return_value = chain
    client = MagicMock()
    client.table.return_value = chain
    return client


class TestCreateDesafioRegistroCoach:

    def test_insere_e_retorna_primeira_linha(self):
        row = {"id": 1, "desafio_id": 5, "coach": "Ana Albertim", "valores": {}, "total_pontos": 10}
        with patch("supabase_client._get_client", return_value=_mock_client([row])):
            result = supabase_client.create_desafio_registro_coach(5, "Ana Albertim", {}, 10)
        assert result == row


class TestGetDesafioRegistroCoachByCoach:

    def test_encontrado_retorna_linha(self):
        row = {"id": 1, "desafio_id": 5, "coach": "Ana Albertim", "total_pontos": 10}
        with patch("supabase_client._get_client", return_value=_mock_client([row])):
            result = supabase_client.get_desafio_registro_coach_by_coach(5, "Ana Albertim")
        assert result == row

    def test_nao_encontrado_retorna_none(self):
        with patch("supabase_client._get_client", return_value=_mock_client([])):
            result = supabase_client.get_desafio_registro_coach_by_coach(5, "Ninguem")
        assert result is None


class TestUpdateDesafioRegistroCoachPontos:

    def test_atualiza_e_retorna_linha(self):
        row = {"id": 1, "valores": {"9": "2"}, "total_pontos": 20}
        with patch("supabase_client._get_client", return_value=_mock_client([row])):
            result = supabase_client.update_desafio_registro_coach_pontos(1, {"9": "2"}, 20)
        assert result == row


class TestListDesafioRegistrosCoach:

    def test_lista_registros_do_desafio(self):
        rows = [{"id": 1, "coach": "Ana Albertim"}, {"id": 2, "coach": "Gustavo Imhof"}]
        with patch("supabase_client._get_client", return_value=_mock_client(rows)):
            result = supabase_client.list_desafio_registros_coach(5)
        assert result == rows


class TestAddDeltaToCoachTotal:

    def test_soma_delta_positivo_ao_total_existente(self):
        with patch("supabase_client.get_coach_totals", return_value={"Ana Albertim": 30}), \
             patch("supabase_client.upsert_coach_total",
                   return_value={"coach": "Ana Albertim", "total_pontos": 40}) as mock_upsert:
            result = supabase_client.add_delta_to_coach_total("Ana Albertim", 10)
        mock_upsert.assert_called_once_with("Ana Albertim", 40)
        assert result == {"coach": "Ana Albertim", "total_pontos": 40}

    def test_coach_sem_total_existente_parte_de_zero(self):
        with patch("supabase_client.get_coach_totals", return_value={}), \
             patch("supabase_client.upsert_coach_total",
                   return_value={"coach": "Novo Coach", "total_pontos": 10}) as mock_upsert:
            supabase_client.add_delta_to_coach_total("Novo Coach", 10)
        mock_upsert.assert_called_once_with("Novo Coach", 10)

    def test_delta_negativo_nao_passa_de_zero(self):
        with patch("supabase_client.get_coach_totals", return_value={"Ana Albertim": 10}), \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert:
            supabase_client.add_delta_to_coach_total("Ana Albertim", -50)
        mock_upsert.assert_called_once_with("Ana Albertim", 0)
