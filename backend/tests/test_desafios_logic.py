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
