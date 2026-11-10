"""Issue #59: API de gestão de usuários (admin)."""
import os
import sys
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

from fastapi.testclient import TestClient

import config
import users
from main import app
from tests.test_users import _FakeDB

SENHA = "senha-correta-123"


@pytest.fixture
def db():
    fake = _FakeDB()
    with patch.object(users, "_get_client", lambda: fake):
        yield fake


@pytest.fixture
def client(monkeypatch, db):
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", False)
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", False)
    monkeypatch.setattr(config, "SESSION_SECRET", "segredo-de-teste")
    return TestClient(app)


def _mk(email, is_admin=False, nome="U"):
    return users.create_user(email, nome, SENHA, is_admin=is_admin, deve_trocar_senha=False)


def _login(client, email):
    assert client.post("/api/auth/login", json={"email": email, "senha": SENHA}).status_code == 200


@pytest.fixture
def admin(client, db):
    a = _mk("admin@x.com", is_admin=True, nome="Admin")
    _login(client, "admin@x.com")
    return a


def _eventos(db, tipo):
    return [e for e in db.tables.get("auth_events", []) if e["tipo"] == tipo]


def test_nao_admin_recebe_403_em_todos(client, db):
    outro = _mk("b@x.com")
    _login(client, "b@x.com")
    assert client.get("/api/usuarios").status_code == 403
    assert client.post("/api/usuarios", json={
        "nome": "N", "email": "n@x.com", "senha_provisoria": SENHA, "is_admin": False}).status_code == 403
    assert client.patch(f"/api/usuarios/{outro['id']}", json={"nome": "Z"}).status_code == 403
    assert client.post(f"/api/usuarios/{outro['id']}/redefinir-senha",
                       json={"senha_provisoria": SENHA}).status_code == 403


def test_sem_sessao_401(client):
    assert client.get("/api/usuarios").status_code == 401


def test_listar_sem_senha_hash(client, db, admin):
    _mk("b@x.com")
    r = client.get("/api/usuarios")
    assert r.status_code == 200 and len(r.json()) == 2
    assert all("senha_hash" not in u for u in r.json())
    assert set(r.json()[0]) == {"id", "email", "nome", "is_admin", "ativo",
                                "deve_trocar_senha", "ultimo_login_em", "criado_em"}


def test_criar_usuario(client, db, admin):
    r = client.post("/api/usuarios", json={
        "nome": "Novo", "email": "Novo@X.com", "senha_provisoria": SENHA, "is_admin": False})
    assert r.status_code == 201
    b = r.json()
    assert b["email"] == "novo@x.com" and b["deve_trocar_senha"] is True and b["ativo"] is True
    assert "senha_hash" not in b
    ev = _eventos(db, "usuario_criado")
    assert len(ev) == 1 and ev[0]["user_id"] == b["id"] and ev[0]["email_tentado"] == "admin@x.com"


def test_criar_email_duplicado_409(client, db, admin):
    r = client.post("/api/usuarios", json={
        "nome": "X", "email": "ADMIN@x.com", "senha_provisoria": SENHA, "is_admin": False})
    assert r.status_code == 409 and "e-mail" in r.json()["detail"]


def test_criar_senha_curta_400(client, db, admin):
    r = client.post("/api/usuarios", json={
        "nome": "X", "email": "x@x.com", "senha_provisoria": "curta", "is_admin": False})
    assert r.status_code == 400 and "10" in r.json()["detail"]
    assert len(db.tables["app_users"]) == 1


def test_editar_nome_email_e_papel(client, db, admin):
    b = _mk("b@x.com")
    r = client.patch(f"/api/usuarios/{b['id']}", json={"nome": "Beto", "email": "beto@x.com", "is_admin": True})
    assert r.status_code == 200
    assert r.json()["nome"] == "Beto" and r.json()["email"] == "beto@x.com" and r.json()["is_admin"]
    assert len(_eventos(db, "papel_alterado")) == 1


def test_editar_email_duplicado_409(client, db, admin):
    b = _mk("b@x.com")
    r = client.patch(f"/api/usuarios/{b['id']}", json={"email": "admin@x.com"})
    assert r.status_code == 409 and "e-mail" in r.json()["detail"]


def test_desativar_e_reativar(client, db, admin):
    b = _mk("b@x.com")
    r = client.patch(f"/api/usuarios/{b['id']}", json={"ativo": False})
    assert r.status_code == 200 and r.json()["ativo"] is False
    assert len(_eventos(db, "usuario_desativado")) == 1
    r = client.patch(f"/api/usuarios/{b['id']}", json={"ativo": True})
    assert r.json()["ativo"] is True and len(_eventos(db, "usuario_reativado")) == 1


def test_patch_sem_mudanca_nao_gera_evento(client, db, admin):
    b = _mk("b@x.com")
    client.patch(f"/api/usuarios/{b['id']}", json={"ativo": True, "is_admin": False})
    assert not _eventos(db, "usuario_desativado") and not _eventos(db, "papel_alterado")


def test_admin_nao_desativa_a_si_mesmo(client, db, admin):
    r = client.patch(f"/api/usuarios/{admin['id']}", json={"ativo": False})
    assert r.status_code == 409
    assert users.get_user_by_id(admin["id"])["ativo"] is True


def test_admin_nao_remove_proprio_papel(client, db, admin):
    _mk("c@x.com", is_admin=True)
    r = client.patch(f"/api/usuarios/{admin['id']}", json={"is_admin": False})
    assert r.status_code == 409
    assert users.get_user_by_id(admin["id"])["is_admin"] is True
    assert not _eventos(db, "papel_alterado")


def test_nao_deixa_sistema_sem_admin_ativo(client, db, admin, monkeypatch):
    # Admin de sessão fictício (auth desativada, id 0) tentando mexer no único admin real.
    unico = _mk("u@x.com", is_admin=True)
    db.tables["app_users"].remove(next(r for r in db.tables["app_users"] if r["email"] == "admin@x.com"))
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", True)
    for body in ({"ativo": False}, {"is_admin": False}):
        r = client.patch(f"/api/usuarios/{unico['id']}", json=body)
        assert r.status_code == 409
    assert users.get_user_by_id(unico["id"])["ativo"] and users.get_user_by_id(unico["id"])["is_admin"]


def test_redefinir_senha(client, db, admin):
    b = _mk("b@x.com")
    r = client.post(f"/api/usuarios/{b['id']}/redefinir-senha", json={"senha_provisoria": "nova-senha-123"})
    assert r.status_code == 204
    novo = users.get_user_by_id(b["id"])
    assert novo["deve_trocar_senha"] is True
    assert users.verify_password("nova-senha-123", novo["senha_hash"])
    ev = _eventos(db, "senha_redefinida")
    assert len(ev) == 1 and ev[0]["user_id"] == b["id"] and ev[0]["email_tentado"] == "admin@x.com"


def test_redefinir_senha_curta_400(client, db, admin):
    b = _mk("b@x.com")
    r = client.post(f"/api/usuarios/{b['id']}/redefinir-senha", json={"senha_provisoria": "curta"})
    assert r.status_code == 400
    assert users.verify_password(SENHA, users.get_user_by_id(b["id"])["senha_hash"])


def test_id_inexistente_404(client, db, admin):
    assert client.patch("/api/usuarios/999", json={"nome": "Z"}).status_code == 404
    assert client.post("/api/usuarios/999/redefinir-senha",
                       json={"senha_provisoria": SENHA}).status_code == 404


def test_ip_do_evento_usa_x_forwarded_for(client, db, admin):
    client.post("/api/usuarios", json={"nome": "X", "email": "x@x.com", "senha_provisoria": SENHA,
                                       "is_admin": False}, headers={"x-forwarded-for": "9.9.9.9, 1.1.1.1"})
    assert _eventos(db, "usuario_criado")[0]["ip"] == "9.9.9.9"
