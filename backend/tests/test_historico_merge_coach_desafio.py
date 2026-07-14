import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import historico


class TestHistoricoMergeCoachDesafio:

    def test_merge_pontos_desafio_no_total_do_coach(self):
        with patch("supabase_client.get_period_clan_totals", return_value={"CLÃ 1": 100}), \
             patch("supabase_client.get_period_desafio_totals", return_value={"CLÃ 1": 20}), \
             patch("supabase_client.get_period_coach_totals", return_value={"Ana Albertim": 50}), \
             patch("supabase_client.get_period_desafio_coach_totals",
                   return_value={"Ana Albertim": 10, "Gustavo Imhof": 5}):
            resultado = asyncio.run(historico(inicio="2026-05-01", fim="2026-06-30"))

        assert resultado.clans == {"CLÃ 1": 120}
        assert resultado.coaches == {"Ana Albertim": 60, "Gustavo Imhof": 5}
