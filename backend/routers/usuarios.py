"""Gestão de usuários (issue #59). Todas as rotas exigem admin.

Eventos em `auth_events`: `users.record_auth_event` não tem campo de autor, e o
schema da migration não muda. Convenção: `user_id` = usuário ALVO da ação e
`email_tentado` = e-mail do ADMIN autor.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

import session_auth
import users

router = APIRouter(dependencies=[Depends(session_auth.require_admin)])

_NAO_ENCONTRADO = "Usuário não encontrado"
_EMAIL_DUPLICADO = "Já existe um usuário com este e-mail"
_AUTO_DESATIVAR = "Você não pode desativar a si mesmo"
_AUTO_REBAIXAR = "Você não pode remover o seu próprio papel de administrador"
_ULTIMO_ADMIN = "O sistema precisa manter ao menos um administrador ativo"


class UsuarioIn(BaseModel):
    nome: str = Field(min_length=1)
    email: str = Field(min_length=3)
    senha_provisoria: str
    is_admin: bool = False


class UsuarioPatch(BaseModel):
    nome: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=3)
    is_admin: bool | None = None
    ativo: bool | None = None


class SenhaProvisoriaIn(BaseModel):
    senha_provisoria: str


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _evento(tipo: str, admin: dict, alvo_id: int, request: Request) -> None:
    users.record_auth_event(
        tipo, email_tentado=admin.get("email"), user_id=alvo_id, ip=_client_ip(request)
    )


def _get_or_404(user_id: int) -> dict:
    alvo = users.get_user_by_id(user_id)
    if not alvo:
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    return alvo


def _senha_curta(exc: users.SenhaCurtaError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("")
def listar():
    return [session_auth.to_usuario(u) for u in users.list_users()]


@router.post("", status_code=201)
def criar(body: UsuarioIn, request: Request, admin: dict = Depends(session_auth.require_admin)):
    try:
        novo = users.create_user(
            body.email, body.nome.strip(), body.senha_provisoria,
            is_admin=body.is_admin, deve_trocar_senha=True,
        )
    except users.SenhaCurtaError as exc:
        raise _senha_curta(exc)
    except users.EmailDuplicadoError:
        raise HTTPException(status_code=409, detail=_EMAIL_DUPLICADO)
    _evento("usuario_criado", admin, novo["id"], request)
    return session_auth.to_usuario(novo)


@router.patch("/{user_id}")
def editar(
    user_id: int, body: UsuarioPatch, request: Request,
    admin: dict = Depends(session_auth.require_admin),
):
    alvo = _get_or_404(user_id)
    campos = body.model_dump(exclude_unset=True, exclude_none=True)
    novo_ativo = campos.get("ativo", alvo["ativo"])
    novo_admin = campos.get("is_admin", alvo["is_admin"])
    if alvo["id"] == admin["id"]:
        if not novo_ativo:
            raise HTTPException(status_code=409, detail=_AUTO_DESATIVAR)
        if not novo_admin:
            raise HTTPException(status_code=409, detail=_AUTO_REBAIXAR)
    if alvo["ativo"] and alvo["is_admin"] and not (novo_ativo and novo_admin):
        outros = [
            u for u in users.list_users()
            if u["id"] != alvo["id"] and u["ativo"] and u["is_admin"]
        ]
        if not outros:
            raise HTTPException(status_code=409, detail=_ULTIMO_ADMIN)
    try:
        atualizado = users.update_user(user_id, **campos)
    except users.EmailDuplicadoError:
        raise HTTPException(status_code=409, detail=_EMAIL_DUPLICADO)
    if atualizado is None:
        raise HTTPException(status_code=404, detail=_NAO_ENCONTRADO)
    if novo_ativo != alvo["ativo"]:
        _evento("usuario_reativado" if novo_ativo else "usuario_desativado", admin, user_id, request)
    if novo_admin != alvo["is_admin"]:
        _evento("papel_alterado", admin, user_id, request)
    return session_auth.to_usuario(atualizado)


@router.post("/{user_id}/redefinir-senha", status_code=204)
def redefinir_senha(
    user_id: int, body: SenhaProvisoriaIn, request: Request,
    admin: dict = Depends(session_auth.require_admin),
):
    _get_or_404(user_id)
    try:
        users.update_user(user_id, senha=body.senha_provisoria, deve_trocar_senha=True)
    except users.SenhaCurtaError as exc:
        raise _senha_curta(exc)
    _evento("senha_redefinida", admin, user_id, request)
    return Response(status_code=204)
