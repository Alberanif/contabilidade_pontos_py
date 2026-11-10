"""Issue #57: bloqueio de login por tentativas (e-mail e IP) e eventos."""
import threading
from types import SimpleNamespace

import pytest

from login_throttle import LOCK_SECONDS, LoginThrottle, client_ip, throttle
from tests.test_session_auth import SENHA, _criar, _login, _tipos, client, db  # noqa: F401


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture(autouse=True)
def _reset():
    throttle.reset()
    yield
    throttle.reset()


def test_cinco_falhas_bloqueiam_email():
    c = Clock()
    th = LoginThrottle(clock=c)
    for _ in range(4):
        th.record_failure("a@x.com", "1.1.1.1")
    assert not th.is_blocked("a@x.com", None)
    th.record_failure("a@x.com", "1.1.1.1")
    assert th.is_blocked("A@x.com", None)


def test_bloqueio_expira_apos_15_minutos():
    c = Clock()
    th = LoginThrottle(clock=c)
    for _ in range(5):
        th.record_failure("a@x.com", None)
    c.t += LOCK_SECONDS - 1
    assert th.is_blocked("a@x.com", None)
    c.t += 2
    assert not th.is_blocked("a@x.com", None)


def test_falhas_antigas_saem_da_janela():
    c = Clock()
    th = LoginThrottle(clock=c)
    for _ in range(4):
        th.record_failure("a@x.com", None)
    c.t += 15 * 60 + 1
    th.record_failure("a@x.com", None)
    assert not th.is_blocked("a@x.com", None)


def test_bloqueio_por_ip_trocando_de_email():
    th = LoginThrottle(clock=Clock())
    for i in range(5):
        th.record_failure(f"u{i}@x.com", "9.9.9.9")
    assert th.is_blocked("novo@x.com", "9.9.9.9")
    assert not th.is_blocked("novo@x.com", "8.8.8.8")


def test_sucesso_zera_contador_do_email():
    th = LoginThrottle(clock=Clock())
    for _ in range(4):
        th.record_failure("a@x.com", None)
    th.record_success("a@x.com")
    th.record_failure("a@x.com", None)
    assert not th.is_blocked("a@x.com", None)


def test_armazenamento_tem_limite():
    c = Clock()
    th = LoginThrottle(clock=c, max_keys=50)
    for i in range(500):
        th.record_failure(f"u{i}@x.com", None)
    assert len(th._failures) + len(th._blocked_until) <= 50


def test_thread_safe():
    th = LoginThrottle(clock=Clock())

    def work():
        for _ in range(50):
            th.record_failure("a@x.com", "1.1.1.1")
            th.is_blocked("a@x.com", "1.1.1.1")

    ts = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert th.is_blocked("a@x.com", None)


def _req(headers=None, host="10.0.0.1"):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=host) if host else None)


def test_client_ip_usa_primeiro_x_forwarded_for():
    assert client_ip(_req({"x-forwarded-for": "2.2.2.2, 3.3.3.3"})) == "2.2.2.2"


def test_client_ip_fallback_para_conexao():
    assert client_ip(_req()) == "10.0.0.1"
    assert client_ip(_req(host=None)) is None


def test_login_bloqueia_com_429_mesmo_com_senha_correta(client, db):
    _criar(db)
    for _ in range(5):
        assert _login(client, senha="errada").status_code == 401
    assert _login(client).status_code == 429
    tipos = _tipos(db)
    assert tipos.count("login_falha") == 5
    assert tipos.count("login_bloqueado") == 1
    assert "login" not in tipos


def test_login_bloqueia_por_ip_trocando_email(client, db):
    _criar(db)
    for i in range(5):
        _login(client, email=f"x{i}@x.com", senha="errada")
    assert _login(client).status_code == 429


def test_eventos_registram_ip_do_forwarded_for(client, db):
    _criar(db)
    r = client.post(
        "/api/auth/login",
        json={"email": "ana@x.com", "senha": SENHA},
        headers={"X-Forwarded-For": "7.7.7.7, 10.0.0.2"},
    )
    assert r.status_code == 200
    ev = db.tables["auth_events"][-1]
    assert ev["tipo"] == "login" and ev["ip"] == "7.7.7.7"


def test_login_ok_zera_falhas_do_email(client, db):
    _criar(db)

    def tenta(senha, ip):
        return client.post(
            "/api/auth/login",
            json={"email": "ana@x.com", "senha": senha},
            headers={"X-Forwarded-For": ip},
        ).status_code

    for _ in range(4):
        assert tenta("errada", "1.1.1.1") == 401
    assert tenta(SENHA, "2.2.2.2") == 200
    for _ in range(4):
        assert tenta("errada", "3.3.3.3") == 401
    assert tenta(SENHA, "4.4.4.4") == 200
