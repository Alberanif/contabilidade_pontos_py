from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from datetime import date

import supabase_client

router = APIRouter()

MENSAGEM_ESCRITA_BLOQUEADA = (
    "A planilha do Google Sheets é a fonte oficial de dados de desafios; "
    "este endpoint não aceita mais escritas."
)


def _bloquear_escrita_legada() -> None:
    """Bloqueia os handlers de escrita legados de desafios (issue #17): a
    sincronização a partir da Google Sheet (`desafio_sync_service.sync_desafios`)
    é agora a única fonte de verdade para desafios. Levanta sempre HTTP 410."""
    raise HTTPException(status_code=410, detail=MENSAGEM_ESCRITA_BLOQUEADA)


class RegistroClanInput(BaseModel):
    clan: str
    pontos: int = Field(ge=0)


class DesafioCreate(BaseModel):
    nome: str
    contabilizar_pontos: bool = True
    data_inicio: date
    data_fim: date
    registros: list[RegistroClanInput] = []


class DesafioUpdate(BaseModel):
    nome: str
    contabilizar_pontos: bool
    data_inicio: date
    data_fim: date
    registros: list[RegistroClanInput] = []


class RegistroCreate(BaseModel):
    clan: str
    valores: dict[str, Any]


@router.get("")
def listar_desafios():
    """Lista todos os desafios com seus campos e contagem de registros."""
    desafios = supabase_client.list_desafios()
    all_campos = supabase_client.list_all_desafio_campos()
    registro_counts = supabase_client.count_desafio_registros_by_desafio()

    campos_by_desafio: dict[int, list[dict]] = {}
    for c in all_campos:
        campos_by_desafio.setdefault(c["desafio_id"], []).append(c)

    return [
        {
            **d,
            "campos": campos_by_desafio.get(d["id"], []),
            "total_registros": registro_counts.get(d["id"], 0),
        }
        for d in desafios
    ]


@router.post("")
def criar_desafio(body: DesafioCreate):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Criação manual de desafios não é mais aceita."""
    _bloquear_escrita_legada()


@router.put("/{desafio_id}")
def editar_desafio(desafio_id: int, body: DesafioUpdate):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Edição manual de desafios não é mais aceita."""
    _bloquear_escrita_legada()


@router.delete("/{desafio_id}")
def excluir_desafio(desafio_id: int):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Exclusão manual de desafios não é mais aceita."""
    _bloquear_escrita_legada()


@router.get("/{desafio_id}/registros")
def listar_registros(desafio_id: int):
    """Lista os registros de clãs de um desafio."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return supabase_client.list_desafio_registros(desafio_id)


@router.post("/{desafio_id}/registros")
def criar_registro(desafio_id: int, body: RegistroCreate):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Criação manual de registros não é mais aceita."""
    _bloquear_escrita_legada()


@router.delete("/{desafio_id}/registros/{registro_id}")
def excluir_registro(desafio_id: int, registro_id: int):
    """Bloqueado (issue #17): a Google Sheet de desafios é a única fonte de
    verdade. Exclusão manual de registros não é mais aceita."""
    _bloquear_escrita_legada()
