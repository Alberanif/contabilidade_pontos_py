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


class TestGetPeriodClanTotalsFloor:

    def test_partial_group_6pts_returns_zero(self):
        records = [{"clan": "CLÃ 1", "pontos": 6}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result.get("CLÃ 1", 0) == 0

    def test_partial_group_24pts_returns_zero(self):
        records = [{"clan": "CLÃ 1", "pontos": 6} for _ in range(4)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result.get("CLÃ 1", 0) == 0

    def test_full_batch_5_records_returns_30(self):
        records = [{"clan": "CLÃ 1", "pontos": 6} for _ in range(5)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_6_records_36pts_floors_to_30(self):
        records = [{"clan": "CLÃ 1", "pontos": 6} for _ in range(6)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_10_records_two_batches_returns_60(self):
        records = [{"clan": "CLÃ 1", "pontos": 6} for _ in range(10)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 60

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

    def test_individual_plus_partial_group_preserves_individual(self):
        """30 (individual) + 6 (partial group) → 30 (grupo ignorado)"""
        records = [
            {"clan": "CLÃ 1", "pontos": 30},
            {"clan": "CLÃ 1", "pontos": 6},
        ]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 30

    def test_individual_plus_full_group_batch(self):
        """30 (individual) + 30 (lote completo) = 60"""
        records = [{"clan": "CLÃ 1", "pontos": 30}] + [{"clan": "CLÃ 1", "pontos": 6} for _ in range(5)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_clan_totals(INICIO, FIM)
        assert result["CLÃ 1"] == 60


class TestGetPeriodCoachTotalsFloor:

    def test_partial_group_6pts_returns_zero(self):
        records = [{"coach": "Coach A", "pontos_coach": 6}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result.get("Coach A", 0) == 0

    def test_full_batch_5_records_returns_30(self):
        records = [{"coach": "Coach A", "pontos_coach": 6} for _ in range(5)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result["Coach A"] == 30

    def test_6_records_floors_to_30(self):
        records = [{"coach": "Coach A", "pontos_coach": 6} for _ in range(6)]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result["Coach A"] == 30

    def test_individual_30pts_preserved(self):
        records = [{"coach": "Coach A", "pontos_coach": 30}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result["Coach A"] == 30

    def test_null_coach_ignored(self):
        records = [{"coach": None, "pontos_coach": 6}]
        with patch("supabase_client._get_client", return_value=_mock_client(records)):
            result = supabase_client.get_period_coach_totals(INICIO, FIM)
        assert result == {}
