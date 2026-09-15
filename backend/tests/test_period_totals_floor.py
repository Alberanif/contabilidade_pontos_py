# backend/tests/test_period_totals_floor.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from unittest.mock import patch, MagicMock
import supabase_client

INICIO = date(2026, 1, 1)
FIM = date(2026, 1, 31)


def _mock_client(records):
    result = MagicMock()
    result.data = records
    chain = MagicMock()
    chain.execute.return_value = result
    for m in ("table", "select", "gte", "lte", "eq", "in_"):
        getattr(chain, m).return_value = chain
    client = MagicMock()
    client.table.return_value = chain
    return client


class TestGetPeriodClanTotalsSemFloor:
    """Coaching em grupo/Empresa vale 30 pontos fixos por registro, igual ao
    Coaching Individual — sem lote de pessoas, sem flooragem."""

    def test_group_record_30pts_soma_direto(self):
        records = [{"clan": "CLÃ 1", "pontos": 30}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_multiplos_registros_de_grupo_somam_direto(self):
        records = [{"clan": "CLÃ 1", "pontos": 30} for _ in range(3)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 90

    def test_individual_30pts_preserved(self):
        records = [{"clan": "CLÃ 1", "pontos": 30}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_pro_bono_10pts_preserved(self):
        records = [{"clan": "CLÃ 1", "pontos": 10}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 10

    def test_individual_mais_grupo_somam(self):
        """30 (individual) + 30 (grupo) = 60"""
        records = [
            {"clan": "CLÃ 1", "pontos": 30},
            {"clan": "CLÃ 1", "pontos": 30},
        ]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 60


class TestGetPeriodCoachTotalsSemFloor:
    """Coaching em grupo/Empresa vale 30 pontos fixos por registro no eixo
    coach também — sem lote de pessoas, sem flooragem."""

    def test_group_record_30pts_soma_direto(self):
        records = [{"coach": "Coach A", "pontos_coach": 30}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result["Coach A"] == 30

    def test_multiplos_registros_de_grupo_somam_direto(self):
        records = [{"coach": "Coach A", "pontos_coach": 30} for _ in range(3)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result["Coach A"] == 90

    def test_individual_30pts_preserved(self):
        records = [{"coach": "Coach A", "pontos_coach": 30}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result["Coach A"] == 30

    def test_null_coach_ignored(self):
        records = [{"coach": None, "pontos_coach": 30}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result == {}


class TestGetTipoClanTotalsSemFloor:

    def test_pagante_group_record_30pts_soma_direto(self):
        records = [{"clan": "CLÃ 1", "pontos": 30, "modalidade": "Coaching em grupo"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_clan_totals("pagante", INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_pagante_multiplos_registros_de_grupo_somam(self):
        records = [{"clan": "CLÃ 1", "pontos": 30, "modalidade": "Coaching em grupo"} for _ in range(3)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_clan_totals("pagante", INICIO, FIM)
        assert result["CLÃ 1"] == 90

    def test_pro_bono_10pts_not_floored(self):
        records = [{"clan": "CLÃ 1", "pontos": 10, "modalidade": "Pro-bono"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_clan_totals("pro_bono", INICIO, FIM)
        assert result["CLÃ 1"] == 10

    def test_pagante_individual_30pts_preserved(self):
        records = [{"clan": "CLÃ 1", "pontos": 30, "modalidade": "Coaching Individual"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_clan_totals("pagante", INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_pro_bono_excluded_from_pagante(self):
        records = [{"clan": "CLÃ 1", "pontos": 10, "modalidade": "Pro-bono"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_clan_totals("pagante", INICIO, FIM)
        assert result.get("CLÃ 1", 0) == 0

    def test_pagante_excluded_from_pro_bono(self):
        records = [{"clan": "CLÃ 1", "pontos": 30, "modalidade": "Coaching Individual"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_clan_totals("pro_bono", INICIO, FIM)
        assert result.get("CLÃ 1", 0) == 0


class TestGetTipoCoachTotalsSemFloor:

    def test_pagante_group_record_30pts_soma_direto(self):
        records = [{"coach": "Coach A", "pontos_coach": 30, "modalidade": "Coaching em grupo"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_coach_totals("pagante", INICIO, FIM)
        assert result["Coach A"] == 30

    def test_pagante_multiplos_registros_de_grupo_somam(self):
        records = [{"coach": "Coach A", "pontos_coach": 30, "modalidade": "Coaching em grupo"} for _ in range(3)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_coach_totals("pagante", INICIO, FIM)
        assert result["Coach A"] == 90

    def test_pagante_individual_30pts_preserved(self):
        records = [{"coach": "Coach A", "pontos_coach": 30, "modalidade": "Coaching Individual"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_coach_totals("pagante", INICIO, FIM)
        assert result["Coach A"] == 30

    def test_null_coach_ignored(self):
        records = [{"coach": None, "pontos_coach": 30, "modalidade": "Coaching em grupo"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_coach_totals("pagante", INICIO, FIM)
        assert result == {}

    def test_pro_bono_excluded_from_pagante(self):
        records = [{"coach": "Coach A", "pontos_coach": 10, "modalidade": "Pro-bono"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_coach_totals("pagante", INICIO, FIM)
        assert result.get("Coach A", 0) == 0

    def test_pro_bono_included_in_pro_bono_filter(self):
        records = [{"coach": "Coach A", "pontos_coach": 10, "modalidade": "Pro-bono"}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_tipo_coach_totals("pro_bono", INICIO, FIM)
        assert result["Coach A"] == 10


class TestGetPeriodDesafioCoachTotals:
    """Fase 2: agrega os tokens `active_counted` de `desafio_submissions_current`
    por coach canônico (coluna B / `raw_name`), filtrando pela data local SP de
    `submitted_at` — antes lia a tabela legada `desafio_registros_coach`."""

    def test_soma_pontos_de_coach_dos_desafios_no_periodo(self):
        rows = [
            {"token": "T1", "raw_name": "Ana Albertim", "points": 20,
             "status": "active_counted", "submitted_at": "2026-01-10T13:00:00-03:00"},
            {"token": "T2", "raw_name": "ana  albertim", "points": 10,
             "status": "active_counted", "submitted_at": "2026-01-20T13:00:00-03:00"},
            {"token": "T3", "raw_name": "Gustavo Imhof", "points": 10,
             "status": "active_counted", "submitted_at": "2026-01-15T13:00:00-03:00"},
        ]
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=rows), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            result = supabase_client.get_period_desafio_coach_totals(INICIO, FIM)
        assert result == {"Ana Albertim": 200, "Gustavo Imhof": 100}

    def test_sem_desafio_no_periodo_retorna_vazio(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            result = supabase_client.get_period_desafio_coach_totals(INICIO, FIM)
        assert result == {}
