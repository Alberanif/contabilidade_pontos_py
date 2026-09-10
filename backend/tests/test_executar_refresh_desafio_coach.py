import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch

from routers.contabilidade import _refresh_desafio_coach_totals


def test_refresh_reconstroi_total_a_partir_dos_breakdowns_mais_desafio():
    coach_totals = [
        {"coach": "Ana", "total_pontos": 30, "total_pagante": 30,
         "total_pro_bono": 0, "pessoas_em_espera": 2},
        {"coach": "Bruno", "total_pontos": 50, "total_pagante": 40,
         "total_pro_bono": 10, "pessoas_em_espera": 0},
    ]
    with patch("supabase_client.get_tipo_coach_totals", return_value={"Ana": 20}), \
         patch("supabase_client.list_coach_totals", return_value=coach_totals), \
         patch("supabase_client.upsert_coach_total") as mock_upsert:
        _refresh_desafio_coach_totals()

    mock_upsert.assert_any_call(
        "Ana", 50, pessoas_em_espera=2, total_pagante=30, total_pro_bono=0
    )
    # Bruno não tem desafio -> total = 40 + 10 + 0, também é reescrito (auto-correção)
    mock_upsert.assert_any_call(
        "Bruno", 50, pessoas_em_espera=0, total_pagante=40, total_pro_bono=10
    )


def test_refresh_inclui_coach_que_so_tem_desafio():
    with patch("supabase_client.get_tipo_coach_totals", return_value={"Carla": 10}), \
         patch("supabase_client.list_coach_totals", return_value=[]), \
         patch("supabase_client.upsert_coach_total") as mock_upsert:
        _refresh_desafio_coach_totals()
    mock_upsert.assert_any_call(
        "Carla", 10, pessoas_em_espera=0, total_pagante=0, total_pro_bono=0
    )
