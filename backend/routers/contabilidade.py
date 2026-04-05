from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
import google_sheets_client
import supabase_client
import points_engine

router = APIRouter()

# Índices das colunas na planilha de registros (verificados via inspect_sheet.py).
# [0] Clã (número), [1] Coach, [2] Cliente, [3] Telefone/email,
# [4] Data início, [5] Tipo de atendimento, [10] Submitted At, [11] Token
COL_MODALIDADE = 5  # "Tipo de atendimento"
COL_CLAN = 0        # Número do clã (ex: "5" → normalizado para "CLÃ 5")
KEY_COLUMNS = [11]  # Token único de submissão

GROUP_MODALIDADES = config.GROUP_MODALIDADES


def _normalize_clan(clan_raw: str) -> str:
    """Converte número do clã ('5') para formato padrão ('CLÃ 5')."""
    try:
        return f"CLÃ {int(clan_raw.strip())}"
    except (ValueError, AttributeError):
        return clan_raw.strip()


def _build_and_insert(record_hash, row, header, data_rows, pontos, extra_fields=None):
    """Constrói o dict do registro, aplica campos extras e insere no Supabase."""
    row_number = data_rows.index(row) + 2 if row in data_rows else 0
    record_data = points_engine.build_record_data(
        record_hash=record_hash,
        row=row,
        header=header,
        modalidade_col=COL_MODALIDADE,
        clan_col=COL_CLAN,
        spreadsheet_id=config.GSHEET_RECORDS_SPREADSHEET_ID,
        sheet_name=config.GSHEET_RECORDS_SHEET_NAME,
        row_number=row_number,
        pontos=pontos,
    )
    # Normaliza o clã antes de salvar: "5" → "CLÃ 5"
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)


def _process_group_records(
    data_rows: list[list[str]],
    header: list[str],
    processed_hashes: set[str],
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Insere novos registros de grupo/empresa como pendentes. SEM auto-promoção.

    A promoção de lotes e contabilização de pontos é feita exclusivamente
    pela aba Fila (endpoint /aprovar-clan), onde o usuário aprova manualmente.

    Retorna:
      (novos_pendentes_inseridos, {}, pendentes_por_clan)
    """
    # 1. Filtrar linhas de grupo/empresa
    group_rows = points_engine.filter_by_modalidades(
        data_rows, COL_MODALIDADE, GROUP_MODALIDADES
    )

    # 2. Detectar registros genuinamente novos
    new_records = points_engine.find_new_records(group_rows, KEY_COLUMNS, processed_hashes)

    # 3. Inserir novos como status='pendente', pontos=0
    for record_hash, row in new_records:
        _build_and_insert(
            record_hash, row, header, data_rows,
            pontos=0,
            extra_fields={"status": "pendente"},
        )

    # 4. Retornar contagem atual de pendentes por clã (sem promover nada)
    clans_pendentes = supabase_client.get_all_pending_clans(GROUP_MODALIDADES)
    pendentes_por_clan: dict[str, int] = {}
    for raw_clan in clans_pendentes:
        remaining = supabase_client.get_pending_group_records_by_clan(raw_clan, GROUP_MODALIDADES)
        if remaining:
            pendentes_por_clan[_normalize_clan(raw_clan)] = len(remaining)

    # pontos_grupo_por_clan é sempre vazio aqui — pontos só são atribuídos via /aprovar-clan
    return len(new_records), {}, pendentes_por_clan


class ImportarResponse(BaseModel):
    registros_importados: int
    registros_ja_existentes: int
    mensagem: str


class AprovarClanRequest(BaseModel):
    clan: str


class AprovarClanResponse(BaseModel):
    clan: str
    lotes_aprovados: int
    registros_promovidos: int
    pontos_adicionados: int
    novo_total: int
    pendentes_restantes: int
    mensagem: str


class ExecutarResponse(BaseModel):
    novos_registros: int
    novos_pendentes: int
    pontos_por_clan: dict[str, int]
    pontos_grupo_por_clan: dict[str, int]
    pendentes_por_clan: dict[str, int]
    totais_atualizados: dict[str, int]
    mensagem: str


class ReprocessarResponse(BaseModel):
    registros_removidos: int
    novos_registros: int
    novos_pendentes: int
    pontos_por_clan: dict[str, int]
    pontos_grupo_por_clan: dict[str, int]
    pendentes_por_clan: dict[str, int]
    totais_atualizados: dict[str, int]
    mensagem: str


@router.post("/importar", response_model=ImportarResponse)
def importar_registros():
    """Importa registros existentes da planilha SEM recalcular pontos.
    Apenas popula os hashes para evitar reprocessamento futuro.
    Não altera totais por clã.
    """
    try:
        rows = google_sheets_client.fetch_records()
        if not rows:
            return ImportarResponse(
                registros_importados=0,
                registros_ja_existentes=0,
                mensagem="Nenhum dado na planilha.",
            )
        header = rows[0]
        data_rows = rows[1:]

        processed_hashes = supabase_client.get_processed_hashes()
        all_new = points_engine.find_new_records(data_rows, KEY_COLUMNS, processed_hashes)
        ja_existentes = len(data_rows) - len(all_new)

        for record_hash, row in all_new:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=0,
                extra_fields={"status": "contabilizado"},
            )

        return ImportarResponse(
            registros_importados=len(all_new),
            registros_ja_existentes=ja_existentes,
            mensagem=(
                f"{len(all_new)} registro(s) importados como processados. "
                f"{ja_existentes} já existiam. "
                "Nenhum ponto foi alterado."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aprovar-clan", response_model=AprovarClanResponse)
def aprovar_clan(body: AprovarClanRequest):
    """Aprova os lotes completos de grupo/empresa de um clã e contabiliza os pontos."""
    try:
        # Normaliza o clã recebido para garantir consistência ("5" ou "CLÃ 5" → "CLÃ 5")
        clan = _normalize_clan(body.clan)
        pending = supabase_client.get_pending_group_records_by_clan(clan, GROUP_MODALIDADES)
        ids_to_promote, n_complete = points_engine.compute_batch_promotions(
            pending, config.BATCH_SIZE_GROUP
        )

        if n_complete == 0:
            return AprovarClanResponse(
                clan=clan,
                lotes_aprovados=0,
                registros_promovidos=0,
                pontos_adicionados=0,
                novo_total=supabase_client.get_clan_totals().get(clan, 0),
                pendentes_restantes=len(pending),
                mensagem=f"Nenhum lote completo disponível. {len(pending)} registro(s) ainda aguardando.",
            )

        # Promover registros e atualizar Supabase
        supabase_client.promote_pending_to_contabilizado(
            ids_to_promote, config.POINTS_PER_RECORD_IN_BATCH
        )
        pontos_adicionados = n_complete * config.POINTS_PER_BATCH_GROUP
        current_totals = supabase_client.get_clan_totals()
        novo_total = current_totals.get(clan, 0) + pontos_adicionados
        supabase_client.upsert_clan_total(clan, novo_total)

        # Atualizar planilha de totais
        google_sheets_client.update_clan_totals({clan: pontos_adicionados})

        pendentes_restantes = len(pending) - len(ids_to_promote)

        return AprovarClanResponse(
            clan=clan,
            lotes_aprovados=n_complete,
            registros_promovidos=len(ids_to_promote),
            pontos_adicionados=pontos_adicionados,
            novo_total=novo_total,
            pendentes_restantes=pendentes_restantes,
            mensagem=(
                f"{n_complete} lote(s) aprovado(s) para {clan}. "
                f"+{pontos_adicionados} pontos. "
                f"Total agora: {novo_total} pts."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executar", response_model=ExecutarResponse)
def executar_contabilidade():
    """Executa a contagem de pontos para novos registros de todas as modalidades."""
    try:
        rows = google_sheets_client.fetch_records()
        if not rows:
            return ExecutarResponse(
                novos_registros=0, novos_pendentes=0,
                pontos_por_clan={}, pontos_grupo_por_clan={},
                pendentes_por_clan={}, totais_atualizados={},
                mensagem="Nenhum dado encontrado na planilha de registros.",
            )

        header = rows[0]
        data_rows = rows[1:]

        # --- Coaching Individual ---
        coaching_rows = points_engine.filter_by_modalidade(
            data_rows, COL_MODALIDADE, "Coaching Individual"
        )
        processed_hashes = supabase_client.get_processed_hashes()
        new_records = points_engine.find_new_records(coaching_rows, KEY_COLUMNS, processed_hashes)

        for record_hash, row in new_records:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
            )

        raw_points = points_engine.calculate_points_by_clan(
            new_records, COL_CLAN, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_clan = {_normalize_clan(k): v for k, v in raw_points.items()}

        # --- Grupo / Empresa (recarregar hashes para incluir os individuais inseridos acima) ---
        processed_hashes = supabase_client.get_processed_hashes()
        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan = _process_group_records(
            data_rows, header, processed_hashes
        )

        # --- Atualizar totais (Supabase + Sheets) ---
        all_new_points: dict[str, int] = {}
        for clan, pts in {**pontos_por_clan, **pontos_grupo_por_clan}.items():
            all_new_points[clan] = all_new_points.get(clan, 0) + pts

        if all_new_points:
            current_totals = supabase_client.get_clan_totals()
            for clan, new_points in all_new_points.items():
                supabase_client.upsert_clan_total(clan, current_totals.get(clan, 0) + new_points)
            totais_atualizados = google_sheets_client.update_clan_totals(all_new_points)
        else:
            totais_atualizados = {}

        partes = []
        if new_records:
            partes.append(f"{len(new_records)} Coaching Individual contabilizados")
        if novos_pendentes:
            partes.append(f"{novos_pendentes} registro(s) de grupo/empresa adicionados à fila")
        if pontos_grupo_por_clan:
            partes.append(f"lote(s) completos contabilizados para {len(pontos_grupo_por_clan)} clã(s)")
        if not partes:
            partes.append("Nenhum novo registro encontrado")

        return ExecutarResponse(
            novos_registros=len(new_records),
            novos_pendentes=novos_pendentes,
            pontos_por_clan=pontos_por_clan,
            pontos_grupo_por_clan=pontos_grupo_por_clan,
            pendentes_por_clan=pendentes_por_clan,
            totais_atualizados=totais_atualizados,
            mensagem=". ".join(partes) + ".",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reprocessar", response_model=ReprocessarResponse)
def reprocessar_contabilidade():
    """Limpa todos os registros e reprocessa tudo do zero."""
    try:
        registros_removidos = supabase_client.delete_all_registros()
        supabase_client.reset_all_totals()

        rows = google_sheets_client.fetch_records()
        if not rows:
            return ReprocessarResponse(
                registros_removidos=registros_removidos,
                novos_registros=0, novos_pendentes=0,
                pontos_por_clan={}, pontos_grupo_por_clan={},
                pendentes_por_clan={}, totais_atualizados={},
                mensagem="Registros limpos. Nenhum dado na planilha de registros.",
            )

        header = rows[0]
        data_rows = rows[1:]

        # --- Coaching Individual ---
        coaching_rows = points_engine.filter_by_modalidade(
            data_rows, COL_MODALIDADE, "Coaching Individual"
        )
        new_records = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS), row)
            for row in coaching_rows
        ]
        for record_hash, row in new_records:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
            )

        raw_points = points_engine.calculate_points_by_clan(
            new_records, COL_CLAN, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_clan = {_normalize_clan(k): v for k, v in raw_points.items()}

        # --- Grupo / Empresa (DB limpo, nenhum hash existente) ---
        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan = _process_group_records(
            data_rows, header, processed_hashes=set()
        )

        # --- Salvar totais (reprocessar: valores absolutos, não incrementos) ---
        all_points: dict[str, int] = {}
        for clan, pts in {**pontos_por_clan, **pontos_grupo_por_clan}.items():
            all_points[clan] = all_points.get(clan, 0) + pts

        for clan, total in all_points.items():
            supabase_client.upsert_clan_total(clan, total)

        totais_atualizados = google_sheets_client.update_clan_totals(all_points)

        return ReprocessarResponse(
            registros_removidos=registros_removidos,
            novos_registros=len(new_records),
            novos_pendentes=novos_pendentes,
            pontos_por_clan=pontos_por_clan,
            pontos_grupo_por_clan=pontos_grupo_por_clan,
            pendentes_por_clan=pendentes_por_clan,
            totais_atualizados=totais_atualizados,
            mensagem=(
                f"Reprocessamento completo: {registros_removidos} removidos, "
                f"{len(new_records)} Coaching Individual processados, "
                f"{novos_pendentes} grupo/empresa na fila."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
