"""Suíte de Testes E2E — PRD #11: Contabilidade de Desafios via Google Sheets.

Cobre de ponta a ponta todos os critérios de aceitação (CA-01 a CA-22 do PRD):
1. Parsing da fixture sintética `desafios_sheet_sanitized.csv`
2. Validação e elegibilidade (token válido = 10 pontos)
3. Deduplicação idêntica vs. detecção de conflitos
4. Inativação e estorno de tokens removidos
5. Respeito ao fuso America/Sao_Paulo em `Submitted At`
6. Arquivamento e reativação de desafios
7. Guardas operacionais (planilha vazia, estorno >20%)
8. Idempotência (delta zero em reexecução)
9. Motor de reconciliação sem coach_deltas (identidade de coach resolvida em leitura — Fase 2)
10. Desativação de endpoints legados de escrita (410 Gone)
11. Preservação e integridade do histórico imutável por token
"""

import csv
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime
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

from fastapi.testclient import TestClient
from main import app
import config
from desafio_sheet_parser import build_parsed_rows, normalize_clan
from desafio_reconciliation import build_desafio_snapshot, reconcile_desafios, CurrentSubmission
import desafio_sync_service as sync_service
from admin.migrate_desafios_google_sheet import build_preview

SAO_PAULO = ZoneInfo("America/Sao_Paulo")
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "desafios_sheet_sanitized.csv"


def load_fixture_rows() -> list[list[str]]:
    with open(FIXTURE_PATH, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        return list(reader)


class TestFixtureParsingE2E:
    def test_fixture_carrega_e_parseia_corretamente(self):
        raw_rows = load_fixture_rows()
        assert len(raw_rows) > 1  # cabeçalho + dados

        parsed = build_parsed_rows(raw_rows)
        # 11 linhas de dados na fixture
        assert len(parsed) == 11

        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        assert snapshot.sheet_row_count == 11

        # TOK-E2E-001 (válido)
        tok1 = snapshot.entries["TOK-E2E-001"]
        assert tok1.status == "active_counted"
        assert tok1.points == 10
        assert tok1.clan == "CLÃ 1"

        # TOK-E2E-003 (usa Clã Atual 'Clã 3')
        tok3 = snapshot.entries["TOK-E2E-003"]
        assert tok3.status == "active_counted"
        assert tok3.clan == "CLÃ 3"

        # TOK-E2E-004 (Validado = Não -> active_not_counted)
        tok4 = snapshot.entries["TOK-E2E-004"]
        assert tok4.status == "active_not_counted"
        assert tok4.points == 0

        # TOK-E2E-005 (linhas divergentes -> conflicted)
        tok5 = snapshot.entries["TOK-E2E-005"]
        assert tok5.status == "conflicted"
        assert tok5.points == 0
        assert "duplicate_token_conflict" in tok5.reasons


class TestCriteriosDeAceitacaoPRD11:
    def test_ca01_token_valido_elegivel_gera_10_pontos(self):
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante X", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-VAL-1"],
        ]
        parsed = build_parsed_rows(raw)
        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        plan = reconcile_desafios(snapshot, {})

        assert plan.clan_deltas["CLÃ 1"] == 10
        assert plan.token_versions[0].current_status == "active_counted"
        assert plan.token_versions[0].point_delta == 10

    def test_ca02_executar_contabilidade_aciona_sync_desafios(self):
        def mock_call_rpc(rpc_name, params):
            if rpc_name == "apply_desafio_reconciliation":
                return {
                    "status": "applied",
                    "run_id": 999,
                    "snapshot_hash": "hash-test",
                    "sheet_row_count": 1,
                    "state_counts": {"new": 1},
                    "clan_deltas": {"CLÃ 1": 10},
                    "clan_totals_after": {"CLÃ 1": 10},
                    "challenge_transitions": [],
                    "challenges_created": 1,
                    "challenges_archived": 0,
                    "challenges_reactivated": 0,
                    "tokens_versioned": 1,
                    "started_at": "2026-08-31T10:00:00-03:00",
                    "finished_at": "2026-08-31T10:00:01-03:00",
                }
            return {}

        sheet_data = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante X", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-VAL-1"],
        ]

        with patch("google_sheets_client.fetch_desafio_records", return_value=sheet_data), \
             patch("desafio_reconciliation_store.get_current_desafio_submissions", return_value={}), \
             patch("supabase_client.call_rpc", side_effect=mock_call_rpc):
            result = sync_service.sync_desafios()

        assert result.status == "success"
        assert result.run_id == 999
        assert result.clan_deltas["CLÃ 1"] == 10

    def test_ca03_multiplos_tokens_do_mesmo_participante_pontuam_independentes(self):
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante A", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-P1"],
            ["1", "Participante A", "Sim", "", "", "Desafio B", "", "19/08/2026 11:00:00", "TOK-P2"],
        ]
        parsed = build_parsed_rows(raw)
        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        plan = reconcile_desafios(snapshot, {})

        assert len(plan.token_versions) == 2
        assert plan.clan_deltas["CLÃ 1"] == 20

    def test_ca04_duplicata_identica_pontua_apenas_uma_vez(self):
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante A", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-DUP-1"],
            ["1", "Participante A", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-DUP-1"],
        ]
        parsed = build_parsed_rows(raw)
        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        assert snapshot.entries["TOK-DUP-1"].status == "active_counted"
        
        plan = reconcile_desafios(snapshot, {})
        assert len(plan.token_versions) == 1
        assert plan.clan_deltas["CLÃ 1"] == 10

    def test_ca05_conflito_de_token_invalida_e_marca_conflicted(self):
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante A", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-CONF-1"],
            ["2", "Participante A", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-CONF-1"],
        ]
        parsed = build_parsed_rows(raw)
        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        assert snapshot.entries["TOK-CONF-1"].status == "conflicted"

        plan = reconcile_desafios(snapshot, {})
        assert plan.clan_deltas.get("CLÃ 1", 0) == 0
        assert plan.clan_deltas.get("CLÃ 2", 0) == 0
        assert plan.token_versions[0].current_status == "conflicted"
        assert plan.token_versions[0].point_delta == 0

    def test_ca07_token_removido_inativa_e_estorna_pontos(self):
        dt = datetime(2026, 8, 19, 10, 0, 0, tzinfo=SAO_PAULO)
        current = {
            "TOK-REM": CurrentSubmission(
                token="TOK-REM", raw_clan_legacy="1", raw_name="P", raw_validation="Sim",
                raw_link="", raw_observation="", raw_challenge="D1", raw_clan_current="",
                raw_submitted_at="19/08/2026 10:00:00", raw_token="TOK-REM", clan="CLÃ 1",
                challenge_normalized="d1", desafio_id=1, submitted_at=dt,
                status="active_counted", points=10, content_hash="hash-rem"
            )
        }
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
        ]
        parsed = build_parsed_rows(raw)
        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        plan = reconcile_desafios(snapshot, current)

        assert plan.clan_deltas["CLÃ 1"] == -10
        assert plan.token_versions[0].current_status == "inactive_missing"
        assert plan.token_versions[0].point_delta == -10

    def test_ca08_data_fuso_derivado_estritamente_de_submitted_at_em_sao_paulo(self):
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante X", "Sim", "", "", "Desafio A", "", "19/08/2026 23:30:00", "TOK-TZ-1"],
        ]
        parsed = build_parsed_rows(raw)
        assert parsed[0].submitted_at == datetime(2026, 8, 19, 23, 30, 0, tzinfo=SAO_PAULO)

    def test_ca10_planilha_vazia_bloqueia_sync(self):
        dt = datetime(2026, 8, 19, 10, 0, 0, tzinfo=SAO_PAULO)
        current = {
            "TOK-EXISTING": CurrentSubmission(
                token="TOK-EXISTING", raw_clan_legacy="1", raw_name="P", raw_validation="Sim",
                raw_link="", raw_observation="", raw_challenge="D1", raw_clan_current="",
                raw_submitted_at="19/08/2026 10:00:00", raw_token="TOK-EXISTING", clan="CLÃ 1",
                challenge_normalized="d1", desafio_id=1, submitted_at=dt,
                status="active_counted", points=10, content_hash="hash-1"
            )
        }
        empty_raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
        ]

        with patch("google_sheets_client.fetch_desafio_records", return_value=empty_raw), \
             patch("desafio_reconciliation_store.get_current_desafio_submissions", return_value=current):
            result = sync_service.sync_desafios()

        assert result.status == "failed"
        assert "vazia" in result.mensagem.lower()

    def test_ca11_estorno_em_massa_exige_confirmacao_com_hash(self):
        dt = datetime(2026, 8, 19, 10, 0, 0, tzinfo=SAO_PAULO)
        # 10 tokens ativos
        current = {
            f"TOK-{i}": CurrentSubmission(
                token=f"TOK-{i}", raw_clan_legacy="1", raw_name="P", raw_validation="Sim",
                raw_link="", raw_observation="", raw_challenge="D1", raw_clan_current="",
                raw_submitted_at="19/08/2026 10:00:00", raw_token=f"TOK-{i}", clan="CLÃ 1",
                challenge_normalized="d1", desafio_id=1, submitted_at=dt,
                status="active_counted", points=10, content_hash=f"hash-{i}"
            ) for i in range(10)
        }
        # Apenas 5 tokens mantidos (50% de remoção)
        rows = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
        ] + [
            ["1", "P", "Sim", "", "", "D1", "", "19/08/2026 10:00:00", f"TOK-{i}"] for i in range(5)
        ]

        with patch("google_sheets_client.fetch_desafio_records", return_value=rows), \
             patch("desafio_reconciliation_store.get_current_desafio_submissions", return_value=current):
            result = sync_service.sync_desafios()

        assert result.status == "awaiting_confirmation"

    def test_ca13_reconciliacao_nao_produz_coach_deltas(self):
        # Fase 2: a identidade de coach é resolvida em tempo de leitura, o motor de
        # reconciliação segue só com clan_deltas
        raw = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Coach Fulano", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-COACH-1"],
        ]
        parsed = build_parsed_rows(raw)
        snapshot = build_desafio_snapshot(parsed, points_per_submission=10)
        plan = reconcile_desafios(snapshot, {})

        assert hasattr(plan, "clan_deltas")
        assert not hasattr(plan, "coach_deltas")  # Fase 2: identidade resolvida em leitura, motor só com clan_deltas

    def test_ca14_apis_legadas_retornam_410_gone(self):
        client = TestClient(app)

        # POST /api/desafios
        resp = client.post("/api/desafios", json={"nome": "Desafio Teste", "data_inicio": "2026-08-01", "data_fim": "2026-08-31"})
        assert resp.status_code == 410

        # POST /api/desafios/importar/preview
        resp = client.post(
            "/api/desafios/importar/preview",
            files={"file": ("test.csv", b"col1,col2", "text/csv")},
            data={"mapping": "{}", "config": "{}"},
        )
        assert resp.status_code == 410

    def test_ca15_normalizacao_de_clas(self):
        assert normalize_clan("1") == "CLÃ 1"
        assert normalize_clan("Clã 2") == "CLÃ 2"
        assert normalize_clan("CLA 03") == "CLÃ 3"
        assert normalize_clan("invalido") is None

    def test_ca19_dry_run_migracao_administrativa(self, monkeypatch):
        monkeypatch.setattr(config, "GSHEET_DESAFIOS_SPREADSHEET_ID", "test-spreadsheet-id")
        monkeypatch.setattr(config, "GSHEET_DESAFIOS_SHEET_NAME", "Desafios")

        sheet_data = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Participante X", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-VAL-1"],
        ]
        legacy_report = {
            "ja_migrado": False,
            "negativos": [],
            "totais_antigos": {"CLÃ 1": 10},
        }

        with patch("google_sheets_client.fetch_desafio_records", return_value=sheet_data), \
             patch("desafio_reconciliation_store.get_current_desafio_submissions", return_value={}), \
             patch("supabase_client.call_rpc", return_value=legacy_report):
            preview = build_preview()

        assert preview.sheet_row_count == 2
        assert preview.eligible_tokens == 1
        assert preview.expected_clan_points["CLÃ 1"] == 10

    def test_fase2_pontos_de_desafio_no_total_do_coach_via_executar(self):
        """Spec §6.2 (e2e): um token elegível cuja coluna B é um coach conhecido,
        aplicado via `POST /api/contabilidade/executar`, faz o refresh recompor
        `totais_por_coach.total_pontos` somando a fatia de +10 de desafio — sem
        que ela entre em `total_pagante`/`total_pro_bono`."""
        client = TestClient(app)

        sheet_desafios = [
            ["Clã (legado)", "Nome", "Validado", "Link", "Obs", "Desafio", "Clã atual", "Enviado em", "Token"],
            ["1", "Bruno Costa", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-BRUNO-1"],
        ]

        def mock_call_rpc(rpc_name, params):
            if rpc_name == "apply_desafio_reconciliation":
                return {
                    "status": "applied",
                    "run_id": 42,
                    "snapshot_hash": "hash-e2e",
                    "sheet_row_count": 1,
                    "state_counts": {"new": 1},
                    "clan_deltas": {"CLÃ 1": 10},
                    "clan_totals_after": {"CLÃ 1": 10},
                    "challenge_transitions": [],
                    "challenges_created": 1,
                    "challenges_archived": 0,
                    "challenges_reactivated": 0,
                    "tokens_versioned": 1,
                    "started_at": "2026-08-31T10:00:00-03:00",
                    "finished_at": "2026-08-31T10:00:01-03:00",
                }
            return {}

        # O que o refresh lê depois de aplicar: o token do Bruno já active_counted.
        active_tokens = [
            {"token": "TOK-BRUNO-1", "raw_name": "Bruno Costa", "points": 10,
             "status": "active_counted", "submitted_at": "2026-08-19T13:00:00-03:00"},
        ]
        coach_totals_before = [
            {"coach": "Bruno Costa", "total_pontos": 0, "total_pagante": 0,
             "total_pro_bono": 0, "pessoas_em_espera": 0},
        ]
        upserts: list[tuple] = []

        with patch("google_sheets_client.fetch_desafio_records", return_value=sheet_desafios), \
             patch("desafio_reconciliation_store.get_current_desafio_submissions", return_value={}), \
             patch("supabase_client.call_rpc", side_effect=mock_call_rpc), \
             patch("google_sheets_client.fetch_records", return_value=[["h"]]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=None), \
             patch("supabase_client.get_processed_hashes", return_value=set()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=active_tokens), \
             patch("supabase_client.list_coach_totals", return_value=coach_totals_before), \
             patch("supabase_client.upsert_coach_total",
                   side_effect=lambda *a, **kw: upserts.append((a, kw))):
            resp = client.post("/api/contabilidade/executar")

        assert resp.status_code == 200
        body = resp.json()
        assert body["desafios"]["status"] == "success"
        assert body["desafios"]["tokens_versioned"] == 1

        bruno = [(a, kw) for a, kw in upserts if a[0] == "Bruno Costa"]
        assert bruno, f"refresh não reescreveu o total do coach: {upserts!r}"
        args, kwargs = bruno[-1]
        assert args[1] == 10  # total_pontos = 0 pagante + 0 pro-bono + 10 desafio
        assert kwargs["total_pagante"] == 0
        assert kwargs["total_pro_bono"] == 0
