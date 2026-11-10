"""HTTP Basic Auth para API + frontend estático.

Lê `config` a cada requisição (não no import) para ser testável. `/api/health`
fica liberado para o healthcheck do Docker/Easypanel; preflight CORS (OPTIONS)
também passa, pois o navegador não envia credenciais nele.
"""
import base64
import binascii
import secrets

from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

import config

PUBLIC_PATHS = {"/api/health"}


def _credentials_ok(header: str | None) -> bool:
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, sep, password = decoded.partition(":")
    if not sep:
        return False
    # Ambas as comparações sempre executam (tempo constante).
    user_ok = secrets.compare_digest(user.encode(), config.APP_USER.encode())
    pass_ok = secrets.compare_digest(password.encode(), config.APP_PASSWORD.encode())
    return user_ok and pass_ok


class BasicAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or config.APP_AUTH_DISABLED:
            await self.app(scope, receive, send)
            return
        if scope["path"] in PUBLIC_PATHS or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if _credentials_ok(headers.get("authorization")):
            await self.app(scope, receive, send)
            return
        response = Response(
            "Autenticação necessária",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Calcula Pontos", charset="UTF-8"'},
        )
        await response(scope, receive, send)
