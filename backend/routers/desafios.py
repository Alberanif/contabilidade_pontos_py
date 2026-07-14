from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from datetime import date

import supabase_client
import points_engine

router = APIRouter()

NOME_CAMPO_PONTOS = "Pontos"


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


def _validar_periodo_e_registros(
    data_inicio: date, data_fim: date, registros: list[RegistroClanInput]
) -> None:
    if data_fim < data_inicio:
        raise HTTPException(
            status_code=400, detail="data_fim deve ser maior ou igual a data_inicio"
        )
    clans = [r.clan for r in registros]
    if len(clans) != len(set(clans)):
        raise HTTPException(
            status_code=400,
            detail="Um mesmo clã não pode aparecer duas vezes na lista de registros",
        )


def _ensure_campo_pontos(desafio_id: int) -> dict:
    """Garante que o desafio tenha exatamente um campo implícito 'Pontos'
    (tipo pontuacao). Se os campos atuais forem diferentes (desafio legado
    com campos customizados), apaga todos e recria o campo implícito —
    essa é a conversão permanente para o novo formato."""
    campos = supabase_client.list_desafio_campos(desafio_id)
    if len(campos) == 1 and campos[0]["nome"] == NOME_CAMPO_PONTOS and campos[0]["tipo"] == "pontuacao":
        return campos[0]
    supabase_client.delete_desafio_campos(desafio_id)
    novos = supabase_client.insert_desafio_campos(
        [{"desafio_id": desafio_id, "nome": NOME_CAMPO_PONTOS, "tipo": "pontuacao", "ordem": 0}]
    )
    return novos[0]


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
    """Cria um novo desafio manual com período e registros de clã/pontuação."""
    _validar_periodo_e_registros(body.data_inicio, body.data_fim, body.registros)

    desafio = supabase_client.create_desafio(
        body.nome,
        body.contabilizar_pontos,
        body.data_fim,
        data_inicio=body.data_inicio,
        data_fim=body.data_fim,
        origem="manual",
    )
    campo_pontos = _ensure_campo_pontos(desafio["id"])

    for r in body.registros:
        supabase_client.create_desafio_registro(
            desafio["id"], r.clan, {str(campo_pontos["id"]): r.pontos}, r.pontos
        )
        if body.contabilizar_pontos and r.pontos > 0:
            supabase_client.add_delta_to_clan_total(r.clan, r.pontos)

    return {**desafio, "campos": [campo_pontos], "total_registros": len(body.registros)}


@router.put("/{desafio_id}")
def editar_desafio(desafio_id: int, body: DesafioUpdate):
    """Edita nome, período, modo de contabilização e registros de clã/pontuação.

    Desafios legados com campos customizados são convertidos para o campo
    implícito único 'Pontos' ao serem salvos por aqui (ver _ensure_campo_pontos).
    """
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    if desafio.get("origem") == "csv_import":
        raise HTTPException(
            status_code=400,
            detail="Desafios importados via CSV são editados pelo wizard de reimportação, não por este formulário.",
        )

    _validar_periodo_e_registros(body.data_inicio, body.data_fim, body.registros)

    old_contabilizar = desafio["contabilizar_pontos"]
    new_contabilizar = body.contabilizar_pontos

    old_registros = supabase_client.list_desafio_registros(desafio_id)
    diff = points_engine.diff_desafio_registros(
        [
            {"id": r["id"], "clan": r["clan"], "total_pontos": r["total_pontos"]}
            for r in old_registros
        ],
        [{"clan": r.clan, "pontos": r.pontos} for r in body.registros],
        old_contabilizar,
        new_contabilizar,
    )

    campo_pontos = _ensure_campo_pontos(desafio_id)

    for registro_id in diff["to_delete"]:
        supabase_client.delete_desafio_registro(registro_id)

    for item in diff["to_create"]:
        supabase_client.create_desafio_registro(
            desafio_id, item["clan"], {str(campo_pontos["id"]): item["pontos"]}, item["pontos"]
        )

    for item in diff["to_update"]:
        supabase_client.update_desafio_registro_pontos(
            item["id"], {str(campo_pontos["id"]): item["pontos"]}, item["pontos"]
        )

    for clan, delta in diff["clan_deltas"].items():
        supabase_client.add_delta_to_clan_total(clan, delta)

    updated = supabase_client.update_desafio(
        desafio_id,
        body.nome,
        new_contabilizar,
        body.data_fim,
        data_inicio=body.data_inicio,
        data_fim=body.data_fim,
    )
    return {**updated, "campos": [campo_pontos], "total_registros": len(body.registros)}


@router.delete("/{desafio_id}")
def excluir_desafio(desafio_id: int):
    """Remove o desafio. Se contabilizar_pontos=true, desconta pontos dos clãs e coaches."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    if desafio["contabilizar_pontos"]:
        registros = supabase_client.list_desafio_registros(desafio_id)
        for reg in registros:
            if reg["total_pontos"] > 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], -reg["total_pontos"])

        registros_coach = supabase_client.list_desafio_registros_coach(desafio_id)
        for reg in registros_coach:
            if reg["total_pontos"] > 0:
                supabase_client.add_delta_to_coach_total(reg["coach"], -reg["total_pontos"])

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
