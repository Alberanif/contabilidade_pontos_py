"""API CRUD de vínculo coach -> clã (issue #4 / Task 4 de "Coaches por Clã").

Endpoints REST para listar, criar, atualizar e remover a linha de
`pontos_ultimate_coach_clas` de cada coach, consumidos pelo frontend de
administração. A camada de dados (`supabase_client.list_coach_clas` /
`upsert_coach_cla` / `delete_coach_cla`) já existe (Task 2); este router só
adiciona validação de request, resolução de alias e as regras de
409/404/422 que a camada de dados não trata (ela é um upsert simples, sem
detecção de conflito).

O nome de coach recebido em `POST`/`PUT`/`DELETE` é sempre resolvido via
`coach_identity.resolve_coach()` antes de qualquer leitura/gravação, para
que um alias nunca cadastrado (variação de caixa/acento/espaço) não crie uma
segunda linha para o mesmo coach — e para que os três endpoints de escrita
concordem sobre qual linha um nome identifica.

O campo `clan` é normalizado para a grafia canônica (`CLÃ 1`..`CLÃ 8`) via
`desafio_sheet_parser.normalize_clan`, a mesma regra usada pelo script de
importação — sem isso a API aceitaria um clã "fantasma" que nunca apareceria
em nenhuma outra tela do sistema.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

import coach_identity
import supabase_client
from desafio_sheet_parser import normalize_clan

router = APIRouter()


Categoria = Literal[
    "Coach",
    "Coach Action",
    "Coach Pro",
    "Coach Hero",
    "Sem Categoria",
    "Novos ULTIMATES",
]


def _clan_normalizado(value: str) -> str:
    """Valida e normaliza para a grafia canônica ``CLÃ 1``..``CLÃ 8`` — mesma
    regra usada pelo script de importação (`desafio_sheet_parser.normalize_clan`).
    Sem essa validação, um `clan` livre gravaria um clã "fantasma" que nunca
    aparece em nenhuma outra tela do sistema."""
    normalizado = normalize_clan(value)
    if normalizado is None:
        raise ValueError(f"Clã inválido: '{value}'. Use CLÃ 1 a CLÃ 8.")
    return normalizado


def _coach_nao_vazio(value: str) -> str:
    """Rejeita nome vazio/só espaço — sem isso, `resolve_coach()` resolveria
    para o nome reservado 'DESCONHECIDO' e criaria um vínculo sem sentido."""
    value = value.strip()
    if not value:
        raise ValueError("Nome do coach não pode ser vazio.")
    return value


class CoachClaCreate(BaseModel):
    coach: str
    clan: str
    categoria: Categoria

    @field_validator("coach")
    @classmethod
    def _valida_coach(cls, v: str) -> str:
        return _coach_nao_vazio(v)

    @field_validator("clan")
    @classmethod
    def _valida_clan(cls, v: str) -> str:
        return _clan_normalizado(v)


class CoachClaUpdate(BaseModel):
    clan: str | None = None
    categoria: Categoria | None = None

    @field_validator("clan")
    @classmethod
    def _valida_clan(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _clan_normalizado(v)


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
    coach já removido (ou nunca vinculado) não é erro.

    Resolve o nome via alias antes de remover — mesma regra de identidade de
    POST/PUT — para que remover pela grafia de um alias apague a mesma linha
    que "Editar" enxergaria, em vez de ser um no-op silencioso."""
    alias_map = supabase_client.get_coach_alias_map()
    coach_canonico = coach_identity.resolve_coach(coach_canonico, alias_map)
    supabase_client.delete_coach_cla(coach_canonico)
    return {"mensagem": f"Vínculo de '{coach_canonico}' removido."}
