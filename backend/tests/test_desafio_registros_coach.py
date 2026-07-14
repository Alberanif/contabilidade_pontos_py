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


class TestGetAllDesafioCoachNames:

    def test_retorna_nomes_distintos_ignorando_nulos(self):
        rows = [{"coach": "Ana Albertim"}, {"coach": "Ana Albertim"}, {"coach": None}]
        with patch("supabase_client._get_client", return_value=_mock_client(rows)):
            result = supabase_client.get_all_desafio_coach_names()
        assert result == {"Ana Albertim"}


class TestUpdateDesafioImportacaoLinhasCoach:

    def test_reescreve_coach_e_retorna_quantidade(self):
        with patch("supabase_client._get_client", return_value=_mock_client([{"id": 1}, {"id": 2}])):
            result = supabase_client.update_desafio_importacao_linhas_coach("Vini Marini", "Vinicius Marini")
        assert result == 2


class TestGetDesafioCoachTotal:

    def test_soma_total_pontos_de_todos_os_desafios_do_coach(self):
        rows = [{"total_pontos": 10}, {"total_pontos": 15}]
        with patch("supabase_client._get_client", return_value=_mock_client(rows)):
            result = supabase_client.get_desafio_coach_total("Vinicius Marini")
        assert result == 25

    def test_sem_registros_retorna_zero(self):
        with patch("supabase_client._get_client", return_value=_mock_client([])):
            result = supabase_client.get_desafio_coach_total("Ninguem")
        assert result == 0


class TestMergeDesafioRegistrosCoach:

    def _mock_merge_client(self, raw_rows, canonical_rows):
        result_raw = MagicMock()
        result_raw.data = raw_rows
        chain_raw = MagicMock()
        chain_raw.execute.return_value = result_raw
        for m in ("table", "select", "eq"):
            getattr(chain_raw, m).return_value = chain_raw

        result_canonical = MagicMock()
        result_canonical.data = canonical_rows
        chain_canonical = MagicMock()
        chain_canonical.execute.return_value = result_canonical
        for m in ("table", "select", "eq"):
            getattr(chain_canonical, m).return_value = chain_canonical

        write_chain = MagicMock()
        write_result = MagicMock()
        write_result.data = []
        write_chain.execute.return_value = write_result
        for m in ("table", "update", "delete", "eq"):
            getattr(write_chain, m).return_value = write_chain

        client = MagicMock()
        client.table.side_effect = [chain_raw, chain_canonical] + [write_chain] * 10
        return client, write_chain

    def test_sem_linhas_do_raw_coach_nao_faz_nada(self):
        client, _ = self._mock_merge_client([], [])
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.merge_desafio_registros_coach("Vini Marini", "Vinicius Marini")
        assert result == 0

    def test_desafio_sem_conflito_so_renomeia(self):
        raw_rows = [{"id": 1, "desafio_id": 100, "coach": "Vini Marini",
                     "valores": {"1": "1", "2": 10}, "total_pontos": 10}]
        client, write_chain = self._mock_merge_client(raw_rows, [])
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.merge_desafio_registros_coach("Vini Marini", "Vinicius Marini")
        assert result == 1
        write_chain.update.assert_any_call({"coach": "Vinicius Marini"})

    def test_desafio_com_conflito_soma_e_apaga_linha_antiga(self):
        raw_rows = [{"id": 1, "desafio_id": 100, "coach": "Vini Marini",
                     "valores": {"1": "1", "2": 10}, "total_pontos": 10}]
        canonical_rows = [{"id": 2, "desafio_id": 100, "coach": "Vinicius Marini",
                            "valores": {"1": "2", "2": 20}, "total_pontos": 20}]
        client, write_chain = self._mock_merge_client(raw_rows, canonical_rows)
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.merge_desafio_registros_coach("Vini Marini", "Vinicius Marini")
        assert result == 1
        write_chain.update.assert_any_call({"valores": {"1": "3", "2": 30}, "total_pontos": 30})
        write_chain.delete.assert_called_once()
