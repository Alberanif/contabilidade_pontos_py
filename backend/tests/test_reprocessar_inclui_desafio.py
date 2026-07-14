import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import reprocessar_contabilidade


class TestReprocessarContabilidadeIncluiDesafio:

    def test_reprocessar_soma_pontos_de_desafio_no_total_final(self):
        with patch("google_sheets_client.fetch_records", return_value=[["header"]]), \
             patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals", return_value=None), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=None), \
             patch("supabase_client.get_tipo_clan_totals", return_value={"CLÃ 5": 40}) as mock_tipo_clan, \
             patch("supabase_client.get_tipo_coach_totals", return_value={"Ana Albertim": 40}) as mock_tipo_coach, \
             patch("supabase_client.upsert_clan_total", return_value={}) as mock_upsert_clan, \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert_coach:
            reprocessar_contabilidade()

        mock_tipo_clan.assert_called_once_with("desafios")
        mock_tipo_coach.assert_called_once_with("desafios")
        mock_upsert_clan.assert_any_call("CLÃ 5", 40, total_pagante=0, total_pro_bono=0)
        mock_upsert_coach.assert_any_call("Ana Albertim", 40, total_pagante=0, total_pro_bono=0)
