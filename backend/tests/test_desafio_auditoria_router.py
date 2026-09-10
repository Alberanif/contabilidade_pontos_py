"""Testes da API somente-leitura de auditoria de desafios (issue #18).

Cobrem: contrato de resposta, mapeamento status=active/archived/all -> valores
em português do banco, filtros combinados, paginação/ordenação (delegada aos
helpers já existentes em `supabase_client`), 404 para desafio/token/execução
inexistentes (mas lista de versões vazia para um token real NÃO é 404),
serialização timezone-aware de datas, e a garantia de que este router é
somente leitura e não sofre shadowing de rota entre segmentos literais
(`/sincronizacoes`, `/submissoes/...`) e genéricos (`/{desafio_id}`).

Usa `TestClient(app)` (roteamento real do FastAPI, não chamadas diretas aos
handlers) justamente para que os testes de ordenação de rota provem
shadowing de verdade — e mocka apenas a borda `supabase_client`.
"""

import os
import sys
import typing
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import desafio_auditoria as auditoria


client = TestClient(app)


def _desafio(**overrides) -> dict:
    base = {
        "id": 1,
        "nome": "Desafio A",
        "contabilizar_pontos": True,
        "data": "2026-08-01",
        "data_inicio": "2026-08-01",
        "data_fim": "2026-08-31",
        "origem": "google_sheets",
        "nome_normalizado": "desafio a",
        "status": "ativo",
        "arquivado_at": None,
        "reativado_at": None,
        "updated_at": "2026-08-19T10:00:00-03:00",
        "created_at": "2026-08-01T09:00:00-03:00",
    }
    base.update(overrides)
    return base


def _submission(**overrides) -> dict:
    base = {
        "token": "TOK-1",
        "row_numbers": [2],
        "raw_cells": ["1", "Ana", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-1"],
        "raw_clan_legacy": "1",
        "raw_name": "Ana",
        "raw_validation": "Sim",
        "raw_link": None,
        "raw_observation": None,
        "raw_challenge": "Desafio A",
        "raw_clan_current": None,
        "raw_submitted_at": "19/08/2026 10:00:00",
        "raw_token": "TOK-1",
        "clan": "CLÃ 1",
        "challenge_normalized": "desafio a",
        "desafio_id": 1,
        "submitted_at": "2026-08-19T10:00:00-03:00",
        "status": "active_counted",
        "invalid_reasons": [],
        "points": 10,
        "content_hash": "hash-1",
        "first_seen_run_id": 1,
        "last_seen_run_id": 1,
        "inactivated_at": None,
        "created_at": "2026-08-19T10:00:00-03:00",
        "updated_at": "2026-08-19T10:00:00-03:00",
    }
    base.update(overrides)
    return base


def _version(**overrides) -> dict:
    base = {
        "id": 1,
        "token": "TOK-1",
        "sync_run_id": 1,
        "version_number": 1,
        "row_numbers": [2],
        "raw_cells": ["1", "Ana", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-1"],
        "raw_clan_legacy": "1",
        "raw_name": "Ana",
        "raw_validation": "Sim",
        "raw_link": None,
        "raw_observation": None,
        "raw_challenge": "Desafio A",
        "raw_clan_current": None,
        "raw_submitted_at": "19/08/2026 10:00:00",
        "raw_token": "TOK-1",
        "previous_state": None,
        "current_state": {"status": "active_counted"},
        "previous_status": None,
        "current_status": "active_counted",
        "point_delta": 10,
        "clan_deltas": {"CLÃ 1": 10},
        "change_reason": "new",
        "observed_at": "2026-08-19T10:00:00-03:00",
    }
    base.update(overrides)
    return base


def _sync_run(**overrides) -> dict:
    base = {
        "id": 1,
        "started_at": "2026-08-19T10:00:00-03:00",
        "finished_at": "2026-08-19T10:05:00-03:00",
        "status": "succeeded",
        "snapshot_hash": "abc123",
        "sheet_row_count": 10,
        "state_counts": {"active_counted": 10},
        "clan_deltas": {"CLÃ 1": 10},
        "challenges_created": 1,
        "challenges_archived": 0,
        "challenges_reactivated": 0,
        "points_per_submission": 10,
        "mass_removal_required": False,
        "mass_removal_confirmed": False,
        "mass_removal_count": 0,
        "error": None,
        "created_at": "2026-08-19T10:05:00-03:00",
    }
    base.update(overrides)
    return base


# --- Step 5: router somente leitura ---


class TestRouterSomenteLeitura:

    def test_todas_as_rotas_do_router_de_auditoria_sao_get(self):
        metodos_nao_get = set()
        for route in auditoria.router.routes:
            metodos_nao_get |= route.methods - {"GET", "HEAD"}
        assert metodos_nao_get == set()

    def test_router_de_auditoria_tem_as_sete_rotas_do_contrato(self):
        paths = sorted(route.path for route in auditoria.router.routes)
        assert paths == sorted([
            "",
            "/sincronizacoes",
            "/sincronizacoes/{run_id:int}",
            "/submissoes/{token}",
            "/submissoes/{token}/versoes",
            "/{desafio_id:int}",
            "/{desafio_id:int}/submissoes",
        ])

    def test_writes_bloqueados_do_desafios_router_continuam_registrados(self):
        """As 5 escritas 410 da Task 6 continuam montadas junto (issue #17)."""
        response = client.post("/api/desafios", json={
            "nome": "x", "contabilizar_pontos": True,
            "data_inicio": "2026-01-01", "data_fim": "2026-01-31", "registros": [],
        })
        assert response.status_code == 410


# --- Contrato de datas timezone-aware ---


class TestSerializacaoDatasTimezoneAware:

    @pytest.mark.parametrize("model,campo", [
        (auditoria.DesafioResponse, "arquivado_at"),
        (auditoria.DesafioResponse, "reativado_at"),
        (auditoria.DesafioResponse, "updated_at"),
        (auditoria.DesafioResponse, "created_at"),
        (auditoria.DesafioSubmissionResponse, "submitted_at"),
        (auditoria.DesafioSubmissionResponse, "inactivated_at"),
        (auditoria.DesafioSubmissionVersionResponse, "observed_at"),
        (auditoria.DesafioSyncRunResponse, "started_at"),
        (auditoria.DesafioSyncRunResponse, "finished_at"),
        (auditoria.DesafioSyncRunResponse, "created_at"),
    ])
    def test_campo_de_data_e_tipado_como_datetime(self, model, campo):
        hints = typing.get_type_hints(model)
        assert hints[campo] in (datetime, datetime | None), (
            f"{model.__name__}.{campo} deveria ser `datetime`, é {hints[campo]!r}"
        )

    def test_offset_de_fuso_e_preservado_na_resposta(self):
        with patch("supabase_client.list_desafio_sync_runs", return_value=[_sync_run()]):
            response = client.get("/api/desafios/sincronizacoes")
        assert response.status_code == 200
        started_at = response.json()[0]["started_at"]
        parsed = datetime.fromisoformat(started_at)
        assert parsed.utcoffset() is not None
        assert parsed.utcoffset().total_seconds() == -3 * 3600


# --- GET /api/desafios?status=... ---


class TestListarDesafios:

    def test_status_default_all_nao_filtra(self):
        with patch("supabase_client.list_desafios", return_value=[_desafio()]) as mock_list:
            response = client.get("/api/desafios")
        assert response.status_code == 200
        mock_list.assert_called_once_with(status=None)
        assert response.json()[0]["id"] == 1

    def test_status_active_mapeia_para_ativo(self):
        with patch("supabase_client.list_desafios", return_value=[]) as mock_list:
            response = client.get("/api/desafios?status=active")
        assert response.status_code == 200
        mock_list.assert_called_once_with(status="ativo")

    def test_status_archived_mapeia_para_arquivado(self):
        with patch("supabase_client.list_desafios", return_value=[]) as mock_list:
            response = client.get("/api/desafios?status=archived")
        assert response.status_code == 200
        mock_list.assert_called_once_with(status="arquivado")

    def test_status_all_explicito_nao_filtra(self):
        with patch("supabase_client.list_desafios", return_value=[]) as mock_list:
            response = client.get("/api/desafios?status=all")
        assert response.status_code == 200
        mock_list.assert_called_once_with(status=None)

    def test_status_invalido_retorna_422(self):
        response = client.get("/api/desafios?status=bogus")
        assert response.status_code == 422


# --- GET /api/desafios/{id} ---


class TestObterDesafio:

    def test_desafio_existente_inclui_totais_por_clan(self):
        with patch("supabase_client.get_desafio", return_value=_desafio()), \
             patch("supabase_client.get_desafio_clan_totals", return_value={"CLÃ 1": 30}) as mock_totais:
            response = client.get("/api/desafios/1")
        assert response.status_code == 200
        body = response.json()
        assert body["pontos_por_clan"] == {"CLÃ 1": 30}
        mock_totais.assert_called_once_with(1)

    def test_desafio_inexistente_retorna_404(self):
        with patch("supabase_client.get_desafio", return_value=None):
            response = client.get("/api/desafios/999")
        assert response.status_code == 404
        assert "não encontrado" in response.json()["detail"].lower()


# --- GET /api/desafios/{id}/submissoes ---


class TestListarSubmissoesDoDesafio:

    def test_desafio_inexistente_retorna_404(self):
        with patch("supabase_client.get_desafio", return_value=None):
            response = client.get("/api/desafios/999/submissoes")
        assert response.status_code == 404

    def test_filtros_combinados_e_paginacao_sao_repassados(self):
        with patch("supabase_client.get_desafio", return_value=_desafio()), \
             patch(
                 "supabase_client.list_desafio_submissions_current", return_value=[_submission()]
             ) as mock_list:
            response = client.get(
                "/api/desafios/1/submissoes?clan=CL%C3%83+1&status=active_counted&limit=5&offset=10"
            )
        assert response.status_code == 200
        mock_list.assert_called_once_with(
            desafio_id=1, clan="CLÃ 1", status="active_counted", limit=5, offset=10
        )
        assert response.json()[0]["token"] == "TOK-1"

    def test_paginacao_default_bate_com_o_helper(self):
        with patch("supabase_client.get_desafio", return_value=_desafio()), \
             patch("supabase_client.list_desafio_submissions_current", return_value=[]) as mock_list:
            client.get("/api/desafios/1/submissoes")
        mock_list.assert_called_once_with(desafio_id=1, clan=None, status=None, limit=100, offset=0)


# --- GET /api/desafios/submissoes/{token} ---


class TestObterSubmissao:

    def test_token_existente(self):
        with patch("supabase_client.get_desafio_submission_current", return_value=_submission()):
            response = client.get("/api/desafios/submissoes/TOK-1")
        assert response.status_code == 200
        assert response.json()["token"] == "TOK-1"

    def test_token_inexistente_retorna_404(self):
        with patch("supabase_client.get_desafio_submission_current", return_value=None):
            response = client.get("/api/desafios/submissoes/TOK-DESCONHECIDO")
        assert response.status_code == 404


# --- GET /api/desafios/submissoes/{token}/versoes ---


class TestListarVersoesSubmissao:

    def test_token_inexistente_retorna_404(self):
        with patch("supabase_client.get_desafio_submission_current", return_value=None), \
             patch("supabase_client.list_desafio_submission_versions") as mock_versions:
            response = client.get("/api/desafios/submissoes/TOK-DESCONHECIDO/versoes")
        assert response.status_code == 404
        mock_versions.assert_not_called()

    def test_token_existente_com_versoes(self):
        with patch("supabase_client.get_desafio_submission_current", return_value=_submission()), \
             patch("supabase_client.list_desafio_submission_versions", return_value=[_version()]):
            response = client.get("/api/desafios/submissoes/TOK-1/versoes")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["change_reason"] == "new"

    def test_token_existente_sem_versoes_nao_e_404(self):
        """Lista vazia para um token real é 200 com [] — só token desconhecido é 404."""
        with patch("supabase_client.get_desafio_submission_current", return_value=_submission()), \
             patch("supabase_client.list_desafio_submission_versions", return_value=[]):
            response = client.get("/api/desafios/submissoes/TOK-1/versoes")
        assert response.status_code == 200
        assert response.json() == []


# --- GET /api/desafios/sincronizacoes ---


class TestListarSincronizacoes:

    def test_lista_ordenada_e_paginada_delegada_ao_helper(self):
        with patch("supabase_client.list_desafio_sync_runs", return_value=[_sync_run()]) as mock_list:
            response = client.get("/api/desafios/sincronizacoes?limit=5&offset=2")
        assert response.status_code == 200
        mock_list.assert_called_once_with(limit=5, offset=2)

    def test_paginacao_default(self):
        with patch("supabase_client.list_desafio_sync_runs", return_value=[]) as mock_list:
            client.get("/api/desafios/sincronizacoes")
        mock_list.assert_called_once_with(limit=50, offset=0)


# --- GET /api/desafios/sincronizacoes/{run_id} ---


class TestObterSincronizacao:

    def test_execucao_existente(self):
        with patch("supabase_client.get_desafio_sync_run", return_value=_sync_run()):
            response = client.get("/api/desafios/sincronizacoes/1")
        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"

    def test_execucao_inexistente_retorna_404(self):
        with patch("supabase_client.get_desafio_sync_run", return_value=None):
            response = client.get("/api/desafios/sincronizacoes/999")
        assert response.status_code == 404


# --- Ordem das rotas: segmentos literais não são engolidos por /{desafio_id}... ---


class TestOrdenacaoDeRotasNaoColide:

    def test_sincronizacoes_nao_cai_em_obter_desafio(self):
        """GET /sincronizacoes deve bater no handler de sincronizações, não em
        obter_desafio(desafio_id="sincronizacoes") — provaria shadowing se
        get_desafio fosse chamado."""
        with patch("supabase_client.list_desafio_sync_runs", return_value=[]) as mock_sync, \
             patch("supabase_client.get_desafio") as mock_desafio:
            response = client.get("/api/desafios/sincronizacoes")
        assert response.status_code == 200
        mock_sync.assert_called_once()
        mock_desafio.assert_not_called()

    def test_submissoes_token_nao_cai_em_submissoes_do_desafio(self):
        """GET /submissoes/{token} deve bater no handler de submissão por
        token, não em listar_submissoes_do_desafio(desafio_id="submissoes")."""
        with patch(
            "supabase_client.get_desafio_submission_current", return_value=_submission()
        ) as mock_token, patch("supabase_client.get_desafio") as mock_desafio:
            response = client.get("/api/desafios/submissoes/TOK-1")
        assert response.status_code == 200
        mock_token.assert_called_once_with("TOK-1")
        mock_desafio.assert_not_called()

    def test_desafio_id_numerico_ainda_funciona(self):
        with patch("supabase_client.get_desafio", return_value=_desafio(id=42)), \
             patch("supabase_client.get_desafio_clan_totals", return_value={}):
            response = client.get("/api/desafios/42")
        assert response.status_code == 200
        assert response.json()["id"] == 42

    def test_desafio_id_nao_numerico_retorna_404_de_rota(self):
        """Um segmento não-inteiro sem rota literal correspondente não bate em
        nenhuma rota registrada (nem vira desafio_id="texto")."""
        response = client.get("/api/desafios/nao-e-um-id")
        assert response.status_code == 404


def test_get_desafio_coach_totals_agrupa_por_canonico(monkeypatch):
    import supabase_client

    class _Chain:
        def __init__(self, data):
            self._data = data

        def select(self, *_):
            return self

        def eq(self, *_):
            return self

        def execute(self):
            return SimpleNamespace(data=self._data)

    rows = [
        {"raw_name": "Ana", "points": 10},
        {"raw_name": "ana", "points": 10},
        {"raw_name": "", "points": 10},
    ]
    monkeypatch.setattr(
        supabase_client,
        "_get_client",
        lambda: SimpleNamespace(table=lambda _t: _Chain(rows)),
    )
    monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {"ana": "Ana"})
    assert supabase_client.get_desafio_coach_totals(7) == {"Ana": 20}
