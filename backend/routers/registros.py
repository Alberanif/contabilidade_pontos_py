from fastapi import APIRouter, HTTPException, Query

import supabase_client

router = APIRouter()


@router.get("")
def listar_registros(
    clan: str | None = Query(None, description="Filtrar por clã"),
    modalidade: str | None = Query(None, description="Filtrar por modalidade"),
    status: str | None = Query(None, description="Filtrar por status: contabilizado | pendente"),
    status_coach: str | None = Query(None, description="Filtrar por status do coach: contabilizado | pendente"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lista registros com filtros opcionais e paginação."""
    registros = supabase_client.list_registros(
        clan=clan, modalidade=modalidade, status=status, status_coach=status_coach, limit=limit, offset=offset
    )
    total = supabase_client.count_registros(clan=clan, modalidade=modalidade, status=status, status_coach=status_coach)
    return {
        "registros": registros,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/{registro_id}")
def excluir_registro(registro_id: int):
    """Exclui um registro contabilizado e desconta os pontos do clã."""
    registro = supabase_client.get_registro_by_id(registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    clan = registro["clan"]
    pontos = registro["pontos"]

    # Excluir registro
    supabase_client.delete_registro(registro_id)

    # Recalcular total do clã
    current_totals = supabase_client.get_clan_totals()
    current = current_totals.get(clan, 0)
    new_total = max(0, current - pontos)
    supabase_client.upsert_clan_total(clan, new_total)

    return {
        "mensagem": f"Registro {registro_id} excluído. {pontos} pontos descontados do clã {clan}.",
        "clan": clan,
        "pontos_descontados": pontos,
        "novo_total": new_total,
    }
