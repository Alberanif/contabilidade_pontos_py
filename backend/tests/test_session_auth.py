"""Issue #56: login/logout/me, cookie de sessão assinado e proteção da API."""
import importlib
import os
import sys
import time
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

from fastapi import Depends
from fastapi.testclient import TestClient

import config
import session_auth
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


def _criar(db, email="ana@x.com", deve_trocar_senha=False):
    return users.create_user(email, "Ana", SENHA, deve_trocar_senha=deve_trocar_senha)


def _login(client, email="ana@x.com", senha=SENHA):
    return client.post("/api/auth/login", json={"email": email, "senha": senha})


def _tipos(db):
    return [e["tipo"] for e in db.tables.get("auth_events", [])]


def test_sem_sessao_api_retorna_401(client):
    assert client.get("/api/clans/").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_health_e_publico(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_login_correto_cria_cookie_e_devolve_usuario(client, db):
    _criar(db)
    r = _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "ana@x.com" and "senha_hash" not in body
    assert body["ultimo_login_em"]
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert "max-age=604800" in set_cookie
    assert client.get("/api/auth/me").json()["email"] == "ana@x.com"
    assert _tipos(db) == ["login"]


def test_cookie_secure_quando_configurado(client, db, monkeypatch):
    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", True)
    _criar(db)
    assert "secure" in _login(client).headers["set-cookie"].lower()


def test_login_incorreto_e_generico(client, db):
    _criar(db)
    errada = _login(client, senha="errada-errada-1")
    inexistente = _login(client, email="nao@x.com")
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json() == inexistente.json()
    assert "set-cookie" not in errada.headers
    assert _tipos(db) == ["login_falha", "login_falha"]


def test_login_usa_verify_password_mesmo_sem_usuario(client, db):
    with patch.object(session_auth.users, "verify_password", return_value=False) as vp:
        _login(client, email="nao@x.com")
    assert vp.call_count == 1


def test_usuario_inativo_nao_loga(client, db):
    u = _criar(db)
    users.update_user(u["id"], ativo=False)
    assert _login(client).status_code == 401


def test_desativar_derruba_acesso_na_hora(client, db):
    u = _criar(db)
    _login(client)
    assert client.get("/api/auth/me").status_code == 200
    users.update_user(u["id"], ativo=False)
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/clans/").status_code == 401


def test_usuario_removido_perde_acesso(client, db):
    _criar(db)
    _login(client)
    db.tables["app_users"].clear()
    assert client.get("/api/auth/me").status_code == 401


def test_logout_limpa_cookie(client, db):
    _criar(db)
    _login(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_logout_sem_sessao_e_401(client):
    # Só health e login são públicos.
    assert client.post("/api/auth/logout").status_code == 401


def test_cookie_adulterado_rejeitado(client, db):
    _criar(db)
    _login(client)
    valor = client.cookies.get(config.SESSION_COOKIE_NAME)
    client.cookies.set(config.SESSION_COOKIE_NAME, valor[:-2] + ("aa" if valor[-2:] != "aa" else "bb"))
    assert client.get("/api/auth/me").status_code == 401


def test_cookie_de_outro_segredo_rejeitado(client, db, monkeypatch):
    u = _criar(db)
    monkeypatch.setattr(config, "SESSION_SECRET", "outro")
    token = session_auth.create_session_token(u["id"])
    monkeypatch.setattr(config, "SESSION_SECRET", "segredo-de-teste")
    client.cookies.set(config.SESSION_COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401


def test_cookie_expirado_rejeitado(client, db):
    u = _criar(db)
    token = session_auth.create_session_token(u["id"], now=time.time() - 8 * 86400)
    client.cookies.set(config.SESSION_COOKIE_NAME, token)
    assert client.get("/api/auth/me").status_code == 401


def test_sessao_e_renovada_com_o_uso(client, db):
    u = _criar(db)
    token = session_auth.create_session_token(u["id"], now=time.time() - 6 * 86400)
    client.cookies.set(config.SESSION_COOKIE_NAME, token)
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert config.SESSION_COOKIE_NAME in r.headers["set-cookie"]


def test_deve_trocar_senha_bloqueia_rotas_exceto_me_logout(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    r = client.get("/api/clans/")
    assert r.status_code == 403 and r.json()["detail"] == "troca_de_senha_obrigatoria"
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204


def test_preflight_cors_nao_exige_sessao(client):
    r = client.options(
        "/api/clans/",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-credentials"] == "true"


def test_cors_nao_e_wildcard(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_require_admin(client, db):
    @app.get("/api/_teste_admin")
    def _rota(u=Depends(session_auth.require_admin)):
        return {"id": u["id"]}

    _criar(db)
    _login(client)
    assert client.get("/api/_teste_admin").status_code == 403
    users.update_user(1, is_admin=True)
    assert client.get("/api/_teste_admin").status_code == 200


def test_bypass_dev_devolve_admin_ficticio(monkeypatch):
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", True)
    r = TestClient(app).get("/api/auth/me")
    assert r.status_code == 200 and r.json()["is_admin"] is True


def test_startup_recusa_sem_session_secret(monkeypatch):
    monkeypatch.setenv("APP_AUTH_DISABLED", "false")
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    try:
        with pytest.raises(ValueError, match="SESSION_SECRET"):
            importlib.reload(config)
    finally:
        monkeypatch.undo()
        importlib.reload(config)
