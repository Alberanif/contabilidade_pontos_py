import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from unittest.mock import patch, MagicMock
import supabase_client


def _mock_totais(rows):
    """Mock que retorna linhas de TABLE_TOTAIS (sem datas — lê de TABLE_TOTAIS)."""
    result = MagicMock()
    result.data = rows
    chain = MagicMock()
    chain.execute.return_value = result
    for m in ("table", "select", "eq"):
        getattr(chain, m).return_value = chain
    client = MagicMock()
    client.table.return_value = chain
    return client


class TestGetTipoClanTotalsNoDate:
    """Sem datas: deve ler total_pagante / total_pro_bono de TABLE_TOTAIS."""

    def test_pagante_reads_total_pagante(self):
        rows = [{"clan": "CLÃ 1", "total_pagante": 1200, "total_pro_bono": 200}]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_clan_totals("pagante")
        assert result == {"CLÃ 1": 1200}

    def test_pro_bono_reads_total_pro_bono(self):
        rows = [{"clan": "CLÃ 1", "total_pagante": 1200, "total_pro_bono": 200}]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_clan_totals("pro_bono")
        assert result == {"CLÃ 1": 200}

    def test_multiple_clans(self):
        rows = [
            {"clan": "CLÃ 1", "total_pagante": 1200, "total_pro_bono": 200},
            {"clan": "CLÃ 2", "total_pagante": 600, "total_pro_bono": 100},
        ]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_clan_totals("pagante")
        assert result == {"CLÃ 1": 1200, "CLÃ 2": 600}

    def test_zero_total_excluded(self):
        rows = [
            {"clan": "CLÃ 1", "total_pagante": 0, "total_pro_bono": 200},
            {"clan": "CLÃ 2", "total_pagante": 600, "total_pro_bono": 0},
        ]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_clan_totals("pagante")
        assert result == {"CLÃ 2": 600}

    def test_null_column_excluded(self):
        rows = [
            {"clan": "CLÃ 1", "total_pagante": None, "total_pro_bono": 200},
            {"clan": "CLÃ 2", "total_pagante": 600, "total_pro_bono": None},
        ]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            pagante = supabase_client.get_tipo_clan_totals("pagante")
            pro_bono = supabase_client.get_tipo_clan_totals("pro_bono")
        assert pagante == {"CLÃ 2": 600}
        assert pro_bono == {"CLÃ 1": 200}


class TestGetTipoCoachTotalsNoDate:
    """Sem datas: deve ler total_pagante / total_pro_bono de TABLE_TOTAIS_COACH."""

    def test_pagante_reads_total_pagante(self):
        rows = [{"coach": "Coach A", "total_pagante": 900, "total_pro_bono": 0}]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_coach_totals("pagante")
        assert result == {"Coach A": 900}

    def test_zero_excluded(self):
        rows = [{"coach": "Coach A", "total_pagante": 0, "total_pro_bono": 0}]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_coach_totals("pagante")
        assert result == {}

    def test_pro_bono_reads_total_pro_bono(self):
        rows = [{"coach": "Coach A", "total_pagante": 900, "total_pro_bono": 150}]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_coach_totals("pro_bono")
        assert result == {"Coach A": 150}

    def test_multiple_coaches(self):
        rows = [
            {"coach": "Coach A", "total_pagante": 900, "total_pro_bono": 0},
            {"coach": "Coach B", "total_pagante": 600, "total_pro_bono": 100},
        ]
        with patch("supabase_client._get_client", return_value=_mock_totais(rows)):
            result = supabase_client.get_tipo_coach_totals("pagante")
        assert result == {"Coach A": 900, "Coach B": 600}


def _mock_active_counted(rows):
    """Mock paginado de `fetch_active_counted_desafio_submissions`: uma
    página com `rows`, depois uma página vazia (fim da varredura)."""
    calls = {"n": 0}
    chain = MagicMock()
    for m in ("table", "select", "eq", "order", "range"):
        getattr(chain, m).return_value = chain

    def _execute():
        calls["n"] += 1
        result = MagicMock()
        result.data = rows if calls["n"] == 1 else []
        return result

    chain.execute.side_effect = _execute
    client = MagicMock()
    client.table.return_value = chain
    return client


class TestGetTipoClanTotalsDesafiosNoDate:
    """Sem datas: soma `points` dos tokens `active_counted` em
    `desafio_submissions_current`, agrupados por clã (issue #19 / Task 8) —
    em vez do antigo join `desafios.contabilizar_pontos` + `desafio_registros`."""

    def test_soma_pontos_de_tokens_ativos_por_cla(self):
        rows = [
            {"clan": "CLÃ 1", "points": 10, "status": "active_counted"},
            {"clan": "CLÃ 1", "points": 5, "status": "active_counted"},
            {"clan": "CLÃ 2", "points": 7, "status": "active_counted"},
        ]
        client = _mock_active_counted(rows)
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.get_tipo_clan_totals("desafios")
        assert result == {"CLÃ 1": 15, "CLÃ 2": 7}

    def test_sem_tokens_ativos_retorna_vazio(self):
        client = _mock_active_counted([])
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.get_tipo_clan_totals("desafios")
        assert result == {}


class TestGetTipoClanTotalsDesafiosComData:

    def test_delega_para_get_period_desafio_totals(self):
        from datetime import date
        inicio, fim = date(2026, 5, 1), date(2026, 6, 30)
        with patch("supabase_client.get_period_desafio_totals",
                   return_value={"CLÃ 1": 30}) as mock_period:
            result = supabase_client.get_tipo_clan_totals("desafios", inicio, fim)
        mock_period.assert_called_once_with(inicio, fim)
        assert result == {"CLÃ 1": 30}


class TestGetTipoCoachTotalsDesafiosLeTokens:
    def test_soma_pontos_dos_tokens_por_coach_canonico(self):
        rows = [
            {"token": "T1", "raw_name": "Ana", "points": 10, "status": "active_counted",
             "submitted_at": "2026-05-10T13:00:00-03:00"},
            {"token": "T2", "raw_name": "ANA", "points": 10, "status": "active_counted",
             "submitted_at": "2026-05-11T13:00:00-03:00"},
        ]
        with patch("supabase_client.fetch_active_counted_desafio_submissions", return_value=rows), \
             patch("supabase_client.get_coach_alias_map", return_value={"ANA": "Ana"}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 200}

    def test_com_data_delega_para_get_period_desafio_coach_totals(self):
        with patch("supabase_client.get_period_desafio_coach_totals",
                   return_value={"Ana": 30}) as mock_period:
            result = supabase_client.get_tipo_coach_totals(
                "desafios", date(2026, 5, 1), date(2026, 5, 31)
            )
        mock_period.assert_called_once_with(date(2026, 5, 1), date(2026, 5, 31))
        assert result == {"Ana": 30}
