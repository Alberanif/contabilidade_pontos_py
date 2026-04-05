from supabase import create_client, Client

import config

TABLE_REGISTROS = "pontos_ultimate_registros_contabilizados"
TABLE_TOTAIS = "pontos_ultimate_totais_por_clan"


def _get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


# --- Registros contabilizados ---


def get_processed_hashes() -> set[str]:
    """Retorna set de todos os registro_hash já processados."""
    client = _get_client()
    data = client.table(TABLE_REGISTROS).select("registro_hash").execute()
    return {row["registro_hash"] for row in data.data}


def insert_processed_record(record: dict) -> dict:
    """Insere um registro processado. Usa upsert para idempotência."""
    client = _get_client()
    result = client.table(TABLE_REGISTROS).upsert(
        record, on_conflict="registro_hash"
    ).execute()
    return result.data[0] if result.data else {}


def list_registros(
    clan: str | None = None,
    modalidade: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Lista registros com filtros opcionais (clan, modalidade, status)."""
    client = _get_client()
    query = client.table(TABLE_REGISTROS).select("*")
    if clan:
        query = query.eq("clan", clan)
    if modalidade:
        query = query.eq("modalidade", modalidade)
    if status:
        query = query.eq("status", status)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return result.data


def count_registros(
    clan: str | None = None,
    modalidade: str | None = None,
    status: str | None = None,
) -> int:
    """Conta registros com filtros opcionais (clan, modalidade, status)."""
    client = _get_client()
    query = client.table(TABLE_REGISTROS).select("id", count="exact")
    if clan:
        query = query.eq("clan", clan)
    if modalidade:
        query = query.eq("modalidade", modalidade)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return result.count or 0


def get_registro_by_id(registro_id: int) -> dict | None:
    """Busca um registro pelo ID."""
    client = _get_client()
    result = client.table(TABLE_REGISTROS).select("*").eq("id", registro_id).execute()
    return result.data[0] if result.data else None


def delete_registro(registro_id: int) -> dict | None:
    """Exclui um registro pelo ID e retorna o registro excluído."""
    client = _get_client()
    result = client.table(TABLE_REGISTROS).delete().eq("id", registro_id).execute()
    return result.data[0] if result.data else None


def delete_all_registros() -> int:
    """Exclui todos os registros. Retorna a quantidade excluída."""
    client = _get_client()
    result = client.table(TABLE_REGISTROS).delete().neq("id", 0).execute()
    return len(result.data)


# --- Fila de grupo / empresa ---


def get_pending_group_records_by_clan(clan: str, modalidades: list[str]) -> list[dict]:
    """Retorna todos os registros pendentes de grupo/empresa do clã em ordem FIFO (created_at ASC)."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .select("id, registro_hash, clan, modalidade, created_at, num_participantes")
        .eq("clan", clan)
        .eq("status", "pendente")
        .in_("modalidade", modalidades)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def promote_pending_to_contabilizado(record_ids: list[int], pontos_each: int) -> int:
    """Atualiza os registros para status=contabilizado e define pontos. Retorna quantidade."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .update({"status": "contabilizado", "pontos": pontos_each})
        .in_("id", record_ids)
        .execute()
    )
    return len(result.data)


def get_all_pending_clans(modalidades: list[str]) -> list[str]:
    """Retorna lista de clãs distintos que possuem ao menos 1 registro pendente nas modalidades."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .select("clan")
        .eq("status", "pendente")
        .in_("modalidade", modalidades)
        .execute()
    )
    return list({row["clan"] for row in result.data})


# --- Totais por clã ---


def get_clan_totals() -> dict[str, int]:
    """Retorna {clan: total_pontos} de todos os clãs."""
    client = _get_client()
    result = client.table(TABLE_TOTAIS).select("*").execute()
    return {row["clan"]: row["total_pontos"] for row in result.data}


def list_clan_totals() -> list[dict]:
    """Lista todos os clãs com totais como lista de dicts."""
    client = _get_client()
    result = client.table(TABLE_TOTAIS).select("*").order("total_pontos", desc=True).execute()
    return result.data


def upsert_clan_total(clan: str, total: int, pessoas_em_espera: int | None = None) -> dict:
    """Atualiza ou insere o total de pontos de um clã.

    Se pessoas_em_espera for informado, também atualiza o carry-over.
    """
    client = _get_client()
    payload: dict = {"clan": clan, "total_pontos": total}
    if pessoas_em_espera is not None:
        payload["pessoas_em_espera"] = pessoas_em_espera
    result = client.table(TABLE_TOTAIS).upsert(
        payload,
        on_conflict="clan",
    ).execute()
    return result.data[0] if result.data else {}


def get_clan_carry_over(clan: str) -> int:
    """Retorna o carry-over (pessoas_em_espera) atual do clã. Default 0."""
    client = _get_client()
    result = (
        client.table(TABLE_TOTAIS)
        .select("pessoas_em_espera")
        .eq("clan", clan)
        .execute()
    )
    return result.data[0]["pessoas_em_espera"] if result.data else 0


def reset_all_totals() -> None:
    """Zera todos os totais dos clãs."""
    client = _get_client()
    client.table(TABLE_TOTAIS).delete().neq("id", 0).execute()
