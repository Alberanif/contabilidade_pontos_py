# backend/routers/desafio_import.py
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter()

MENSAGEM_ESCRITA_BLOQUEADA = (
    "A planilha do Google Sheets é a fonte oficial de dados de desafios; "
    "este endpoint não aceita mais escritas."
)


def _bloquear_escrita_legada() -> None:
    """Bloqueia a importação legada de desafios via CSV (issue #17): a
    sincronização a partir da Google Sheet (`desafio_sync_service.sync_desafios`)
    é agora a única fonte de verdade para desafios. Levanta sempre HTTP 410."""
    raise HTTPException(status_code=410, detail=MENSAGEM_ESCRITA_BLOQUEADA)


@router.post("/preview")
def preview(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    config: str = Form(...),
):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Preview de importação CSV não é mais aceito."""
    _bloquear_escrita_legada()


@router.post("/confirmar")
def confirmar(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    config: str = Form(...),
):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Confirmação de importação CSV não é mais aceita."""
    _bloquear_escrita_legada()
