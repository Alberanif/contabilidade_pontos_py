import pytest
from datetime import date
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app
import supabase_client

client = TestClient(app)

def test_historico_com_travar_inicio_apenas_data_inicio():
    inicio = "2026-05-01"
    
    with patch("supabase_client.get_period_clan_totals") as mock_clan, \
         patch("supabase_client.get_period_desafio_totals") as mock_desafio_clan, \
         patch("supabase_client.get_period_coach_totals") as mock_coach, \
         patch("supabase_client.get_period_desafio_coach_totals") as mock_desafio_coach:
        
        mock_clan.return_value = {"CLÃ 1": 30}
        mock_desafio_clan.return_value = {}
        mock_coach.return_value = {"Karlla Andrade": 30}
        mock_desafio_coach.return_value = {}

        response = client.get(f"/api/contabilidade/historico?inicio={inicio}")
        assert response.status_code == 200
        data = response.json()
        assert data["clans"]["CLÃ 1"] == 30
        assert data["coaches"]["Karlla Andrade"] == 30

        # Verifica se o backend chamou as funções com fim = None
        mock_clan.assert_called_once_with(date(2026, 5, 1), None)
        mock_coach.assert_called_once_with(date(2026, 5, 1), None)

def test_totais_por_tipo_com_travar_inicio():
    inicio = "2026-05-01"
    
    with patch("supabase_client.get_tipo_clan_totals") as mock_clan, \
         patch("supabase_client.get_tipo_coach_totals") as mock_coach:
        
        mock_clan.return_value = {"CLÃ 2": 60}
        mock_coach.return_value = {"Vinicius Marini": 60}

        response = client.get(f"/api/contabilidade/totais-por-tipo?tipo=pagante&inicio={inicio}")
        assert response.status_code == 200
        data = response.json()
        assert data["clans"]["CLÃ 2"] == 60
        assert data["coaches"]["Vinicius Marini"] == 60

        mock_clan.assert_called_once_with("pagante", date(2026, 5, 1), None)
        mock_coach.assert_called_once_with("pagante", date(2026, 5, 1), None)
