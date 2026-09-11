"""Testes da issue #2 (Task 2): camada de dados Supabase para o vínculo
coach -> clã (`pontos_ultimate_coach_clas`), usada tanto pelo script de
importação quanto pelos endpoints da API (issues futuras).
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supabase_client


# ---------------------------------------------------------------------------
# Helper de mock
# ---------------------------------------------------------------------------


def _single_page_client(rows):
    """Client fake cujo `.table(...).select()/.eq()/.upsert()/.delete()
    .execute()` devolve `rows`, registrando as chamadas de `.eq(...)` e o
    payload passado a `.upsert(...)` para que os testes verifiquem a
    construção real da query (não apenas o retorno mockado)."""
    eq_calls: list[tuple] = []
    upsert_calls: list[tuple] = []

    class _Query:
        def select(self, *_):
            return self

        def eq(self, *args):
            eq_calls.append(args)
            return self

        def upsert(self, payload, **kwargs):
            upsert_calls.append((payload, kwargs))
            return self

        def delete(self):
            return self

        def execute(self):
            return SimpleNamespace(data=rows)

    client = SimpleNamespace(table=lambda *_: _Query())
    return client, eq_calls, upsert_calls


# ---------------------------------------------------------------------------
# list_coach_clas
# ---------------------------------------------------------------------------


class TestListCoachClas:

    def test_lista_todos_sem_filtro(self):
        rows = [
            {"coach_canonico": "Coach A", "clan": "CLÃ 1", "categoria": "Coach"},
            {"coach_canonico": "Coach B", "clan": "CLÃ 2", "categoria": "Coach Pro"},
        ]
        client, eq_calls, _ = _single_page_client(rows)
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.list_coach_clas()
        assert result == rows
        assert eq_calls == []

    def test_filtra_por_clan(self):
        rows = [{"coach_canonico": "Coach A", "clan": "CLÃ 1", "categoria": "Coach"}]
        client, eq_calls, _ = _single_page_client(rows)
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.list_coach_clas(clan="CLÃ 1")
        assert result == rows
        assert ("clan", "CLÃ 1") in eq_calls


# ---------------------------------------------------------------------------
# upsert_coach_cla
# ---------------------------------------------------------------------------


class TestUpsertCoachCla:

    def test_insere_coach_novo(self):
        row = {"coach_canonico": "Coach A", "clan": "CLÃ 1", "categoria": "Coach"}
        client, _, upsert_calls = _single_page_client([row])
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.upsert_coach_cla("Coach A", "CLÃ 1", "Coach")
        assert result == row
        assert len(upsert_calls) == 1
        payload, kwargs = upsert_calls[0]
        assert payload == {
            "coach_canonico": "Coach A",
            "clan": "CLÃ 1",
            "categoria": "Coach",
        }
        assert kwargs.get("on_conflict") == "coach_canonico"

    def test_atualiza_clan_e_categoria_de_coach_existente(self):
        """Mesmo coach_canonico, clã/categoria diferentes: upsert por
        `coach_canonico`, sem duplicar linha (o `ON CONFLICT` fica no banco;
        aqui garantimos que a função manda o payload/on_conflict certos)."""
        row = {"coach_canonico": "Coach A", "clan": "CLÃ 2", "categoria": "Coach Hero"}
        client, _, upsert_calls = _single_page_client([row])
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.upsert_coach_cla("Coach A", "CLÃ 2", "Coach Hero")
        assert result == row
        payload, kwargs = upsert_calls[0]
        assert payload == {
            "coach_canonico": "Coach A",
            "clan": "CLÃ 2",
            "categoria": "Coach Hero",
        }
        assert kwargs.get("on_conflict") == "coach_canonico"


# ---------------------------------------------------------------------------
# delete_coach_cla
# ---------------------------------------------------------------------------


class TestDeleteCoachCla:

    def test_remove_coach_existente(self):
        client, eq_calls, _ = _single_page_client(
            [{"coach_canonico": "Coach A", "clan": "CLÃ 1", "categoria": "Coach"}]
        )
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.delete_coach_cla("Coach A")
        assert result is None
        assert ("coach_canonico", "Coach A") in eq_calls

    def test_idempotente_em_coach_inexistente(self):
        """Supabase não levanta erro para `.delete().eq(...).execute()` sem
        linhas casadas; a função não deve levantar erro nesse caso."""
        client, eq_calls, _ = _single_page_client([])
        with patch.object(supabase_client, "_get_client", return_value=client):
            result = supabase_client.delete_coach_cla("Coach Inexistente")
        assert result is None
        assert ("coach_canonico", "Coach Inexistente") in eq_calls
