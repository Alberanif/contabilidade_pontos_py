"""Regra permanente: nenhum registro (Coaching Individual, Coaching em
Grupo/Empresa ou Pro-bono) anterior a `config.DATA_INICIO_CONTABILIZACAO`
(01/08/2026) é inserido/contado — nem em `/executar`, nem em `/reprocessar`,
mesmo que apareça "novo" (ainda não processado) na planilha.

Não cobre desafios: confirmado à parte (root cause investigation da mudança)
que nenhuma submissão `active_counted` hoje é anterior a essa data, então o
filtro não tem efeito prático ali — a regra de corte de desafios
(`config.DESAFIO_PERCENTUAL_CLAN_CORTE`) já é um mecanismo separado.
"""

import os
import sys
from unittest.mock import patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desafio_sync_service import DesafioSyncResult
from routers.contabilidade import (
    _process_pro_bono_records,
    _process_group_records,
    executar_contabilidade,
    reprocessar_contabilidade,
)


class TestProcessProBonoRecordsIgnoraAnteriorAoCorte:
    """COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10."""

    def _rows(self):
        header = [f"col_{i}" for i in range(11)]
        antigo = ["1", "Ana", "", "", "", "", "", "", "", "15/07/2026", "keyA"]
        novo = ["1", "Ana", "", "", "", "", "", "", "", "15/08/2026", "keyB"]
        return [header, antigo, novo]

    def test_so_conta_o_registro_a_partir_do_corte(self):
        with patch("google_sheets_client.fetch_records_pro_bono", return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.insert_processed_record", side_effect=lambda r: r) as mock_insert:
            n_novos, pontos_por_clan, pontos_por_coach = _process_pro_bono_records(set())

        assert n_novos == 1
        assert pontos_por_coach == {"Ana": 10}
        assert pontos_por_clan == {"CLÃ 1": 10}
        assert mock_insert.call_count == 1
        assert mock_insert.call_args[0][0]["data_registro"] == "2026-08-15"


class TestProcessGroupRecordsIgnoraAnteriorAoCorte:
    """COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_PARTICIPANTES=8,
    COL_DATE_PAYING=10, KEY_COLUMNS=[11]."""

    def _rows(self):
        header = [f"col_{i}" for i in range(12)]
        antigo = ["1", "Bruno", "", "", "", "Coaching em grupo", "", "", "5", "", "10/07/2026", "keyA"]
        novo = ["1", "Bruno", "", "", "", "Coaching em grupo", "", "", "5", "", "10/08/2026", "keyB"]
        return header, [antigo, novo]

    def test_so_insere_o_registro_a_partir_do_corte(self):
        header, data_rows = self._rows()
        with patch("supabase_client.insert_processed_record", side_effect=lambda r: r) as mock_insert, \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]):
            _process_group_records(data_rows, header, set())

        assert mock_insert.call_count == 1
        assert mock_insert.call_args[0][0]["data_registro"] == "2026-08-10"


class TestExecutarContabilidadeIgnoraCoachingIndividualAnteriorAoCorte:
    """COL_MODALIDADE=5, COL_CLAN=0, COL_COACH=1, COL_DATE_PAYING=10, KEY_COLUMNS=[11]."""

    def _rows(self):
        header = [f"col_{i}" for i in range(12)]
        antigo = ["1", "Carla", "", "", "", "Coaching Individual", "", "", "", "", "20/07/2026", "keyA"]
        novo = ["1", "Carla", "", "", "", "Coaching Individual", "", "", "", "", "20/08/2026", "keyB"]
        return [header, antigo, novo]

    def test_novos_registros_e_pontos_ignoram_o_anterior_ao_corte(self):
        with patch(
                 "routers.contabilidade._sync_desafios_isolado",
                 return_value=DesafioSyncResult(status="success", run_id=1, tokens_versioned=0, mensagem="ok"),
             ), \
             patch("routers.contabilidade.processar_desafios_apuracao_prazo"), \
             patch("google_sheets_client.fetch_records", return_value=self._rows()), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=None), \
             patch("supabase_client.get_processed_hashes", return_value=set()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.list_clan_totals", return_value=[]), \
             patch("supabase_client.list_coach_totals", return_value=[]), \
             patch("supabase_client.upsert_clan_total"), \
             patch("supabase_client.upsert_coach_total"), \
             patch("supabase_client.insert_processed_record", side_effect=lambda r: r) as mock_insert:
            response = executar_contabilidade()

        assert response.novos_registros == 1
        assert response.pontos_por_clan == {"CLÃ 1": 30}
        assert response.pontos_por_coach == {"Carla": 30}
        coaching_inserts = [
            c for c in mock_insert.call_args_list
            if c[0][0].get("modalidade") == "Coaching Individual"
        ]
        assert len(coaching_inserts) == 1
        assert coaching_inserts[0][0][0]["data_registro"] == "2026-08-20"


class TestReprocessarContabilidadeIgnoraCoachingIndividualAnteriorAoCorte:

    def _rows(self):
        header = [f"col_{i}" for i in range(12)]
        antigo = ["1", "Carla", "", "", "", "Coaching Individual", "", "", "", "", "20/07/2026", "keyA"]
        novo = ["1", "Carla", "", "", "", "Coaching Individual", "", "", "", "", "20/08/2026", "keyB"]
        return [header, antigo, novo]

    def test_novos_registros_e_pontos_ignoram_o_anterior_ao_corte(self):
        with patch("supabase_client.delete_all_registros", return_value=2), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=self._rows()), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=None), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.insert_processed_record", side_effect=lambda r: r) as mock_insert, \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.get_tipo_coach_totals", return_value={}), \
             patch("supabase_client.upsert_clan_total"), \
             patch("supabase_client.upsert_coach_total"):
            response = reprocessar_contabilidade()

        assert response.novos_registros == 1
        assert response.pontos_por_clan == {"CLÃ 1": 30}
        assert response.pontos_por_coach == {"Carla": 30}
        coaching_inserts = [
            c for c in mock_insert.call_args_list
            if c[0][0].get("modalidade") == "Coaching Individual"
        ]
        assert len(coaching_inserts) == 1
        assert coaching_inserts[0][0][0]["data_registro"] == "2026-08-20"
