# backend/tests/test_importar_inicial_pontos.py
"""Verifica que importar_inicial() grava pontos corretos por tipo de registro.

Todos os mocks são aplicados antes de qualquer import do módulo router,
pois config.py chama _validate() no import e exige env vars.
"""
import os
import sys

# Env vars mínimas antes de qualquer import que carregue config.py
_FAKE_ENV = {
    "GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
    "GSHEET_RECORDS_SPREADSHEET_ID": "fake-id",
    "GSHEET_RECORDS_SHEET_NAME": "Sheet1",
    "GSHEET_TOTALS_SPREADSHEET_ID": "fake-totals-id",
    "GSHEET_TOTALS_SHEET_NAME": "Totals",
    "SUPABASE_URL": "https://fake.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "fake-key",
}
for k, v in _FAKE_ENV.items():
    os.environ.setdefault(k, v)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
import config


# ── Helpers para construir linhas de planilha ──────────────────────────────

def _ci_row(date_str: str) -> list[str]:
    row = [""] * 12
    row[0] = "1"                       # clan (col 0)
    row[1] = "Coach X"                 # coach (COL_COACH = 1)
    row[5] = "Coaching Individual"     # modalidade (COL_MODALIDADE = 5)
    row[10] = date_str                 # data (COL_DATE_PAYING = 10)
    row[11] = f"CI-{date_str}"         # chave hash (KEY_COLUMNS = [11])
    return row


def _group_row(date_str: str, n: int = 6) -> list[str]:
    row = [""] * 12
    row[0] = "1"
    row[1] = "Coach X"
    row[5] = "Coaching em grupo"       # modalidade
    row[8] = str(n)                    # participantes (COL_PARTICIPANTES_GROUP = 8)
    row[10] = date_str
    row[11] = f"GRP-{date_str}-{n}"
    return row


def _pb_row(date_str: str) -> list[str]:
    row = [""] * 12
    row[0] = "1"
    row[1] = "Coach X"
    row[9] = date_str                  # data pro-bono (COL_DATE_PRO_BONO = 9)
    row[10] = f"PB-{date_str}"         # chave (COL_PRO_BONO_KEY = 10)
    return row


HEADER = ["clan", "coach", "", "", "", "modalidade", "", "", "participantes", "", "data", "key"]
PB_HEADER = ["clan", "coach", "", "", "", "", "", "", "", "data_pb", "key_pb", ""]


# ── Helper para executar o import com mocks ────────────────────────────────

def _run_import(ci_rows=None, group_rows=None, pb_rows=None, ranking=None):
    """Executa importar_inicial() com deps externas mockadas.

    Retorna a lista de dicts passados a insert_processed_record.
    """
    ci_rows = ci_rows or []
    group_rows = group_rows or []
    pb_rows = pb_rows or []
    ranking = ranking or []

    inserted: list[dict] = []

    def capture_insert(record_data: dict):
        inserted.append(dict(record_data))

    with patch("routers.contabilidade.supabase_client") as mock_supa, \
         patch("routers.contabilidade.google_sheets_client") as mock_gsc:

        mock_supa.delete_all_registros.return_value = 0
        mock_supa.reset_all_totals.return_value = None
        mock_supa.upsert_clan_total.return_value = None
        mock_supa.upsert_coach_total.return_value = None
        mock_supa.get_tipo_clan_totals.return_value = {}
        mock_supa.insert_processed_record.side_effect = capture_insert

        mock_gsc.fetch_records.return_value = [HEADER] + ci_rows + group_rows
        mock_gsc.fetch_records_pro_bono.return_value = [PB_HEADER] + pb_rows
        mock_gsc.fetch_ranking.return_value = ranking

        from routers.contabilidade import importar_inicial
        importar_inicial()

    return inserted


# ── Testes ─────────────────────────────────────────────────────────────────

class TestImportarInicialPontos:

    def test_ci_elegivel_pontos_e_pontos_coach_corretos(self):
        """CI coaching com data >= COACH_RANKING_START_DATE:
        pontos = POINTS_PER_COACHING_INDIVIDUAL, pontos_coach = POINTS_PER_COACHING_INDIVIDUAL."""
        records = _run_import(
            ci_rows=[_ci_row("06/04/2026")],
            ranking=[{"clan": "CLÃ 1", "total_pontos": 30}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_COACHING_INDIVIDUAL
        assert records[0]["pontos_coach"] == config.POINTS_PER_COACHING_INDIVIDUAL

    def test_ci_pre_april_pontos_coach_full(self):
        """CI coaching com data < COACH_RANKING_START_DATE (antes de 01/04/2026):
        pontos = POINTS_PER_COACHING_INDIVIDUAL, pontos_coach = POINTS_PER_COACHING_INDIVIDUAL
        (sem restrição de data — todos os registros contam para o ranking de coach)."""
        records = _run_import(
            ci_rows=[_ci_row("15/03/2026")],
            ranking=[{"clan": "CLÃ 1", "total_pontos": 30}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_COACHING_INDIVIDUAL
        assert records[0]["pontos_coach"] == config.POINTS_PER_COACHING_INDIVIDUAL

    def test_grupo_contabilizado_pontos_per_record_in_batch(self):
        """Grupo com pessoas >= BATCH_SIZE_GROUP (clã tem lote completo):
        pontos = POINTS_PER_RECORD_IN_BATCH."""
        records = _run_import(
            group_rows=[_group_row("06/04/2026", n=6)],  # 6 >= BATCH_SIZE_GROUP (5)
            ranking=[{"clan": "CLÃ 1", "total_pontos": 6}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_RECORD_IN_BATCH

    def test_grupo_pendente_pontos_zero(self):
        """Grupo com pessoas < BATCH_SIZE_GROUP (sem lote completo): pontos = 0."""
        records = _run_import(
            group_rows=[_group_row("06/04/2026", n=2)],  # 2 < BATCH_SIZE_GROUP (5)
            ranking=[{"clan": "CLÃ 1", "total_pontos": 0}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == 0

    def test_pro_bono_pontos_per_pro_bono(self):
        """Pro-bono contabilizado: pontos = POINTS_PER_PRO_BONO."""
        records = _run_import(
            pb_rows=[_pb_row("06/04/2026")],
            ranking=[{"clan": "CLÃ 1", "total_pontos": 10}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_PRO_BONO
