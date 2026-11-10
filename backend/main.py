import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config  # noqa: F401 — valida variáveis de ambiente ao importar
from logging_config import configure_logging
import session_auth
import users
from routers import (
    auth as auth_router,
    contabilidade,
    registros,
    clans,
    coaches,
    coach_clas,
    desafios,
    desafio_auditoria,
    desafio_import,
)
from routers import usuarios as usuarios_router

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Semeia o primeiro admin (idempotente). Falha no banco não derruba a API.
    if not config.APP_AUTH_DISABLED:
        try:
            users.seed_first_admin()
        except Exception:
            logger.exception("Falha ao semear o administrador inicial")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Calcula Pontos Ultimate",
    description="Sistema de contabilidade de pontos para o desafio de clãs IGT ULTIMATE",
    version="1.0.0",
    # Toda rota da API exige sessão, exceto /api/health e /api/auth/login.
    dependencies=[Depends(session_auth.require_session)],
)

# CORS com credenciais (cookie de sessão): origens explícitas, nunca "*".
# O middleware responde ao preflight (OPTIONS) antes da autenticação.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api/auth", tags=["Autenticação"])
app.include_router(usuarios_router.router, prefix="/api/usuarios", tags=["Usuários"])
app.include_router(contabilidade.router, prefix="/api/contabilidade", tags=["Contabilidade"])
app.include_router(registros.router, prefix="/api/registros", tags=["Registros"])
app.include_router(clans.router, prefix="/api/clans", tags=["Clãs"])
app.include_router(coaches.router, prefix="/api/coaches", tags=["Coaches"])
app.include_router(coach_clas.router, prefix="/api/coach-clas", tags=["Coaches"])

# `desafios.router` (5 escritas bloqueadas com HTTP 410 — issue #17) e
# `desafio_auditoria.router` (7 leituras de auditoria — issue #18) são dois
# APIRouters mantidos em arquivos separados por responsabilidade, montados
# aqui no mesmo prefixo "/api/desafios" via duas chamadas a `include_router`.
# Isso é seguro porque não há colisão de (método, path) entre eles: todas as
# rotas de `desafios.router` são POST/PUT/DELETE e todas as de
# `desafio_auditoria.router` são GET.
app.include_router(desafios.router, prefix="/api/desafios", tags=["Desafios"])
app.include_router(desafio_auditoria.router, prefix="/api/desafios", tags=["Desafios"])
app.include_router(desafio_import.router, prefix="/api/desafios/importar", tags=["Desafios"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve frontend estático — deve ser montado após todas as rotas /api
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.BACKEND_HOST, port=config.BACKEND_PORT, reload=True)
