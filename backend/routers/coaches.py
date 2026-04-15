from fastapi import APIRouter, Query

import supabase_client

router = APIRouter()

@router.get("")
def listar_coaches():
    """Lista todos os coaches com seus totais de pontos."""
    return supabase_client.list_coach_totals()
