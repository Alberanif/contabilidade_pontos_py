import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import _build_and_insert, _build_and_insert_pro_bono


def _row(coach="Tati Pellicel"):
    # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_DATE_PAYING=10, KEY_COLUMNS=[11]
    return ["1", coach, "", "", "", "Coaching Individual", "", "", "", "", "01/03/2026", "key1"]


class TestBuildAndInsertNormalizesCoach:

    def test_coach_e_normalizado_via_alias(self):
        row = _row("Tati Pellicel")
        header = [f"col_{i}" for i in range(len(row))]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Tati Pellicel": "Tatiane Pellicel"}), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _build_and_insert(
                "hash1", row, header, [row], pontos=30,
                extra_fields={"status": "contabilizado"},
                date_col=10,
            )

        assert inserted[0]["coach"] == "Tatiane Pellicel"

    def test_coach_sem_alias_mantem_nome_aparado(self):
        row = _row("Vivian Gaspar")
        header = [f"col_{i}" for i in range(len(row))]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _build_and_insert(
                "hash1", row, header, [row], pontos=30,
                extra_fields={"status": "contabilizado"},
                date_col=10,
            )

        assert inserted[0]["coach"] == "Vivian Gaspar"


def _pb_row(coach="Tati Pellicel"):
    # COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10
    return ["1", coach, "", "", "", "", "", "", "", "01/03/2026", "keypb1"]


class TestBuildAndInsertProBonoNormalizesCoach:

    def test_coach_e_normalizado_via_alias(self):
        row = _pb_row("Tati Pellicel")
        header = [f"col_{i}" for i in range(len(row))]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Tati Pellicel": "Tatiane Pellicel"}), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _build_and_insert_pro_bono(
                "hash1", row, header, [row], pontos=10,
                extra_fields={"status": "contabilizado", "status_coach": "contabilizado"},
                date_col=9,
            )

        assert inserted[0]["coach"] == "Tatiane Pellicel"


from routers.contabilidade import aprovar_coach, AprovarCoachRequest


class TestAprovarCoachResolveAlias:

    def test_aprovar_com_alias_busca_fila_do_canonico(self):
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.get_pending_group_records_by_coach",
                   return_value=[]) as mock_pending, \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[]), \
             patch("supabase_client.upsert_coach_total", return_value={}):
            aprovar_coach(AprovarCoachRequest(coach="Vini Marini"))

        mock_pending.assert_called_once()
        args, _ = mock_pending.call_args
        assert args[0] == "Vinicius Marini"


from routers.contabilidade import _process_pro_bono_records


class TestProcessProBonoMergesCoach:

    def test_dois_alias_do_mesmo_coach_somam(self):
        # COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10
        row_a = ["1", "Vini Marini", "", "", "", "", "", "", "", "01/03/2026", "keyA"]
        row_b = ["1", "Vinicius Marini", "", "", "", "", "", "", "", "01/03/2026", "keyB"]

        with patch("google_sheets_client.fetch_records_pro_bono",
                   return_value=[[f"col_{i}" for i in range(11)], row_a, row_b]), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.insert_processed_record", side_effect=lambda r: r):
            _n_novos, _pontos_por_clan, pontos_por_coach = _process_pro_bono_records(set())

        assert pontos_por_coach == {"Vinicius Marini": 20}
