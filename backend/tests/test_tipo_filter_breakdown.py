import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
