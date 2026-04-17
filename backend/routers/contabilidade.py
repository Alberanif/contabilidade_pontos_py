from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import config
import google_sheets_client
import supabase_client
import points_engine

router = APIRouter()

COL_MODALIDADE = 5
COL_CLAN = 0
COL_COACH = config.COL_COACH
KEY_COLUMNS = [11]

GROUP_MODALIDADES = config.GROUP_MODALIDADES
COL_PARTICIPANTES = config.COL_PARTICIPANTES_GROUP

# Pro-bono: planilha separada, coluna K (índice 10) como chave de deduplicação
KEY_COLUMNS_PRO_BONO = [config.COL_PRO_BONO_KEY]
HASH_PREFIX_PRO_BONO = "pro_bono:"


def _normalize_clan(clan_raw: str) -> str:
    try:
        return f"CLÃ {int(clan_raw.strip())}"
    except (ValueError, AttributeError):
        return clan_raw.strip()


def _build_and_insert(record_hash, row, header, data_rows, pontos, extra_fields=None, date_col=None):
    row_number = data_rows.index(row) + 2 if row in data_rows else 0
    record_data = points_engine.build_record_data(
        record_hash=record_hash,
        row=row,
        header=header,
        modalidade_col=COL_MODALIDADE,
        clan_col=COL_CLAN,
        coach_col=COL_COACH,
        spreadsheet_id=config.GSHEET_RECORDS_SPREADSHEET_ID,
        sheet_name=config.GSHEET_RECORDS_SHEET_NAME,
        row_number=row_number,
        pontos=pontos,
        date_col=date_col,
    )
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)


def _build_and_insert_pro_bono(record_hash, row, header, data_rows, pontos, extra_fields=None, date_col=None):
    row_number = data_rows.index(row) + 2 if row in data_rows else 0
    record_data = points_engine.build_record_data(
        record_hash=record_hash,
        row=row,
        header=header,
        modalidade_col=COL_CLAN,  # dummy — será sobrescrito abaixo
        clan_col=COL_CLAN,
        coach_col=COL_COACH,
        spreadsheet_id=config.GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID,
        sheet_name=config.GSHEET_RECORDS_PRO_BONO_SHEET_NAME,
        row_number=row_number,
        pontos=pontos,
        date_col=date_col,
    )
    record_data["modalidade"] = "Pro-bono"
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)


def _process_pro_bono_records(
    processed_hashes: set[str],
) -> tuple[int, dict[str, int], dict[str, int]]:
    """Busca e processa registros Pro-bono ainda não contabilizados.

    Retorna (n_novos, pontos_por_clan, pontos_por_coach).
    """
    rows = google_sheets_client.fetch_records_pro_bono()
    if not rows:
        return 0, {}, {}

    header = rows[0]
    data_rows = rows[1:]

    new_records = points_engine.find_new_records(
        data_rows, KEY_COLUMNS_PRO_BONO, processed_hashes, hash_prefix=HASH_PREFIX_PRO_BONO
    )

    for record_hash, row in new_records:
        _build_and_insert_pro_bono(
            record_hash, row, header, data_rows,
            pontos=config.POINTS_PER_PRO_BONO,
            extra_fields={
                "status": "contabilizado",
                "status_coach": "contabilizado",
                "pontos_coach": config.POINTS_PER_PRO_BONO,
            },
            date_col=config.COL_DATE_PRO_BONO,
        )

    raw_clan_pts = points_engine.calculate_points_by_clan(
        new_records, COL_CLAN, config.POINTS_PER_PRO_BONO
    )
    pontos_por_clan = {_normalize_clan(k): v for k, v in raw_clan_pts.items()}
    coach_eligible_pb = points_engine.filter_records_by_date_from(
        new_records, config.COL_DATE_PRO_BONO, config.COACH_RANKING_START_DATE
    )
    pontos_por_coach = points_engine.calculate_points_by_coach(
        coach_eligible_pb, COL_COACH, config.POINTS_PER_PRO_BONO
    )
    return len(new_records), pontos_por_clan, pontos_por_coach


def _process_group_records(
    data_rows: list[list[str]],
    header: list[str],
    processed_hashes: set[str],
) -> tuple[int, dict[str, int], dict[str, int], dict[str, int]]:
    group_rows = points_engine.filter_by_modalidades(
        data_rows, COL_MODALIDADE, GROUP_MODALIDADES
    )
    new_records = points_engine.find_new_records(group_rows, KEY_COLUMNS, processed_hashes)

    for record_hash, row in new_records:
        raw_participantes = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
        try:
            num_participantes = max(1, int(raw_participantes))
        except (ValueError, AttributeError):
            num_participantes = 1
        record_date = points_engine._parse_date(
            row[config.COL_DATE_PAYING].strip() if config.COL_DATE_PAYING < len(row) else ""
        )
        coach_elegivel = record_date is not None and record_date >= config.COACH_RANKING_START_DATE
        _build_and_insert(
            record_hash, row, header, data_rows,
            pontos=0,
            extra_fields={
                "status": "pendente",
                "num_participantes": num_participantes,
                "status_coach": "pendente" if coach_elegivel else "contabilizado",
                "pontos_coach": 0
            },
            date_col=config.COL_DATE_PAYING,
        )

    clans_pendentes = supabase_client.get_all_pending_clans(GROUP_MODALIDADES)
    pendentes_por_clan: dict[str, int] = {}
    for raw_clan in clans_pendentes:
        remaining = supabase_client.get_pending_group_records_by_clan(raw_clan, GROUP_MODALIDADES)
        if remaining:
            pendentes_por_clan[_normalize_clan(raw_clan)] = len(remaining)
            
    coaches_pendentes = supabase_client.get_all_pending_coaches(GROUP_MODALIDADES)
    pendentes_por_coach: dict[str, int] = {}
    for c in coaches_pendentes:
        rem = supabase_client.get_pending_group_records_by_coach(c, GROUP_MODALIDADES)
        if rem:
            pendentes_por_coach[c] = len(rem)

    return len(new_records), {}, pendentes_por_clan, pendentes_por_coach


class ImportarResponse(BaseModel):
    registros_importados: int
    registros_ja_existentes: int
    mensagem: str


class AprovarClanRequest(BaseModel):
    clan: str

class AprovarCoachRequest(BaseModel):
    coach: str


class AprovarClanResponse(BaseModel):
    clan: str
    lotes_aprovados: int
    registros_promovidos: int
    pessoas_contabilizadas: int
    pessoas_em_espera: int
    pontos_adicionados: int
    novo_total: int
    pendentes_restantes: int
    mensagem: str

class AprovarCoachResponse(BaseModel):
    coach: str
    lotes_aprovados: int
    registros_promovidos: int
    pessoas_contabilizadas: int
    pessoas_em_espera: int
    pontos_adicionados: int
    novo_total: int
    pendentes_restantes: int
    mensagem: str


class ExecutarResponse(BaseModel):
    novos_registros: int
    novos_pendentes: int
    pro_bono_registros: int
    pontos_por_clan: dict[str, int]
    pontos_grupo_por_clan: dict[str, int]
    pendentes_por_clan: dict[str, int]
    pontos_por_coach: dict[str, int]
    pendentes_por_coach: dict[str, int]
    totais_atualizados: dict[str, int]
    mensagem: str


class ReprocessarResponse(BaseModel):
    registros_removidos: int
    novos_registros: int
    novos_pendentes: int
    pro_bono_registros: int
    pontos_por_clan: dict[str, int]
    pontos_grupo_por_clan: dict[str, int]
    pendentes_por_clan: dict[str, int]
    pontos_por_coach: dict[str, int]
    pendentes_por_coach: dict[str, int]
    totais_atualizados: dict[str, int]
    mensagem: str


class ImportarInicialResponse(BaseModel):
    registros_removidos: int
    coaching_individual_importados: int
    grupo_contabilizados: int
    grupo_pendentes: int
    pro_bono_importados: int
    totais_clans: dict[str, int]
    carry_over_por_clan: dict[str, int]
    totais_coaches: dict[str, int]
    carry_over_por_coach: dict[str, int]
    mensagem: str


class AtualizarPlanilhaResponse(BaseModel):
    totais_atualizados: dict[str, int]
    mensagem: str


class PreencherDatasResponse(BaseModel):
    registros_atualizados: int
    registros_sem_data: int
    mensagem: str


@router.post("/importar", response_model=ImportarResponse)
def importar_registros():
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
                extra_fields={"status": "contabilizado", "status_coach": "contabilizado", "pontos_coach": 0},
                date_col=config.COL_DATE_PAYING,
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
    try:
        clan = _normalize_clan(body.clan)
        pending = supabase_client.get_pending_group_records_by_clan(clan, GROUP_MODALIDADES)
        carry_over = supabase_client.get_clan_carry_over(clan)

        ids_to_promote, n_complete, novo_carry_over = points_engine.compute_batch_promotions_by_people(
            pending, carry_over, config.BATCH_SIZE_GROUP
        )

        if n_complete == 0:
            accumulated = carry_over + sum(r.get("num_participantes", 1) for r in pending)
            current_total = supabase_client.get_clan_totals().get(clan, 0)
            supabase_client.upsert_clan_total(clan, current_total, pessoas_em_espera=accumulated)
            return AprovarClanResponse(
                clan=clan,
                lotes_aprovados=0,
                registros_promovidos=0,
                pessoas_contabilizadas=0,
                pessoas_em_espera=accumulated,
                pontos_adicionados=0,
                novo_total=current_total,
                pendentes_restantes=len(pending),
                mensagem=f"Nenhum lote completo disponível. {len(pending)} registro(s) ainda aguardando.",
            )

        pessoas_contabilizadas = carry_over + sum(r.get("num_participantes", 1) for r in pending)

        supabase_client.promote_pending_to_contabilizado(
            ids_to_promote, config.POINTS_PER_RECORD_IN_BATCH
        )
        pontos_adicionados = n_complete * config.POINTS_PER_BATCH_GROUP
        current_totals = supabase_client.get_clan_totals()
        novo_total = current_totals.get(clan, 0) + pontos_adicionados
        supabase_client.upsert_clan_total(clan, novo_total, pessoas_em_espera=novo_carry_over)

        pendentes_restantes = len(pending) - len(ids_to_promote)

        return AprovarClanResponse(
            clan=clan,
            lotes_aprovados=n_complete,
            registros_promovidos=len(ids_to_promote),
            pessoas_contabilizadas=pessoas_contabilizadas,
            pessoas_em_espera=novo_carry_over,
            pontos_adicionados=pontos_adicionados,
            novo_total=novo_total,
            pendentes_restantes=pendentes_restantes,
            mensagem=(
                f"{n_complete} lote(s) aprovado(s) para {clan}. "
                f"+{pontos_adicionados} pontos. "
                f"Total agora: {novo_total} pts. "
                f"{novo_carry_over} pessoa(s) em espera."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/aprovar-coach", response_model=AprovarCoachResponse)
def aprovar_coach(body: AprovarCoachRequest):
    try:
        coach = body.coach.strip()
        pending = supabase_client.get_pending_group_records_by_coach(coach, GROUP_MODALIDADES)
        carry_over = supabase_client.get_coach_carry_over(coach)

        ids_to_promote, n_complete, novo_carry_over = points_engine.compute_batch_promotions_by_people(
            pending, carry_over, config.BATCH_SIZE_GROUP
        )

        if n_complete == 0:
            accumulated = carry_over + sum(r.get("num_participantes", 1) for r in pending)
            current_total = supabase_client.get_coach_totals().get(coach, 0)
            supabase_client.upsert_coach_total(coach, current_total, pessoas_em_espera=accumulated)
            return AprovarCoachResponse(
                coach=coach,
                lotes_aprovados=0,
                registros_promovidos=0,
                pessoas_contabilizadas=0,
                pessoas_em_espera=accumulated,
                pontos_adicionados=0,
                novo_total=current_total,
                pendentes_restantes=len(pending),
                mensagem=f"Nenhum lote completo disponível. {len(pending)} registro(s) ainda aguardando.",
            )

        pessoas_contabilizadas = carry_over + sum(r.get("num_participantes", 1) for r in pending)

        supabase_client.promote_pending_to_contabilizado_coach(
            ids_to_promote, config.POINTS_PER_RECORD_IN_BATCH
        )
        pontos_adicionados = n_complete * config.POINTS_PER_BATCH_GROUP
        current_totals = supabase_client.get_coach_totals()
        novo_total = current_totals.get(coach, 0) + pontos_adicionados
        supabase_client.upsert_coach_total(coach, novo_total, pessoas_em_espera=novo_carry_over)

        pendentes_restantes = len(pending) - len(ids_to_promote)

        return AprovarCoachResponse(
            coach=coach,
            lotes_aprovados=n_complete,
            registros_promovidos=len(ids_to_promote),
            pessoas_contabilizadas=pessoas_contabilizadas,
            pessoas_em_espera=novo_carry_over,
            pontos_adicionados=pontos_adicionados,
            novo_total=novo_total,
            pendentes_restantes=pendentes_restantes,
            mensagem=(
                f"{n_complete} lote(s) aprovado(s) para {coach}. "
                f"+{pontos_adicionados} pontos. "
                f"Total agora: {novo_total} pts. "
                f"{novo_carry_over} pessoa(s) em espera."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executar", response_model=ExecutarResponse)
def executar_contabilidade():
    try:
        rows = google_sheets_client.fetch_records()
        if not rows:
            return ExecutarResponse(
                novos_registros=0, novos_pendentes=0, pro_bono_registros=0,
                pontos_por_clan={}, pontos_grupo_por_clan={},
                pendentes_por_clan={}, pontos_por_coach={}, pendentes_por_coach={},
                totais_atualizados={},
                mensagem="Nenhum dado encontrado na planilha de registros.",
            )

        header = rows[0]
        data_rows = rows[1:]

        coaching_rows = points_engine.filter_by_modalidade(
            data_rows, COL_MODALIDADE, "Coaching Individual"
        )
        processed_hashes = supabase_client.get_processed_hashes()
        new_records = points_engine.find_new_records(coaching_rows, KEY_COLUMNS, processed_hashes)

        for record_hash, row in new_records:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
                extra_fields={
                    "status_coach": "contabilizado",
                    "pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL
                },
                date_col=config.COL_DATE_PAYING,
            )

        raw_points = points_engine.calculate_points_by_clan(
            new_records, COL_CLAN, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_clan = {_normalize_clan(k): v for k, v in raw_points.items()}

        coach_eligible_ci = points_engine.filter_records_by_date_from(
            new_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
        )
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coach_eligible_ci, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        processed_hashes = supabase_client.get_processed_hashes()
        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan, pendentes_por_coach = _process_group_records(
            data_rows, header, processed_hashes
        )

        # Processar registros Pro-bono (pontos imediatos, sem fila)
        processed_hashes = supabase_client.get_processed_hashes()
        n_pro_bono, pro_bono_clan_pts, pro_bono_coach_pts = _process_pro_bono_records(processed_hashes)

        all_new_points: dict[str, int] = {}
        for clan, pts in {**pontos_por_clan, **pontos_grupo_por_clan, **pro_bono_clan_pts}.items():
            all_new_points[clan] = all_new_points.get(clan, 0) + pts

        if all_new_points:
            current_totals = supabase_client.get_clan_totals()
            for clan, new_points in all_new_points.items():
                supabase_client.upsert_clan_total(clan, current_totals.get(clan, 0) + new_points)
            totais_atualizados = {clan: current_totals.get(clan, 0) + pts for clan, pts in all_new_points.items()}
        else:
            totais_atualizados = {}

        all_coach_points: dict[str, int] = {}
        for coach, pts in {**pontos_por_coach, **pro_bono_coach_pts}.items():
            all_coach_points[coach] = all_coach_points.get(coach, 0) + pts

        if all_coach_points:
            current_coach_totals = supabase_client.get_coach_totals()
            for coach, new_points in all_coach_points.items():
                supabase_client.upsert_coach_total(coach, current_coach_totals.get(coach, 0) + new_points)

        partes = []
        if new_records:
            partes.append(f"{len(new_records)} Coaching Individual contabilizados")
        if novos_pendentes:
            partes.append(f"{novos_pendentes} registro(s) de grupo/empresa adicionados à fila")
        if n_pro_bono:
            partes.append(f"{n_pro_bono} Pro-bono contabilizados")
        if not partes:
            partes.append("Nenhum novo registro encontrado")

        return ExecutarResponse(
            novos_registros=len(new_records),
            novos_pendentes=novos_pendentes,
            pro_bono_registros=n_pro_bono,
            pontos_por_clan=pontos_por_clan,
            pontos_grupo_por_clan=pontos_grupo_por_clan,
            pendentes_por_clan=pendentes_por_clan,
            pontos_por_coach=all_coach_points,
            pendentes_por_coach=pendentes_por_coach,
            totais_atualizados=totais_atualizados,
            mensagem=". ".join(partes) + ".",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reprocessar", response_model=ReprocessarResponse)
def reprocessar_contabilidade():
    try:
        registros_removidos = supabase_client.delete_all_registros()
        supabase_client.reset_all_totals()

        rows = google_sheets_client.fetch_records()
        if not rows:
            return ReprocessarResponse(
                registros_removidos=registros_removidos,
                novos_registros=0, novos_pendentes=0, pro_bono_registros=0,
                pontos_por_clan={}, pontos_grupo_por_clan={},
                pendentes_por_clan={}, pontos_por_coach={}, pendentes_por_coach={},
                totais_atualizados={},
                mensagem="Registros limpos. Nenhum dado na planilha de registros.",
            )

        header = rows[0]
        data_rows = rows[1:]

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
                extra_fields={
                    "status_coach": "contabilizado",
                    "pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL
                },
                date_col=config.COL_DATE_PAYING,
            )

        raw_points = points_engine.calculate_points_by_clan(
            new_records, COL_CLAN, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_clan = {_normalize_clan(k): v for k, v in raw_points.items()}

        coach_eligible_ci = points_engine.filter_records_by_date_from(
            new_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
        )
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coach_eligible_ci, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan, pendentes_por_coach = _process_group_records(
            data_rows, header, processed_hashes=set()
        )

        # Processar registros Pro-bono (banco zerado, usar set() vazio)
        n_pro_bono, pro_bono_clan_pts, pro_bono_coach_pts = _process_pro_bono_records(set())

        all_points: dict[str, int] = {}
        for clan, pts in {**pontos_por_clan, **pontos_grupo_por_clan, **pro_bono_clan_pts}.items():
            all_points[clan] = all_points.get(clan, 0) + pts

        all_coach_points: dict[str, int] = {}
        for coach, pts in {**pontos_por_coach, **pro_bono_coach_pts}.items():
            all_coach_points[coach] = all_coach_points.get(coach, 0) + pts

        for clan, total in all_points.items():
            supabase_client.upsert_clan_total(clan, total)

        for coach, total in all_coach_points.items():
            supabase_client.upsert_coach_total(coach, total)

        partes = [
            f"{registros_removidos} removidos",
            f"{len(new_records)} Coaching Individual processados",
        ]
        if novos_pendentes:
            partes.append(f"{novos_pendentes} grupo/empresa na fila")
        if n_pro_bono:
            partes.append(f"{n_pro_bono} Pro-bono contabilizados")

        return ReprocessarResponse(
            registros_removidos=registros_removidos,
            novos_registros=len(new_records),
            novos_pendentes=novos_pendentes,
            pro_bono_registros=n_pro_bono,
            pontos_por_clan=pontos_por_clan,
            pontos_grupo_por_clan=pontos_grupo_por_clan,
            pendentes_por_clan=pendentes_por_clan,
            pontos_por_coach=all_coach_points,
            pendentes_por_coach=pendentes_por_coach,
            totais_atualizados=all_points,
            mensagem=f"Reprocessamento completo: {'. '.join(partes)}.",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/importar-inicial", response_model=ImportarInicialResponse)
def importar_inicial():
    """Importa todos os registros da planilha, semeando totais da planilha de pontuação.
    Registros de grupo com pessoas suficientes (>= lote) → contabilizado.
    Registros de grupo sem lote completo → pendente (fila para futuras contabilizações).
    Apaga todos os dados existentes antes."""
    try:
        # Fase 1: Limpar banco
        registros_removidos = supabase_client.delete_all_registros()
        supabase_client.reset_all_totals()

        # Fase 2: Buscar registros
        rows = google_sheets_client.fetch_records()
        if not rows:
            return ImportarInicialResponse(
                registros_removidos=registros_removidos,
                coaching_individual_importados=0,
                grupo_contabilizados=0,
                grupo_pendentes=0,
                pro_bono_importados=0,
                totais_clans={},
                carry_over_por_clan={},
                totais_coaches={},
                carry_over_por_coach={},
                mensagem="Registros limpos. Nenhum dado na planilha de registros.",
            )

        header = rows[0]
        data_rows = rows[1:]

        # Fase 3: Importar Coaching Individual como contabilizado
        coaching_rows = points_engine.filter_by_modalidade(
            data_rows, COL_MODALIDADE, "Coaching Individual"
        )
        coaching_records = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS), row)
            for row in coaching_rows
        ]
        for record_hash, row in coaching_records:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=0,
                extra_fields={
                    "status": "contabilizado",
                    "status_coach": "contabilizado",
                    "pontos_coach": 0,
                },
                date_col=config.COL_DATE_PAYING,
            )

        # Fase 4: Pré-calcular total de pessoas por clã e por coach nos registros de grupo.
        # Isso determina se os registros vão como contabilizado ou pendente.
        group_rows = points_engine.filter_by_modalidades(
            data_rows, COL_MODALIDADE, GROUP_MODALIDADES
        )
        group_records = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS), row)
            for row in group_rows
        ]

        clan_group_people: dict[str, int] = {}
        coach_group_people: dict[str, int] = {}
        for _, row in group_records:
            clan = _normalize_clan(row[COL_CLAN]) if COL_CLAN < len(row) else "DESCONHECIDO"
            coach = row[COL_COACH].strip() if COL_COACH < len(row) else ""
            if not coach:
                coach = "DESCONHECIDO"
            raw_part = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
            try:
                n = max(1, int(raw_part))
            except (ValueError, AttributeError):
                n = 1
            clan_group_people[clan] = clan_group_people.get(clan, 0) + n
            coach_group_people[coach] = coach_group_people.get(coach, 0) + n

        # Clãs/coaches com total >= BATCH_SIZE tiveram pelo menos 1 lote completo.
        # Seus registros vão como contabilizado (a pontuação já está na planilha).
        # Clãs/coaches com total < BATCH_SIZE nunca completaram um lote: vão para pendente.
        clans_com_lote = {c for c, t in clan_group_people.items() if t >= config.BATCH_SIZE_GROUP}
        coaches_com_lote = {c for c, t in coach_group_people.items() if t >= config.BATCH_SIZE_GROUP}

        grupo_contabilizados = 0
        grupo_pendentes = 0

        for record_hash, row in group_records:
            clan = _normalize_clan(row[COL_CLAN]) if COL_CLAN < len(row) else "DESCONHECIDO"
            coach = row[COL_COACH].strip() if COL_COACH < len(row) else ""
            if not coach:
                coach = "DESCONHECIDO"
            raw_part = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
            try:
                num_participantes = max(1, int(raw_part))
            except (ValueError, AttributeError):
                num_participantes = 1

            status = "contabilizado" if clan in clans_com_lote else "pendente"
            status_coach = "contabilizado" if coach in coaches_com_lote else "pendente"

            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=0,
                extra_fields={
                    "status": status,
                    "status_coach": status_coach,
                    "num_participantes": num_participantes,
                    "pontos_coach": 0,
                },
                date_col=config.COL_DATE_PAYING,
            )

            if status == "contabilizado":
                grupo_contabilizados += 1
            else:
                grupo_pendentes += 1

        # Fase 5: Seed totais dos clãs a partir da planilha de pontuação
        ranking = google_sheets_client.fetch_ranking()
        clan_totals_from_sheet = {r["clan"]: r["total_pontos"] for r in ranking}

        # Fase 6: Totais e carry-over por clã.
        # - Lote completo: carry_over = total_pessoas % BATCH_SIZE (sobra do último lote)
        # - Sem lote completo: carry_over = 0 (as pessoas pendentes ficam nos registros, não no carry-over)
        carry_over_por_clan: dict[str, int] = {}
        all_clans = set(clan_totals_from_sheet.keys()) | set(clan_group_people.keys())
        for clan in all_clans:
            total = clan_totals_from_sheet.get(clan, 0)
            pessoas = clan_group_people.get(clan, 0)
            carry_over = pessoas % config.BATCH_SIZE_GROUP if clan in clans_com_lote else 0
            carry_over_por_clan[clan] = carry_over
            supabase_client.upsert_clan_total(clan, total, pessoas_em_espera=carry_over)

        # Fase 7: Totais e carry-over por coach.
        # Apenas registros >= COACH_RANKING_START_DATE contam para pontuação de coaches.
        coach_eligible_seed = points_engine.filter_records_by_date_from(
            coaching_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
        )
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coach_eligible_seed, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        carry_over_por_coach: dict[str, int] = {}
        all_coaches = set(pontos_por_coach.keys()) | set(coach_group_people.keys())
        for coach in all_coaches:
            total = pontos_por_coach.get(coach, 0)
            pessoas = coach_group_people.get(coach, 0)
            carry_over = pessoas % config.BATCH_SIZE_GROUP if coach in coaches_com_lote else 0
            carry_over_por_coach[coach] = carry_over
            supabase_client.upsert_coach_total(coach, total, pessoas_em_espera=carry_over)

        # Fase 8: Importar registros Pro-bono como contabilizado (10 pts cada, sem fila)
        pb_rows = google_sheets_client.fetch_records_pro_bono()
        pro_bono_importados = 0
        if pb_rows:
            pb_header = pb_rows[0]
            pb_data_rows = pb_rows[1:]
            pb_records = [
                (points_engine.compute_record_hash(row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO), row)
                for row in pb_data_rows
            ]
            for record_hash, row in pb_records:
                _build_and_insert_pro_bono(
                    record_hash, row, pb_header, pb_data_rows,
                    pontos=0,
                    extra_fields={
                        "status": "contabilizado",
                        "status_coach": "contabilizado",
                        "pontos_coach": 0,
                    },
                    date_col=config.COL_DATE_PRO_BONO,
                )
            pro_bono_importados = len(pb_records)
            # Os totais já foram semeados a partir da planilha de ranking (Fases 6 e 7).
            # Não somamos pontos Pro-bono aqui — os registros são apenas marcados como
            # contabilizados para que executar() não os reprocesse futuramente.

        partes = [
            f"{registros_removidos} registros removidos",
            f"{len(coaching_records)} Coaching Individual importados",
            f"{grupo_contabilizados} grupo/empresa contabilizados",
        ]
        if grupo_pendentes:
            partes.append(f"{grupo_pendentes} grupo/empresa na fila (aguardando lote completo)")
        if pro_bono_importados:
            partes.append(f"{pro_bono_importados} Pro-bono importados")

        return ImportarInicialResponse(
            registros_removidos=registros_removidos,
            coaching_individual_importados=len(coaching_records),
            grupo_contabilizados=grupo_contabilizados,
            grupo_pendentes=grupo_pendentes,
            pro_bono_importados=pro_bono_importados,
            totais_clans=clan_totals_from_sheet,
            carry_over_por_clan=carry_over_por_clan,
            totais_coaches=pontos_por_coach,
            carry_over_por_coach=carry_over_por_coach,
            mensagem=f"Importação inicial concluída: {'. '.join(partes)}.",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/date-sample")
def debug_date_sample():
    """Diagnóstico: resumo por modalidade/mês e amostra dos registros elegíveis."""
    rows_pay = google_sheets_client.fetch_records()
    rows_pb  = google_sheets_client.fetch_records_pro_bono()

    ci_total = ci_elegiveis = 0
    group_total = group_elegiveis_coach = 0
    ci_abril_sample = []

    for i, row in enumerate(rows_pay[1:], start=2):
        modalidade = row[COL_MODALIDADE].strip() if COL_MODALIDADE < len(row) else ""
        coach = row[config.COL_COACH].strip() if config.COL_COACH < len(row) else ""
        raw_date = row[config.COL_DATE_PAYING] if config.COL_DATE_PAYING < len(row) else ""
        parsed = points_engine._parse_date(raw_date)
        elegivel = parsed is None or parsed >= config.COACH_RANKING_START_DATE

        if modalidade.upper() == "COACHING INDIVIDUAL":
            ci_total += 1
            if elegivel:
                ci_elegiveis += 1
                if len(ci_abril_sample) < 10:
                    ci_abril_sample.append({
                        "linha": i, "coach": coach,
                        "col_k_raw": raw_date, "data_parsed": str(parsed) if parsed else None,
                    })
        elif any(m.upper() in modalidade.upper() for m in ["GRUPO", "EMPRESA"]):
            group_total += 1
            if elegivel:
                group_elegiveis_coach += 1

    pb_total = pb_elegiveis = 0
    pb_abril_sample = []
    for i, row in enumerate(rows_pb[1:], start=2):
        coach = row[config.COL_COACH].strip() if config.COL_COACH < len(row) else ""
        raw_date = row[config.COL_DATE_PRO_BONO] if config.COL_DATE_PRO_BONO < len(row) else ""
        parsed = points_engine._parse_date(raw_date)
        elegivel = parsed is None or parsed >= config.COACH_RANKING_START_DATE
        pb_total += 1
        if elegivel:
            pb_elegiveis += 1
            if len(pb_abril_sample) < 10:
                pb_abril_sample.append({
                    "linha": i, "coach": coach,
                    "col_j_raw": raw_date, "data_parsed": str(parsed) if parsed else None,
                })

    return {
        "resumo": {
            "ci_total": ci_total,
            "ci_elegiveis_abril_em_diante": ci_elegiveis,
            "group_total": group_total,
            "group_elegiveis_coach_abril_em_diante": group_elegiveis_coach,
            "pro_bono_total": pb_total,
            "pro_bono_elegiveis_abril_em_diante": pb_elegiveis,
        },
        "ci_elegiveis_amostra": ci_abril_sample,
        "pro_bono_elegiveis_amostra": pb_abril_sample,
        "config": {
            "col_date_paying": config.COL_DATE_PAYING,
            "col_date_pro_bono": config.COL_DATE_PRO_BONO,
            "coach_ranking_start": str(config.COACH_RANKING_START_DATE),
        },
    }


@router.post("/atualizar-planilha", response_model=AtualizarPlanilhaResponse)
def atualizar_planilha():
    """Sincroniza os totais de pontos dos clãs do banco para a planilha Google Sheets."""
    try:
        totais = supabase_client.get_clan_totals()
        resultado = google_sheets_client.sync_clan_totals_to_sheet(totais)
        return AtualizarPlanilhaResponse(
            totais_atualizados=resultado,
            mensagem=f"{len(resultado)} clã(s) atualizados na planilha.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preencher-datas", response_model=PreencherDatasResponse)
def preencher_datas():
    """Popula data_registro para registros existentes a partir das planilhas. Uso único (backfill)."""
    try:
        atualizados = 0
        sem_data = 0

        rows_pay = google_sheets_client.fetch_records()
        if rows_pay:
            data_rows = rows_pay[1:]
            for row in data_rows:
                record_hash = points_engine.compute_record_hash(row, KEY_COLUMNS)
                raw_date = row[config.COL_DATE_PAYING].strip() if config.COL_DATE_PAYING < len(row) else ""
                parsed = points_engine._parse_date(raw_date)
                val = str(parsed) if parsed else None
                encontrado = supabase_client.update_data_registro(record_hash, val)
                if encontrado:
                    if val:
                        atualizados += 1
                    else:
                        sem_data += 1

        rows_pb = google_sheets_client.fetch_records_pro_bono()
        if rows_pb:
            data_rows_pb = rows_pb[1:]
            for row in data_rows_pb:
                record_hash = points_engine.compute_record_hash(
                    row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO
                )
                raw_date = row[config.COL_DATE_PRO_BONO].strip() if config.COL_DATE_PRO_BONO < len(row) else ""
                parsed = points_engine._parse_date(raw_date)
                val = str(parsed) if parsed else None
                encontrado = supabase_client.update_data_registro(record_hash, val)
                if encontrado:
                    if val:
                        atualizados += 1
                    else:
                        sem_data += 1

        return PreencherDatasResponse(
            registros_atualizados=atualizados,
            registros_sem_data=sem_data,
            mensagem=f"Backfill concluído: {atualizados} registro(s) com data. {sem_data} sem data válida.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
