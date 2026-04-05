from fastapi import APIRouter, Query

import supabase_client
import google_sheets_client

router = APIRouter()


@router.get("")
def listar_clans():
    """Lista todos os clãs com seus totais de pontos."""
    return supabase_client.list_clan_totals()


@router.get("/ranking")
def ranking_geral():
    """Retorna o ranking geral da seção PONTUAÇÃO GERAL da planilha de totais."""
    return google_sheets_client.fetch_ranking()


@router.get("/{clan}/registros")
def listar_registros_clan(
    clan: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lista registros contabilizados de um clã específico."""
    registros = supabase_client.list_registros(clan=clan, limit=limit, offset=offset)
    total = supabase_client.count_registros(clan=clan)
    return {
        "clan": clan,
        "registros": registros,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
