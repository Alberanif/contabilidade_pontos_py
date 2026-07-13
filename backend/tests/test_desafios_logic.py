import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from points_engine import calculate_desafio_pontos


class TestCalculateDesafioPontos:

    def test_sem_campos_retorna_zero(self):
        assert calculate_desafio_pontos([], {}) == 0

    def test_soma_campos_pontuacao(self):
        campos = [
            {"id": 1, "tipo": "pontuacao"},
            {"id": 2, "tipo": "pontuacao"},
        ]
        valores = {"1": 30, "2": 20}
        assert calculate_desafio_pontos(campos, valores) == 50

    def test_ignora_campos_texto(self):
        campos = [
            {"id": 1, "tipo": "texto"},
            {"id": 2, "tipo": "pontuacao"},
        ]
        valores = {"1": "descrição", "2": 15}
        assert calculate_desafio_pontos(campos, valores) == 15

    def test_campo_ausente_no_valores_conta_zero(self):
        campos = [{"id": 1, "tipo": "pontuacao"}]
        assert calculate_desafio_pontos(campos, {}) == 0

    def test_valor_string_numerica_convertida(self):
        campos = [{"id": 1, "tipo": "pontuacao"}]
        valores = {"1": "25"}
        assert calculate_desafio_pontos(campos, valores) == 25

    def test_valor_invalido_ignorado(self):
        campos = [{"id": 1, "tipo": "pontuacao"}]
        valores = {"1": "abc"}
        assert calculate_desafio_pontos(campos, valores) == 0

    def test_todos_campos_texto_retorna_zero(self):
        campos = [{"id": 1, "tipo": "texto"}, {"id": 2, "tipo": "texto"}]
        valores = {"1": "foo", "2": "bar"}
        assert calculate_desafio_pontos(campos, valores) == 0


from points_engine import diff_desafio_registros


class TestDiffDesafioRegistros:

    def test_clan_novo_com_contabilizar_soma_delta(self):
        resultado = diff_desafio_registros([], [{"clan": "Clã 1", "pontos": 50}], True, True)
        assert resultado["to_create"] == [{"clan": "Clã 1", "pontos": 50}]
        assert resultado["to_delete"] == []
        assert resultado["to_update"] == []
        assert resultado["clan_deltas"] == {"Clã 1": 50}

    def test_clan_novo_sem_contabilizar_nao_gera_delta(self):
        resultado = diff_desafio_registros([], [{"clan": "Clã 1", "pontos": 50}], True, False)
        assert resultado["to_create"] == [{"clan": "Clã 1", "pontos": 50}]
        assert resultado["clan_deltas"] == {}

    def test_clan_removido_com_contabilizar_desconta(self):
        old = [{"id": 1, "clan": "Clã 1", "total_pontos": 40}]
        resultado = diff_desafio_registros(old, [], True, True)
        assert resultado["to_delete"] == [1]
        assert resultado["clan_deltas"] == {"Clã 1": -40}

    def test_clan_removido_sem_contabilizar_nao_desconta(self):
        old = [{"id": 1, "clan": "Clã 1", "total_pontos": 40}]
        resultado = diff_desafio_registros(old, [], False, True)
        assert resultado["to_delete"] == [1]
        assert resultado["clan_deltas"] == {}

    def test_clan_atualizado_true_true_aplica_delta_liquido(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, True, True)
        assert resultado["to_update"] == [{"id": 2, "clan": "Clã 1", "pontos": 50}]
        assert resultado["clan_deltas"] == {"Clã 1": 20}

    def test_clan_atualizado_true_false_desconta_total_antigo(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, True, False)
        assert resultado["clan_deltas"] == {"Clã 1": -30}

    def test_clan_atualizado_false_true_soma_total_novo(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, False, True)
        assert resultado["clan_deltas"] == {"Clã 1": 50}

    def test_clan_atualizado_false_false_sem_delta(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, False, False)
        assert resultado["clan_deltas"] == {}

    def test_clan_inalterado_aparece_em_to_update_sem_delta(self):
        old = [{"id": 3, "clan": "Clã 1", "total_pontos": 50}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, True, True)
        assert resultado["to_update"] == [{"id": 3, "clan": "Clã 1", "pontos": 50}]
        assert resultado["clan_deltas"] == {}

    def test_multiplos_clans_combinados(self):
        old = [
            {"id": 1, "clan": "Clã 1", "total_pontos": 30},
            {"id": 2, "clan": "Clã 2", "total_pontos": 20},
        ]
        new = [
            {"clan": "Clã 1", "pontos": 30},
            {"clan": "Clã 3", "pontos": 10},
        ]
        resultado = diff_desafio_registros(old, new, True, True)
        assert resultado["to_delete"] == [2]
        assert resultado["to_create"] == [{"clan": "Clã 3", "pontos": 10}]
        assert resultado["to_update"] == [{"id": 1, "clan": "Clã 1", "pontos": 30}]
        assert resultado["clan_deltas"] == {"Clã 2": -20, "Clã 3": 10}
