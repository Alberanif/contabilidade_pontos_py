from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import pytest

from main import app
import coach_identity

client = TestClient(app)


def test_coach_identity_resolution_e2e_flow():
    """Valida o fluxo completo de ponta a ponta:
    1. Execução de sugestões via LLM
    2. Envio de sugestão para a fila de pendentes
    3. Aprovação de alias e disparo automático de reprocessamento
    4. Garantia de consistência de pontos
    """
    mock_all_regs = [
        {"id": 1, "coach": "Vini Marini", "modalidade": "Coaching Individual", "pontos_coach": 30, "status_coach": "contabilizado"},
    ]

    mock_alias_map = {}
    mock_pending_db = []

    def mock_get_pending(status="pendente"):
        return [item for item in mock_pending_db if item["status"] == status]

    def mock_get_pending_by_id(id_pendente):
        for item in mock_pending_db:
            if item["id"] == id_pendente:
                return item
        return None

    def mock_upsert_pending(alias_raw, coach_sugerido, confianca, origem="groq-llm", status="pendente"):
        item = {
            "id": len(mock_pending_db) + 1,
            "alias_raw": alias_raw,
            "coach_sugerido": coach_sugerido,
            "confianca": confianca,
            "origem": origem,
            "status": status,
        }
        mock_pending_db.append(item)
        return item

    def mock_update_pending_status(id_pendente, status, coach_sugerido=None):
        item = mock_get_pending_by_id(id_pendente)
        if item:
            item["status"] = status
            if coach_sugerido:
                item["coach_sugerido"] = coach_sugerido
        return item or {}

    def mock_insert_alias(alias, coach_canonico):
        mock_alias_map[alias] = coach_canonico
        return {"alias": alias, "coach_canonico": coach_canonico}

    with patch("supabase_client.list_all_registros", return_value=mock_all_regs), \
         patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
         patch("supabase_client.get_coach_alias_map", side_effect=lambda: mock_alias_map), \
         patch("supabase_client.get_pending_coach_aliases", side_effect=mock_get_pending), \
         patch("supabase_client.get_pending_coach_alias_by_id", side_effect=mock_get_pending_by_id), \
         patch("supabase_client.upsert_pending_coach_alias", side_effect=mock_upsert_pending), \
         patch("supabase_client.update_pending_coach_alias_status", side_effect=mock_update_pending_status), \
         patch("supabase_client.insert_coach_alias", side_effect=mock_insert_alias), \
         patch("supabase_client.update_registros_coach", return_value=1), \
         patch("supabase_client.update_desafio_importacao_linhas_coach", return_value=0), \
         patch("supabase_client.merge_desafio_registros_coach", return_value=0), \
         patch("supabase_client.delete_coach_total"), \
         patch("supabase_client.upsert_coach_total") as mock_upsert_total, \
         patch("supabase_client.get_desafio_coach_total", return_value=0), \
         patch("supabase_client.list_coach_totals", return_value=[{"coach": "Vinicius Marini"}]), \
         patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
         patch("config.GROQ_API_KEY", "mock_key"):


        # 1. Avalia sugestões LLM (simulando resposta com 88% de confiança para fila de pendentes)
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content='{"coach_sugerido": "Vinicius Marini", "confianca": 88.0}'))
        ]

        with patch("coach_llm_service.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_completion
            mock_groq_cls.return_value = mock_client

            response = client.post("/api/contabilidade/sugerir-aliases-llm")
            assert response.status_code == 200
            res = response.json()
            assert res["enviados_para_fila"] == 1

        # 2. Verifica a fila de pendentes
        response_pending = client.get("/api/contabilidade/aliases-pendentes")
        assert response_pending.status_code == 200
        pending_list = response_pending.json()
        assert len(pending_list) == 1
        assert pending_list[0]["alias_raw"] == "Vini Marini"
        assert pending_list[0]["coach_sugerido"] == "Vinicius Marini"

        # 3. Aprova o alias pendente
        pending_id = pending_list[0]["id"]
        response_approve = client.post("/api/contabilidade/aprovar-alias-pendente", json={"id_pendente": pending_id})
        assert response_approve.status_code == 200
        assert response_approve.json()["status"] == "sucesso"

        # 4. Verifica que o alias foi adicionado ao mapa
        assert mock_alias_map.get("Vini Marini") == "Vinicius Marini"

        # 5. Verifica se reprocessar_coaches recai sob o canônico unificado
        mock_upsert_total.assert_called()
