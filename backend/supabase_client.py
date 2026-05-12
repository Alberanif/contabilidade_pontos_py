from datetime import date
from supabase import create_client, Client

import config

TABLE_REGISTROS = "pontos_ultimate_registros_contabilizados"
TABLE_TOTAIS = "pontos_ultimate_totais_por_clan"
TABLE_TOTAIS_COACH = "pontos_ultimate_totais_por_coach"
TABLE_DESAFIOS = "desafios"
TABLE_DESAFIO_CAMPOS = "desafio_campos"
TABLE_DESAFIO_REGISTROS = "desafio_registros"


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
    status_coach: str | None = None,
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
    if status_coach:
        query = query.eq("status_coach", status_coach)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return result.data


def count_registros(
    clan: str | None = None,
    modalidade: str | None = None,
    status: str | None = None,
    status_coach: str | None = None,
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
    if status_coach:
        query = query.eq("status_coach", status_coach)
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


def update_data_registro(registro_hash: str, data_registro: str | None) -> bool:
    """Atualiza data_registro de um registro pelo hash. Retorna True se encontrou o registro."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .update({"data_registro": data_registro})
        .eq("registro_hash", registro_hash)
        .execute()
    )
    return len(result.data) > 0


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
    return list({row["clan"] for row in result.data if row.get("clan")})


def get_pending_group_records_by_coach(coach: str, modalidades: list[str]) -> list[dict]:
    """Retorna todos os registros pendentes de grupo/empresa do coach em ordem FIFO."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .select("id, registro_hash, coach, clan, modalidade, created_at, num_participantes")
        .eq("coach", coach)
        .eq("status_coach", "pendente")
        .in_("modalidade", modalidades)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def promote_pending_to_contabilizado_coach(record_ids: list[int], pontos_each: int) -> int:
    """Atualiza os registros para status_coach=contabilizado e define pontos_coach. Retorna quantidade."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .update({"status_coach": "contabilizado", "pontos_coach": pontos_each})
        .in_("id", record_ids)
        .execute()
    )
    return len(result.data)


def get_all_pending_coaches(modalidades: list[str]) -> list[str]:
    """Retorna lista de coaches distintos que possuem ao menos 1 registro pendente nas modalidades."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .select("coach")
        .eq("status_coach", "pendente")
        .in_("modalidade", modalidades)
        .execute()
    )
    return list({row["coach"] for row in result.data if row.get("coach")})


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
    return result.data[0]["pessoas_em_espera"] or 0 if result.data else 0


def reset_all_totals() -> None:
    """Zera todos os totais dos clãs."""
    client = _get_client()
    client.table(TABLE_TOTAIS).delete().neq("id", 0).execute()
    client.table(TABLE_TOTAIS_COACH).delete().neq("id", 0).execute()


# --- Totais por Coach ---


def get_coach_totals() -> dict[str, int]:
    """Retorna {coach: total_pontos} de todos os coaches."""
    client = _get_client()
    result = client.table(TABLE_TOTAIS_COACH).select("*").execute()
    return {row["coach"]: row["total_pontos"] for row in result.data}


def list_coach_totals() -> list[dict]:
    """Lista todos os coaches com totais como lista de dicts."""
    client = _get_client()
    result = client.table(TABLE_TOTAIS_COACH).select("*").order("total_pontos", desc=True).execute()
    return result.data


def upsert_coach_total(coach: str, total: int, pessoas_em_espera: int | None = None) -> dict:
    """Atualiza ou insere o total de pontos de um coach.

    Se pessoas_em_espera for informado, também atualiza o carry-over.
    """
    client = _get_client()
    payload: dict = {"coach": coach, "total_pontos": total}
    if pessoas_em_espera is not None:
        payload["pessoas_em_espera"] = pessoas_em_espera
    result = client.table(TABLE_TOTAIS_COACH).upsert(
        payload,
        on_conflict="coach",
    ).execute()
    return result.data[0] if result.data else {}


def get_coach_carry_over(coach: str) -> int:
    """Retorna o carry-over (pessoas_em_espera) atual do coach. Default 0."""
    client = _get_client()
    result = (
        client.table(TABLE_TOTAIS_COACH)
        .select("pessoas_em_espera")
        .eq("coach", coach)
        .execute()
    )
    return result.data[0]["pessoas_em_espera"] or 0 if result.data else 0


# --- Desafios ---


def create_desafio(nome: str, contabilizar_pontos: bool, data: date) -> dict:
    """Cria um novo desafio."""
    client = _get_client()
    result = client.table(TABLE_DESAFIOS).insert(
        {"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)}
    ).execute()
    return result.data[0]


def list_desafios() -> list[dict]:
    """Lista todos os desafios ordenados por data de criação."""
    client = _get_client()
    result = client.table(TABLE_DESAFIOS).select("*").order("created_at", desc=False).execute()
    return result.data


def get_desafio(desafio_id: int) -> dict | None:
    """Busca um desafio pelo ID."""
    client = _get_client()
    result = client.table(TABLE_DESAFIOS).select("*").eq("id", desafio_id).execute()
    return result.data[0] if result.data else None


def update_desafio(desafio_id: int, nome: str, contabilizar_pontos: bool, data: date) -> dict:
    """Atualiza nome, modo de contabilização e data de um desafio."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIOS)
        .update({"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)})
        .eq("id", desafio_id)
        .execute()
    )
    return result.data[0]


def delete_desafio(desafio_id: int) -> dict | None:
    """Exclui um desafio (CASCADE exclui campos e registros)."""
    client = _get_client()
    result = client.table(TABLE_DESAFIOS).delete().eq("id", desafio_id).execute()
    return result.data[0] if result.data else None


# --- Desafio Campos ---


def insert_desafio_campos(campos: list[dict]) -> list[dict]:
    """Insere lista de campos. Cada dict: {desafio_id, nome, tipo, ordem}."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_CAMPOS).insert(campos).execute()
    return result.data


def list_desafio_campos(desafio_id: int) -> list[dict]:
    """Lista campos de um desafio ordenados por 'ordem'."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_CAMPOS)
        .select("*")
        .eq("desafio_id", desafio_id)
        .order("ordem", desc=False)
        .execute()
    )
    return result.data


def delete_desafio_campos(desafio_id: int) -> None:
    """Remove todos os campos de um desafio (usado ao editar campos)."""
    client = _get_client()
    client.table(TABLE_DESAFIO_CAMPOS).delete().eq("desafio_id", desafio_id).execute()


# --- Desafio Registros ---


def create_desafio_registro(
    desafio_id: int, clan: str, valores: dict, total_pontos: int
) -> dict:
    """Cria um registro de clã em um desafio."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_REGISTROS).insert(
        {
            "desafio_id": desafio_id,
            "clan": clan,
            "valores": valores,
            "total_pontos": total_pontos,
        }
    ).execute()
    return result.data[0]


def list_desafio_registros(desafio_id: int) -> list[dict]:
    """Lista registros de um desafio ordenados por data de criação."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS)
        .select("*")
        .eq("desafio_id", desafio_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def get_desafio_registro_by_clan(desafio_id: int, clan: str) -> dict | None:
    """Busca o registro de um clã específico em um desafio."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS)
        .select("*")
        .eq("desafio_id", desafio_id)
        .eq("clan", clan)
        .execute()
    )
    return result.data[0] if result.data else None


def get_desafio_registro_by_id(registro_id: int) -> dict | None:
    """Busca um registro de desafio pelo ID."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS)
        .select("*")
        .eq("id", registro_id)
        .execute()
    )
    return result.data[0] if result.data else None


def delete_desafio_registro(registro_id: int) -> dict | None:
    """Exclui um registro de desafio pelo ID."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS).delete().eq("id", registro_id).execute()
    )
    return result.data[0] if result.data else None


def update_desafio_registro_pontos(
    registro_id: int, valores: dict, total_pontos: int
) -> dict:
    """Atualiza os valores e total_pontos de um registro (usado no recálculo)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS)
        .update({"valores": valores, "total_pontos": total_pontos})
        .eq("id", registro_id)
        .execute()
    )
    return result.data[0]


# --- Helper de delta para clãs ---


def add_delta_to_clan_total(clan: str, delta: int) -> dict:
    """Soma delta (positivo ou negativo) ao total_pontos do clã. Mínimo 0."""
    current_totals = get_clan_totals()
    current = current_totals.get(clan, 0)
    new_total = max(0, current + delta)
    return upsert_clan_total(clan, new_total)


def update_desafio_campo(campo_id: int, nome: str, tipo: str, ordem: int) -> dict:
    """Atualiza um campo de desafio existente."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_CAMPOS)
        .update({"nome": nome, "tipo": tipo, "ordem": ordem})
        .eq("id", campo_id)
        .execute()
    )
    return result.data[0]


def delete_desafio_campo(campo_id: int) -> None:
    """Remove um campo de desafio pelo ID."""
    client = _get_client()
    client.table(TABLE_DESAFIO_CAMPOS).delete().eq("id", campo_id).execute()


def list_all_desafio_campos() -> list[dict]:
    """Retorna todos os campos de todos os desafios."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_CAMPOS).select("*").order("ordem", desc=False).execute()
    return result.data


def count_desafio_registros_by_desafio() -> dict[int, int]:
    """Retorna {desafio_id: contagem_registros} para todos os desafios."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_REGISTROS).select("desafio_id").execute()
    counts: dict[int, int] = {}
    for row in result.data:
        did = row["desafio_id"]
        counts[did] = counts.get(did, 0) + 1
    return counts


# --- Consultas por período (filtradas por data_registro) ---


def get_period_clan_totals(inicio: date, fim: date) -> dict[str, int]:
    """
    Sum all pontos for records within the period [inicio, fim].
    Group coaching records (pontos == POINTS_PER_RECORD_IN_BATCH) are floored
    to the nearest complete batch — partial batches are discarded.
    Returns dict[clan_name, total_pontos].
    """
    client = _get_client()
    query = (
        client.table(TABLE_REGISTROS)
        .select("clan, pontos")
        .gte("data_registro", inicio.isoformat())
        .lte("data_registro", fim.isoformat())
        .eq("status", "contabilizado")
    )
    records = query.execute().data

    group_raw: dict[str, int] = {}
    totals: dict[str, int] = {}
    for record in records:
        clan = record["clan"]
        p = record["pontos"]
        if p == config.POINTS_PER_RECORD_IN_BATCH:
            group_raw[clan] = group_raw.get(clan, 0) + p
        else:
            totals[clan] = totals.get(clan, 0) + p

    for clan, g in group_raw.items():
        complete = (g // config.POINTS_PER_BATCH_GROUP) * config.POINTS_PER_BATCH_GROUP
        if complete:
            totals[clan] = totals.get(clan, 0) + complete

    return totals


def get_period_coach_totals(inicio: date, fim: date) -> dict[str, int]:
    """
    Sum all pontos_coach for records within the period [inicio, fim].
    Group coaching records (pontos_coach == POINTS_PER_RECORD_IN_BATCH) are floored
    to the nearest complete batch — partial batches are discarded.
    Returns dict[coach_name, total_pontos_coach].
    """
    client = _get_client()
    query = (
        client.table(TABLE_REGISTROS)
        .select("coach, pontos_coach")
        .gte("data_registro", inicio.isoformat())
        .lte("data_registro", fim.isoformat())
        .eq("status_coach", "contabilizado")
    )
    records = query.execute().data

    group_raw: dict[str, int] = {}
    totals: dict[str, int] = {}
    for record in records:
        coach = record["coach"]
        if not coach:
            continue
        p = record["pontos_coach"]
        if p == config.POINTS_PER_RECORD_IN_BATCH:
            group_raw[coach] = group_raw.get(coach, 0) + p
        else:
            totals[coach] = totals.get(coach, 0) + p

    for coach, g in group_raw.items():
        complete = (g // config.POINTS_PER_BATCH_GROUP) * config.POINTS_PER_BATCH_GROUP
        if complete:
            totals[coach] = totals.get(coach, 0) + complete

    return totals


def get_period_desafio_totals(inicio: date, fim: date) -> dict[str, int]:
    """
    Sum desafio points for desafios within the period [inicio, fim].
    Only includes desafios with contabilizar_pontos=true.
    Returns dict[clan_name, total_pontos].
    """
    client = _get_client()

    # Fetch desafios in the period
    desafios_query = (
        client.table(TABLE_DESAFIOS)
        .select("id")
        .gte("data", inicio.isoformat())
        .lte("data", fim.isoformat())
        .eq("contabilizar_pontos", True)
    )
    desafios = desafios_query.execute().data
    desafio_ids = [d["id"] for d in desafios]

    if not desafio_ids:
        return {}

    # Fetch desafio_registros for those desafios
    registros_query = (
        client.table(TABLE_DESAFIO_REGISTROS)
        .select("clan, total_pontos")
        .in_("desafio_id", desafio_ids)
    )
    registros = registros_query.execute().data

    totals = {}
    for registro in registros:
        clan = registro["clan"]
        totals[clan] = totals.get(clan, 0) + registro["total_pontos"]

    return totals


def get_tipo_clan_totals(
    tipo: str,
    inicio: "date | None" = None,
    fim: "date | None" = None,
) -> dict[str, int]:
    client = _get_client()

    if tipo == "desafios":
        if inicio and fim:
            return get_period_desafio_totals(inicio, fim)
        # All-time desafio totals
        desafios = (
            client.table(TABLE_DESAFIOS)
            .select("id")
            .eq("contabilizar_pontos", True)
            .execute()
            .data
        )
        desafio_ids = [d["id"] for d in desafios]
        if not desafio_ids:
            return {}
        registros = (
            client.table(TABLE_DESAFIO_REGISTROS)
            .select("clan, total_pontos")
            .in_("desafio_id", desafio_ids)
            .execute()
            .data
        )
        totals: dict[str, int] = {}
        for r in registros:
            totals[r["clan"]] = totals.get(r["clan"], 0) + r["total_pontos"]
        return totals

    query = (
        client.table(TABLE_REGISTROS)
        .select("clan, pontos, registro_hash")
        .eq("status", "contabilizado")
    )
    if inicio and fim:
        query = (
            query
            .gte("data_registro", inicio.isoformat())
            .lte("data_registro", fim.isoformat())
        )
    records = query.execute().data

    is_pro_bono = tipo == "pro_bono"
    totals = {}
    for rec in records:
        h = rec.get("registro_hash", "")
        if is_pro_bono != h.startswith("pro_bono:"):
            continue
        clan = rec["clan"]
        totals[clan] = totals.get(clan, 0) + rec["pontos"]
    return totals


def get_tipo_coach_totals(
    tipo: str,
    inicio: "date | None" = None,
    fim: "date | None" = None,
) -> dict[str, int]:
    if tipo == "desafios":
        return {}

    client = _get_client()
    query = (
        client.table(TABLE_REGISTROS)
        .select("coach, pontos_coach, registro_hash")
        .eq("status_coach", "contabilizado")
    )
    if inicio and fim:
        query = (
            query
            .gte("data_registro", inicio.isoformat())
            .lte("data_registro", fim.isoformat())
        )
    records = query.execute().data

    is_pro_bono = tipo == "pro_bono"
    totals: dict[str, int] = {}
    for rec in records:
        h = rec.get("registro_hash", "")
        if is_pro_bono != h.startswith("pro_bono:"):
            continue
        coach = rec.get("coach")
        if coach:
            totals[coach] = totals.get(coach, 0) + rec["pontos_coach"]
    return totals
