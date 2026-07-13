import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import (
    _process_group_records,
    importar_inicial,
)


def _group_row(date_str: str, key: str = "key_grp") -> list[str]:
    # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_PARTICIPANTES=8,
    # COL_DATE_PAYING=10, KEY_COLUMNS=[11]
    return ["1", "Coach A", "", "", "", "Coaching em grupo", "", "", "3", "", date_str, key]


def _pb_row(date_str: str, key: str = "key_pb") -> list[str]:
    # COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10
    return ["1", "Coach A", "", "", "", "", "", "", "", date_str, key]


def _ci_row(date_str: str, key: str = "key_ci") -> list[str]:
    # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_DATE_PAYING=10, KEY_COLUMNS=[11]
    return ["1", "Coach A", "", "", "", "Coaching Individual", "", "", "", "", date_str, key]


class TestGroupRecordAlwaysPendente:
    """Registros de grupo via executar devem sempre ter status_coach='pendente'."""

    def _run(self, date_str: str) -> list[dict]:
        row = _group_row(date_str)
        header = [f"col_{i}" for i in range(len(row))]
        inserted: list[dict] = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.insert_processed_record", side_effect=capture), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_pending_group_records_by_clan", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_alias_map", return_value={}):
            _process_group_records([row], header, processed_hashes=set())

        return inserted

    def test_pre_april_group_gets_status_coach_pendente(self):
        inserted = self._run("15/03/2026")
        assert len(inserted) == 1
        assert inserted[0]["status_coach"] == "pendente"

    def test_post_april_group_gets_status_coach_pendente(self):
        inserted = self._run("15/04/2026")
        assert len(inserted) == 1
        assert inserted[0]["status_coach"] == "pendente"


class TestProBonoAlways10Pts:
    """Registros Pro Bono devem sempre ter pontos_coach=10.

    Tested via importar_inicial because that is where the date gate applies to
    pontos_coach for pro-bono records (Phase 8 uses coach_eligible_pb_hashes).
    """

    def _run(self, date_str: str) -> list[dict]:
        pb_row = _pb_row(date_str)
        ci_header = [f"col_{i}" for i in range(12)]
        pb_header = [f"col_{i}" for i in range(len(pb_row))]
        inserted: list[dict] = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=[ci_header]), \
             patch("google_sheets_client.fetch_records_pro_bono",
                   return_value=[pb_header, pb_row]), \
             patch("google_sheets_client.fetch_ranking",
                   return_value=[{"clan": "CLÃ 1", "total_pontos": 10}]), \
             patch("supabase_client.insert_processed_record", side_effect=capture), \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.upsert_clan_total", return_value={}), \
             patch("supabase_client.upsert_coach_total", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.get_coach_alias_map", return_value={}):
            importar_inicial()

        return [r for r in inserted if r.get("modalidade") == "Pro-bono"]

    def test_pre_april_pro_bono_gets_pontos_coach_10(self):
        inserted = self._run("15/03/2026")
        assert len(inserted) == 1
        assert inserted[0]["pontos_coach"] == 10

    def test_post_april_pro_bono_gets_pontos_coach_10(self):
        inserted = self._run("15/04/2026")
        assert len(inserted) == 1
        assert inserted[0]["pontos_coach"] == 10


class TestIndividualCoachingAlways30Pts:
    """Coaching Individual em importar_inicial deve sempre ter pontos_coach=30."""

    def _run(self, date_str: str) -> list[dict]:
        header = [f"col_{i}" for i in range(12)]
        row = _ci_row(date_str)
        pb_header = [f"col_{i}" for i in range(11)]
        inserted: list[dict] = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=[header, row]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=[pb_header]), \
             patch("google_sheets_client.fetch_ranking",
                   return_value=[{"clan": "CLÃ 1", "total_pontos": 30}]), \
             patch("supabase_client.insert_processed_record", side_effect=capture), \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.upsert_clan_total", return_value={}), \
             patch("supabase_client.upsert_coach_total", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.get_coach_alias_map", return_value={}):
            importar_inicial()

        return [r for r in inserted if r.get("modalidade") == "Coaching Individual"]

    def test_pre_april_individual_coaching_gets_pontos_coach_30(self):
        ci = self._run("15/03/2026")
        assert len(ci) == 1
        assert ci[0]["pontos_coach"] == 30

    def test_post_april_individual_coaching_gets_pontos_coach_30(self):
        ci = self._run("15/04/2026")
        assert len(ci) == 1
        assert ci[0]["pontos_coach"] == 30
