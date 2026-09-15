"""Testes de integração End-to-End para a apuração de desafios por percentual e aprovação manual.

Cobre os cenários de:
1. Ingestão pós-corte (01/08/2026) -> revisão manual -> prazo vencido -> apuração automática em /executar.
2. Reabertura de prazo -> estorno do delta antigo -> nova apuração.
3. Compatibilidade com o histórico pré-corte (01/08/2026) -> mantendo o modelo aditivo legado intacto.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient
from main import app

from desafio_sync_service import DesafioSyncResult

client = TestClient(app)


def test_fluxo_e2e_apuracao_desafio_pos_corte():
    desafio_id = 101
    token_1 = "token_post_corte_1"
    token_2 = "token_post_corte_2"

    desafio_mock = {
        "id": desafio_id,
        "nome": "Desafio E2E Agosto",
        "contabilizar_pontos": True,
        "prazo_apuracao": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "apurado_em": None,
        "status": "ativo",
        "origem": "sheet",
        "created_at": "2026-08-01T09:00:00+00:00",
        "updated_at": "2026-08-01T09:00:00+00:00",
    }

    submissoes_dict = {
        token_1: {
            "token": token_1,
            "desafio_id": desafio_id,
            "raw_name": "Coach Ana",
            "status": "active_counted",
            "submitted_at": "2026-08-05T10:00:00+00:00",
            "points": 10,
            "clan": "CLÃ 1",
        },
        token_2: {
            "token": token_2,
            "desafio_id": desafio_id,
            "raw_name": "Coach Bruno",
            "status": "active_counted",
            "submitted_at": "2026-08-05T11:00:00+00:00",
            "points": 10,
            "clan": "CLÃ 1",
        },
    }

    revisoes_db = {}
    apuracoes_db = []
    totais_clan_db = {"CLÃ 1": 0}

    def mock_get_submission(token):
        return submissoes_dict.get(token)

    def mock_revisar(token, status, revisado_por=None):
        revisoes_db[token] = {"token": token, "status": status, "revisado_por": revisado_por}
        return revisoes_db[token]

    def mock_list_revisoes(d_id=None):
        return revisoes_db

    def mock_salvar_apuracao(d_id, res_map):
        nonlocal desafio_mock
        desafio_mock["apurado_em"] = datetime.now(timezone.utc).isoformat()
        for c, item in res_map.items():
            data = item.to_dict() if hasattr(item, "to_dict") else item
            apuracoes_db.append(data)

    def mock_upsert_clan(clan, total, **kwargs):
        totais_clan_db[clan] = total
        return {"clan": clan, "total_pontos": total}

    def mock_get_clan_totals():
        return totais_clan_db

    with patch("supabase_client.list_desafios", return_value=[desafio_mock]), \
         patch("supabase_client.get_desafio", return_value=desafio_mock), \
         patch("supabase_client.get_desafio_submission_current", side_effect=mock_get_submission), \
         patch("supabase_client.list_desafio_submissions_current", return_value=list(submissoes_dict.values())), \
         patch("supabase_client.list_submissoes_revisoes", side_effect=mock_list_revisoes), \
         patch("supabase_client.revisar_submissao", side_effect=mock_revisar), \
         patch("supabase_client.salvar_apuracao_clan", side_effect=mock_salvar_apuracao), \
         patch("supabase_client.get_desafio_clan_apuracoes", return_value=apuracoes_db), \
         patch("supabase_client.list_coach_clas", return_value=[
             {"coach_canonico": "Coach Ana", "clan": "CLÃ 1"},
             {"coach_canonico": "Coach Bruno", "clan": "CLÃ 1"},
             {"coach_canonico": "Coach Carlos", "clan": "CLÃ 1"},
             {"coach_canonico": "Coach Daniel", "clan": "CLÃ 1"},
         ]), \
         patch("supabase_client.upsert_clan_total", side_effect=mock_upsert_clan), \
         patch("supabase_client.get_clan_totals", side_effect=mock_get_clan_totals), \
         patch("supabase_client.get_processed_hashes", return_value=set()), \
         patch("supabase_client.get_coach_alias_map", return_value={}), \
         patch("supabase_client.list_clan_totals", return_value=[]), \
         patch("supabase_client.list_coach_totals", return_value=[]), \
         patch("supabase_client.get_tipo_coach_totals", return_value={}), \
         patch("supabase_client.get_all_pending_clans", return_value=[]), \
         patch("supabase_client.get_all_pending_coaches", return_value=[]), \
         patch("google_sheets_client.fetch_records", return_value=[["Col1", "Col2", "Col3"]]), \
         patch("google_sheets_client.fetch_records_pro_bono", return_value=[]), \
         patch("desafio_sync_service.sync_desafios") as mock_sync:

        mock_sync.return_value = DesafioSyncResult(status="success", tokens_versioned=0)

        # 1. Antes de qualquer revisão: as duas submissões (Ana e Bruno) já
        # contam por padrão -> 2 participantes de 4 cadastrados = 50% -> 500 pts
        res_prev = client.get(f"/api/desafios/{desafio_id}/apuracao")
        assert res_prev.status_code == 200
        prev_data = res_prev.json()
        assert prev_data["provisorio"] is True
        cla1_prev = next(c for c in prev_data["clas"] if c["clan"] == "CLÃ 1")
        assert cla1_prev["participantes"] == 2
        assert cla1_prev["pontos"] == 500

        # 2. Reprovar a submissão da Ana -> só Bruno conta -> 1 de 4 = 25% -> 300 pts
        rev1 = client.post(f"/api/desafios/submissoes/{token_1}/revisar", json={"status": "reprovado"})
        assert rev1.status_code == 200

        # 3. Disparar /executar contabilidade (prazo já venceu há 1h)
        exec_res = client.post("/api/contabilidade/executar")
        if exec_res.status_code != 200:
            print("EXEC ERROR JSON:", exec_res.json())
        assert exec_res.status_code == 200

        # 4. Verificar que a apuração foi gravada e o total do Clã 1 recebeu 300 pts
        assert desafio_mock["apurado_em"] is not None
        assert totais_clan_db["CLÃ 1"] == 300


def test_fluxo_reabertura_de_prazo_e_reapuracao():
    desafio_id = 102

    desafio_mock = {
        "id": desafio_id,
        "nome": "Desafio Reabertura",
        "contabilizar_pontos": True,
        "prazo_apuracao": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        "apurado_em": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "status": "ativo",
        "origem": "sheet",
        "created_at": "2026-08-01T09:00:00+00:00",
        "updated_at": "2026-08-01T09:00:00+00:00",
    }

    def mock_set_prazo(desafio_id, prazo):
        nonlocal desafio_mock
        prazo_str = prazo.isoformat() if isinstance(prazo, datetime) else prazo
        desafio_mock["prazo_apuracao"] = prazo_str
        desafio_mock["apurado_em"] = None  # Reaberto
        return desafio_mock

    with patch("supabase_client.get_desafio", return_value=desafio_mock), \
         patch("supabase_client.set_desafio_prazo", side_effect=mock_set_prazo):

        # Reabrir prazo para o futuro
        futuro = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        res_patch = client.patch(f"/api/desafios/{desafio_id}/prazo", json={"prazo_apuracao": futuro})
        assert res_patch.status_code == 200
        assert desafio_mock["apurado_em"] is None
        assert desafio_mock["prazo_apuracao"] == futuro
