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
