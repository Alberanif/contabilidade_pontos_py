from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config  # noqa: F401 — valida variáveis de ambiente ao importar
from routers import contabilidade, registros, clans

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


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.BACKEND_HOST, port=config.BACKEND_PORT, reload=True)
