import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desafio_import_engine import (
    normalizar_validado,
    normalizar_nome,
    normalizar_clan,
    parse_submitted_at,
)


class TestNormalizarValidado:

    def test_sim_exato(self):
        assert normalizar_validado("Sim") is True

    def test_sim_minusculo(self):
        assert normalizar_validado("sim") is True

    def test_sim_com_espacos(self):
        assert normalizar_validado("  Sim  ") is True

    def test_nao_e_falso(self):
        assert normalizar_validado("Não") is False

    def test_vazio_e_falso(self):
        assert normalizar_validado("") is False

    def test_valor_ambiguo_e_falso(self):
        assert normalizar_validado("Talvez") is False


class TestNormalizarNome:

    def test_trim_e_lowercase(self):
        assert normalizar_nome("  Ana Albertim  ") == "ana albertim"

    def test_mesma_pessoa_capitalizacao_diferente(self):
        # Caso real do CSV: "Carolina dorte gadbem" vs "carolina dorte gadbem"
        assert normalizar_nome("Carolina dorte gadbem") == normalizar_nome("carolina dorte gadbem")

    def test_espacos_internos_multiplos_preservados(self):
        assert normalizar_nome("Ana  Paula") == "ana  paula"


class TestNormalizarClan:

    def test_numero_simples(self):
        assert normalizar_clan("2") == "CLÃ 2"

    def test_numero_com_espacos(self):
        assert normalizar_clan(" 8 ") == "CLÃ 8"

    def test_nao_numerico_mantido_como_esta(self):
        # Mesmo fallback de _normalize_clan em routers/contabilidade.py
        assert normalizar_clan("abc") == "abc"


class TestParseSubmittedAt:

    def test_formato_completo_com_hora(self):
        assert parse_submitted_at("11/05/2026 14:34:00") == datetime(2026, 5, 11, 14, 34, 0)

    def test_data_invalida_retorna_none(self):
        # Junho só tem 30 dias
        assert parse_submitted_at("31/06/2026 10:00:00") is None

    def test_texto_nao_reconhecido_retorna_none(self):
        assert parse_submitted_at("não é uma data") is None

    def test_vazio_retorna_none(self):
        assert parse_submitted_at("") is None
