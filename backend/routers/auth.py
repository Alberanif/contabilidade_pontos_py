"""Login, logout e usuário da sessão (issue #56)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import session_auth
import users

router = APIRouter()

_LOGIN_INVALIDO = "E-mail ou senha inválidos"


class LoginIn(BaseModel):
    email: str
    senha: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    user = users.get_user_by_email(body.email)
    # Sempre verifica um hash (fictício se o usuário não existe): tempo constante.
    senha_ok = users.verify_password(
        body.senha, user["senha_hash"] if user else session_auth.DUMMY_HASH
    )
    if not (user and user.get("ativo") and senha_ok):
        users.record_auth_event(
            "login_falha", email_tentado=body.email, user_id=user["id"] if user else None
        )
        raise HTTPException(status_code=401, detail=_LOGIN_INVALIDO)
    agora = datetime.now(timezone.utc).isoformat()
    atualizado = users.update_user(user["id"], ultimo_login_em=agora) or user
    users.record_auth_event("login", email_tentado=body.email, user_id=user["id"])
    session_auth.set_session_cookie(response, user["id"])
    return session_auth.to_usuario(atualizado)


@router.post("/logout", status_code=204)
def logout():
    response = Response(status_code=204)
    session_auth.clear_session_cookie(response)
    return response


@router.get("/me")
def me(user: dict = Depends(session_auth.get_current_user)):
    return session_auth.to_usuario(user)
