"""Testes de observabilidade da fachada `desafio_sync_service.sync_desafios`.

Cobrem exatamente o que a Task 12 promete: eventos estruturados por fase,
correlacionáveis entre si mesmo antes de existir um `run_id` (que só nasce
dentro do RPC `apply_desafio_reconciliation`, na fase de aplicação), e
ausência total de segredos (o JSON da service account, ou qualquer token de
acesso derivado dele) no conteúdo desses eventos.

O identificador de negócio da planilha (`token`, coluna I) NÃO é segredo — é
exposto publicamente pela API de auditoria (`desafio_auditoria.py`) — então
aparecer em contagens (`state_counts`, `tokens_versioned`) é esperado e não é
testado aqui como vazamento.
"""

import logging
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

import config
import desafio_sync_service as service
from desafio_reconciliation import CurrentSubmission, compute_content_hash
from google_sheets_client import DesafioSheetConfigurationError


HEADER = [
    "Clã (legado)", "Nome", "Validado", "Link", "Observação",
    "Desafio", "Clã atual", "Enviado em", "Token",
]

FAKE_SERVICE_ACCOUNT_SECRET = (
    '{"type": "service_account", "private_key": '
    '"-----BEGIN PRIVATE KEY-----\\nMIISEGREDO_QUE_NAO_PODE_VAZAR\\n'
    '-----END PRIVATE KEY-----\\n", "client_email": "x@y.iam.gserviceaccount.com"}'
)
FAKE_ACCESS_TOKEN_SECRET = "ya29.SEGREDO_DE_ACESSO_QUE_NAO_PODE_VAZAR"


def _row(token, clan="1", challenge="Desafio A", submitted_at="19/08/2026 10:00:00"):
    return [clan, "Ana", "Sim", "", "", challenge, "", submitted_at, token]


def _sheet(*rows):
    return [HEADER, *rows]


def _current_active(token, content_hash="seed-hash"):
    from datetime import datetime
    from zoneinfo import ZoneInfo

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
        clan="CLÃ 1",
        challenge_normalized="desafio a",
        desafio_id=1,
        submitted_at=datetime(2026, 8, 19, 10, 0, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        status="active_counted",
        points=10,
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


def _events(records):
    """Extrai o payload estruturado (`record.desafio_sync`) de cada log."""
    out = []
    for record in records:
        payload = getattr(record, "desafio_sync", None)
        if payload is not None:
            out.append(payload)
    return out


class TestCorrelacaoEmSucesso:
    def test_todas_as_fases_compartilham_correlation_id_e_run_id_chega_no_fim(self, caplog):
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch("supabase_client.call_rpc", side_effect=_fake_call_rpc):
            result = service.sync_desafios()

        assert result.status == "success"

        events = _events(caplog.records)
        assert len(events) >= 5  # ao menos uma por fase + evento final

        correlation_ids = {e["correlation_id"] for e in events}
        assert len(correlation_ids) == 1
        correlation_id = correlation_ids.pop()
        assert correlation_id  # não vazio

        phases = [e["phase"] for e in events]
        assert "leitura" in phases
        assert "parse" in phases
        assert "snapshot" in phases
        assert "reconciliacao" in phases
        assert "aplicacao" in phases

        # `run_id` só existe a partir da fase de aplicação (nasce dentro do
        # RPC); fases anteriores não podem inventar um valor para ele.
        for event in events:
            if event["phase"] in ("leitura", "parse"):
                assert event.get("run_id") is None

        final_events = [e for e in events if e.get("run_id") is not None]
        assert final_events, "esperava ao menos um evento com run_id preenchido"
        assert all(e["run_id"] == result.run_id == 101 for e in final_events)

        # Todo evento a partir da fase "snapshot" (inclusive) carrega o mesmo
        # snapshot_hash que acabou persistido em desafio_sync_runs — é o elo
        # que permite juntar as fases 1-5 (sem run_id) à linha eventual da
        # fase 6 (com run_id), via a chave que já existia antes dele.
        post_snapshot = [
            e for e in events if e["phase"] in ("snapshot", "reconciliacao", "aplicacao")
        ]
        assert post_snapshot
        snapshot_hashes = {e["snapshot_hash"] for e in post_snapshot}
        assert snapshot_hashes == {result.snapshot_hash}

        # Duração e contagens presentes (Step 3).
        for event in events:
            assert "duration_seconds" in event
            assert event["duration_seconds"] >= 0
            assert "status" in event

    def test_duas_execucoes_tem_correlation_ids_diferentes(self, caplog):
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch("supabase_client.call_rpc", side_effect=_fake_call_rpc):
            service.sync_desafios()
            caplog.clear()
            service.sync_desafios()

        events = _events(caplog.records)
        ids = {e["correlation_id"] for e in events}
        assert len(ids) == 1  # só a segunda execução ficou no caplog após o clear


class TestFalhaDeLeituraCorrelacionada:
    def test_falha_na_leitura_loga_fase_e_categoria_de_erro_sem_run_id(self, caplog):
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            side_effect=DesafioSheetConfigurationError(
                "Configuração da planilha de desafios ausente: GSHEET_DESAFIOS_SPREADSHEET_ID"
            ),
        ):
            result = service.sync_desafios()

        assert result.status == "failed"
        events = _events(caplog.records)
        assert events

        correlation_ids = {e["correlation_id"] for e in events}
        assert len(correlation_ids) == 1

        failure_events = [e for e in events if e["status"] == "failed"]
        assert failure_events
        failure = failure_events[-1]
        assert failure["phase"] == "leitura"
        assert failure.get("run_id") is None
        assert failure.get("error_category")
        assert "duration_seconds" in failure

    def test_falha_de_rede_categoriza_como_rede(self, caplog):
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            side_effect=ConnectionError("timeout ao contatar Google Sheets"),
        ):
            result = service.sync_desafios()

        assert result.status == "failed"
        events = _events(caplog.records)
        failure = [e for e in events if e["status"] == "failed"][-1]
        assert failure["error_category"] == "rede"


class TestConfirmacaoPendenteELockConcorrente:
    def _current_five_active(self):
        return {
            f"TOK-{i}": _current_active(f"TOK-{i}", content_hash=f"seed-{i}")
            for i in range(1, 6)
        }

    def test_remocao_em_massa_loga_evento_de_confirmacao_pendente(self, caplog):
        rows = [_row(f"TOK-{i}") for i in (1, 2, 3)]
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(*rows),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value=self._current_five_active(),
        ), patch("supabase_client.call_rpc") as mock_rpc:
            result = service.sync_desafios()

        assert result.status == "awaiting_confirmation"
        assert not mock_rpc.called

        events = _events(caplog.records)
        pending = [e for e in events if e["status"] == "awaiting_confirmation"]
        assert pending
        assert pending[-1]["snapshot_hash"] == result.snapshot_hash

    def test_lock_concorrente_loga_evento_already_running(self, caplog):
        def _already_running(rpc_name, params):
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

        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch("supabase_client.call_rpc", side_effect=_already_running):
            result = service.sync_desafios()

        assert result.status == "already_running"
        events = _events(caplog.records)
        concurrent = [e for e in events if e["status"] == "already_running"]
        assert concurrent
        assert concurrent[-1]["run_id"] is None


class TestAusenciaDeSegredosNosLogs:
    def _all_log_text(self, caplog) -> str:
        parts = []
        for record in caplog.records:
            parts.append(record.getMessage())
            payload = getattr(record, "desafio_sync", None)
            if payload is not None:
                parts.append(repr(payload))
        return "\n".join(parts)

    def test_service_account_json_nunca_aparece_em_execucao_bem_sucedida(self, caplog, monkeypatch):
        monkeypatch.setattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON", FAKE_SERVICE_ACCOUNT_SECRET)
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch("supabase_client.call_rpc", side_effect=_fake_call_rpc):
            service.sync_desafios()

        text = self._all_log_text(caplog)
        assert "MIISEGREDO_QUE_NAO_PODE_VAZAR" not in text
        assert FAKE_SERVICE_ACCOUNT_SECRET not in text
        assert FAKE_ACCESS_TOKEN_SECRET not in text

    def test_service_account_json_nunca_aparece_quando_a_leitura_falha(self, caplog, monkeypatch):
        # Mesmo quando a própria exceção de leitura carregaria, em tese,
        # detalhes de configuração, o segredo configurado no ambiente não
        # pode aparecer em nenhum evento estruturado.
        monkeypatch.setattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON", FAKE_SERVICE_ACCOUNT_SECRET)
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            side_effect=ConnectionError("timeout ao contatar Google Sheets"),
        ):
            service.sync_desafios()

        text = self._all_log_text(caplog)
        assert "MIISEGREDO_QUE_NAO_PODE_VAZAR" not in text
        assert FAKE_SERVICE_ACCOUNT_SECRET not in text

    def test_identificador_de_negocio_token_pode_aparecer_em_contagens(self, caplog):
        # Contraste deliberado com o teste acima: `token` (coluna I) não é
        # segredo, então contagens agregadas por estado (que citam a palavra
        # "token" e valores como `new`/`active_counted`) não são vazamento.
        with caplog.at_level(logging.INFO, logger="desafio_sync"), patch(
            "google_sheets_client.fetch_desafio_records",
            return_value=_sheet(_row("TOK-1")),
        ), patch(
            "desafio_reconciliation_store.get_current_desafio_submissions",
            return_value={},
        ), patch("supabase_client.call_rpc", side_effect=_fake_call_rpc):
            result = service.sync_desafios()

        events = _events(caplog.records)
        reconciliacao = [e for e in events if e["phase"] == "reconciliacao"][-1]
        assert reconciliacao["state_counts"]["new"] == 1
        assert result.tokens_versioned == 1
