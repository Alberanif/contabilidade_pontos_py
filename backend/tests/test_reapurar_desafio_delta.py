"""Testes de `supabase_client.reapurar_desafio_e_aplicar_delta` — recálculo
da apuração por percentual de um desafio (congelado ou não) e aplicação do
delta resultante ao total do clã."""

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

import supabase_client
from desafio_percentual_clan import ApuracaoClan


def _apuracao(clan, pontos, participantes=1, total_grupo=4, percentual=25.0):
    return ApuracaoClan(clan=clan, participantes=participantes, total_grupo=total_grupo,
                         percentual=percentual, pontos=pontos)


def test_desafio_inexistente_retorna_dict_vazio():
    with patch("supabase_client.get_desafio", return_value=None):
        assert supabase_client.reapurar_desafio_e_aplicar_delta(999) == {}


def test_aplica_delta_positivo_ao_total_do_cla_e_regrava_apuracao():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 500)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 300}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan") as mock_salvar:
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5)

    mock_upsert.assert_called_once_with(clan="CLÃ 1", total=500)
    mock_salvar.assert_called_once()
    assert resultado["CLÃ 1"]["pontos"] == 500
    assert resultado["CLÃ 1"]["delta"] == 200


def test_aplica_delta_negativo_sem_deixar_total_negativo():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 0)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 100}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan"):
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5)

    # total atual (100) + delta (0 - 300 = -300) = -200 -> travado em 0
    mock_upsert.assert_called_once_with(clan="CLÃ 1", total=0)
    assert resultado["CLÃ 1"]["delta"] == -300


def test_sem_mudanca_nao_chama_upsert():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 300)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 300}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan") as mock_salvar:
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5)

    mock_upsert.assert_not_called()
    mock_salvar.assert_called_once()  # ainda regrava (idempotente), só não move o total
    assert resultado["CLÃ 1"]["delta"] == 0


def test_dry_run_nao_grava_nada_mas_retorna_delta():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 500)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 300}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan") as mock_salvar:
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5, dry_run=True)

    mock_upsert.assert_not_called()
    mock_salvar.assert_not_called()
    assert resultado["CLÃ 1"]["delta"] == 200
