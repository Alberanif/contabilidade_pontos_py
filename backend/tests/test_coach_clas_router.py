"""Testes da API CRUD de vínculo coach -> clã (issue #4 / Task 4).

Cobre os 4 endpoints (`GET`/`POST`/`PUT`/`DELETE` `/api/coach-clas`), a
resolução de alias via `resolve_coach()` antes de qualquer
leitura/gravação, o 409 quando o coach (já resolvido) pertence a outro
clã, o 422 de categoria inválida (validado via `Literal` do Pydantic, sem
tocar `supabase_client`) e o 404 de `PUT` para coach sem vínculo.

Usa `TestClient(app)` (roteamento real do FastAPI) e monkeypatcha apenas a
borda `supabase_client` (`list_coach_clas`, `upsert_coach_cla`,
`delete_coach_cla`, `get_coach_alias_map`) — nunca `_get_client` — seguindo
o mesmo estilo de `test_desafio_auditoria_router.py`.
"""

import os
import sys

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

import supabase_client
from main import app

client = TestClient(app)


def _row(**overrides) -> dict:
    base = {
        "coach_canonico": "Coach A",
        "clan": "CLÃ 1",
        "categoria": "Coach",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /api/coach-clas
# ---------------------------------------------------------------------------


class TestListarCoachClas:

    def test_lista_todos_sem_filtro(self, monkeypatch):
        rows = [_row(), _row(coach_canonico="Coach B", clan="CLÃ 2", categoria="Coach Pro")]
        chamadas = []
        monkeypatch.setattr(
            supabase_client,
            "list_coach_clas",
            lambda clan=None: (chamadas.append(clan), rows)[1],
        )

        resposta = client.get("/api/coach-clas")

        assert resposta.status_code == 200
        assert resposta.json() == rows
        assert chamadas == [None]

    def test_filtra_por_clan(self, monkeypatch):
        rows = [_row()]
        chamadas = []
        monkeypatch.setattr(
            supabase_client,
            "list_coach_clas",
            lambda clan=None: (chamadas.append(clan), rows)[1],
        )

        resposta = client.get("/api/coach-clas", params={"clan": "CLÃ 1"})

        assert resposta.status_code == 200
        assert resposta.json() == rows
        assert chamadas == ["CLÃ 1"]


# ---------------------------------------------------------------------------
# POST /api/coach-clas
# ---------------------------------------------------------------------------


class TestCriarCoachCla:

    def test_cria_vinculo_novo(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
        monkeypatch.setattr(supabase_client, "list_coach_clas", lambda clan=None: [])
        upsert_calls = []
        monkeypatch.setattr(
            supabase_client,
            "upsert_coach_cla",
            lambda coach_canonico, clan, categoria: (
                upsert_calls.append((coach_canonico, clan, categoria)),
                _row(coach_canonico=coach_canonico, clan=clan, categoria=categoria),
            )[1],
        )

        resposta = client.post(
            "/api/coach-clas",
            json={"coach": "Coach A", "clan": "CLÃ 1", "categoria": "Coach"},
        )

        assert resposta.status_code == 200
        assert resposta.json() == _row()
        assert upsert_calls == [("Coach A", "CLÃ 1", "Coach")]

    def test_resolve_alias_antes_de_gravar(self, monkeypatch):
        """Nome bruto vindo de um alias cadastrado deve ser resolvido ao
        canônico antes de qualquer leitura/gravação."""
        monkeypatch.setattr(
            supabase_client, "get_coach_alias_map", lambda: {"coach a (apelido)": "Coach A"}
        )
        monkeypatch.setattr(supabase_client, "list_coach_clas", lambda clan=None: [])
        upsert_calls = []
        monkeypatch.setattr(
            supabase_client,
            "upsert_coach_cla",
            lambda coach_canonico, clan, categoria: (
                upsert_calls.append((coach_canonico, clan, categoria)),
                _row(coach_canonico=coach_canonico, clan=clan, categoria=categoria),
            )[1],
        )

        resposta = client.post(
            "/api/coach-clas",
            json={"coach": "Coach A (apelido)", "clan": "CLÃ 1", "categoria": "Coach"},
        )

        assert resposta.status_code == 200
        assert upsert_calls == [("Coach A", "CLÃ 1", "Coach")]

    def test_409_quando_coach_ja_pertence_a_outro_clan(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
        monkeypatch.setattr(
            supabase_client, "list_coach_clas", lambda clan=None: [_row(clan="CLÃ 1")]
        )

        def _falha_se_chamado(*args, **kwargs):
            raise AssertionError("upsert_coach_cla não deveria ser chamado em conflito")

        monkeypatch.setattr(supabase_client, "upsert_coach_cla", _falha_se_chamado)

        resposta = client.post(
            "/api/coach-clas",
            json={"coach": "Coach A", "clan": "CLÃ 2", "categoria": "Coach"},
        )

        assert resposta.status_code == 409
        assert "CLÃ 1" in resposta.json()["detail"]

    def test_nao_conflita_ao_repostar_mesmo_clan(self, monkeypatch):
        """Reenviar o mesmo coach para o MESMO clã (ex.: só trocando
        categoria) não é conflito — é upsert normal."""
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
        monkeypatch.setattr(
            supabase_client,
            "list_coach_clas",
            lambda clan=None: [_row(clan="CLÃ 1", categoria="Coach")],
        )
        upsert_calls = []
        monkeypatch.setattr(
            supabase_client,
            "upsert_coach_cla",
            lambda coach_canonico, clan, categoria: (
                upsert_calls.append((coach_canonico, clan, categoria)),
                _row(coach_canonico=coach_canonico, clan=clan, categoria=categoria),
            )[1],
        )

        resposta = client.post(
            "/api/coach-clas",
            json={"coach": "Coach A", "clan": "CLÃ 1", "categoria": "Coach Pro"},
        )

        assert resposta.status_code == 200
        assert upsert_calls == [("Coach A", "CLÃ 1", "Coach Pro")]

    def test_422_categoria_invalida(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})

        def _falha_se_chamado(*args, **kwargs):
            raise AssertionError("supabase_client não deveria ser chamado com payload inválido")

        monkeypatch.setattr(supabase_client, "list_coach_clas", _falha_se_chamado)
        monkeypatch.setattr(supabase_client, "upsert_coach_cla", _falha_se_chamado)

        resposta = client.post(
            "/api/coach-clas",
            json={"coach": "Coach A", "clan": "CLÃ 1", "categoria": "Categoria Inventada"},
        )

        assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/coach-clas/{coach_canonico}
# ---------------------------------------------------------------------------


class TestAtualizarCoachCla:

    def test_move_de_clan(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
        monkeypatch.setattr(
            supabase_client,
            "list_coach_clas",
            lambda clan=None: [_row(clan="CLÃ 1", categoria="Coach")],
        )
        upsert_calls = []
        monkeypatch.setattr(
            supabase_client,
            "upsert_coach_cla",
            lambda coach_canonico, clan, categoria: (
                upsert_calls.append((coach_canonico, clan, categoria)),
                _row(coach_canonico=coach_canonico, clan=clan, categoria=categoria),
            )[1],
        )

        resposta = client.put("/api/coach-clas/Coach A", json={"clan": "CLÃ 2"})

        assert resposta.status_code == 200
        assert resposta.json()["clan"] == "CLÃ 2"
        # categoria preservada (não enviada no payload)
        assert upsert_calls == [("Coach A", "CLÃ 2", "Coach")]

    def test_edita_categoria(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
        monkeypatch.setattr(
            supabase_client,
            "list_coach_clas",
            lambda clan=None: [_row(clan="CLÃ 1", categoria="Coach")],
        )
        upsert_calls = []
        monkeypatch.setattr(
            supabase_client,
            "upsert_coach_cla",
            lambda coach_canonico, clan, categoria: (
                upsert_calls.append((coach_canonico, clan, categoria)),
                _row(coach_canonico=coach_canonico, clan=clan, categoria=categoria),
            )[1],
        )

        resposta = client.put("/api/coach-clas/Coach A", json={"categoria": "Coach Hero"})

        assert resposta.status_code == 200
        assert upsert_calls == [("Coach A", "CLÃ 1", "Coach Hero")]

    def test_404_coach_inexistente(self, monkeypatch):
        monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
        monkeypatch.setattr(supabase_client, "list_coach_clas", lambda clan=None: [])

        def _falha_se_chamado(*args, **kwargs):
            raise AssertionError("upsert_coach_cla não deveria ser chamado em 404")

        monkeypatch.setattr(supabase_client, "upsert_coach_cla", _falha_se_chamado)

        resposta = client.put("/api/coach-clas/Coach Fantasma", json={"clan": "CLÃ 1"})

        assert resposta.status_code == 404

    def test_422_categoria_invalida(self, monkeypatch):
        resposta = client.put(
            "/api/coach-clas/Coach A", json={"categoria": "Categoria Inventada"}
        )
        assert resposta.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/coach-clas/{coach_canonico}
# ---------------------------------------------------------------------------


class TestDeletarCoachCla:

    def test_remove_vinculo(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            supabase_client, "delete_coach_cla", lambda coach_canonico: chamadas.append(coach_canonico)
        )

        resposta = client.delete("/api/coach-clas/Coach A")

        assert resposta.status_code == 200
        assert chamadas == ["Coach A"]

    def test_idempotente_ao_chamar_de_novo(self, monkeypatch):
        chamadas = []
        monkeypatch.setattr(
            supabase_client, "delete_coach_cla", lambda coach_canonico: chamadas.append(coach_canonico)
        )

        primeira = client.delete("/api/coach-clas/Coach A")
        segunda = client.delete("/api/coach-clas/Coach A")

        assert primeira.status_code == 200
        assert segunda.status_code == 200
        assert chamadas == ["Coach A", "Coach A"]
