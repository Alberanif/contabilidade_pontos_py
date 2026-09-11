"""API CRUD de vínculo coach -> clã (issue #4 / Task 4 de "Coaches por Clã").

Endpoints REST para listar, criar, atualizar e remover a linha de
`pontos_ultimate_coach_clas` de cada coach, consumidos pelo frontend de
administração. A camada de dados (`supabase_client.list_coach_clas` /
`upsert_coach_cla` / `delete_coach_cla`) já existe (Task 2); este router só
adiciona validação de request, resolução de alias e as regras de
409/404/422 que a camada de dados não trata (ela é um upsert simples, sem
detecção de conflito).

O nome de coach recebido em `POST`/`PUT` é sempre resolvido via
`coach_identity.resolve_coach()` antes de qualquer leitura/gravação, para
que um alias nunca cadastrado (variação de caixa/acento/espaço) não crie uma
segunda linha para o mesmo coach.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import coach_identity
import supabase_client

router = APIRouter()


Categoria = Literal[
    "Coach",
    "Coach Action",
    "Coach Pro",
    "Coach Hero",
    "Sem Categoria",
    "Novos ULTIMATES",
]


class CoachClaCreate(BaseModel):
    coach: str
    clan: str
    categoria: Categoria


class CoachClaUpdate(BaseModel):
    clan: str | None = None
    categoria: Categoria | None = None


def _buscar_por_canonico(coach_canonico: str) -> dict | None:
    """Busca a linha de vínculo de um coach pelo nome canônico, ou None se
    não existir. Não há um lookup pontual em `supabase_client`, então
    filtramos a lista completa aqui (volume esperado é pequeno — um coach
    por linha)."""
    for row in supabase_client.list_coach_clas():
        if row["coach_canonico"] == coach_canonico:
            return row
    return None


@router.get("")
def listar_coach_clas(clan: str | None = Query(None, description="Filtrar por clã")):
    """Lista todos os vínculos coach -> clã, com filtro opcional por clã."""
    return supabase_client.list_coach_clas(clan=clan)


@router.post("")
def criar_coach_cla(payload: CoachClaCreate):
    """Cria (ou atualiza in-place, se já existir com o mesmo clã) o vínculo
    de um coach a um clã. Retorna 409 se o coach (já resolvido ao nome
    canônico) já pertence a outro clã — mover de clã é feito via `PUT`, não
    `POST`."""
    alias_map = supabase_client.get_coach_alias_map()
    coach_canonico = coach_identity.resolve_coach(payload.coach, alias_map)

    existente = _buscar_por_canonico(coach_canonico)
    if existente is not None and existente["clan"] != payload.clan:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Coach '{coach_canonico}' já pertence ao clã '{existente['clan']}'. "
                "Use PUT /api/coach-clas/{coach_canonico} para mover de clã."
            ),
        )

    return supabase_client.upsert_coach_cla(coach_canonico, payload.clan, payload.categoria)


@router.put("/{coach_canonico}")
def atualizar_coach_cla(coach_canonico: str, payload: CoachClaUpdate):
    """Atualiza `clan` e/ou `categoria` de um coach já vinculado (mover de
    clã / editar categoria). Retorna 404 se o coach não tiver vínculo
    cadastrado."""
    alias_map = supabase_client.get_coach_alias_map()
    coach_canonico = coach_identity.resolve_coach(coach_canonico, alias_map)

    existente = _buscar_por_canonico(coach_canonico)
    if existente is None:
        raise HTTPException(status_code=404, detail=f"Coach '{coach_canonico}' não encontrado")

    clan = payload.clan if payload.clan is not None else existente["clan"]
    categoria = payload.categoria if payload.categoria is not None else existente["categoria"]
    return supabase_client.upsert_coach_cla(coach_canonico, clan, categoria)


@router.delete("/{coach_canonico}")
def deletar_coach_cla(coach_canonico: str):
    """Remove o vínculo de um coach. Idempotente: chamar de novo para um
    coach já removido (ou nunca vinculado) não é erro."""
    supabase_client.delete_coach_cla(coach_canonico)
    return {"mensagem": f"Vínculo de '{coach_canonico}' removido."}
