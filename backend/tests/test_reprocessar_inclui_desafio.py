import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import reprocessar_contabilidade


class TestReprocessarContabilidadeIncluiDesafio:

    def test_reprocessar_soma_pontos_de_desafio_no_total_final_do_cla(self):
        """Clã: reprocessar_contabilidade ainda mescla o total de desafios legado
        (fora de escopo da issue #17 — só o lado coach foi removido)."""
        with patch("google_sheets_client.fetch_records", return_value=[["header"]]), \
             patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals", return_value=None), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=None), \
             patch("supabase_client.get_tipo_clan_totals", return_value={"CLÃ 5": 40}) as mock_tipo_clan, \
             patch("supabase_client.get_tipo_coach_totals", return_value={}), \
             patch("supabase_client.upsert_clan_total", return_value={}) as mock_upsert_clan, \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert_coach:
            reprocessar_contabilidade()

        mock_tipo_clan.assert_called_once_with("desafios")
        mock_upsert_clan.assert_any_call("CLÃ 5", 40, total_pagante=0, total_pro_bono=0)
        # Nenhum ponto de desafio deve chegar ao coach: sem pontos de coach vindos de
        # nenhuma fonte pagante/pro-bono/desafio, upsert_coach_total nem é chamado.
        mock_upsert_coach.assert_not_called()

    def test_reprocessar_soma_desafio_no_total_final_do_coach(self):
        """Fase 2: reprocessar_contabilidade mescla get_tipo_coach_totals('desafios')
        no total geral do coach (mesmo padrão do clã)."""
        with patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=[["h"]]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=[]), \
             patch("google_sheets_client.fetch_ranking", return_value=[]), \
             patch("routers.contabilidade._process_group_records",
                   return_value=(0, {}, {})), \
             patch("routers.contabilidade._process_pro_bono_records",
                   return_value=(0, {}, {})), \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.get_tipo_coach_totals",
                   return_value={"Ana Albertim": 40}) as mock_tipo_coach, \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.upsert_clan_total"), \
             patch("supabase_client.upsert_coach_total") as mock_upsert_coach:
            from routers.contabilidade import reprocessar_contabilidade
            reprocessar_contabilidade()

        mock_tipo_coach.assert_any_call("desafios")
        mock_upsert_coach.assert_any_call(
            "Ana Albertim", 40, total_pagante=0, total_pro_bono=0
        )
