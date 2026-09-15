"""Finding 2: fiação de `_refresh_desafio_coach_totals` em `/executar` e
`/confirmar-desafios`.

O refresh só deve rodar quando a sincronização de desafios de fato aplicou
tokens (`status == "success"` e `tokens_versioned > 0`); e uma falha do refresh
nunca pode derrubar o endpoint (o bloco é isolado por try/except).
"""

import os
import sys
from unittest.mock import patch

import pytest

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
    ConfirmarDesafiosRequest,
    confirmar_desafios,
    executar_contabilidade,
)


def _result(**overrides) -> DesafioSyncResult:
    base = dict(status="success", run_id=1, tokens_versioned=1, mensagem="ok")
    base.update(overrides)
    return DesafioSyncResult(**base)


class TestExecutarRefreshWiring:
    """Caminho de retorno principal de `/executar` (planilha só com cabeçalho):
    todas as demais fontes ficam vazias, sobrando apenas o bloco de refresh."""

    def _run(self, desafios_result):
        with patch("routers.contabilidade._sync_desafios_isolado",
                   return_value=desafios_result), \
             patch("routers.contabilidade._refresh_desafio_coach_totals") as mock_refresh, \
             patch("google_sheets_client.fetch_records", return_value=[["h"]]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=None), \
             patch("supabase_client.get_processed_hashes", return_value=set()), \
             patch("supabase_client.get_coach_alias_map", return_value={}):
            response = executar_contabilidade()
        return response, mock_refresh

    def test_refresh_chamado_quando_sucesso_e_tokens_versionados(self):
        response, mock_refresh = self._run(_result(status="success", tokens_versioned=1))
        mock_refresh.assert_called_once_with()
        assert response.desafios.status == "success"

    def test_refresh_nao_chamado_quando_zero_tokens_versionados(self):
        _, mock_refresh = self._run(_result(status="success", tokens_versioned=0))
        mock_refresh.assert_not_called()

    def test_refresh_nao_chamado_quando_awaiting_confirmation(self):
        _, mock_refresh = self._run(
            _result(status="awaiting_confirmation", tokens_versioned=0)
        )
        mock_refresh.assert_not_called()


class TestConfirmarDesafiosRefreshWiring:

    def test_refresh_chamado_e_resultado_retornado(self):
        with patch("desafio_sync_service.sync_desafios",
                   return_value=_result(status="success", tokens_versioned=1)), \
             patch("routers.contabilidade._refresh_desafio_coach_totals") as mock_refresh:
            result = confirmar_desafios(ConfirmarDesafiosRequest(snapshot_hash="h"))
        mock_refresh.assert_called_once_with()
        assert result.status == "success"

    def test_refresh_nao_chamado_quando_zero_tokens_versionados(self):
        with patch("desafio_sync_service.sync_desafios",
                   return_value=_result(status="success", tokens_versioned=0)), \
             patch("routers.contabilidade._refresh_desafio_coach_totals") as mock_refresh:
            result = confirmar_desafios(ConfirmarDesafiosRequest(snapshot_hash="h"))
        mock_refresh.assert_not_called()
        assert result.status == "success"

    def test_falha_do_refresh_nao_propaga_nem_vira_500(self):
        with patch("desafio_sync_service.sync_desafios",
                   return_value=_result(status="success", tokens_versioned=1)), \
             patch("routers.contabilidade._refresh_desafio_coach_totals",
                   side_effect=RuntimeError("boom")):
            result = confirmar_desafios(ConfirmarDesafiosRequest(snapshot_hash="h"))
        assert result.status == "success"
