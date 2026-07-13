import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desafio_import_engine import (
    normalizar_validado,
    normalizar_nome,
    normalizar_clan,
    parse_submitted_at,
    parse_row,
    ImportRow,
    filtrar_por_periodo,
    filtrar_clans_validos,
)

MAPPING = {
    "clan": "Selecionar o Clã em que você está (1 a 8):",
    "nome": "Coloque aqui o seu Nome:",
    "validado": "Você cumpriu o Desafio Pontual G?",
    "submitted_at": "Submitted At",
    "token": "Token",
}


def _row(submitted_at):
    return ImportRow(
        clan="CLÃ 1", nome="X", nome_normalizado="x",
        validado=True, submitted_at=submitted_at, token="t1",
    )


def _row_com_clan(clan):
    return ImportRow(
        clan=clan, nome="X", nome_normalizado="x",
        validado=True, submitted_at=datetime(2026, 5, 20, 10, 0, 0), token="t1",
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


class TestParseRow:

    def test_linha_real_do_csv(self):
        raw_row = {
            "Selecionar o Clã em que você está (1 a 8):": "2",
            "Coloque aqui o seu Nome:": "Vinicius Alves",
            "Você cumpriu o Desafio Pontual G?": "Sim",
            "Submitted At": "11/05/2026 14:34:00",
            "Token": "gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        }
        row = parse_row(raw_row, MAPPING)
        assert row == ImportRow(
            clan="CLÃ 2",
            nome="Vinicius Alves",
            nome_normalizado="vinicius alves",
            validado=True,
            submitted_at=datetime(2026, 5, 11, 14, 34, 0),
            token="gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        )

    def test_linha_com_data_ilegivel(self):
        raw_row = {**{k: "" for k in MAPPING.values()}, MAPPING["submitted_at"]: "lixo"}
        row = parse_row(raw_row, MAPPING)
        assert row.submitted_at is None


class TestFiltrarPorPeriodo:

    def test_dentro_do_periodo(self):
        row = _row(datetime(2026, 5, 20, 10, 0, 0))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [row] and fora == []

    def test_limites_inclusivos(self):
        inicio = _row(datetime(2026, 5, 11, 0, 0, 0))
        fim = _row(datetime(2026, 6, 30, 23, 59, 59))
        dentro, fora = filtrar_por_periodo([inicio, fim], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [inicio, fim]

    def test_antes_do_periodo_excluido(self):
        row = _row(datetime(2026, 5, 1, 10, 0, 0))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]

    def test_depois_do_periodo_excluido(self):
        # Caso real: submissão de "Desafio H" em julho não deve contar pro "Desafio G"
        row = _row(datetime(2026, 7, 5, 0, 10, 21))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]

    def test_data_ausente_e_fail_closed(self):
        row = _row(None)
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]


CLANS_1_A_8 = {f"CLÃ {n}" for n in range(1, 9)}


class TestFiltrarClansValidos:

    def test_clan_valido_mantido(self):
        row = _row_com_clan("CLÃ 1")
        ok, invalidos = filtrar_clans_validos([row], CLANS_1_A_8)
        assert ok == [row] and invalidos == []

    def test_clan_fora_do_ranking_e_invalido(self):
        row = _row_com_clan("CLÃ 9")
        ok, invalidos = filtrar_clans_validos([row], CLANS_1_A_8)
        assert ok == [] and invalidos == [row]
