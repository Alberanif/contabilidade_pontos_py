"""Issue #58: troca de senha e bloqueio por senha provisória."""
from tests.test_session_auth import (  # noqa: F401  (fixtures reutilizadas; define o ambiente)
    SENHA, _criar, _login, _tipos, client, db,
)
import users
from main import app

NOVA = "outra-senha-456"
URL = "/api/auth/trocar-senha"


@app.get("/api/_teste_livre")
def _rota_livre():
    return {"ok": True}


def _trocar(client, atual=SENHA, nova=NOVA):
    return client.post(URL, json={"senha_atual": atual, "nova_senha": nova})


def test_troca_ok_204_limpa_flag_e_registra_evento(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    assert _trocar(client).status_code == 204
    u = users.get_user_by_id(1)
    assert u["deve_trocar_senha"] is False
    assert users.verify_password(NOVA, u["senha_hash"])
    assert "senha_trocada" in _tipos(db)
    assert _login(client, senha=NOVA).status_code == 200


def test_senha_atual_errada_400_e_nao_altera(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    antes = users.get_user_by_id(1)["senha_hash"]
    assert _trocar(client, atual="errada-errada-1").status_code == 400
    u = users.get_user_by_id(1)
    assert u["senha_hash"] == antes and u["deve_trocar_senha"] is True
    assert "senha_trocada" not in _tipos(db)


def test_nova_senha_curta_400(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    assert _trocar(client, nova="curta123").status_code == 400
    assert users.get_user_by_id(1)["deve_trocar_senha"] is True


def test_nova_igual_a_atual_400(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    assert _trocar(client, nova=SENHA).status_code == 400
    assert users.get_user_by_id(1)["deve_trocar_senha"] is True


def test_trocar_senha_exige_sessao(client):
    assert _trocar(client).status_code == 401


def test_bloqueio_por_senha_provisoria_e_liberacao_apos_troca(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    r = client.get("/api/_teste_livre")
    assert r.status_code == 403 and r.json()["detail"] == "troca_de_senha_obrigatoria"
    assert client.get("/api/auth/me").status_code == 200
    assert _trocar(client).status_code == 204
    # sem novo login
    assert client.get("/api/auth/me").json()["deve_trocar_senha"] is False
    assert client.get("/api/_teste_livre").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204


def test_logout_permitido_com_troca_pendente(client, db):
    _criar(db, deve_trocar_senha=True)
    _login(client)
    assert client.post("/api/auth/logout").status_code == 204
