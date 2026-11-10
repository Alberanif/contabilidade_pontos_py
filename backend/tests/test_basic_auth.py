"""Basic Auth: 401 sem credencial, 200 com, /api/health público, startup sem senha."""
import base64
import importlib
import os
import sys

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
from main import app


def _basic(user, pwd):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "APP_AUTH_DISABLED", False)
    monkeypatch.setattr(config, "APP_USER", "admin")
    monkeypatch.setattr(config, "APP_PASSWORD", "s3nha-ç")
    return TestClient(app)


def test_sem_credencial_retorna_401_com_challenge(client):
    r = client.get("/api/clans/")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")


def test_credencial_errada_retorna_401(client):
    assert client.get("/api/clans/", headers=_basic("admin", "errada")).status_code == 401
    assert client.get("/api/clans/", headers=_basic("outro", "s3nha-ç")).status_code == 401


def test_header_malformado_retorna_401(client):
    assert client.get("/api/clans/", headers={"Authorization": "Basic !!!"}).status_code == 401


def test_credencial_correta_passa_pela_autenticacao(client):
    r = client.get("/api/health", headers=_basic("admin", "s3nha-ç"))
    assert r.status_code == 200


def test_health_e_publico(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_preflight_cors_nao_exige_credencial(client):
    r = client.options(
        "/api/clans/",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code == 200


def test_cors_nao_e_mais_wildcard(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert r.headers.get("access-control-allow-origin") != "*"
    assert "access-control-allow-origin" not in r.headers


def test_startup_recusa_sem_senha(monkeypatch):
    monkeypatch.setenv("APP_AUTH_DISABLED", "false")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    try:
        with pytest.raises(ValueError, match="APP_PASSWORD"):
            importlib.reload(config)
    finally:
        monkeypatch.undo()
        importlib.reload(config)
