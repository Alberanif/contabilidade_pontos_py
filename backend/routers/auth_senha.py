"""Troca de senha do próprio usuário (issue #58)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import session_auth
import users

router = APIRouter()


class TrocarSenhaIn(BaseModel):
    senha_atual: str
    nova_senha: str


@router.post("/trocar-senha", status_code=204)
def trocar_senha(body: TrocarSenhaIn, user: dict = Depends(session_auth.get_current_user)):
    if not users.verify_password(body.senha_atual, user.get("senha_hash", "")):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if body.nova_senha == body.senha_atual:
        raise HTTPException(status_code=400, detail="A nova senha deve ser diferente da atual")
    try:
        users.update_user(user["id"], senha=body.nova_senha, deve_trocar_senha=False)
    except users.SenhaCurtaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    users.record_auth_event("senha_trocada", email_tentado=user.get("email"), user_id=user["id"])
    return Response(status_code=204)
