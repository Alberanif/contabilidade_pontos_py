from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import pytest

from main import app

client = TestClient(app)


def test_get_aliases_pendentes_route():
    mock_data = [
        {
            "id": 1,
            "alias_raw": "Vini Marini",
            "coach_sugerido": "Vinicius Marini",
            "confianca": 92.5,
            "origem": "groq-llm",
            "status": "pendente",
            "created_at": "2026-09-01T21:00:00Z",
        }
    ]
    with patch("supabase_client.get_pending_coach_aliases", return_value=mock_data):
        response = client.get("/api/contabilidade/aliases-pendentes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["alias_raw"] == "Vini Marini"


def test_aprovar_alias_pendente_route():
    mock_pendente = {
        "id": 10,
        "alias_raw": "Tati P.",
        "coach_sugerido": "Tatiane Pellicel",
        "confianca": 88.0,
        "origem": "groq-llm",
        "status": "pendente",
    }
    with patch("supabase_client.get_pending_coach_alias_by_id", return_value=mock_pendente), \
         patch("supabase_client.insert_coach_alias") as mock_insert, \
         patch("supabase_client.update_pending_coach_alias_status") as mock_update_status, \
         patch("routers.contabilidade.reprocessar_coaches") as mock_reprocessar:
        
        mock_reprocessar.return_value = {"registros_atualizados": 2, "coaches_afetados": ["Tatiane Pellicel"]}

        payload = {"id_pendente": 10, "coach_canonico_override": None}
        response = client.post("/api/contabilidade/aprovar-alias-pendente", json=payload)
        
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["status"] == "sucesso"
        mock_insert.assert_called_once_with("Tati P.", "Tatiane Pellicel")
        mock_update_status.assert_called_once_with(10, status="aprovado", coach_sugerido="Tatiane Pellicel")
        mock_reprocessar.assert_called_once()


def test_nome_so_de_desafio_e_oferecido_para_resolucao_mas_nunca_e_alvo_canonico():
    """Finding 4: um nome vindo apenas da coluna B (texto livre) da planilha de
    desafios PRECISA ser resolvido, mas NUNCA pode entrar na lista de alvos
    canônicos que o LLM escolhe (senão um typo vira alvo auto-aprovável a >=95%)."""
    captured_targets = []

    def fake_evaluate(raw_name, targets):
        captured_targets.append((raw_name, list(targets)))
        return {"action": "no_match", "coach_canonico": raw_name,
                "confianca": 0.0, "origem": "none"}

    with patch("supabase_client.get_coach_alias_map", return_value={}), \
         patch("supabase_client.list_all_registros",
               return_value=[{"coach": "Bruno Costa"}]), \
         patch("supabase_client.list_coach_totals", return_value=[]), \
         patch("supabase_client.get_all_desafio_token_coach_names",
               return_value={"Vinicious Marinni"}), \
         patch("coach_llm_service.evaluate_coach_identity", side_effect=fake_evaluate), \
         patch("supabase_client.insert_coach_alias"), \
         patch("supabase_client.upsert_pending_coach_alias"):
        response = client.post("/api/contabilidade/sugerir-aliases-llm")

    assert response.status_code == 200
    data = response.json()
    # Ambos os nomes brutos foram oferecidos para resolução.
    assert data["total_analisados"] == 2
    analisados = {raw for raw, _ in captured_targets}
    assert "Vinicious Marinni" in analisados
    # O nome de desafio NUNCA aparece como alvo canônico em nenhuma avaliação.
    for _, targets in captured_targets:
        assert "Vinicious Marinni" not in targets


def test_rejeitar_alias_pendente_route():
    mock_pendente = {
        "id": 15,
        "alias_raw": "Nome Desconhecido",
        "coach_sugerido": "Coach Qualquer",
        "confianca": 71.0,
        "origem": "groq-llm",
        "status": "pendente",
    }
    with patch("supabase_client.get_pending_coach_alias_by_id", return_value=mock_pendente), \
         patch("supabase_client.update_pending_coach_alias_status") as mock_update_status:
        
        payload = {"id_pendente": 15}
        response = client.post("/api/contabilidade/rejeitar-alias-pendente", json=payload)
        
        assert response.status_code == 200
        res_data = response.json()
        assert res_data["status"] == "sucesso"
        mock_update_status.assert_called_once_with(15, status="rejeitado")
