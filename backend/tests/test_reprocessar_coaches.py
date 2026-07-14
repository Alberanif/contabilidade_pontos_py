import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import reprocessar_coaches


def _registro(coach, modalidade, pontos_coach, status_coach="contabilizado", num_participantes=1):
    return {
        "coach": coach,
        "modalidade": modalidade,
        "pontos_coach": pontos_coach,
        "status_coach": status_coach,
        "num_participantes": num_participantes,
    }


class TestReprocessarCoachesMergeERecalcula:

    def test_funde_dois_alias_e_recalcula_totais(self):
        regs_antes = [
            _registro("Vini Marini", "Coaching Individual", 30),
            _registro("Vinicius Marini", "Pro-bono", 10),
        ]
        regs_depois = [
            _registro("Vinicius Marini", "Coaching Individual", 30),
            _registro("Vinicius Marini", "Pro-bono", 10),
        ]

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.list_all_registros",
                   side_effect=[regs_antes, regs_depois]), \
             patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
             patch("supabase_client.update_registros_coach", return_value=1) as mock_update, \
             patch("supabase_client.update_desafio_importacao_linhas_coach", return_value=0), \
             patch("supabase_client.merge_desafio_registros_coach", return_value=0), \
             patch("supabase_client.get_desafio_coach_total", return_value=0), \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert, \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[
                 {"coach": "Vinicius Marini", "total_pontos": 40,
                  "total_pagante": 30, "total_pro_bono": 10, "pessoas_em_espera": 0},
             ]):
            resultado = reprocessar_coaches()

        mock_update.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_delete.assert_called_once_with("Vini Marini")
        mock_upsert.assert_any_call(
            "Vinicius Marini", 40,
            pessoas_em_espera=0, total_pagante=30, total_pro_bono=10,
        )
        assert resultado.registros_atualizados == 1
        assert resultado.coaches_afetados == ["Vinicius Marini"]
        assert resultado.totais_recalculados == {"Vinicius Marini": 40}

    def test_sem_alias_correspondente_nao_altera_nada(self):
        regs = [_registro("Vivian Gaspar", "Coaching Individual", 30)]

        with patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_all_registros", return_value=regs), \
             patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
             patch("supabase_client.update_registros_coach") as mock_update, \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.upsert_coach_total") as mock_upsert:
            resultado = reprocessar_coaches()

        mock_update.assert_not_called()
        mock_delete.assert_not_called()
        mock_upsert.assert_not_called()
        assert resultado.registros_atualizados == 0
        assert resultado.coaches_afetados == []
        assert resultado.avisos == []

    def test_detecta_cadeia_de_alias_e_reporta_aviso(self):
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"A": "B", "B": "C"}), \
             patch("supabase_client.list_all_registros", return_value=[]), \
             patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
             patch("supabase_client.update_registros_coach"), \
             patch("supabase_client.delete_coach_total"), \
             patch("supabase_client.upsert_coach_total"):
            resultado = reprocessar_coaches()

        assert len(resultado.avisos) == 1
        assert "A" in resultado.avisos[0] and "B" in resultado.avisos[0] and "C" in resultado.avisos[0]

    def test_funde_alias_de_coach_que_so_existe_em_desafio(self):
        """Coach que nunca apareceu em pontos_ultimate_registros_contabilizados
        (só tem pontos de desafio CSV) ainda deve ser fundido pela reprocessagem."""
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.list_all_registros", return_value=[]), \
             patch("supabase_client.get_all_desafio_coach_names", return_value={"Vini Marini"}), \
             patch("supabase_client.update_registros_coach", return_value=0), \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.update_desafio_importacao_linhas_coach", return_value=2) as mock_update_linhas, \
             patch("supabase_client.merge_desafio_registros_coach", return_value=1) as mock_merge, \
             patch("supabase_client.get_desafio_coach_total", return_value=25) as mock_desafio_total, \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[
                 {"coach": "Vinicius Marini", "total_pontos": 25,
                  "total_pagante": 0, "total_pro_bono": 0, "pessoas_em_espera": 0},
             ]), \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert:
            resultado = reprocessar_coaches()

        mock_update_linhas.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_merge.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_desafio_total.assert_called_once_with("Vinicius Marini")
        mock_delete.assert_called_once_with("Vini Marini")
        mock_upsert.assert_any_call(
            "Vinicius Marini", 25,
            pessoas_em_espera=0, total_pagante=0, total_pro_bono=0,
        )
        assert resultado.coaches_afetados == ["Vinicius Marini"]
        assert resultado.totais_recalculados == {"Vinicius Marini": 25}
