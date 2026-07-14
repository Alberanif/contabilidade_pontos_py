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
    filtrar_tokens_novos,
    deduplicar_por_pessoa,
    ContabilizacaoRow,
    processar_importacao,
)

MAPPING_TESTE = {
    "clan": "clan", "nome": "nome", "validado": "validado",
    "submitted_at": "data", "token": "token",
}


def _raw(clan, nome, validado, data, token):
    return {"clan": clan, "nome": nome, "validado": validado, "data": data, "token": token}

MAPPING = {
    "clan": "Selecionar o Clã em que você está (1 a 8):",
    "nome": "Coloque aqui o seu Nome:",
    "validado": "Você cumpriu o Desafio Pontual G?",
    "submitted_at": "Submitted At",
    "token": "Token",
}


def _row(submitted_at):
    return ImportRow(
        clan="CLÃ 1", nome="X", nome_normalizado="x", coach="X",
        validado=True, submitted_at=submitted_at, token="t1",
    )


def _row_com_clan(clan):
    return ImportRow(
        clan=clan, nome="X", nome_normalizado="x", coach="X",
        validado=True, submitted_at=datetime(2026, 5, 20, 10, 0, 0), token="t1",
    )


def _row_com_token(token):
    return ImportRow(
        clan="CLÃ 1", nome="X", nome_normalizado="x", coach="X",
        validado=True, submitted_at=datetime(2026, 5, 20, 10, 0, 0), token=token,
    )


def _row_pessoa(clan, nome, submitted_at):
    return ImportRow(
        clan=clan, nome=nome, nome_normalizado=normalizar_nome(nome), coach=nome,
        validado=True, submitted_at=submitted_at, token=f"{clan}-{nome}",
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
        assert normalizar_nome("Carolina dorte gadbem") == normalizar_nome("carolina dorte gadbem")

    def test_espacos_internos_multiplos_preservados(self):
        assert normalizar_nome("Ana  Paula") == "ana  paula"


class TestNormalizarClan:

    def test_numero_simples(self):
        assert normalizar_clan("2") == "CLÃ 2"

    def test_numero_com_espacos(self):
        assert normalizar_clan(" 8 ") == "CLÃ 8"

    def test_nao_numerico_mantido_como_esta(self):
        assert normalizar_clan("abc") == "abc"


class TestParseSubmittedAt:

    def test_formato_completo_com_hora(self):
        assert parse_submitted_at("11/05/2026 14:34:00") == datetime(2026, 5, 11, 14, 34, 0)

    def test_data_invalida_retorna_none(self):
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
        row = parse_row(raw_row, MAPPING, {})
        assert row == ImportRow(
            clan="CLÃ 2",
            nome="Vinicius Alves",
            nome_normalizado="vinicius alves",
            coach="Vinicius Alves",
            validado=True,
            submitted_at=datetime(2026, 5, 11, 14, 34, 0),
            token="gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        )

    def test_linha_com_data_ilegivel(self):
        raw_row = {**{k: "" for k in MAPPING.values()}, MAPPING["submitted_at"]: "lixo"}
        row = parse_row(raw_row, MAPPING, {})
        assert row.submitted_at is None

    def test_coach_resolvido_via_alias_map(self):
        raw_row = {
            "Selecionar o Clã em que você está (1 a 8):": "1",
            "Coloque aqui o seu Nome:": "Vini Marini",
            "Você cumpriu o Desafio Pontual G?": "Sim",
            "Submitted At": "11/05/2026 14:34:00",
            "Token": "tok1",
        }
        row = parse_row(raw_row, MAPPING, {"Vini Marini": "Vinicius Marini"})
        assert row.coach == "Vinicius Marini"


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


class TestFiltrarTokensNovos:

    def test_token_novo_mantido(self):
        row = _row_com_token("abc")
        novos, repetidos = filtrar_tokens_novos([row], {"outro_token"})
        assert novos == [row] and repetidos == []

    def test_token_ja_importado_e_pulado(self):
        row = _row_com_token("ja_visto")
        novos, repetidos = filtrar_tokens_novos([row], {"ja_visto"})
        assert novos == [] and repetidos == [row]


class TestDeduplicarPorPessoa:

    def test_pessoa_unica_conta(self):
        row = _row(datetime(2026, 5, 25, 16, 3, 30))
        result = deduplicar_por_pessoa([row])
        assert result == [ContabilizacaoRow(row=row, contabilizado=True)]

    def test_duas_submissoes_mesma_pessoa_so_a_mais_recente_conta(self):
        antiga = ImportRow(
            clan="CLÃ 1", nome="Luciana Batista", nome_normalizado="luciana batista",
            coach="Luciana Batista",
            validado=True, submitted_at=datetime(2026, 6, 26, 17, 59, 7), token="1tih",
        )
        recente = ImportRow(
            clan="CLÃ 1", nome="Luciana Batista", nome_normalizado="luciana batista",
            coach="Luciana Batista",
            validado=True, submitted_at=datetime(2026, 6, 30, 1, 14, 36), token="9w3r",
        )
        result = deduplicar_por_pessoa([antiga, recente])
        assert set(result) == {
            ContabilizacaoRow(row=antiga, contabilizado=False),
            ContabilizacaoRow(row=recente, contabilizado=True),
        }

    def test_pessoas_diferentes_mesmo_clan_ambas_contam(self):
        ana = _row_pessoa("CLÃ 1", "Ana Albertim", datetime(2026, 5, 25, 16, 3, 30))
        gustavo = _row_pessoa("CLÃ 1", "Gustavo Imhof", datetime(2026, 5, 31, 5, 2, 47))
        result = deduplicar_por_pessoa([ana, gustavo])
        assert all(r.contabilizado for r in result)


class TestProcessarImportacao:

    def test_cenario_completo(self):
        raw_rows = [
            _raw("1", "Ana Albertim", "Sim", "25/05/2026 16:03:30", "AAA"),
            _raw("1", "Luciana Batista", "Sim", "26/06/2026 17:59:07", "BBB1"),
            _raw("1", "Luciana Batista", "Sim", "30/06/2026 01:14:36", "BBB2"),
            _raw("8", "Paula Petroli Pierozzi", "Sim", "21/06/2026 23:18:42", "CCC"),
            _raw("9", "Alguem", "Sim", "01/06/2026 00:00:00", "DDD"),
            _raw("1", "Outra Pessoa", "Não", "01/06/2026 00:00:00", "EEE"),
            _raw("1", "Mais Alguem", "Sim", "05/07/2026 00:10:21", "FFF"),
        ]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={f"CLÃ {n}" for n in range(1, 9)},
            tokens_ja_importados=set(),
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
            coach_alias_map={},
        )

        assert result.pontos_por_clan == {"CLÃ 1": 20, "CLÃ 8": 10}
        assert result.participacoes_por_clan == {"CLÃ 1": 2, "CLÃ 8": 1}
        assert result.pontos_por_coach == {
            "Ana Albertim": 10, "Luciana Batista": 10, "Paula Petroli Pierozzi": 10,
        }
        assert result.participacoes_por_coach == {
            "Ana Albertim": 1, "Luciana Batista": 1, "Paula Petroli Pierozzi": 1,
        }
        assert len(result.avisos) >= 2

        auditoria_por_token = {a["token_original"]: a for a in result.linhas_auditoria}
        assert set(auditoria_por_token) == {"AAA", "BBB1", "BBB2", "CCC", "EEE"}
        assert auditoria_por_token["BBB1"]["contabilizado"] is False
        assert auditoria_por_token["BBB2"]["contabilizado"] is True
        assert auditoria_por_token["BBB2"]["coach"] == "Luciana Batista"
        assert auditoria_por_token["EEE"]["validado"] is False
        assert auditoria_por_token["EEE"]["contabilizado"] is False

    def test_token_ja_importado_e_ignorado_silenciosamente(self):
        raw_rows = [_raw("1", "Ana Albertim", "Sim", "25/05/2026 16:03:30", "AAA")]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={"CLÃ 1"},
            tokens_ja_importados={"AAA"},
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
            coach_alias_map={},
        )
        assert result.pontos_por_clan == {}
        assert result.pontos_por_coach == {}
        assert result.linhas_auditoria == []

    def test_coach_com_alias_agrega_sob_canonico(self):
        raw_rows = [
            _raw("1", "Vini Marini", "Sim", "20/05/2026 10:00:00", "T1"),
            _raw("1", "Ana Albertim", "Sim", "21/05/2026 10:00:00", "T2"),
        ]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={"CLÃ 1"},
            tokens_ja_importados=set(),
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
            coach_alias_map={"Vini Marini": "Vinicius Marini"},
        )
        assert result.pontos_por_coach == {"Vinicius Marini": 10, "Ana Albertim": 10}
        assert result.participacoes_por_coach == {"Vinicius Marini": 1, "Ana Albertim": 1}
