from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config  # noqa: F401 — valida variáveis de ambiente ao importar
from routers import contabilidade, registros, clans, coaches, desafios

app = FastAPI(
    title="Calcula Pontos Ultimate",
    description="Sistema de contabilidade de pontos para o desafio de clãs IGT ULTIMATE",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contabilidade.router, prefix="/api/contabilidade", tags=["Contabilidade"])
app.include_router(registros.router, prefix="/api/registros", tags=["Registros"])
app.include_router(clans.router, prefix="/api/clans", tags=["Clãs"])
app.include_router(coaches.router, prefix="/api/coaches", tags=["Coaches"])
app.include_router(desafios.router, prefix="/api/desafios", tags=["Desafios"])


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
