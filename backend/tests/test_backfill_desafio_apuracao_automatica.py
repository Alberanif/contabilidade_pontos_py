"""Testes do backfill administrativo único de apuração automática (Task 4)."""

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

from admin.backfill_desafio_apuracao_automatica import desafios_para_backfill, main


def test_desafios_para_backfill_so_retorna_apurados():
    desafios = [
        {"id": 1, "nome": "A", "apurado_em": "2026-08-20T00:00:00+00:00"},
        {"id": 2, "nome": "B", "apurado_em": None},
    ]
    with patch("supabase_client.list_desafios", return_value=desafios):
        assert desafios_para_backfill() == [desafios[0]]


def test_main_dry_run_nao_aplica_por_padrao(capsys):
    desafios = [{"id": 1, "nome": "A", "apurado_em": "2026-08-20T00:00:00+00:00"}]
    with patch("supabase_client.list_desafios", return_value=desafios), \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_reapurar.return_value = {"CLÃ 1": {"pontos": 500, "delta": 200}}
        main([])

    mock_reapurar.assert_called_once_with(1, dry_run=True)
    assert "Dry-run" in capsys.readouterr().out


def test_main_apply_grava_de_verdade():
    desafios = [{"id": 1, "nome": "A", "apurado_em": "2026-08-20T00:00:00+00:00"}]
    with patch("supabase_client.list_desafios", return_value=desafios), \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_reapurar.return_value = {"CLÃ 1": {"pontos": 500, "delta": 200}}
        main(["--apply"])

    mock_reapurar.assert_any_call(1, dry_run=True)   # preview
    mock_reapurar.assert_any_call(1)                 # aplicação de fato


def test_main_sem_alvos_nao_chama_reapurar(capsys):
    with patch("supabase_client.list_desafios", return_value=[]), \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        main([])

    mock_reapurar.assert_not_called()
    assert "Nenhum desafio" in capsys.readouterr().out
