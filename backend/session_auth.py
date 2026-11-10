"""Sessão por cookie assinado (HMAC-SHA256) e dependências de autenticação.

Ponto de extensão para as demais rotas de autenticação/usuários:

    from session_auth import get_current_user, require_admin

    @router.get("/x")
    def x(user: dict = Depends(require_admin)): ...

A cada requisição o usuário é relido do banco (`users.get_user_by_id`): se foi
removido ou desativado, a sessão deixa de valer na hora. Com
`APP_AUTH_DISABLED=true` (dev/testes) `get_current_user` devolve um admin fictício.
"""
import hashlib
import hmac
import time

from fastapi import Depends, HTTPException, Request, Response

import config
import users

# Públicos: /api/health e /api/auth/login. Demais rotas exigem sessão.
PUBLIC_PATHS = {"/api/health", "/api/auth/login"}
# Rotas liberadas para quem ainda precisa trocar a senha provisória.
PASSWORD_CHANGE_ALLOWED_PATHS = {"/api/auth/me", "/api/auth/logout", "/api/auth/trocar-senha"}

# Hash bcrypt fictício para igualar o tempo de resposta quando o e-mail não existe.
DUMMY_HASH = users.hash_password("senha-ficticia-para-tempo-constante")

_USUARIO_CAMPOS = (
    "id", "email", "nome", "is_admin", "ativo", "deve_trocar_senha",
    "ultimo_login_em", "criado_em",
)

_DEV_USER = {
    "id": 0, "email": "dev@local", "nome": "Dev (auth desativada)", "is_admin": True,
    "ativo": True, "deve_trocar_senha": False, "ultimo_login_em": None, "criado_em": None,
}


def to_usuario(row: dict) -> dict:
    """Objeto `Usuario` do contrato da API (nunca inclui senha_hash)."""
    return {k: row.get(k) for k in _USUARIO_CAMPOS}


# --- token ----------------------------------------------------------------


def _sign(payload: str) -> str:
    return hmac.new(config.SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(user_id: int, now: float | None = None) -> str:
    payload = f"{user_id}.{int(now if now is not None else time.time())}"
    return f"{payload}.{_sign(payload)}"


def read_session_token(token: str | None, now: float | None = None) -> int | None:
    """Id do usuário se a assinatura e a validade forem boas; senão None."""
    if not token or not config.SESSION_SECRET:
        return None
    payload, _, sig = token.rpartition(".")
    if not payload or not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        uid_s, iat_s = payload.split(".")
        uid, iat = int(uid_s), int(iat_s)
    except ValueError:
        return None
    if (now if now is not None else time.time()) - iat > config.SESSION_MAX_AGE:
        return None
    return uid


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        config.SESSION_COOKIE_NAME,
        create_session_token(user_id),
        max_age=config.SESSION_MAX_AGE,
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        config.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=config.SESSION_COOKIE_SECURE,
        samesite="lax",
    )


# --- dependências ---------------------------------------------------------


def get_current_user(request: Request, response: Response) -> dict:
    """Usuário autenticado (dict do banco, com senha_hash) ou 401.

    Renova o cookie (validade deslizante de 7 dias) a cada uso."""
    if config.APP_AUTH_DISABLED:
        return dict(_DEV_USER)
    uid = read_session_token(request.cookies.get(config.SESSION_COOKIE_NAME))
    user = users.get_user_by_id(uid) if uid is not None else None
    if not user or not user.get("ativo"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    set_session_cookie(response, user["id"])
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user


def require_session(request: Request, response: Response) -> None:
    """Dependência global do app: protege toda rota da API exceto as públicas."""
    path = request.url.path
    if path in PUBLIC_PATHS:
        return
    user = get_current_user(request, response)
    if user.get("deve_trocar_senha") and path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise HTTPException(status_code=403, detail="troca_de_senha_obrigatoria")
