from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

import supabase_client
import points_engine

router = APIRouter()


class CampoInput(BaseModel):
    nome: str
    tipo: str  # 'texto' | 'pontuacao'
    ordem: int = 0


class DesafioCreate(BaseModel):
    nome: str
    contabilizar_pontos: bool = True
    campos: list[CampoInput]


class DesafioUpdate(BaseModel):
    nome: str
    contabilizar_pontos: bool
    campos: list[CampoInput]


class RegistroCreate(BaseModel):
    clan: str
    valores: dict[str, Any]


@router.get("")
def listar_desafios():
    """Lista todos os desafios com seus campos e contagem de registros."""
    desafios = supabase_client.list_desafios()
    result = []
    for d in desafios:
        campos = supabase_client.list_desafio_campos(d["id"])
        registros = supabase_client.list_desafio_registros(d["id"])
        result.append({**d, "campos": campos, "total_registros": len(registros)})
    return result


@router.post("")
def criar_desafio(body: DesafioCreate):
    """Cria um novo desafio com seus campos."""
    desafio = supabase_client.create_desafio(body.nome, body.contabilizar_pontos)
    campos_data = [
        {"desafio_id": desafio["id"], "nome": c.nome, "tipo": c.tipo, "ordem": c.ordem}
        for c in body.campos
    ]
    campos = supabase_client.insert_desafio_campos(campos_data) if campos_data else []
    return {**desafio, "campos": campos, "total_registros": 0}


@router.put("/{desafio_id}")
def editar_desafio(desafio_id: int, body: DesafioUpdate):
    """Edita nome, modo de contabilização e campos. Recalcula registros existentes."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    old_contabilizar = desafio["contabilizar_pontos"]
    new_contabilizar = body.contabilizar_pontos

    registros = supabase_client.list_desafio_registros(desafio_id)

    # Substituir todos os campos
    supabase_client.delete_desafio_campos(desafio_id)
    campos_data = [
        {"desafio_id": desafio_id, "nome": c.nome, "tipo": c.tipo, "ordem": c.ordem}
        for c in body.campos
    ]
    new_campos = supabase_client.insert_desafio_campos(campos_data) if campos_data else []

    # Recalcular cada registro e aplicar deltas no total do clã
    for reg in registros:
        old_total = reg["total_pontos"]
        new_total = points_engine.calculate_desafio_pontos(new_campos, reg["valores"])
        supabase_client.update_desafio_registro_pontos(reg["id"], reg["valores"], new_total)

        if old_contabilizar and new_contabilizar:
            # Ambos true: aplicar apenas o delta
            delta = new_total - old_total
            if delta != 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], delta)
        elif old_contabilizar and not new_contabilizar:
            # true → false: descontar pontos antigos
            if old_total > 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], -old_total)
        elif not old_contabilizar and new_contabilizar:
            # false → true: adicionar novos pontos
            if new_total > 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], new_total)
        # false → false: nenhum efeito no ranking

    updated = supabase_client.update_desafio(desafio_id, body.nome, new_contabilizar)
    return {**updated, "campos": new_campos, "total_registros": len(registros)}


@router.delete("/{desafio_id}")
def excluir_desafio(desafio_id: int):
    """Remove o desafio. Se contabilizar_pontos=true, desconta pontos dos clãs."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    if desafio["contabilizar_pontos"]:
        registros = supabase_client.list_desafio_registros(desafio_id)
        for reg in registros:
            if reg["total_pontos"] > 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], -reg["total_pontos"])

    supabase_client.delete_desafio(desafio_id)
    return {"mensagem": f"Desafio '{desafio['nome']}' excluído com sucesso."}


@router.get("/{desafio_id}/registros")
def listar_registros(desafio_id: int):
    """Lista os registros de clãs de um desafio."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return supabase_client.list_desafio_registros(desafio_id)


@router.post("/{desafio_id}/registros")
def criar_registro(desafio_id: int, body: RegistroCreate):
    """Registra pontos de um clã. Soma ao total geral se contabilizar_pontos=true."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    existing = supabase_client.get_desafio_registro_by_clan(desafio_id, body.clan)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Clã '{body.clan}' já possui registro neste desafio.",
        )

    campos = supabase_client.list_desafio_campos(desafio_id)
    total_pontos = points_engine.calculate_desafio_pontos(campos, body.valores)

    registro = supabase_client.create_desafio_registro(
        desafio_id, body.clan, body.valores, total_pontos
    )

    if desafio["contabilizar_pontos"] and total_pontos > 0:
        supabase_client.add_delta_to_clan_total(body.clan, total_pontos)

    return registro


@router.delete("/{desafio_id}/registros/{registro_id}")
def excluir_registro(desafio_id: int, registro_id: int):
    """Remove registro de um clã. Desconta pontos se contabilizar_pontos=true."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    registro = supabase_client.get_desafio_registro_by_id(registro_id)
    if not registro or registro["desafio_id"] != desafio_id:
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    if desafio["contabilizar_pontos"] and registro["total_pontos"] > 0:
        supabase_client.add_delta_to_clan_total(registro["clan"], -registro["total_pontos"])

    supabase_client.delete_desafio_registro(registro_id)
    return {"mensagem": f"Registro do clã '{registro['clan']}' excluído."}
