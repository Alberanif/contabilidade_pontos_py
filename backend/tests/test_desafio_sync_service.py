"""Testes da fachada `desafio_sync_service.sync_desafios`.

A fachada orquestra: leitura da planilha -> parse -> snapshot -> reconciliação
-> aplicação (ou retorno de confirmação pendente). Estes testes mockam apenas
as bordas de I/O real (`google_sheets_client.fetch_desafio_records` e
`supabase_client.call_rpc`) e deixam as regras das Tasks 2-4 (parser,
reconciliação, guardas de `apply_reconciliation`) rodarem de verdade, para não
duplicar cobertura já feita nos módulos de origem nem testar mocks contra
mocks.
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

from datetime import datetime
from zoneinfo import ZoneInfo

import desafio_sync_service as service
from desafio_reconciliation import CurrentSubmission, compute_content_hash
from google_sheets_client import DesafioSheetConfigurationError

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


HEADER = [
    "Clã (legado)", "Nome", "Validado", "Link", "Observação",
    "Desafio", "Clã atual", "Enviado em", "Token",
]


def _row(
    token,
    clan="1",
    name="Ana",
    validation="Sim",
    challenge="Desafio A",
    submitted_at="19/08/2026 10:00:00",
):
    return [clan, name, validation, "", "", challenge, "", submitted_at, token]


def _sheet(*rows):
    return [HEADER, *rows]


def _current_active(
    token,
    clan="CLÃ 1",
    challenge="desafio a",
    points=10,
    content_hash="seed-hash",
    submitted_at=datetime(2026, 8, 19, 10, 0, 0, tzinfo=SAO_PAULO),
):
    return CurrentSubmission(
        token=token,
        raw_clan_legacy="1",
        raw_name="Ana",
        raw_validation="Sim",
        raw_link="",
        raw_observation="",
        raw_challenge="Desafio A",
        raw_clan_current="",
        raw_submitted_at="19/08/2026 10:00:00",
        raw_token=token,
        clan=clan,
        challenge_normalized=challenge,
        desafio_id=1,
        submitted_at=submitted_at,
        status="active_counted",
        points=points,
        content_hash=content_hash,
    )


def _fake_call_rpc(rpc_name, params):
    payload = params["p_payload"]
    return {
        "status": "applied",
        "run_id": 101,
        "snapshot_hash": payload["snapshot_hash"],
        "sheet_row_count": payload["sheet_row_count"],
        "state_counts": payload["state_counts"],
        "clan_deltas": payload["clan_deltas"],
        "clan_totals_after": dict(payload["clan_deltas"]),
        "challenge_transitions": payload["challenge_transitions"],
        "challenges_created": payload["challenges_created"],
        "challenges_archived": payload["challenges_archived"],
        "challenges_reactivated": payload["challenges_reactivated"],
        "tokens_versioned": len(payload["token_versions"]),
        "started_at": "2026-08-25T10:00:00-03:00",
        "finished_at": "2026-08-25T10:00:01-03:00",
    }


def _fake_call_rpc_already_running(rpc_name, params):
    return {
        "status": "already_running",
        "run_id": None,
        "snapshot_hash": params["p_payload"]["snapshot_hash"],
        "sheet_row_count": 0,
        "state_counts": {},
        "clan_deltas": {},
        "clan_totals_after": {},
        "challenge_transitions": [],
        "challenges_created": 0,
        "challenges_archived": 0,
        "challenges_reactivated": 0,
        "tokens_versioned": 0,
        "started_at": None,
        "finished_at": None,
    }


class TestSucesso:
    def test_novo_token_e_aplicado_com_sucesso(self):
        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch(
            "supabase_client.call_rpc", side_effect=_fake_call_rpc
        ) as mock_rpc:
            result = service.sync_desafios()

        assert result.status == "success"
        assert result.run_id == 101
        assert result.sheet_row_count == 1
        assert result.tokens_versioned == 1
        assert result.state_counts["new"] == 1
        assert mock_rpc.called

    def test_delta_zero_quando_nada_mudou(self):
        content_hash = compute_content_hash(
            "TOK-1", "active_counted", [list(_row("TOK-1"))]
        )
        current = {
            "TOK-1": _current_active("TOK-1", content_hash=content_hash),
        }
        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch(
            "supabase_client.call_rpc", side_effect=_fake_call_rpc
        ):
            result = service.sync_desafios()

        assert result.status == "success"
        assert result.tokens_versioned == 0
        assert result.clan_deltas == {}


class TestConfiguracaoAusente:
    def test_configuracao_ausente_nao_propaga_e_marca_falha(self):
        with patch(
            "google_sheets_client.fetch_desafio_records",
            side_effect=DesafioSheetConfigurationError(
                "Configuração da planilha de desafios ausente: GSHEET_DESAFIOS_SPREADSHEET_ID"
            ),
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios()

        assert result.status == "failed"
        assert "GSHEET_DESAFIOS_SPREADSHEET_ID" in result.mensagem
        assert not mock_rpc.called


class TestGoogleSheetsIndisponivel:
    def test_erro_de_rede_na_planilha_marca_falha_sem_propagar(self):
        with patch(
            "google_sheets_client.fetch_desafio_records",
            side_effect=ConnectionError("timeout ao contatar Google Sheets"),
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios()

        assert result.status == "failed"
        assert "timeout" in result.mensagem
        assert not mock_rpc.called


class TestPlanilhaVaziaComTokensAtivos:
    def test_planilha_vazia_com_tokens_ativos_e_bloqueada(self):
        current = {"TOK-1": _current_active("TOK-1")}
        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=[HEADER],
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios()

        assert result.status == "failed"
        assert not mock_rpc.called


class TestReducaoEmMassa:
    def _current_five_active(self):
        return {
            f"TOK-{i}": _current_active(f"TOK-{i}", content_hash=f"seed-{i}")
            for i in range(1, 6)
        }

    def test_reducao_acima_de_20_por_cento_aguarda_confirmacao(self):
        # Só 3 dos 5 tokens ativos permanecem na planilha -> 2 somem (40%).
        rows = [_row(f"TOK-{i}") for i in (1, 2, 3)]
        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=self._current_five_active(),
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios()

        assert result.status == "awaiting_confirmation"
        assert result.mass_removal_required is True
        assert result.mass_removal_count == 2
        assert result.mass_removal_ratio == 0.4
        assert result.snapshot_hash
        assert not mock_rpc.called

    def test_confirmacao_valida_vinculada_ao_hash_aplica(self):
        rows = [_row(f"TOK-{i}") for i in (1, 2, 3)]
        current = self._current_five_active()

        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch("supabase_client.call_rpc") as mock_rpc:
            preview = service.sync_desafios()

        assert preview.status == "awaiting_confirmation"

        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch(
            "supabase_client.call_rpc", side_effect=_fake_call_rpc
        ) as mock_rpc2:
            confirmed = service.sync_desafios(
                confirm_snapshot_hash=preview.snapshot_hash,
                confirm_mass_removal=True,
            )

        assert confirmed.status == "success"
        assert mock_rpc2.called

    def test_confirmacao_sem_aceitar_remocao_continua_pedindo(self):
        # Hash correto (vindo de uma prévia real), mas sem aceitar a remoção
        # em massa: apply_reconciliation ainda deve recusar e a fachada deve
        # continuar pedindo confirmação, não aplicar nem "falhar" de vez.
        rows = [_row(f"TOK-{i}") for i in (1, 2, 3)]
        current = self._current_five_active()

        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch("supabase_client.call_rpc") as mock_rpc:
            preview = service.sync_desafios()

        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios(confirm_snapshot_hash=preview.snapshot_hash)

        assert result.status == "awaiting_confirmation"
        assert not mock_rpc.called


class TestSnapshotAlteradoEntrePreviaEConfirmacao:
    def test_hash_confirmado_nao_bate_com_snapshot_atual_falha(self):
        current = {
            f"TOK-{i}": _current_active(f"TOK-{i}", content_hash=f"seed-{i}")
            for i in range(1, 6)
        }
        rows = [_row(f"TOK-{i}") for i in (1, 2, 3)]

        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=current,
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios(
                confirm_snapshot_hash="hash-de-uma-previa-antiga-que-nao-bate",
                confirm_mass_removal=True,
            )

        assert result.status == "failed"
        assert not mock_rpc.called


class TestJaEmAndamento:
    def test_lock_ja_adquirido_reporta_already_running(self):
        with patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch(
            "supabase_client.call_rpc", side_effect=_fake_call_rpc_already_running
        ):
            result = service.sync_desafios()

        assert result.status == "already_running"
        assert result.run_id is None
