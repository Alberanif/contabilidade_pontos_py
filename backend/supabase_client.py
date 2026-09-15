from datetime import date, datetime
from typing import Any
from supabase import create_client, Client

import coach_identity
import config
from desafio_sheet_parser import SAO_PAULO

TABLE_REGISTROS = "pontos_ultimate_registros_contabilizados"
TABLE_TOTAIS = "pontos_ultimate_totais_por_clan"
TABLE_TOTAIS_COACH = "pontos_ultimate_totais_por_coach"
TABLE_DESAFIOS = "desafios"
TABLE_DESAFIO_CAMPOS = "desafio_campos"
TABLE_DESAFIO_REGISTROS = "desafio_registros"
TABLE_DESAFIO_REGISTROS_COACH = "desafio_registros_coach"
TABLE_DESAFIO_IMPORTACAO_LINHAS = "desafio_importacao_linhas"
TABLE_COACH_ALIASES = "pontos_ultimate_coach_aliases"
TABLE_COACH_ALIASES_PENDENTES = "pontos_ultimate_coach_aliases_pendentes"
TABLE_DESAFIO_SYNC_RUNS = "desafio_sync_runs"
TABLE_DESAFIO_SUBMISSIONS_CURRENT = "desafio_submissions_current"
TABLE_DESAFIO_SUBMISSION_VERSIONS = "desafio_submission_versions"
TABLE_COACH_CLAS = "pontos_ultimate_coach_clas"
TABLE_DESAFIO_SUBMISSAO_REVISOES = "desafio_submissao_revisoes"
TABLE_DESAFIO_CLAN_APURACOES = "desafio_clan_apuracoes"


def _get_client() -> Client:
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def call_rpc(function_name: str, params: dict):
    """Executa uma função do Postgres (RPC) e devolve o dado retornado.

    Usado por operações que precisam acontecer em uma única transação do banco,
    onde escritas separadas pelo cliente deixariam estado parcial observável.
    """
    return _get_client().rpc(function_name, params).execute().data


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


def fetch_all_registros_contabilizados() -> list[dict]:
    """Retorna todas as linhas de `pontos_ultimate_registros_contabilizados`,
    paginando até o fim — nunca trunca, diferente de `list_registros`
    (auditoria paginada, `limit` padrão de 100). Base de leitura da correção
    retroativa não-destrutiva de totais (`admin/recalcular_totais_data_inicio.py`
    + `points_engine.sum_registros_pontos_from_date`); não apaga nem altera
    nada."""
    client = _get_client()
    all_rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table(TABLE_REGISTROS)
            .select("*")
            .order("id", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        all_rows.extend(rows)
        # Avança pelo que de fato veio, nunca para só porque a página veio
        # curta: isso pode ser o limite do PostgREST (db-max-rows), não o fim
        # da tabela — só uma página vazia sinaliza o fim (mesma lógica de
        # `fetch_active_counted_desafio_submissions`).
        offset += len(rows)
    return all_rows


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


def list_all_registros() -> list[dict]:
    """Retorna todos os registros contabilizados, sem paginação (usa range
    internamente para superar o limite padrão do PostgREST)."""
    client = _get_client()
    all_rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table(TABLE_REGISTROS)
            .select("*")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        all_rows.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return all_rows


def update_registros_coach(old_coach: str, new_coach: str) -> int:
    """Reescreve o campo coach de old_coach para new_coach em todos os
    registros que casam. Retorna a quantidade de linhas atualizadas."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .update({"coach": new_coach})
        .eq("coach", old_coach)
        .execute()
    )
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


def upsert_clan_total(
    clan: str,
    total: int,
    pessoas_em_espera: int | None = None,
    total_pagante: int | None = None,
    total_pro_bono: int | None = None,
) -> dict:
    """Atualiza ou insere o total de pontos de um clã.

    Se pessoas_em_espera for informado, também atualiza o carry-over.
    Se total_pagante/total_pro_bono for informado, atualiza o breakdown por tipo.
    """
    client = _get_client()
    payload: dict = {"clan": clan, "total_pontos": total}
    if pessoas_em_espera is not None:
        payload["pessoas_em_espera"] = pessoas_em_espera
    if total_pagante is not None:
        payload["total_pagante"] = total_pagante
    if total_pro_bono is not None:
        payload["total_pro_bono"] = total_pro_bono
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


def upsert_coach_total(
    coach: str,
    total: int,
    pessoas_em_espera: int | None = None,
    total_pagante: int | None = None,
    total_pro_bono: int | None = None,
) -> dict:
    """Atualiza ou insere o total de pontos de um coach.

    Se pessoas_em_espera for informado, também atualiza o carry-over.
    Se total_pagante/total_pro_bono for informado, atualiza o breakdown por tipo.
    """
    client = _get_client()
    payload: dict = {"coach": coach, "total_pontos": total}
    if pessoas_em_espera is not None:
        payload["pessoas_em_espera"] = pessoas_em_espera
    if total_pagante is not None:
        payload["total_pagante"] = total_pagante
    if total_pro_bono is not None:
        payload["total_pro_bono"] = total_pro_bono
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


def delete_coach_total(coach: str) -> None:
    """Remove a linha de totais de um coach (usado ao fundir aliases)."""
    client = _get_client()
    client.table(TABLE_TOTAIS_COACH).delete().eq("coach", coach).execute()


def get_coach_alias_map() -> dict[str, str]:
    """Retorna {alias: coach_canonico} de todos os aliases cadastrados."""
    client = _get_client()
    result = client.table(TABLE_COACH_ALIASES).select("alias, coach_canonico").execute()
    return {row["alias"]: row["coach_canonico"] for row in result.data}


# --- Coach x Clã (vínculo) ---


def list_coach_clas(clan: str | None = None) -> list[dict]:
    """Lista os vínculos coach -> clã, com filtro opcional por clã."""
    client = _get_client()
    query = client.table(TABLE_COACH_CLAS).select("*")
    if clan:
        query = query.eq("clan", clan)
    result = query.execute()
    return result.data


def upsert_coach_cla(coach_canonico: str, clan: str, categoria: str) -> dict:
    """Cria ou atualiza o vínculo de um coach a um clã, por `coach_canonico`."""
    client = _get_client()
    payload = {
        "coach_canonico": coach_canonico,
        "clan": clan,
        "categoria": categoria,
    }
    result = client.table(TABLE_COACH_CLAS).upsert(
        payload, on_conflict="coach_canonico"
    ).execute()
    return result.data[0] if result.data else {}


def delete_coach_cla(coach_canonico: str) -> None:
    """Remove o vínculo de um coach a um clã. Idempotente: não falha se o
    coach não tiver vínculo cadastrado."""
    client = _get_client()
    client.table(TABLE_COACH_CLAS).delete().eq("coach_canonico", coach_canonico).execute()


# --- Sincronização de desafios via Google Sheets (somente leitura) ---


def list_desafio_sync_runs(limit: int = 50, offset: int = 0) -> list[dict]:
    """Lista execuções de sincronização, da mais recente para a mais antiga."""
    result = (
        _get_client()
        .table(TABLE_DESAFIO_SYNC_RUNS)
        .select("*")
        .order("started_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


def list_desafio_submissions_current(
    desafio_id: int | None = None,
    clan: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Lista o estado atual dos tokens com filtros de auditoria opcionais."""
    query = _get_client().table(TABLE_DESAFIO_SUBMISSIONS_CURRENT).select("*")
    if desafio_id is not None:
        query = query.eq("desafio_id", desafio_id)
    if clan is not None:
        query = query.eq("clan", clan)
    if status is not None:
        query = query.eq("status", status)
    result = (
        query.order("submitted_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


def fetch_all_desafio_submissions_current() -> list[dict]:
    """Retorna todas as linhas de estado atual, paginando até o fim.

    Diferente de `list_desafio_submissions_current` (auditoria, com filtros e
    página), esta leitura é a base completa da próxima reconciliação: nenhuma
    linha pode faltar, sob pena de um token ser tratado como novo e pontuar
    duas vezes.
    """
    client = _get_client()
    all_rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table(TABLE_DESAFIO_SUBMISSIONS_CURRENT)
            .select("*")
            .order("token", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        all_rows.extend(rows)
        # Avança pelo que de fato veio, e nunca para só porque a página veio
        # curta: o PostgREST pode limitar a resposta (`db-max-rows`) abaixo de
        # `page_size`, e nesse caso uma página curta ainda tem continuação. Só
        # uma página vazia prova o fim — o custo é uma requisição extra.
        offset += len(rows)
    return all_rows


def fetch_active_counted_desafio_submissions() -> list[dict]:
    """Retorna todos os tokens com `status='active_counted'`, paginando até o fim.

    Base de agregação dos totais de clã por tipo `desafios` (`get_period_desafio_totals`,
    `get_tipo_clan_totals('desafios')`). Diferente de `list_desafio_submissions_current`
    (auditoria paginada, `limit` padrão de 100), esta leitura nunca pode truncar
    silenciosamente: um clã com mais de 100 tokens ativos seria subcontado.
    Diferente de `fetch_all_desafio_submissions_current` (base completa da
    reconciliação, sem filtro), o filtro `status='active_counted'` acontece no
    servidor para não trazer linhas inválidas/conflitantes/inativas que nunca
    entrariam na soma.
    """
    client = _get_client()
    all_rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table(TABLE_DESAFIO_SUBMISSIONS_CURRENT)
            .select("*")
            .eq("status", "active_counted")
            .order("token", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        all_rows.extend(rows)
        # Mesma lógica de `fetch_all_desafio_submissions_current`: avança pelo
        # que de fato veio, nunca para só porque a página veio curta (o
        # PostgREST pode limitar a resposta abaixo de `page_size`).
        offset += len(rows)
    return all_rows


def get_all_desafio_token_coach_names() -> set[str]:
    """Nomes brutos de coach (coluna B) distintos, não vazios, dos tokens
    `active_counted`. Base de descoberta de coach para `reprocessar_coaches`
    e `sugerir_aliases_llm` — a fonte de desafios não escreve mais em
    `desafio_registros_coach`."""
    return {
        (row.get("raw_name") or "").strip()
        for row in fetch_active_counted_desafio_submissions()
        if (row.get("raw_name") or "").strip()
    }


def _submissao_conta_para_pontos_individuais_coach(
    submitted_at, revisao_status: str
) -> bool:
    """Mesma regra de corte usada por `get_desafio_apuracao` no eixo clã
    (`config.DESAFIO_PERCENTUAL_CLAN_CORTE`): antes do corte, `active_counted`
    já basta. A partir do corte, toda submissão conta por padrão — só
    `revisao_status == "reprovado"` exclui (não há mais exigência de
    aprovação manual explícita)."""
    sub_date = _submitted_at_local_date(submitted_at)
    if sub_date and sub_date >= config.DESAFIO_PERCENTUAL_CLAN_CORTE:
        return revisao_status != "reprovado"
    return True


def desafio_submission_pontos_individuais_coach(
    status: str, submitted_at, revisao_status: str
) -> int:
    """Pontos individuais do coach para uma linha de auditoria de submissão
    (`GET /api/desafios/submissoes/{token}`, `GET /api/desafios/{id}/submissoes`)
    — não o `points` gravado na linha, que é a taxa de clã. Mesma elegibilidade
    de `_aggregate_desafio_tokens_by_coach`/`get_desafio_coach_totals`: exige
    `status == "active_counted"` e `_submissao_conta_para_pontos_individuais_coach`."""
    if status != "active_counted":
        return 0
    if not _submissao_conta_para_pontos_individuais_coach(submitted_at, revisao_status):
        return 0
    return config.POINTS_PER_DESAFIO_SUBMISSION_COACH


def _aggregate_desafio_tokens_by_coach(
    rows: list[dict], inicio: "date | None" = None, fim: "date | None" = None
) -> dict[str, int]:
    """Agrupa os pontos individuais de tokens de desafio pelo coach canônico
    (coluna B resolvida via `pontos_ultimate_coach_aliases`). Cada token
    elegível vale `config.POINTS_PER_DESAFIO_SUBMISSION_COACH` — não o campo
    `points` gravado, que é a taxa de clã e pode divergir. Elegibilidade segue
    `_submissao_conta_para_pontos_individuais_coach`. Quando `inicio` é dado,
    inclui só os tokens cuja data local (São Paulo) de `submitted_at` cai em
    `[inicio, fim]` (`fim=None` = sem limite superior)."""
    revisoes_map = list_submissoes_revisoes()
    raw: dict[str, int] = {}
    for row in rows:
        name = (row.get("raw_name") or "").strip()
        if not name:
            continue
        submitted_at = row.get("submitted_at")
        if inicio is not None:
            local_date = _submitted_at_local_date(submitted_at)
            if local_date is None or local_date < inicio:
                continue
            if fim is not None and local_date > fim:
                continue
        revisao_status = revisoes_map.get(row.get("token"), {}).get("status", "pendente")
        if not _submissao_conta_para_pontos_individuais_coach(submitted_at, revisao_status):
            continue
        raw[name] = raw.get(name, 0) + config.POINTS_PER_DESAFIO_SUBMISSION_COACH
    return coach_identity.aggregate_by_canonical(raw, get_coach_alias_map())


def _submitted_at_local_date(raw_value) -> date | None:
    """Converte `submitted_at` (string ISO8601 com offset, ou `datetime`) para
    a data de calendário em América/São_Paulo — a unidade de período usada por
    `get_period_desafio_totals`."""
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        parsed = raw_value
    else:
        text = str(raw_value).strip()
        if not text:
            return None
        if text.endswith(("Z", "z")):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SAO_PAULO)
    return parsed.astimezone(SAO_PAULO).date()


def get_desafio_submission_current(token: str) -> dict | None:
    """Busca o estado atual de um token global sem alterar sua grafia."""
    result = (
        _get_client()
        .table(TABLE_DESAFIO_SUBMISSIONS_CURRENT)
        .select("*")
        .eq("token", token)
        .execute()
    )
    return result.data[0] if result.data else None


def list_desafio_submission_versions(token: str) -> list[dict]:
    """Lista todas as versões imutáveis de um token em ordem cronológica."""
    result = (
        _get_client()
        .table(TABLE_DESAFIO_SUBMISSION_VERSIONS)
        .select("*")
        .eq("token", token)
        .order("version_number", desc=False)
        .execute()
    )
    return result.data


def get_desafio_sync_run(run_id: int) -> dict | None:
    """Busca uma única execução de sincronização pelo ID."""
    result = (
        _get_client()
        .table(TABLE_DESAFIO_SYNC_RUNS)
        .select("*")
        .eq("id", run_id)
        .execute()
    )
    return result.data[0] if result.data else None


def insert_coach_alias(alias: str, coach_canonico: str) -> dict:
    """Cadastra (ou atualiza) um alias de coach."""
    client = _get_client()
    result = (
        client.table(TABLE_COACH_ALIASES)
        .upsert({"alias": alias, "coach_canonico": coach_canonico}, on_conflict="alias")
        .execute()
    )
    return result.data[0] if result.data else {}


def get_pending_coach_aliases(status: str = "pendente") -> list[dict]:
    """Retorna lista de sugestões de aliases pendentes."""
    try:
        client = _get_client()
        query = client.table(TABLE_COACH_ALIASES_PENDENTES).select("*")
        if status:
            query = query.eq("status", status)
        result = query.order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        print(f"[AVISO] Tabela {TABLE_COACH_ALIASES_PENDENTES} pode não existir ainda no Supabase: {e}")
        return []


def get_pending_coach_alias_by_id(id_pendente: int) -> dict | None:
    """Busca uma sugestão pendente pelo ID."""
    try:
        client = _get_client()
        result = client.table(TABLE_COACH_ALIASES_PENDENTES).select("*").eq("id", id_pendente).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"[ERRO] Falha ao buscar alias pendente {id_pendente}: {e}")
        return None


def upsert_pending_coach_alias(
    alias_raw: str, coach_sugerido: str, confianca: float, origem: str = "groq-llm", status: str = "pendente"
) -> dict:
    """Cadastra ou atualiza uma sugestão de alias pendente."""
    try:
        client = _get_client()
        data = {
            "alias_raw": alias_raw,
            "coach_sugerido": coach_sugerido,
            "confianca": confianca,
            "origem": origem,
            "status": status,
        }
        result = (
            client.table(TABLE_COACH_ALIASES_PENDENTES)
            .upsert(data, on_conflict="alias_raw")
            .execute()
        )
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"[ERRO] Falha ao upsertar alias pendente {alias_raw}: {e}")
        return {}


def update_pending_coach_alias_status(id_pendente: int, status: str, coach_sugerido: str | None = None) -> dict:
    """Atualiza o status (e opcionalmente a sugestão) de um alias pendente."""
    try:
        client = _get_client()
        payload = {"status": status}
        if coach_sugerido:
            payload["coach_sugerido"] = coach_sugerido
        result = client.table(TABLE_COACH_ALIASES_PENDENTES).update(payload).eq("id", id_pendente).execute()
        return result.data[0] if result.data else {}
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar status do alias pendente {id_pendente}: {e}")
        return {}




# --- Desafios ---


def create_desafio(
    nome: str,
    contabilizar_pontos: bool,
    data: date,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    origem: str = "manual",
    pontos_por_participacao: int | None = None,
) -> dict:
    """Cria um novo desafio. `data_inicio`/`data_fim`/`pontos_por_participacao` só
    são usados por desafios criados via importação de CSV (origem='csv_import')."""
    client = _get_client()
    payload = {
        "nome": nome,
        "contabilizar_pontos": contabilizar_pontos,
        "data": str(data),
        "origem": origem,
    }
    if data_inicio is not None:
        payload["data_inicio"] = str(data_inicio)
    if data_fim is not None:
        payload["data_fim"] = str(data_fim)
    if pontos_por_participacao is not None:
        payload["pontos_por_participacao"] = pontos_por_participacao
    result = client.table(TABLE_DESAFIOS).insert(payload).execute()
    return result.data[0]


def update_desafio_periodo_e_pontos(
    desafio_id: int, data_inicio: date, data_fim: date, pontos_por_participacao: int
) -> dict:
    """Atualiza período e pontos-por-participação de um desafio importado (reimportação)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIOS)
        .update({
            "data_inicio": str(data_inicio),
            "data_fim": str(data_fim),
            "data": str(data_fim),
            "pontos_por_participacao": pontos_por_participacao,
        })
        .eq("id", desafio_id)
        .execute()
    )
    return result.data[0]


def list_desafios(origem: str | None = None, status: str | None = None) -> list[dict]:
    """Lista desafios, opcionalmente filtrando por origem ('manual' | 'csv_import' |
    'google_sheets') e/ou status. `status` aqui já deve ser o valor em português
    usado no banco ('ativo' | 'arquivado') — o mapeamento do parâmetro em inglês
    da API (`active`/`archived`/`all`) é responsabilidade do chamador."""
    client = _get_client()
    query = client.table(TABLE_DESAFIOS).select("*").order("created_at", desc=False)
    if origem is not None:
        query = query.eq("origem", origem)
    if status is not None:
        query = query.eq("status", status)
    return query.execute().data


def get_desafio(desafio_id: int) -> dict | None:
    """Busca um desafio pelo ID."""
    client = _get_client()
    result = client.table(TABLE_DESAFIOS).select("*").eq("id", desafio_id).execute()
    return result.data[0] if result.data else None


def get_desafio_clan_totals(desafio_id: int) -> dict[str, int]:
    """Soma os pontos das submissões contabilizadas (`active_counted`) de um
    desafio, agrupados por clã. A tabela fica restrita às submissões de um
    único desafio, então somar em Python é suficiente e mais simples do que uma
    função RPC dedicada só para este agrupamento."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_SUBMISSIONS_CURRENT)
        .select("clan, points")
        .eq("desafio_id", desafio_id)
        .eq("status", "active_counted")
        .execute()
    )
    totals: dict[str, int] = {}
    for row in result.data:
        clan = row.get("clan")
        if not clan:
            continue
        totals[clan] = totals.get(clan, 0) + (row.get("points") or 0)
    return totals


def get_desafio_coach_totals(desafio_id: int) -> dict[str, int]:
    """Soma os pontos individuais das submissões `active_counted` de um
    desafio, agrupadas pelo coach canônico (coluna B / `raw_name` resolvida
    via `pontos_ultimate_coach_aliases`). Cada token elegível vale
    `config.POINTS_PER_DESAFIO_SUBMISSION_COACH` — ver
    `_submissao_conta_para_pontos_individuais_coach` para a regra de corte."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_SUBMISSIONS_CURRENT)
        .select("raw_name, token, submitted_at")
        .eq("desafio_id", desafio_id)
        .eq("status", "active_counted")
        .execute()
    )
    revisoes_map = list_submissoes_revisoes()
    raw: dict[str, int] = {}
    for row in result.data:
        name = (row.get("raw_name") or "").strip()
        if not name:
            continue
        revisao_status = revisoes_map.get(row.get("token"), {}).get("status", "pendente")
        if not _submissao_conta_para_pontos_individuais_coach(row.get("submitted_at"), revisao_status):
            continue
        raw[name] = raw.get(name, 0) + config.POINTS_PER_DESAFIO_SUBMISSION_COACH
    return coach_identity.aggregate_by_canonical(raw, get_coach_alias_map())


def update_desafio(
    desafio_id: int,
    nome: str,
    contabilizar_pontos: bool,
    data: date,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict:
    """Atualiza nome, modo de contabilização, data e (opcionalmente) período de um desafio."""
    client = _get_client()
    payload = {"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)}
    if data_inicio is not None:
        payload["data_inicio"] = str(data_inicio)
    if data_fim is not None:
        payload["data_fim"] = str(data_fim)
    result = (
        client.table(TABLE_DESAFIOS)
        .update(payload)
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


# --- Desafio Registros Coach ---


def create_desafio_registro_coach(
    desafio_id: int, coach: str, valores: dict, total_pontos: int
) -> dict:
    """Cria um registro de coach em um desafio."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_REGISTROS_COACH).insert(
        {
            "desafio_id": desafio_id,
            "coach": coach,
            "valores": valores,
            "total_pontos": total_pontos,
        }
    ).execute()
    return result.data[0]


def list_desafio_registros_coach(desafio_id: int) -> list[dict]:
    """Lista registros de coach de um desafio ordenados por data de criação."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .select("*")
        .eq("desafio_id", desafio_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def get_desafio_registro_coach_by_coach(desafio_id: int, coach: str) -> dict | None:
    """Busca o registro de um coach específico em um desafio."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .select("*")
        .eq("desafio_id", desafio_id)
        .eq("coach", coach)
        .execute()
    )
    return result.data[0] if result.data else None


def update_desafio_registro_coach_pontos(
    registro_id: int, valores: dict, total_pontos: int
) -> dict:
    """Atualiza os valores e total_pontos de um registro de coach (usado no recálculo)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .update({"valores": valores, "total_pontos": total_pontos})
        .eq("id", registro_id)
        .execute()
    )
    return result.data[0]


def add_delta_to_coach_total(coach: str, delta: int) -> dict:
    """Soma delta (positivo ou negativo) ao total_pontos do coach. Mínimo 0."""
    current_totals = get_coach_totals()
    current = current_totals.get(coach, 0)
    new_total = max(0, current + delta)
    return upsert_coach_total(coach, new_total)


# --- Desafio Importação Linhas ---


def get_tokens_importados(desafio_id: int) -> set[str]:
    """Retorna o set de tokens já importados para um desafio (usado no dedup entre importações)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_IMPORTACAO_LINHAS)
        .select("token_original")
        .eq("desafio_id", desafio_id)
        .execute()
    )
    return {row["token_original"] for row in result.data}


def insert_desafio_importacao_linhas(desafio_id: int, linhas: list[dict]) -> list[dict]:
    """Insere as linhas de auditoria de uma importação. Cada dict já vem no formato
    de ImportResult.linhas_auditoria (clan, nome_participante, validado, contabilizado,
    submitted_at, token_original)."""
    if not linhas:
        return []
    client = _get_client()
    payload = [{**linha, "desafio_id": desafio_id, "submitted_at": str(linha["submitted_at"])} for linha in linhas]
    result = client.table(TABLE_DESAFIO_IMPORTACAO_LINHAS).insert(payload).execute()
    return result.data


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


def get_period_clan_totals(inicio: date, fim: date | None = None) -> dict[str, int]:
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
        .eq("status", "contabilizado")
    )
    if fim:
        query = query.lte("data_registro", fim.isoformat())
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


def get_period_coach_totals(inicio: date, fim: date | None = None) -> dict[str, int]:
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
        .eq("status_coach", "contabilizado")
    )
    if fim:
        query = query.lte("data_registro", fim.isoformat())
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


def get_period_desafio_totals(inicio: date, fim: date | None = None) -> dict[str, int]:
    """
    Sum desafio points per clan from active tokens (`status='active_counted'`
    in `desafio_submissions_current`) whose `submitted_at`, converted to
    América/São_Paulo local time and taken as a calendar date, falls within
    [inicio, fim]. Period membership is per-token, not per-desafio: a
    correction that moves a token's submitted_at, clan or validation moves or
    removes its contribution the next time this runs.
    Returns dict[clan_name, total_pontos].
    """
    totals: dict[str, int] = {}
    for row in fetch_active_counted_desafio_submissions():
        clan = row.get("clan")
        if not clan:
            continue
        local_date = _submitted_at_local_date(row.get("submitted_at"))
        if local_date is None or local_date < inicio:
            continue
        if fim is not None and local_date > fim:
            continue
        totals[clan] = totals.get(clan, 0) + (row.get("points") or 0)
    return totals


def get_period_desafio_coach_totals(inicio: date, fim: date | None = None) -> dict[str, int]:
    """
    Soma os pontos de desafio por coach a partir dos tokens `active_counted`
    de `desafio_submissions_current` cujo `submitted_at`, convertido para a data
    de calendário em América/São_Paulo, cai em `[inicio, fim]`. O coach é a
    coluna B (`raw_name`) resolvida ao nome canônico. Fase 2 — antes lia a
    tabela legada `desafio_registros_coach`.
    """
    return _aggregate_desafio_tokens_by_coach(
        fetch_active_counted_desafio_submissions(), inicio, fim
    )


def get_tipo_clan_totals(
    tipo: str,
    inicio: "date | None" = None,
    fim: "date | None" = None,
) -> dict[str, int]:
    client = _get_client()

    if tipo == "desafios":
        if inicio:
            return get_period_desafio_totals(inicio, fim)
        # Sem filtro de data: soma todos os tokens ativos, sem olhar
        # `submitted_at`. O status `active_counted` (computado pela
        # reconciliação a partir da própria coluna "Sim" da planilha) é o
        # único portão sobre se um token conta — não há mais um toggle
        # `contabilizar_pontos` por desafio a preservar aqui.
        totals: dict[str, int] = {}
        for row in fetch_active_counted_desafio_submissions():
            clan = row.get("clan")
            if not clan:
                continue
            totals[clan] = totals.get(clan, 0) + (row.get("points") or 0)
        return totals

    # Without date filter: read breakdown columns from TABLE_TOTAIS
    if not inicio:
        if tipo == "pagante":
            col = "total_pagante"
        elif tipo == "pro_bono":
            col = "total_pro_bono"
        else:
            raise ValueError(f"tipo inválido para totais por tipo: {tipo!r}")
        rows = (
            client.table(TABLE_TOTAIS)
            .select(f"clan, {col}")
            .execute()
            .data
        )
        return {r["clan"]: r[col] for r in rows if (r.get(col) or 0) > 0}

    # With date filter: sum from TABLE_REGISTROS (period-based, existing behavior)
    query = (
        client.table(TABLE_REGISTROS)
        .select("clan, pontos, modalidade")
        .eq("status", "contabilizado")
        .gte("data_registro", inicio.isoformat())
    )
    if fim:
        query = query.lte("data_registro", fim.isoformat())
    records = query.execute().data

    is_pro_bono = tipo == "pro_bono"
    group_raw: dict[str, int] = {}
    totals: dict[str, int] = {}
    for rec in records:
        rec_is_pro_bono = rec.get("modalidade", "") == "Pro-bono"
        if is_pro_bono != rec_is_pro_bono:
            continue
        clan = rec["clan"]
        p = rec["pontos"]
        if p == config.POINTS_PER_RECORD_IN_BATCH:
            group_raw[clan] = group_raw.get(clan, 0) + p
        else:
            totals[clan] = totals.get(clan, 0) + p

    for clan, g in group_raw.items():
        complete = (g // config.POINTS_PER_BATCH_GROUP) * config.POINTS_PER_BATCH_GROUP
        if complete:
            totals[clan] = totals.get(clan, 0) + complete
    return totals


def get_tipo_coach_totals(
    tipo: str,
    inicio: "date | None" = None,
    fim: "date | None" = None,
) -> dict[str, int]:
    if tipo == "desafios":
        if inicio:
            return get_period_desafio_coach_totals(inicio, fim)
        return _aggregate_desafio_tokens_by_coach(
            fetch_active_counted_desafio_submissions()
        )

    client = _get_client()

    # Without date filter: read breakdown columns from TABLE_TOTAIS_COACH
    if not inicio:
        if tipo == "pagante":
            col = "total_pagante"
        elif tipo == "pro_bono":
            col = "total_pro_bono"
        else:
            raise ValueError(f"tipo inválido para totais por tipo: {tipo!r}")
        rows = (
            client.table(TABLE_TOTAIS_COACH)
            .select(f"coach, {col}")
            .execute()
            .data
        )
        return {r["coach"]: r[col] for r in rows if (r.get(col) or 0) > 0}

    # With date filter: sum from TABLE_REGISTROS (period-based, existing behavior)
    query = (
        client.table(TABLE_REGISTROS)
        .select("coach, pontos_coach, modalidade")
        .eq("status_coach", "contabilizado")
        .gte("data_registro", inicio.isoformat())
    )
    if fim:
        query = query.lte("data_registro", fim.isoformat())
    records = query.execute().data

    is_pro_bono = tipo == "pro_bono"
    group_raw: dict[str, int] = {}
    totals: dict[str, int] = {}
    for rec in records:
        rec_is_pro_bono = rec.get("modalidade", "") == "Pro-bono"
        if is_pro_bono != rec_is_pro_bono:
            continue
        coach = rec.get("coach")
        if not coach:
            continue
        p = rec["pontos_coach"]
        if p == config.POINTS_PER_RECORD_IN_BATCH:
            group_raw[coach] = group_raw.get(coach, 0) + p
        else:
            totals[coach] = totals.get(coach, 0) + p

    for coach, g in group_raw.items():
        complete = (g // config.POINTS_PER_BATCH_GROUP) * config.POINTS_PER_BATCH_GROUP
        if complete:
            totals[coach] = totals.get(coach, 0) + complete
    return totals


# --- Apuração por Percentual & Revisão Manual de Desafios ---


def set_desafio_prazo(desafio_id: int, prazo: datetime | str | None) -> dict:
    """Define ou edita o prazo de apuração de um desafio."""
    client = _get_client()
    if isinstance(prazo, datetime):
        prazo_str = prazo.isoformat()
    else:
        prazo_str = prazo

    desafio = get_desafio(desafio_id)
    if not desafio:
        raise ValueError("Desafio não encontrado")

    payload: dict = {"prazo_apuracao": prazo_str}

    # Se reabrindo para o futuro ou limpando o prazo, limpa apurado_em
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    if prazo_str is None:
        payload["apurado_em"] = None
    elif isinstance(prazo, datetime):
        if prazo > now_utc:
            payload["apurado_em"] = None
    else:
        try:
            dt = datetime.fromisoformat(prazo_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > now_utc:
                payload["apurado_em"] = None
        except ValueError:
            pass

    result = client.table(TABLE_DESAFIOS).update(payload).eq("id", desafio_id).execute()
    return result.data[0] if result.data else {}


def revisar_submissao(token: str, status: str, revisado_por: str | None = None) -> dict:
    """Aprova ou reprova uma submissão individual na tabela `desafio_submissao_revisoes`."""
    if status not in ("aprovado", "reprovado", "pendente"):
        raise ValueError(f"Status de revisão inválido: {status}")

    from datetime import timezone
    client = _get_client()
    now_str = datetime.now(timezone.utc).isoformat()
    payload = {
        "token": token,
        "status": status,
        "revisado_por": revisado_por,
        "revisado_em": now_str,
        "updated_at": now_str,
    }
    result = client.table(TABLE_DESAFIO_SUBMISSAO_REVISOES).upsert(
        payload, on_conflict="token"
    ).execute()
    return result.data[0] if result.data else {}


def list_submissoes_revisoes(desafio_id: int | None = None) -> dict[str, dict]:
    """Retorna o mapeamento token -> dict de revisão (status, revisado_por, revisado_em)."""
    try:
        client = _get_client()
        query = client.table(TABLE_DESAFIO_SUBMISSAO_REVISOES).select("*")
        result = query.execute()
        return {row["token"]: row for row in (result.data or [])}
    except Exception:
        return {}


def get_desafio_clan_apuracoes(desafio_id: int) -> list[dict]:
    """Retorna os registros de apuração gravados em `desafio_clan_apuracoes` para um desafio."""
    try:
        client = _get_client()
        result = (
            client.table(TABLE_DESAFIO_CLAN_APURACOES)
            .select("*")
            .eq("desafio_id", desafio_id)
            .order("clan", desc=False)
            .execute()
        )
        return result.data or []
    except Exception:
        return []


def salvar_apuracao_clan(desafio_id: int, resultados: dict[str, Any]) -> None:
    """Salva/upserta os resultados de apuração por clã em `desafio_clan_apuracoes`
    e marca `apurado_em` na tabela `desafios`."""
    from datetime import timezone
    client = _get_client()
    now_str = datetime.now(timezone.utc).isoformat()

    rows_to_upsert = []
    for clan, ap in resultados.items():
        data = ap.to_dict() if hasattr(ap, "to_dict") else ap
        rows_to_upsert.append({
            "desafio_id": desafio_id,
            "clan": clan,
            "participantes": data["participantes"],
            "total_grupo": data["total_grupo"],
            "percentual": float(data["percentual"]),
            "pontos": int(data["pontos"]),
            "apurado_em": now_str,
        })

    if rows_to_upsert:
        client.table(TABLE_DESAFIO_CLAN_APURACOES).upsert(
            rows_to_upsert, on_conflict="desafio_id,clan"
        ).execute()

    client.table(TABLE_DESAFIOS).update({"apurado_em": now_str}).eq("id", desafio_id).execute()


def get_desafio_apuracao(desafio_id: int) -> dict:
    """Retorna o estado de apuração do desafio: resultado final se apurado, ou prévia se em andamento."""
    desafio = get_desafio(desafio_id)
    if not desafio:
        return {"desafio_id": desafio_id, "error": "Desafio não encontrado"}

    prazo_apuracao = desafio.get("prazo_apuracao")
    apurado_em = desafio.get("apurado_em")

    if apurado_em:
        apuracoes = get_desafio_clan_apuracoes(desafio_id)
        return {
            "desafio_id": desafio_id,
            "prazo_apuracao": prazo_apuracao,
            "apurado_em": apurado_em,
            "provisorio": False,
            "clas": apuracoes,
        }

    res_dict = _calcular_apuracao_atual_desafio(desafio_id)
    clas_list = [ap.to_dict() for ap in res_dict.values()]
    return {
        "desafio_id": desafio_id,
        "prazo_apuracao": prazo_apuracao,
        "apurado_em": None,
        "provisorio": True,
        "clas": clas_list,
    }


def _calcular_apuracao_atual_desafio(desafio_id: int) -> dict[str, "ApuracaoClan"]:
    """Calcula a apuração por percentual de clã de um desafio a partir do
    estado *atual* de revisões — ignora se o desafio já está `apurado_em`
    (quem decide se usa o resultado congelado ou recalcula ao vivo é o
    chamador: `get_desafio_apuracao` para a prévia, `reapurar_desafio_e_aplicar_delta`
    para reabrir um desafio já congelado). Pós-corte, toda submissão conta por
    padrão — só `revisao_status == "reprovado"` exclui (mesma regra de
    `_submissao_conta_para_pontos_individuais_coach`)."""
    submissoes = list_desafio_submissions_current(desafio_id=desafio_id, status="active_counted")
    revisoes_map = list_submissoes_revisoes(desafio_id)
    alias_map = get_coach_alias_map()

    aprovadas = []
    for s in submissoes:
        token = s.get("token")
        rev_status = revisoes_map.get(token, {}).get("status", "pendente")

        if not _submissao_conta_para_pontos_individuais_coach(s.get("submitted_at"), rev_status):
            continue

        raw_name = (s.get("raw_name") or "").strip()
        canonical = coach_identity.resolve_coach(raw_name, alias_map) if raw_name else None
        aprovadas.append({
            "coach": canonical or raw_name,
            "clan_planilha": s.get("clan") or s.get("raw_clan_current") or s.get("raw_clan_legacy"),
        })

    from desafio_percentual_clan import apurar_desafio
    rows_clas = list_coach_clas()
    coach_clas = {r["coach_canonico"]: r["clan"] for r in rows_clas}
    tamanho_grupo: dict[str, int] = {}
    for r in rows_clas:
        c = r["clan"]
        tamanho_grupo[c] = tamanho_grupo.get(c, 0) + 1

    todos_clas = ["CLÃ 1", "CLÃ 2", "CLÃ 3", "CLÃ 4", "CLÃ 5", "CLÃ 6", "CLÃ 7", "CLÃ 8"]
    return apurar_desafio(
        submissoes_aprovadas=aprovadas,
        coach_clas=coach_clas,
        tamanho_grupo_por_clan=tamanho_grupo,
        todos_os_clas=todos_clas,
    )
