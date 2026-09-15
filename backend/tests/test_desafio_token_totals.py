"""Testes da issue #19 (Task 8) e #44: totais por `desafios`.

Eixo coach (`get_tipo_coach_totals`/`get_period_desafio_coach_totals`):
derivados de `desafio_submissions_current`, agrupados por `submitted_at`
convertido para América/São_Paulo — inalterado desde a issue #19/Task 8.

Eixo clã (`get_tipo_clan_totals("desafios")`/`get_period_desafio_totals`):
desde a issue #44, somam a apuração por percentual já fechada
(`desafio_clan_apuracoes`) dos desafios apurados, agrupada pelo
`prazo_apuracao` do desafio — não mais a soma flat por token, já que a
apuração por percentual vale para o desafio inteiro, não é atribuível por
submissão individual.
"""

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supabase_client


# ---------------------------------------------------------------------------
# Helpers de mock
# ---------------------------------------------------------------------------


def _row(clan, points, submitted_at, token=None):
    return {
        "token": token or f"TOK-{uuid.uuid4().hex[:8]}",
        "clan": clan,
        "points": points,
        "status": "active_counted",
        "submitted_at": submitted_at,
    }


def _paged_client(pages):
    """Client fake cujo `.table(...).select(...).eq(...).order(...).range(...)
    .execute()` devolve `pages` em sequência (uma página vazia sinaliza fim),
    espelhando o padrão já usado para `fetch_all_desafio_submissions_current`
    em `test_desafio_reconciliation_store.py`."""
    ranges: list[tuple[int, int]] = []
    eq_calls: list[tuple] = []

    class _Query:
        def select(self, *_):
            return self

        def eq(self, *args):
            eq_calls.append(args)
            return self

        def order(self, *_, **__):
            return self

        def range(self, start, end):
            ranges.append((start, end))
            return self

        def execute(self):
            # Módulo: permite que o mesmo client sirva múltiplas varreduras
            # completas (chamadas repetidas de get_period_desafio_totals /
            # get_tipo_clan_totals no mesmo teste), repetindo o mesmo ciclo de
            # páginas a cada nova varredura.
            idx = (len(ranges) - 1) % len(pages)
            return SimpleNamespace(data=pages[idx])

    client = SimpleNamespace(table=lambda *_: _Query())
    return client, ranges, eq_calls


def _single_page_client(rows):
    client, ranges, eq_calls = _paged_client([rows, []])
    return client, eq_calls


# ---------------------------------------------------------------------------
# fetch_active_counted_desafio_submissions: full-scan, filtrado no servidor
# ---------------------------------------------------------------------------


class TestFetchActiveCountedDesafioSubmissions:

    def test_filtra_status_active_counted_no_servidor(self):
        rows = [_row("CLÃ 1", 10, "2026-05-15T12:00:00+00:00")]
        client, eq_calls = _single_page_client(rows)
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.fetch_active_counted_desafio_submissions()
        assert result == rows
        assert ("status", "active_counted") in eq_calls

    def test_paginacao_nao_para_em_pagina_curta(self):
        """Página curta pode ser limite do PostgREST (db-max-rows), não fim da
        tabela: parar ali subcontaria um clã com muitos tokens ativos."""
        pages = [
            [_row("CLÃ 1", 10, "2026-05-01T12:00:00+00:00", token="TOK-1"),
             _row("CLÃ 1", 5, "2026-05-02T12:00:00+00:00", token="TOK-2")],
            [_row("CLÃ 1", 7, "2026-05-03T12:00:00+00:00", token="TOK-3")],
            [],
        ]
        client, ranges, _ = _paged_client(pages)
        with patch.object(supabase_client, "_get_client", return_value=client):
            rows = supabase_client.fetch_active_counted_desafio_submissions()
        assert [r["token"] for r in rows] == ["TOK-1", "TOK-2", "TOK-3"]
        assert [start for start, _ in ranges] == [0, 2, 3]

    def test_mais_de_cem_linhas_nao_e_truncado(self):
        """`list_desafio_submissions_current` (auditoria) tem limit=100 por
        padrão; a base de agregação não pode herdar esse teto."""
        rows = [
            _row("CLÃ 1", 1, "2026-05-01T12:00:00+00:00", token=f"TOK-{i}")
            for i in range(150)
        ]
        client, eq_calls = _single_page_client(rows)
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.fetch_active_counted_desafio_submissions()
        assert len(result) == 150


# ---------------------------------------------------------------------------
# _submitted_at_local_date: conversão para o dia de calendário em SP
# ---------------------------------------------------------------------------


class TestSubmittedAtLocalDate:

    def test_string_utc_com_offset_explicito(self):
        # 2026-06-01T02:59:00+00:00 == 2026-05-31 23:59:00 em América/São_Paulo (UTC-3)
        result = supabase_client._submitted_at_local_date("2026-06-01T02:59:00+00:00")
        assert result.isoformat() == "2026-05-31"

    def test_string_utc_com_sufixo_z(self):
        result = supabase_client._submitted_at_local_date("2026-06-01T03:01:00Z")
        assert result.isoformat() == "2026-06-01"

    def test_valor_none_retorna_none(self):
        assert supabase_client._submitted_at_local_date(None) is None

    def test_string_vazia_retorna_none(self):
        assert supabase_client._submitted_at_local_date("") is None


# ---------------------------------------------------------------------------
# get_tipo_clan_totals("desafios") sem data: soma a apuração por percentual
# já fechada (`desafio_clan_apuracoes`) de todos os desafios apurados (issue
# #44) — não mais soma flat por token: a apuração por percentual vale para o
# desafio inteiro, não é atribuível por submissão individual.
# ---------------------------------------------------------------------------


def _desafio(desafio_id, apurado_em="2026-09-01T00:00:00+00:00", prazo_apuracao=None):
    return {"id": desafio_id, "apurado_em": apurado_em, "prazo_apuracao": prazo_apuracao}


def _apuracao_row(clan, pontos):
    return {"clan": clan, "pontos": pontos}


class TestGetTipoClanTotalsDesafiosNoDate:

    def test_soma_apuracao_de_todos_os_desafios_apurados_agrupada_por_cla(self):
        with patch("supabase_client.list_desafios", return_value=[_desafio(1), _desafio(2)]), \
             patch("supabase_client.get_desafio_clan_apuracoes", side_effect=[
                 [_apuracao_row("CLÃ 1", 10), _apuracao_row("CLÃ 1", 5)],
                 [_apuracao_row("CLÃ 2", 7)],
             ]):
            result = supabase_client.get_tipo_clan_totals("desafios")
        assert result == {"CLÃ 1": 15, "CLÃ 2": 7}

    def test_sem_desafios_apurados_retorna_vazio(self):
        with patch("supabase_client.list_desafios", return_value=[]):
            result = supabase_client.get_tipo_clan_totals("desafios")
        assert result == {}

    def test_desafio_nao_apurado_e_ignorado(self):
        with patch("supabase_client.list_desafios",
                    return_value=[_desafio(1, apurado_em=None)]), \
             patch("supabase_client.get_desafio_clan_apuracoes") as mock_apuracoes:
            result = supabase_client.get_tipo_clan_totals("desafios")
        mock_apuracoes.assert_not_called()
        assert result == {}


# ---------------------------------------------------------------------------
# get_period_desafio_totals: período é pelo prazo_apuracao do desafio (issue
# #44) — não mais por submitted_at de cada token, já que a apuração por
# percentual vale para o desafio inteiro, não para cada submissão isolada.
# ---------------------------------------------------------------------------


class TestGetPeriodDesafioTotalsPorPrazoApuracao:

    def test_desafio_com_prazo_dentro_do_periodo_conta(self):
        from datetime import date
        with patch("supabase_client.list_desafios",
                    return_value=[_desafio(1, prazo_apuracao="2026-08-31T11:38:00+00:00")]), \
             patch("supabase_client.get_desafio_clan_apuracoes",
                   return_value=[_apuracao_row("CLÃ 1", 500)]):
            result = supabase_client.get_period_desafio_totals(date(2026, 8, 1), date(2026, 8, 31))
        assert result == {"CLÃ 1": 500}

    def test_desafio_com_prazo_fora_do_periodo_nao_conta(self):
        from datetime import date
        with patch("supabase_client.list_desafios",
                    return_value=[_desafio(1, prazo_apuracao="2026-09-10T11:38:00+00:00")]), \
             patch("supabase_client.get_desafio_clan_apuracoes",
                   return_value=[_apuracao_row("CLÃ 1", 500)]):
            result = supabase_client.get_period_desafio_totals(date(2026, 8, 1), date(2026, 8, 31))
        assert result == {}

    def test_desafio_nao_apurado_nao_conta_mesmo_com_prazo_no_periodo(self):
        from datetime import date
        with patch("supabase_client.list_desafios", return_value=[
                 _desafio(1, apurado_em=None, prazo_apuracao="2026-08-31T11:38:00+00:00"),
             ]), \
             patch("supabase_client.get_desafio_clan_apuracoes") as mock_apuracoes:
            result = supabase_client.get_period_desafio_totals(date(2026, 8, 1), date(2026, 8, 31))
        mock_apuracoes.assert_not_called()
        assert result == {}

    def test_desafio_sem_prazo_definido_nao_conta_em_nenhum_periodo(self):
        from datetime import date
        with patch("supabase_client.list_desafios",
                    return_value=[_desafio(1, prazo_apuracao=None)]), \
             patch("supabase_client.get_desafio_clan_apuracoes",
                   return_value=[_apuracao_row("CLÃ 1", 500)]):
            result = supabase_client.get_period_desafio_totals(date(2026, 8, 1), date(2026, 8, 31))
        assert result == {}

    def test_prazo_incluido_nas_bordas_inicio_e_fim(self):
        from datetime import date
        with patch("supabase_client.list_desafios", return_value=[
                 _desafio(1, prazo_apuracao="2026-08-01T15:00:00+00:00"),
                 _desafio(2, prazo_apuracao="2026-08-31T15:00:00+00:00"),
             ]), \
             patch("supabase_client.get_desafio_clan_apuracoes", side_effect=[
                 [_apuracao_row("CLÃ 1", 1)],
                 [_apuracao_row("CLÃ 1", 2)],
             ]):
            result = supabase_client.get_period_desafio_totals(date(2026, 8, 1), date(2026, 8, 31))
        assert result == {"CLÃ 1": 3}

    def test_soma_varios_desafios_apurados_no_periodo_por_cla(self):
        from datetime import date
        with patch("supabase_client.list_desafios", return_value=[
                 _desafio(1, prazo_apuracao="2026-08-10T12:00:00+00:00"),
                 _desafio(2, prazo_apuracao="2026-08-20T12:00:00+00:00"),
             ]), \
             patch("supabase_client.get_desafio_clan_apuracoes", side_effect=[
                 [_apuracao_row("CLÃ 1", 10)],
                 [_apuracao_row("CLÃ 1", 5), _apuracao_row("CLÃ 2", 7)],
             ]):
            result = supabase_client.get_period_desafio_totals(date(2026, 8, 1), date(2026, 8, 31))
        assert result == {"CLÃ 1": 15, "CLÃ 2": 7}

    def test_desafio_com_prazo_antes_do_inicio_do_periodo_conta(self):
        """Issue #49/#50: um desafio já apurado conta de forma cumulativa a
        partir do seu encerramento — um filtro cujo `inicio` é posterior ao
        `prazo_apuracao` não deve mais excluí-lo."""
        from datetime import date
        with patch("supabase_client.list_desafios",
                    return_value=[_desafio(1, prazo_apuracao="2026-08-31T11:38:00+00:00")]), \
             patch("supabase_client.get_desafio_clan_apuracoes",
                   return_value=[_apuracao_row("CLÃ 1", 500)]):
            result = supabase_client.get_period_desafio_totals(date(2026, 9, 1), date(2026, 9, 30))
        assert result == {"CLÃ 1": 500}

    def test_desafio_com_prazo_antes_do_inicio_sem_fim_conta(self):
        from datetime import date
        with patch("supabase_client.list_desafios",
                    return_value=[_desafio(1, prazo_apuracao="2026-08-31T11:38:00+00:00")]), \
             patch("supabase_client.get_desafio_clan_apuracoes",
                   return_value=[_apuracao_row("CLÃ 1", 500)]):
            result = supabase_client.get_period_desafio_totals(date(2026, 9, 1))
        assert result == {"CLÃ 1": 500}


# ---------------------------------------------------------------------------
# A apuração persistida em `desafio_clan_apuracoes` é sempre lida em tempo
# real — uma reapuração (ex.: correção de revisão de submissão, ou fechamento
# tardio) muda o resultado na próxima leitura, sem exigir nenhuma invalidação
# nem cache.
# ---------------------------------------------------------------------------


class TestApuracaoRefletidaEmTempoReal:

    def test_mudanca_na_apuracao_persistida_reflete_na_proxima_leitura(self):
        with patch("supabase_client.list_desafios", return_value=[_desafio(1)]), \
             patch("supabase_client.get_desafio_clan_apuracoes", side_effect=[
                 [_apuracao_row("CLÃ 1", 500)],
                 [_apuracao_row("CLÃ 1", 300)],
             ]):
            primeiro = supabase_client.get_tipo_clan_totals("desafios")
            segundo = supabase_client.get_tipo_clan_totals("desafios")

        assert primeiro == {"CLÃ 1": 500}
        assert segundo == {"CLÃ 1": 300}


# ---------------------------------------------------------------------------
# Fase 2: o lado coach dos desafios também passa a ler os tokens
# `active_counted` (coluna B / raw_name), nunca a tabela legada
# `desafio_registros_coach`.
# ---------------------------------------------------------------------------


class TestGetTipoCoachTotalsDesafiosLeDosTokens:
    """Fase 2: get_tipo_coach_totals('desafios') e get_period_desafio_coach_totals
    agregam os tokens active_counted de desafio_submissions_current por coach
    canônico (coluna B / raw_name), e nunca tocam a tabela legada
    desafio_registros_coach.

    As datas de `_rows()` são todas anteriores a `config.DESAFIO_PERCENTUAL_CLAN_CORTE`
    (01/08/2026), então contam automaticamente sem exigir revisão manual — ver
    `TestPontosIndividuaisCoachValorEGateDeCorte` para o comportamento a partir
    do corte. O valor por token vem de `config.POINTS_PER_DESAFIO_SUBMISSION_COACH`
    (100), não do campo `points` gravado (aqui deliberadamente 10, para provar
    que não é mais essa a fonte)."""

    def _rows(self):
        return [
            {"token": "T1", "raw_name": "Ana Albertim", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-10T13:00:00-03:00"},
            {"token": "T2", "raw_name": "ana  albertim", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-20T13:00:00-03:00"},
            {"token": "T3", "raw_name": "Bruno Costa", "points": 10,
             "status": "active_counted", "submitted_at": "2026-06-01T13:00:00-03:00"},
            {"token": "T4", "raw_name": "", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-15T13:00:00-03:00"},
        ]

    def test_sem_data_soma_todos_agrupando_por_canonico(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            result = supabase_client.get_tipo_coach_totals("desafios")
        assert result == {"Ana Albertim": 200, "Bruno Costa": 100}

    def test_raw_name_vazio_e_ignorado(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[{"token": "X", "raw_name": "   ", "points": 10,
                                  "status": "active_counted",
                                  "submitted_at": "2026-05-10T13:00:00-03:00"}]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {}

    def test_com_data_delega_e_filtra_por_submitted_at_local(self):
        from datetime import date
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            result = supabase_client.get_tipo_coach_totals(
                "desafios", date(2026, 5, 1), date(2026, 5, 31)
            )
        assert result == {"Ana Albertim": 200}

    def test_periodo_sem_fim_conta_tudo_a_partir_do_inicio(self):
        from datetime import date
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            result = supabase_client.get_period_desafio_coach_totals(date(2026, 6, 1), None)
        assert result == {"Bruno Costa": 100}

    def test_nunca_consulta_desafio_registros_coach(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}), \
             patch("supabase_client._get_client",
                   side_effect=AssertionError("não deve tocar o banco legado")):
            supabase_client.get_tipo_coach_totals("desafios")


class TestPontosIndividuaisCoachValorEGateDeCorte:
    """Pontos individuais do coach por desafio: valor fixo de
    `config.POINTS_PER_DESAFIO_SUBMISSION_COACH` (não o `points` gravado, que
    continua só alimentando o lado clã). A partir do corte de vigência
    (`config.DESAFIO_PERCENTUAL_CLAN_CORTE`), toda submissão `active_counted`
    conta por padrão — só `revisao_status == "reprovado"` exclui."""

    def _row(self, submitted_at, token="T1"):
        return {"token": token, "raw_name": "Ana", "points": 10,
                "status": "active_counted", "submitted_at": submitted_at}

    def test_pre_corte_conta_automaticamente_sem_revisao(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-07-31T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}

    def test_pos_corte_sem_registro_de_revisao_conta_por_padrao(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}

    def test_pos_corte_com_revisao_pendente_conta(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"T1": {"status": "pendente"}}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}

    def test_pos_corte_com_revisao_reprovada_nao_conta(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"T1": {"status": "reprovado"}}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {}

    def test_pos_corte_com_revisao_aprovada_legado_ainda_conta(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"T1": {"status": "aprovado"}}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}


class TestGetAllDesafioTokenCoachNames:

    def test_nomes_brutos_distintos_nao_vazios(self):
        rows = [
            {"token": "A", "raw_name": "Ana", "points": 10, "status": "active_counted"},
            {"token": "B", "raw_name": "Ana", "points": 10, "status": "active_counted"},
            {"token": "C", "raw_name": "  Bruno  ", "points": 10, "status": "active_counted"},
            {"token": "D", "raw_name": "", "points": 10, "status": "active_counted"},
        ]
        with patch("supabase_client.fetch_active_counted_desafio_submissions", return_value=rows):
            assert supabase_client.get_all_desafio_token_coach_names() == {"Ana", "Bruno"}


# ---------------------------------------------------------------------------
# Step 5 (proxy no sandbox): a agregação Python é internamente consistente —
# soma-por-clã bate com um cálculo manual sobre a mesma fixture.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Step 5 (a alegação real): reconcilia contra o resultado que
# `apply_desafio_reconciliation` de fato grava em Postgres. Só roda com
# TEST_POSTGRES_DSN configurado (mesma lacuna conhecida das Tasks 1 e 4 neste
# sandbox); sem isso, skip limpo — igual às demais suítes `*_postgres.py`.
# ---------------------------------------------------------------------------

TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")

PINNED_SEARCH_PATH = "SET search_path = public, pg_temp"

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


@pytest.mark.skipif(
    not TEST_POSTGRES_DSN,
    reason="TEST_POSTGRES_DSN não configurado para testes reais de RPC",
)
class TestSomaDeTokensAtivosReconciliaComClanTotalsAfter:
    """Prova a alegação real da Task 8 (brief Step 5): a soma de
    `desafio_submissions_current.points` para tokens `active_counted`,
    agrupada por clã, bate com o `clan_totals_after` que o próprio
    `apply_desafio_reconciliation` (migração 009) produziu para o mesmo
    payload — nesse schema isolado, sem nenhuma outra fonte de pontos, os dois
    precisam ser idênticos."""

    def test_soma_agrupada_por_cla_bate_com_clan_totals_after(self):
        psycopg = pytest.importorskip("psycopg")
        from psycopg import sql
        import json

        legacy_schema = """
        CREATE TABLE desafios (
          id                       SERIAL PRIMARY KEY,
          nome                     VARCHAR NOT NULL,
          contabilizar_pontos      BOOLEAN NOT NULL DEFAULT TRUE,
          data                     DATE NOT NULL,
          data_inicio              DATE,
          data_fim                 DATE,
          pontos_por_participacao  INTEGER,
          created_at               TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE pontos_ultimate_totais_por_clan (
          clan              VARCHAR PRIMARY KEY,
          total_pontos      INTEGER NOT NULL DEFAULT 0,
          pessoas_em_espera INTEGER NOT NULL DEFAULT 0,
          total_pagante     INTEGER NOT NULL DEFAULT 0,
          total_pro_bono    INTEGER NOT NULL DEFAULT 0
        );
        """
        migration_008 = (MIGRATIONS_DIR / "008_add_desafio_google_sync.sql").read_text(
            encoding="utf-8"
        )
        migration_009 = (MIGRATIONS_DIR / "009_apply_desafio_reconciliation.sql").read_text(
            encoding="utf-8"
        )
        assert PINNED_SEARCH_PATH in migration_009

        def current_state(status, points, clan, token, name):
            raw_cells = [
                "1", name, "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", token,
            ]
            return {
                "status": status,
                "eligible": status == "active_counted",
                "clan": clan,
                "challenge_display": "Desafio A",
                "challenge_normalized": "desafio a",
                "submitted_at": "2026-08-19T10:00:00-03:00",
                "name": name,
                "points": points,
                "row_numbers": [2],
                "variants": [raw_cells],
            }

        def token_version(token, clan, points):
            return {
                "token": token,
                "change_reason": "new",
                "previous_status": None,
                "current_status": "active_counted",
                "previous_state": None,
                "current_state": current_state("active_counted", points, clan, token, token),
                "content_hash": f"hash-{token}",
                "point_delta": points,
                "clan_deltas": {clan: points},
                "challenge_normalized": "desafio a",
                "challenge_display": "Desafio A",
                "row_numbers": [2],
            }

        versions = [
            token_version("TOK-1", "CLÃ 1", 10),
            token_version("TOK-2", "CLÃ 1", 5),
            token_version("TOK-3", "CLÃ 2", 7),
        ]
        clan_deltas = {"CLÃ 1": 15, "CLÃ 2": 7}
        payload = json.dumps({
            "snapshot_hash": "hash-abc",
            "sheet_row_count": 3,
            "state_counts": {"new": 3},
            "clan_deltas": clan_deltas,
            "points_per_submission": 5,
            "mass_removal_required": False,
            "mass_removal_confirmed": False,
            "mass_removal_count": 0,
            "challenges_created": 1,
            "challenges_archived": 0,
            "challenges_reactivated": 0,
            "challenge_transitions": [
                {
                    "challenge_normalized": "desafio a",
                    "challenge_display": "Desafio A",
                    "transition": "create",
                }
            ],
            "token_versions": versions,
        })

        schema_name = f"desafio_token_totals_test_{uuid.uuid4().hex}"
        connection = psycopg.connect(TEST_POSTGRES_DSN, autocommit=True)
        try:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name)))
            connection.execute(legacy_schema)
            connection.execute(migration_008)
            connection.execute(
                migration_009.replace(
                    PINNED_SEARCH_PATH, f"SET search_path = {schema_name}, pg_temp"
                )
            )

            result = connection.execute(
                "SELECT apply_desafio_reconciliation(%s::JSONB)", (payload,)
            ).fetchone()[0]
            assert result["status"] == "applied"

            rows = connection.execute(
                "SELECT clan, points FROM desafio_submissions_current"
                " WHERE status = 'active_counted'"
            ).fetchall()
        finally:
            connection.execute("RESET search_path")
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name)))
            connection.close()

        computed_totals: dict[str, int] = {}
        for clan, points in rows:
            computed_totals[clan] = computed_totals.get(clan, 0) + points

        assert computed_totals == {"CLÃ 1": 15, "CLÃ 2": 7}
        assert computed_totals == result["clan_totals_after"]
