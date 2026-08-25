"""Testes do wrapper transacional de aplicação da reconciliação de desafios.

Estes testes cobrem tudo que é verificável sem um PostgreSQL real: guardas de
domínio, marshalling do payload do RPC, tradução dos erros do banco e a leitura
que fecha o ciclo (`get_current_desafio_submissions`). O comportamento
transacional propriamente dito (lock, rollback, totais negativos) é coberto por
`test_desafio_reconciliation_apply_postgres.py`.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import desafio_reconciliation_store as store
from desafio_reconciliation import (
    ChallengeTransition,
    CurrentSubmission,
    ReconciliationPlan,
    TokenVersion,
    compute_content_hash,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "009_apply_desafio_reconciliation.sql"
)

RAW_CELLS = ["1", "Ana", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-1"]


def _current_state(status: str = "active_counted", points: int = 10) -> dict:
    return {
        "status": status,
        "eligible": status == "active_counted",
        "clan": "CLÃ 1",
        "challenge_display": "Desafio A",
        "challenge_normalized": "desafio a",
        "submitted_at": "2026-08-19T10:00:00-03:00",
        "name": "Ana",
        "points": points,
        "row_numbers": [2],
        "variants": [RAW_CELLS],
    }


_DEFAULT = object()


def _token_version(
    token: str = "TOK-1",
    change_reason: str = "new",
    point_delta: int = 10,
    clan_deltas: dict | None = None,
    previous_state: dict | None = None,
    previous_status: str | None = None,
    current_state=_DEFAULT,
    current_status: str = "active_counted",
) -> TokenVersion:
    return TokenVersion(
        token=token,
        change_reason=change_reason,
        previous_status=previous_status,
        current_status=current_status,
        previous_state=previous_state,
        current_state=_current_state() if current_state is _DEFAULT else current_state,
        point_delta=point_delta,
        clan_deltas={"CLÃ 1": 10} if clan_deltas is None else clan_deltas,
        challenge_normalized="desafio a",
        challenge_display="Desafio A",
        row_numbers=(2,),
    )


def _plan(
    token_versions: tuple[TokenVersion, ...] = (),
    clan_deltas: dict | None = None,
    challenge_transitions: tuple[ChallengeTransition, ...] = (),
    snapshot_hash: str = "hash-abc",
    is_empty_snapshot: bool = False,
    mass_removal_required: bool = False,
    active_tokens_before: int = 0,
) -> ReconciliationPlan:
    return ReconciliationPlan(
        snapshot_hash=snapshot_hash,
        sheet_row_count=5,
        state_counts={"new": len(token_versions), "unchanged": 0},
        token_versions=token_versions,
        clan_deltas={} if clan_deltas is None else clan_deltas,
        challenge_transitions=challenge_transitions,
        challenges_created=sum(
            1 for t in challenge_transitions if t.transition == "create"
        ),
        challenges_archived=sum(
            1 for t in challenge_transitions if t.transition == "archive"
        ),
        challenges_reactivated=sum(
            1 for t in challenge_transitions if t.transition == "reactivate"
        ),
        active_tokens_before=active_tokens_before,
        is_empty_snapshot=is_empty_snapshot,
        mass_removal_required=mass_removal_required,
        mass_removal_ratio=0.5 if mass_removal_required else 0.0,
        mass_removal_count=3 if mass_removal_required else 0,
    )


def _rpc_success(**overrides) -> dict:
    payload = {
        "status": "applied",
        "run_id": 42,
        "snapshot_hash": "hash-abc",
        "sheet_row_count": 5,
        "state_counts": {"new": 1, "unchanged": 0},
        "clan_deltas": {"CLÃ 1": 10},
        "clan_totals_after": {"CLÃ 1": 110},
        "challenge_transitions": [
            {
                "challenge_normalized": "desafio a",
                "transition": "create",
                "desafio_id": 7,
            }
        ],
        "challenges_created": 1,
        "challenges_archived": 0,
        "challenges_reactivated": 0,
        "tokens_versioned": 1,
        "started_at": "2026-08-19T13:00:00+00:00",
        "finished_at": "2026-08-19T13:00:01+00:00",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Guardas de domínio (nada é aplicado)
# ---------------------------------------------------------------------------


class TestGuards:
    def test_confirmacao_com_hash_divergente_nao_chama_o_rpc(self):
        plan = _plan((_token_version(),), clan_deltas={"CLÃ 1": 10})
        with patch("supabase_client.call_rpc") as mock_rpc:
            with pytest.raises(store.SnapshotConfirmationMismatchError):
                store.apply_reconciliation(
                    plan, confirmed_snapshot_hash="hash-obsoleto"
                )
        mock_rpc.assert_not_called()

    def test_confirmacao_com_hash_igual_aplica(self):
        plan = _plan(
            (_token_version(),),
            clan_deltas={"CLÃ 1": 10},
            mass_removal_required=True,
            active_tokens_before=6,
        )
        with patch("supabase_client.call_rpc", return_value=_rpc_success()) as mock_rpc:
            result = store.apply_reconciliation(
                plan, confirmed_snapshot_hash="hash-abc"
            )
        assert result.status == store.STATUS_APPLIED
        payload = mock_rpc.call_args.args[1]["p_payload"]
        assert payload["mass_removal_confirmed"] is True
        assert payload["mass_removal_required"] is True

    def test_planilha_vazia_com_tokens_ativos_e_bloqueada(self):
        plan = _plan(
            (_token_version(change_reason="missing"),),
            is_empty_snapshot=True,
            active_tokens_before=4,
        )
        with patch("supabase_client.call_rpc") as mock_rpc:
            with pytest.raises(store.EmptySnapshotBlockedError):
                store.apply_reconciliation(plan)
        mock_rpc.assert_not_called()

    def test_remocao_em_massa_sem_confirmacao_e_bloqueada(self):
        plan = _plan(
            (_token_version(change_reason="missing"),),
            mass_removal_required=True,
            active_tokens_before=6,
        )
        with patch("supabase_client.call_rpc") as mock_rpc:
            with pytest.raises(store.MassRemovalConfirmationRequiredError):
                store.apply_reconciliation(plan)
        mock_rpc.assert_not_called()


# ---------------------------------------------------------------------------
# Marshalling do payload
# ---------------------------------------------------------------------------


class TestPayload:
    def _payload_for(self, plan, **kwargs) -> dict:
        with patch("supabase_client.call_rpc", return_value=_rpc_success()) as mock_rpc:
            store.apply_reconciliation(plan, **kwargs)
        assert mock_rpc.call_args.args[0] == store.RPC_APPLY_DESAFIO_RECONCILIATION
        return mock_rpc.call_args.args[1]["p_payload"]

    def test_payload_carrega_execucao_e_contagens(self):
        plan = _plan((_token_version(),), clan_deltas={"CLÃ 1": 10})
        payload = self._payload_for(plan)
        assert payload["snapshot_hash"] == "hash-abc"
        assert payload["sheet_row_count"] == 5
        assert payload["state_counts"] == {"new": 1, "unchanged": 0}
        assert payload["clan_deltas"] == {"CLÃ 1": 10}
        assert payload["mass_removal_confirmed"] is False

    def test_payload_usa_pontos_por_submissao_do_config_por_padrao(self):
        import config

        payload = self._payload_for(_plan())
        assert payload["points_per_submission"] == config.POINTS_PER_DESAFIO_SUBMISSION

    def test_payload_aceita_pontos_por_submissao_explicito(self):
        payload = self._payload_for(_plan(), points_per_submission=25)
        assert payload["points_per_submission"] == 25

    def test_payload_de_token_inclui_content_hash_reproduzivel(self):
        version = _token_version()
        payload = self._payload_for(_plan((version,), clan_deltas={"CLÃ 1": 10}))
        token_payload = payload["token_versions"][0]
        assert token_payload["token"] == "TOK-1"
        assert token_payload["change_reason"] == "new"
        assert token_payload["current_status"] == "active_counted"
        assert token_payload["previous_state"] is None
        assert token_payload["point_delta"] == 10
        assert token_payload["clan_deltas"] == {"CLÃ 1": 10}
        assert token_payload["row_numbers"] == [2]
        assert token_payload["content_hash"] == compute_content_hash(
            "TOK-1", "active_counted", [RAW_CELLS]
        )

    def test_payload_de_token_ausente_nao_tem_estado_atual_nem_hash(self):
        version = _token_version(
            change_reason="missing",
            current_status="inactive_missing",
            current_state=None,
            point_delta=-10,
            clan_deltas={"CLÃ 1": -10},
            previous_status="active_counted",
            previous_state={"status": "active_counted", "clan": "CLÃ 1", "points": 10},
        )
        payload = self._payload_for(_plan((version,), clan_deltas={"CLÃ 1": -10}))
        token_payload = payload["token_versions"][0]
        assert token_payload["current_state"] is None
        assert token_payload["content_hash"] is None
        assert token_payload["previous_state"]["status"] == "active_counted"

    def test_payload_carrega_transicoes_de_desafio(self):
        transitions = (
            ChallengeTransition("desafio a", "Desafio A", "create"),
            ChallengeTransition("desafio b", None, "archive"),
        )
        payload = self._payload_for(_plan(challenge_transitions=transitions))
        assert payload["challenge_transitions"] == [
            {
                "challenge_normalized": "desafio a",
                "challenge_display": "Desafio A",
                "transition": "create",
            },
            {
                "challenge_normalized": "desafio b",
                "challenge_display": None,
                "transition": "archive",
            },
        ]
        assert payload["challenges_created"] == 1
        assert payload["challenges_archived"] == 1

    def test_plano_vazio_ainda_registra_execucao(self):
        payload = self._payload_for(_plan())
        assert payload["token_versions"] == []
        assert payload["clan_deltas"] == {}
        assert payload["challenge_transitions"] == []

    def test_payload_e_serializavel_em_json(self):
        import json

        plan = _plan(
            (_token_version(),),
            clan_deltas={"CLÃ 1": 10},
            challenge_transitions=(ChallengeTransition("desafio a", "Desafio A", "create"),),
        )
        payload = self._payload_for(plan)
        assert json.loads(json.dumps(payload)) == payload


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


class TestAppliedSyncResult:
    def test_resultado_aplicado(self):
        plan = _plan((_token_version(),), clan_deltas={"CLÃ 1": 10})
        with patch("supabase_client.call_rpc", return_value=_rpc_success()):
            result = store.apply_reconciliation(plan)

        assert result.status == store.STATUS_APPLIED
        assert result.already_running is False
        assert result.run_id == 42
        assert result.snapshot_hash == "hash-abc"
        assert result.sheet_row_count == 5
        assert result.state_counts == {"new": 1, "unchanged": 0}
        assert result.clan_deltas == {"CLÃ 1": 10}
        assert result.clan_totals_after == {"CLÃ 1": 110}
        assert result.tokens_versioned == 1
        assert result.challenges_created == 1
        assert result.challenge_transitions == (
            store.AppliedChallengeTransition("desafio a", "create", 7),
        )
        assert result.started_at == datetime(
            2026, 8, 19, 13, 0, 0, tzinfo=ZoneInfo("UTC")
        )
        assert result.finished_at == datetime(
            2026, 8, 19, 13, 0, 1, tzinfo=ZoneInfo("UTC")
        )

    def test_resultado_already_running_nao_aplica_nada(self):
        plan = _plan((_token_version(),), clan_deltas={"CLÃ 1": 10})
        rpc_data = {
            "status": "already_running",
            "run_id": None,
            "snapshot_hash": "hash-abc",
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
        with patch("supabase_client.call_rpc", return_value=rpc_data):
            result = store.apply_reconciliation(plan)

        assert result.status == store.STATUS_ALREADY_RUNNING
        assert result.already_running is True
        assert result.run_id is None
        assert result.clan_deltas == {}
        assert result.clan_totals_after == {}
        assert result.tokens_versioned == 0

    def test_lista_de_retorno_do_postgrest_e_desembrulhada(self):
        # PostgREST pode devolver o jsonb dentro de uma lista de uma posição.
        plan = _plan()
        with patch("supabase_client.call_rpc", return_value=[_rpc_success()]):
            result = store.apply_reconciliation(plan)
        assert result.run_id == 42

    def test_resposta_vazia_do_rpc_e_erro_de_dominio(self):
        with patch("supabase_client.call_rpc", return_value=None):
            with pytest.raises(store.DesafioReconciliationError):
                store.apply_reconciliation(_plan())


# ---------------------------------------------------------------------------
# Tradução de erros do banco
# ---------------------------------------------------------------------------


class TestDatabaseErrors:
    def test_total_negativo_vira_erro_de_dominio(self):
        error = RuntimeError(
            "desafio_reconciliation_negative_clan_total: CLÃ 1 ficaria com -5 pontos"
        )
        with patch("supabase_client.call_rpc", side_effect=error):
            with pytest.raises(store.NegativeClanTotalError) as excinfo:
                store.apply_reconciliation(_plan(clan_deltas={"CLÃ 1": -50}))
        assert "CLÃ 1" in str(excinfo.value)

    def test_plano_obsoleto_vira_erro_de_dominio(self):
        error = RuntimeError(
            "desafio_reconciliation_stale_plan: token TOK-1 mudou desde a leitura"
        )
        with patch("supabase_client.call_rpc", side_effect=error):
            with pytest.raises(store.StalePlanError):
                store.apply_reconciliation(_plan((_token_version(),)))

    def test_erro_desconhecido_do_banco_propaga_sem_mascarar(self):
        error = RuntimeError("connection refused")
        with patch("supabase_client.call_rpc", side_effect=error):
            with pytest.raises(RuntimeError, match="connection refused"):
                store.apply_reconciliation(_plan())


# ---------------------------------------------------------------------------
# Leitura que fecha o ciclo
# ---------------------------------------------------------------------------


class TestGetCurrentDesafioSubmissions:
    def test_mapeia_linhas_para_current_submission(self):
        rows = [
            {
                "token": "TOK-1",
                "raw_clan_legacy": "1",
                "raw_name": "Ana",
                "raw_validation": "Sim",
                "raw_link": "",
                "raw_observation": "",
                "raw_challenge": "Desafio A",
                "raw_clan_current": "",
                "raw_submitted_at": "19/08/2026 10:00:00",
                "raw_token": "TOK-1",
                "clan": "CLÃ 1",
                "challenge_normalized": "desafio a",
                "desafio_id": 7,
                "submitted_at": "2026-08-19T10:00:00-03:00",
                "status": "active_counted",
                "points": 10,
                "content_hash": "hash-token-1",
            }
        ]
        with patch(
            "supabase_client.fetch_all_desafio_submissions_current", return_value=rows
        ):
            current = store.get_current_desafio_submissions()

        assert set(current) == {"TOK-1"}
        submission = current["TOK-1"]
        assert isinstance(submission, CurrentSubmission)
        assert submission.clan == "CLÃ 1"
        assert submission.desafio_id == 7
        assert submission.status == "active_counted"
        assert submission.points == 10
        assert submission.content_hash == "hash-token-1"
        assert submission.submitted_at == datetime(
            2026, 8, 19, 10, 0, 0, tzinfo=SAO_PAULO
        )

    def test_aceita_sufixo_z_e_ausencia_de_submitted_at(self):
        rows = [
            {
                "token": "TOK-Z",
                "raw_cells": [],
                "clan": None,
                "challenge_normalized": None,
                "desafio_id": None,
                "submitted_at": "2026-08-19T13:00:00Z",
                "status": "invalid",
                "points": 0,
                "content_hash": "hash-z",
            },
            {
                "token": "TOK-NULL",
                "clan": None,
                "challenge_normalized": None,
                "desafio_id": None,
                "submitted_at": None,
                "status": "inactive_missing",
                "points": 0,
                "content_hash": "hash-null",
            },
        ]
        with patch(
            "supabase_client.fetch_all_desafio_submissions_current", return_value=rows
        ):
            current = store.get_current_desafio_submissions()

        assert current["TOK-Z"].submitted_at == datetime(
            2026, 8, 19, 13, 0, 0, tzinfo=ZoneInfo("UTC")
        )
        assert current["TOK-NULL"].submitted_at is None
        assert current["TOK-NULL"].raw_name is None

    def test_banco_vazio_retorna_dicionario_vazio(self):
        with patch(
            "supabase_client.fetch_all_desafio_submissions_current", return_value=[]
        ):
            assert store.get_current_desafio_submissions() == {}


# ---------------------------------------------------------------------------
# Contrato da migration 009
#
# Verificações estáticas do SQL: pegam regressões sem depender de um Postgres
# ligado. O comportamento em si é validado em
# `test_desafio_reconciliation_apply_postgres.py`.
# ---------------------------------------------------------------------------


class TestMigrationSqlContract:
    def _sql(self) -> str:
        return re.sub(
            r"\s+", " ", MIGRATION_PATH.read_text(encoding="utf-8")
        ).lower()

    def test_migration_e_sql_e_plpgsql_valido(self):
        """Pega erro de sintaxe que só apareceria no deploy da migration."""
        parser = pytest.importorskip("pglast.parser")
        raw = MIGRATION_PATH.read_text(encoding="utf-8")

        assert len(parser.parse_sql(raw)) >= 1
        parsed_bodies = json.loads(parser.parse_plpgsql_json(raw))
        assert parsed_bodies, "corpo plpgsql da função não foi reconhecido"

    def test_lock_e_nao_bloqueante(self):
        """Pega troca por um lock bloqueante, que faria a 2ª chamada travar."""
        sql = self._sql()
        assert "pg_try_advisory_xact_lock" in sql
        assert "pg_advisory_lock(" not in sql
        assert "pg_advisory_xact_lock(" not in sql
        assert "'already_running'" in sql

    def test_total_negativo_levanta_excecao_em_vez_de_truncar(self):
        """Pega a volta do clamp `max(0, ...)` do helper legado (decisão 32.6)."""
        sql = self._sql()
        assert "desafio_reconciliation_negative_clan_total" in sql
        assert re.search(r"if v_new_total < 0 then\s+raise exception", sql)
        assert "greatest(" not in sql
        assert "max(0" not in sql

    def test_arquivar_nunca_apaga_historia(self):
        """Pega uma migration que resolvesse remoção com DELETE/DROP/TRUNCATE."""
        sql = self._sql()
        assert "drop table" not in sql
        assert "truncate" not in sql
        assert "delete from" not in sql
        assert "status = 'arquivado'" in sql

    def test_execucao_e_versao_ficam_na_mesma_funcao(self):
        """Pega escrita de auditoria movida para fora da transação única."""
        sql = self._sql()
        assert "insert into desafio_sync_runs" in sql
        assert "insert into desafio_submissions_current" in sql
        assert "insert into desafio_submission_versions" in sql
        assert "insert into pontos_ultimate_totais_por_clan" in sql
        assert sql.count("create or replace function") == 1

    def test_wrapper_usa_exatamente_o_rpc_da_migration(self):
        """Pega divergência entre o nome chamado no Python e o criado no SQL."""
        assert (
            f"create or replace function {store.RPC_APPLY_DESAFIO_RECONCILIATION}("
            in self._sql()
        )
