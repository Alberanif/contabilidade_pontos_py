import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import historico


class TestHistoricoNaoMergeiaDesafioNoCoach:
    """Desde a issue #17, nenhuma fonte de desafio contribui para o total
    individual de coach (Global Constraint): `historico()` deve continuar
    somando pontos de desafio ao total do clã (fora de escopo, inalterado),
    mas o total de coach é só `get_period_coach_totals`, sem merge de desafio."""

    def test_merge_pontos_desafio_no_total_do_cla_mas_nao_no_coach(self):
        with patch("supabase_client.get_period_clan_totals", return_value={"CLÃ 1": 100}), \
             patch("supabase_client.get_period_desafio_totals", return_value={"CLÃ 1": 20}), \
             patch("supabase_client.get_period_coach_totals", return_value={"Ana Albertim": 50}), \
             patch("supabase_client.get_period_desafio_coach_totals") as mock_desafio_coach:
            resultado = asyncio.run(historico(inicio="2026-05-01", fim="2026-06-30"))

        mock_desafio_coach.assert_not_called()
        assert resultado.clans == {"CLÃ 1": 120}
        assert resultado.coaches == {"Ana Albertim": 50}
