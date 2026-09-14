"""`fetch_all_registros_contabilizados`: leitura completa (paginada, sem
truncar) de `pontos_ultimate_registros_contabilizados` — base da correção
retroativa não-destrutiva (`admin/recalcular_totais_data_inicio.py`)."""

import os
import sys
from types import SimpleNamespace
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


def _paged_client(pages):
    ranges: list[tuple[int, int]] = []

    class _Query:
        def select(self, *_):
            return self

        def order(self, *_, **__):
            return self

        def range(self, start, end):
            ranges.append((start, end))
            return self

        def execute(self):
            idx = len(ranges) - 1
            return SimpleNamespace(data=pages[idx])

    client = SimpleNamespace(table=lambda *_: _Query())
    return client, ranges


class TestFetchAllRegistrosContabilizados:

    def test_pagina_unica(self):
        rows = [{"id": 1, "clan": "CLÃ 1"}]
        client, ranges = _paged_client([rows, []])
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.fetch_all_registros_contabilizados()
        assert result == rows

    def test_paginacao_nao_para_em_pagina_curta(self):
        pages = [
            [{"id": 1}, {"id": 2}],
            [{"id": 3}],
            [],
        ]
        client, ranges = _paged_client(pages)
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.fetch_all_registros_contabilizados()
        assert [r["id"] for r in result] == [1, 2, 3]
        assert [start for start, _ in ranges] == [0, 2, 3]

    def test_mais_de_mil_linhas_nao_e_truncado(self):
        rows = [{"id": i} for i in range(1500)]
        client, ranges = _paged_client([rows[:1000], rows[1000:], []])
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.fetch_all_registros_contabilizados()
        assert len(result) == 1500
