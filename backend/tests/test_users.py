"""Issue #55: módulo de usuários, hash de senha e semeadura do primeiro admin."""

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

for _k, _v in {
    "GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
    "GSHEET_RECORDS_SPREADSHEET_ID": "t",
    "GSHEET_RECORDS_SHEET_NAME": "t",
    "GSHEET_TOTALS_SPREADSHEET_ID": "t",
    "GSHEET_TOTALS_SHEET_NAME": "t",
    "SUPABASE_URL": "http://localhost:54321",
    "SUPABASE_SERVICE_ROLE_KEY": "k",
}.items():
    os.environ.setdefault(_k, _v)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import users


class _FakeDB:
    """Client Supabase fake em memória para as tabelas app_users/auth_events."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self._seq = 0

    def table(self, name):
        return _Query(self, name)


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.rows = db.tables.setdefault(name, [])
        self.filters, self.op, self.payload, self._limit = [], "select", None, None

    def select(self, *_, **__):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, *_, **__):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload):
        self.op, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def _match(self):
        return [r for r in self.rows if all(r.get(c) == v for c, v in self.filters)]

    def execute(self):
        if self.op == "insert":
            self.db._seq += 1
            row = {"id": self.db._seq, **self.payload}
            if self.name == "app_users" and any(
                r["email"].lower() == row["email"].lower() for r in self.rows
            ):
                raise Exception("duplicate key value violates unique constraint")
            self.rows.append(row)
            return SimpleNamespace(data=[dict(row)])
        if self.op == "update":
            if (
                self.name == "app_users"
                and "email" in self.payload
                and any(
                    r["email"].lower() == self.payload["email"].lower()
                    and r not in self._match()
                    for r in self.rows
                )
            ):
                raise Exception("duplicate key value violates unique constraint")
            matched = self._match()
            for r in matched:
                r.update(self.payload)
            return SimpleNamespace(data=[dict(r) for r in matched])
        data = [dict(r) for r in self._match()]
        if self._limit is not None:
            data = data[: self._limit]
        return SimpleNamespace(data=data)


@pytest.fixture
def db():
    fake = _FakeDB()
    with patch.object(users, "_get_client", lambda: fake):
        yield fake


# --- hash de senha ---------------------------------------------------------


def test_hash_nao_guarda_senha_em_texto_puro():
    h = users.hash_password("uma-senha-longa-1")
    assert "uma-senha-longa-1" not in h


def test_verify_password_correta_e_incorreta():
    h = users.hash_password("uma-senha-longa-1")
    assert users.verify_password("uma-senha-longa-1", h) is True
    assert users.verify_password("outra-senha-123", h) is False


def test_hash_tem_salt_diferente_a_cada_chamada():
    assert users.hash_password("uma-senha-longa-1") != users.hash_password("uma-senha-longa-1")


def test_verify_password_com_hash_invalido_retorna_false():
    assert users.verify_password("x", "nao-e-um-hash") is False
    assert users.verify_password("x", "") is False


def test_senha_muito_longa_e_unicode_funcionam():
    senha = "ç" * 100
    assert users.verify_password(senha, users.hash_password(senha))


def test_senha_curta_e_rejeitada():
    with pytest.raises(users.SenhaCurtaError):
        users.hash_password("123456789")  # 9 caracteres
    users.hash_password("1234567890")  # 10 caracteres ok


# --- CRUD ------------------------------------------------------------------


def test_create_user_normaliza_email_e_nao_expoe_hash(db):
    u = users.create_user("  Maria@Exemplo.COM ", "Maria", "senha-bem-longa")
    assert u["email"] == "maria@exemplo.com"
    assert u["nome"] == "Maria"
    assert u["is_admin"] is False and u["ativo"] is True
    assert u["deve_trocar_senha"] is True
    assert "senha_hash" not in u
    stored = db.tables["app_users"][0]
    assert stored["senha_hash"] != "senha-bem-longa"
    assert users.verify_password("senha-bem-longa", stored["senha_hash"])


def test_email_unico_sem_diferenciar_maiusculas(db):
    users.create_user("a@x.com", "A", "senha-bem-longa")
    with pytest.raises(users.EmailDuplicadoError):
        users.create_user("A@X.COM", "A2", "senha-bem-longa")
    assert len(db.tables["app_users"]) == 1


def test_create_user_senha_curta(db):
    with pytest.raises(users.SenhaCurtaError):
        users.create_user("a@x.com", "A", "curta")
    assert not db.tables.get("app_users")


def test_get_user_by_email_ignora_caixa_e_inclui_hash(db):
    users.create_user("a@x.com", "A", "senha-bem-longa")
    u = users.get_user_by_email(" A@X.com ")
    assert u["email"] == "a@x.com" and "senha_hash" in u
    assert users.get_user_by_email("nao@existe.com") is None


def test_get_user_by_id(db):
    created = users.create_user("a@x.com", "A", "senha-bem-longa")
    assert users.get_user_by_id(created["id"])["email"] == "a@x.com"
    assert users.get_user_by_id(999) is None


def test_list_users_sem_hash(db):
    users.create_user("a@x.com", "A", "senha-bem-longa")
    users.create_user("b@x.com", "B", "senha-bem-longa")
    lst = users.list_users()
    assert len(lst) == 2
    assert all("senha_hash" not in u for u in lst)


def test_update_user_campos_e_senha(db):
    u = users.create_user("a@x.com", "A", "senha-bem-longa")
    out = users.update_user(u["id"], nome="Novo", is_admin=True, ativo=False, email="N@X.com")
    assert out["nome"] == "Novo" and out["is_admin"] is True and out["ativo"] is False
    assert out["email"] == "n@x.com"
    assert "senha_hash" not in out

    users.update_user(u["id"], senha="outra-senha-longa", deve_trocar_senha=False)
    stored = db.tables["app_users"][0]
    assert users.verify_password("outra-senha-longa", stored["senha_hash"])
    assert stored["deve_trocar_senha"] is False
    assert "atualizado_em" in stored


def test_update_user_senha_curta_e_inexistente(db):
    u = users.create_user("a@x.com", "A", "senha-bem-longa")
    with pytest.raises(users.SenhaCurtaError):
        users.update_user(u["id"], senha="curta")
    assert users.update_user(999, nome="X") is None


def test_update_user_email_duplicado(db):
    users.create_user("a@x.com", "A", "senha-bem-longa")
    b = users.create_user("b@x.com", "B", "senha-bem-longa")
    with pytest.raises(users.EmailDuplicadoError):
        users.update_user(b["id"], email="A@x.com")


def test_update_user_rejeita_campos_desconhecidos(db):
    u = users.create_user("a@x.com", "A", "senha-bem-longa")
    with pytest.raises(TypeError):
        users.update_user(u["id"], senha_hash="x")


def test_record_auth_event(db):
    users.record_auth_event("login_falha", email_tentado=" A@X.com ", ip="1.2.3.4")
    ev = db.tables["auth_events"][0]
    assert ev["tipo"] == "login_falha" and ev["email_tentado"] == "a@x.com"
    assert ev["user_id"] is None and ev["ip"] == "1.2.3.4"


# --- semeadura -------------------------------------------------------------


def test_seed_cria_admin_quando_vazia(db, monkeypatch):
    monkeypatch.setattr(users.config, "APP_USER", "Admin@Igt.com")
    monkeypatch.setattr(users.config, "APP_PASSWORD", "curta")  # semeia mesmo curta
    assert users.seed_first_admin() is True
    row = db.tables["app_users"][0]
    assert row["email"] == "admin@igt.com"
    assert row["is_admin"] is True and row["ativo"] is True
    assert row["deve_trocar_senha"] is True
    assert row["senha_hash"] != "curta"
    assert users.verify_password("curta", row["senha_hash"])


def test_seed_idempotente(db, monkeypatch):
    monkeypatch.setattr(users.config, "APP_USER", "admin@igt.com")
    monkeypatch.setattr(users.config, "APP_PASSWORD", "senha-inicial-1")
    assert users.seed_first_admin() is True
    assert users.seed_first_admin() is False
    assert len(db.tables["app_users"]) == 1


def test_seed_nao_roda_se_ja_existe_algum_usuario(db, monkeypatch):
    users.create_user("outro@x.com", "Outro", "senha-bem-longa")
    monkeypatch.setattr(users.config, "APP_USER", "admin@igt.com")
    monkeypatch.setattr(users.config, "APP_PASSWORD", "senha-inicial-1")
    assert users.seed_first_admin() is False
    assert len(db.tables["app_users"]) == 1


def test_seed_sem_app_password_nao_faz_nada(db, monkeypatch):
    monkeypatch.setattr(users.config, "APP_PASSWORD", "")
    assert users.seed_first_admin() is False
    assert not db.tables.get("app_users")


def test_seed_nao_loga_senha(db, monkeypatch, caplog):
    monkeypatch.setattr(users.config, "APP_USER", "admin@igt.com")
    monkeypatch.setattr(users.config, "APP_PASSWORD", "segredo-que-nao-vaza")
    with caplog.at_level("DEBUG"):
        users.seed_first_admin()
    assert "segredo-que-nao-vaza" not in caplog.text


# --- config / migration ----------------------------------------------------


def test_session_secret_obrigatoria_sem_auth_disabled(monkeypatch):
    import config

    monkeypatch.setenv("APP_AUTH_DISABLED", "false")
    monkeypatch.setenv("APP_PASSWORD", "alguma-senha-1")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    try:
        with pytest.raises(ValueError, match="SESSION_SECRET"):
            importlib.reload(config)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_session_secret_dispensada_com_auth_disabled(monkeypatch):
    import config

    monkeypatch.setenv("APP_AUTH_DISABLED", "true")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    try:
        importlib.reload(config)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_migration_define_tabelas_e_unicidade_case_insensitive():
    path = Path(__file__).resolve().parents[1] / "migrations" / "013_add_app_users_auth_events.sql"
    sql = path.read_text(encoding="utf-8").lower()
    assert "create table if not exists app_users" in sql
    assert "create table if not exists auth_events" in sql
    assert "unique index" in sql and "lower(email)" in sql
    for col in (
        "senha_hash", "is_admin", "ativo", "deve_trocar_senha", "ultimo_login_em",
        "criado_em", "atualizado_em", "email_tentado", "tipo", "ip", "user_id",
    ):
        assert col in sql


# --- startup ---------------------------------------------------------------


def test_startup_semeia_admin_quando_auth_ativa(monkeypatch):
    from fastapi.testclient import TestClient

    import config
    from main import app

    chamadas = []
    monkeypatch.setattr(users, "seed_first_admin", lambda: chamadas.append(1) or True)
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", False)
    with TestClient(app):
        pass
    assert chamadas == [1]


def test_startup_nao_semeia_com_auth_desativada_e_tolera_falha(monkeypatch):
    from fastapi.testclient import TestClient

    import config
    from main import app

    def boom():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(users, "seed_first_admin", boom)
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", True)
    with TestClient(app):
        pass  # não chama a semeadura
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", False)
    with TestClient(app):
        pass  # falha é logada, app sobe
