"""`apply_grupo_flat_correction`: aplica a correção retroativa não-destrutiva
de registros de Coaching em grupo/Empresa presos no antigo esquema de lote
(issue #42) — atualiza pontos/status nos dois eixos (clã e coach) de uma vez
para os ids informados."""

import os
import sys
from unittest.mock import MagicMock, patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supabase_client


def test_ids_vazio_nao_toca_o_banco():
    with patch("supabase_client._get_client") as mock_get_client:
        result = supabase_client.apply_grupo_flat_correction([], 30)
    mock_get_client.assert_not_called()
    assert result == 0


def test_atualiza_pontos_e_status_dos_dois_eixos_para_os_ids_informados():
    chain = MagicMock()
    for m in ("table", "update", "in_"):
        getattr(chain, m).return_value = chain
    chain.execute.return_value = MagicMock(data=[{"id": 1}, {"id": 2}])
    client = MagicMock()
    client.table.return_value = chain

    with patch("supabase_client._get_client", return_value=client):
        result = supabase_client.apply_grupo_flat_correction([1, 2], 30)

    chain.update.assert_called_once_with({
        "pontos": 30,
        "status": "contabilizado",
        "pontos_coach": 30,
        "status_coach": "contabilizado",
    })
    chain.in_.assert_called_once_with("id", [1, 2])
    assert result == 2
