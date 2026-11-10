"""Usuários da aplicação: hash de senha, CRUD em `app_users` e semeadura do admin.

Senhas só existem em texto puro em memória: o banco guarda apenas o hash bcrypt
e nada aqui as registra em log. As funções públicas `create_user`, `list_users`
e `update_user` devolvem o usuário SEM `senha_hash`; só `get_user_by_email` e
`get_user_by_id` o incluem (necessário para verificar login).
"""

import base64
import hashlib
import logging
from datetime import datetime, timezone

import bcrypt

import config
from supabase_client import _get_client

logger = logging.getLogger(__name__)

TABLE_USERS = "app_users"
TABLE_AUTH_EVENTS = "auth_events"
MIN_PASSWORD_LENGTH = 10

_UPDATABLE = {"nome", "email", "is_admin", "ativo", "deve_trocar_senha", "ultimo_login_em"}


class SenhaCurtaError(ValueError):
    """Senha com menos de MIN_PASSWORD_LENGTH caracteres."""


class EmailDuplicadoError(ValueError):
    """Já existe usuário com este e-mail (sem diferenciar maiúsculas)."""


# --- senha ---------------------------------------------------------------


def _prehash(senha: str) -> bytes:
    # bcrypt ignora/rejeita bytes além de 72; o SHA-256 em base64 (44 bytes)
    # torna qualquer tamanho de senha seguro e sem truncamento silencioso.
    return base64.b64encode(hashlib.sha256(senha.encode("utf-8")).digest())


def _hash(senha: str) -> str:
    return bcrypt.hashpw(_prehash(senha), bcrypt.gensalt()).decode("ascii")


def hash_password(senha: str) -> str:
    """Valida o tamanho mínimo e devolve o hash bcrypt (com salt)."""
    if len(senha) < MIN_PASSWORD_LENGTH:
        raise SenhaCurtaError(
            f"A senha deve ter no mínimo {MIN_PASSWORD_LENGTH} caracteres."
        )
    return _hash(senha)


def verify_password(senha: str, senha_hash: str) -> bool:
    """True se `senha` corresponde ao hash; hash inválido/vazio retorna False."""
    try:
        return bcrypt.checkpw(_prehash(senha), senha_hash.encode("ascii"))
    except (ValueError, TypeError, AttributeError, UnicodeError):
        return False


# --- usuários ------------------------------------------------------------


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "senha_hash"}


def _is_unique_violation(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "duplicate" in msg or "unique" in msg or "23505" in msg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_user(email, nome, senha_hash, is_admin, deve_trocar_senha) -> dict:
    payload = {
        "email": email,
        "nome": nome,
        "senha_hash": senha_hash,
        "is_admin": is_admin,
        "ativo": True,
        "deve_trocar_senha": deve_trocar_senha,
    }
    try:
        res = _get_client().table(TABLE_USERS).insert(payload).execute()
    except Exception as exc:
        if _is_unique_violation(exc):
            raise EmailDuplicadoError(f"E-mail já cadastrado: {email}") from exc
        raise
    return _public(res.data[0])


def create_user(
    email: str,
    nome: str,
    senha: str,
    is_admin: bool = False,
    deve_trocar_senha: bool = True,
) -> dict:
    """Cria o usuário (ativo). Levanta SenhaCurtaError / EmailDuplicadoError."""
    senha_hash = hash_password(senha)
    return _insert_user(normalize_email(email), nome, senha_hash, is_admin, deve_trocar_senha)


def get_user_by_email(email: str) -> dict | None:
    """Usuário (com `senha_hash`) pelo e-mail, sem diferenciar maiúsculas."""
    res = (
        _get_client()
        .table(TABLE_USERS)
        .select("*")
        .eq("email", normalize_email(email))
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def get_user_by_id(user_id: int) -> dict | None:
    """Usuário (com `senha_hash`) pelo id."""
    res = _get_client().table(TABLE_USERS).select("*").eq("id", user_id).limit(1).execute()
    return res.data[0] if res.data else None


def list_users() -> list[dict]:
    """Todos os usuários, sem `senha_hash`, ordenados por nome."""
    res = _get_client().table(TABLE_USERS).select("*").order("nome").execute()
    return [_public(r) for r in res.data]


def update_user(user_id: int, *, senha: str | None = None, **campos) -> dict | None:
    """Atualiza campos permitidos (nome, email, is_admin, ativo, deve_trocar_senha,
    ultimo_login_em) e/ou redefine a senha. Retorna o usuário sem hash, ou None
    se não existir. Campos desconhecidos levantam TypeError."""
    desconhecidos = set(campos) - _UPDATABLE
    if desconhecidos:
        raise TypeError(f"Campos não atualizáveis: {', '.join(sorted(desconhecidos))}")
    payload = dict(campos)
    if "email" in payload:
        payload["email"] = normalize_email(payload["email"])
    if senha is not None:
        payload["senha_hash"] = hash_password(senha)
    payload["atualizado_em"] = _now()
    try:
        res = _get_client().table(TABLE_USERS).update(payload).eq("id", user_id).execute()
    except Exception as exc:
        if _is_unique_violation(exc):
            raise EmailDuplicadoError(f"E-mail já cadastrado: {payload.get('email')}") from exc
        raise
    return _public(res.data[0]) if res.data else None


def record_auth_event(
    tipo: str,
    email_tentado: str | None = None,
    user_id: int | None = None,
    ip: str | None = None,
) -> None:
    """Registra um evento de autenticação em `auth_events`."""
    _get_client().table(TABLE_AUTH_EVENTS).insert(
        {
            "tipo": tipo,
            "email_tentado": normalize_email(email_tentado) if email_tentado else None,
            "user_id": user_id,
            "ip": ip,
        }
    ).execute()


# --- semeadura -----------------------------------------------------------


def seed_first_admin() -> bool:
    """Se `app_users` estiver vazia, cria o admin com APP_USER / APP_PASSWORD
    (deve_trocar_senha=true). Idempotente. Retorna True se criou."""
    if not config.APP_PASSWORD:
        return False
    existente = _get_client().table(TABLE_USERS).select("id").limit(1).execute()
    if existente.data:
        return False
    email = normalize_email(config.APP_USER)
    # Semente ignora o mínimo de 10 caracteres: a troca é forçada no 1º login.
    try:
        _insert_user(email, "Administrador", _hash(config.APP_PASSWORD), True, True)
    except EmailDuplicadoError:
        return False  # corrida entre instâncias subindo juntas
    logger.info("Administrador inicial criado: %s", email)
    return True
