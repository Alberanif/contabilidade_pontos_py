import hashlib
import json
import re
from datetime import date, datetime


def compute_record_hash(row: list[str], key_columns: list[int], prefix: str = "") -> str:
    """Calcula hash SHA-256 determinístico a partir das colunas-chave.

    O parâmetro opcional `prefix` permite namespacing para evitar colisões
    entre fontes de dados diferentes (ex: registros pagantes vs. pro-bono).
    """
    key_values = []
    for col_idx in key_columns:
        val = row[col_idx].strip() if col_idx < len(row) else ""
        key_values.append(val)
    raw = prefix + "|".join(key_values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def filter_by_modalidade(
    rows: list[list[str]], modalidade_col: int, modalidade_value: str
) -> list[list[str]]:
    """Filtra linhas onde a coluna de modalidade corresponde ao valor desejado."""
    result = []
    for row in rows:
        if modalidade_col < len(row):
            cell_value = row[modalidade_col].strip()
            if cell_value.upper() == modalidade_value.upper():
                result.append(row)
    return result


def filter_by_modalidades(
    rows: list[list[str]], modalidade_col: int, modalidade_values: list[str]
) -> list[list[str]]:
    """Filtra linhas onde a coluna de modalidade corresponde a qualquer valor da lista."""
    normalized = {v.strip().upper() for v in modalidade_values}
    return [
        row for row in rows
        if modalidade_col < len(row) and row[modalidade_col].strip().upper() in normalized
    ]


def compute_batch_promotions(
    pending_records: list[dict], batch_size: int
) -> tuple[list[int], int]:
    """Calcula quais registros promover em lotes completos (FIFO).

    Retorna (ids_para_promover, n_lotes_completos).
    """
    n_complete = len(pending_records) // batch_size
    ids_to_promote = [r["id"] for r in pending_records[: n_complete * batch_size]]
    return ids_to_promote, n_complete


def compute_batch_promotions_by_people(
    pending_records: list[dict],
    pessoas_em_espera: int,
    batch_size: int,
) -> tuple[list[int], int, int]:
    """Calcula lotes baseados em número de pessoas (não registros).

    Soma os participantes de todos os registros pendentes com o carry-over
    existente. Todos os registros pendentes são promovidos de uma vez.

    Retorna (ids_para_promover, n_lotes_completos, novo_carry_over).
    """
    total_pessoas = pessoas_em_espera + sum(
        r.get("num_participantes", 1) for r in pending_records
    )
    n_lotes = total_pessoas // batch_size
    novo_carry_over = total_pessoas % batch_size
    ids_to_promote = [r["id"] for r in pending_records]
    return ids_to_promote, n_lotes, novo_carry_over


def find_new_records(
    rows: list[list[str]],
    key_columns: list[int],
    processed_hashes: set[str],
    hash_prefix: str = "",
) -> list[tuple[str, list[str]]]:
    """Retorna lista de (hash, row) para registros ainda não processados.

    O parâmetro opcional `hash_prefix` é repassado para `compute_record_hash`
    para namespacing de hashes entre fontes de dados diferentes.
    """
    new_records = []
    for row in rows:
        record_hash = compute_record_hash(row, key_columns, prefix=hash_prefix)
        if record_hash not in processed_hashes:
            new_records.append((record_hash, row))
    return new_records


def calculate_points_by_clan(
    new_records: list[tuple[str, list[str]]],
    clan_col: int,
    points_per_record: int = 30,
) -> dict[str, int]:
    """Retorna {clan: total_novos_pontos} para o lote de novos registros."""
    clan_points: dict[str, int] = {}
    for _hash, row in new_records:
        clan = row[clan_col].strip() if clan_col < len(row) else "DESCONHECIDO"
        clan_points[clan] = clan_points.get(clan, 0) + points_per_record
    return clan_points


def calculate_points_by_coach(
    new_records: list[tuple[str, list[str]]],
    coach_col: int,
    points_per_record: int = 30,
) -> dict[str, int]:
    """Retorna {coach: total_novos_pontos} para o lote de novos registros."""
    coach_points: dict[str, int] = {}
    for _hash, row in new_records:
        coach = row[coach_col].strip() if coach_col < len(row) else "DESCONHECIDO"
        if not coach:
            coach = "DESCONHECIDO"
        coach_points[coach] = coach_points.get(coach, 0) + points_per_record
    return coach_points


def build_record_data(
    record_hash: str,
    row: list[str],
    header: list[str],
    modalidade_col: int,
    clan_col: int,
    coach_col: int,
    spreadsheet_id: str,
    sheet_name: str,
    row_number: int,
    pontos: int,
) -> dict:
    """Constrói o dicionário de dados para inserção no Supabase."""
    raw_data = {}
    for i, val in enumerate(row):
        col_name = header[i] if i < len(header) else f"col_{i}"
        raw_data[col_name] = val

    coach = row[coach_col].strip() if coach_col < len(row) else "DESCONHECIDO"
    if not coach:
        coach = "DESCONHECIDO"

    return {
        "registro_hash": record_hash,
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "row_number": row_number,
        "modalidade": row[modalidade_col].strip() if modalidade_col < len(row) else "",
        "clan": row[clan_col].strip() if clan_col < len(row) else "",
        "coach": coach,
        "pontos": pontos,
        "raw_data": json.dumps(raw_data, ensure_ascii=False),
    }


_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _parse_date(raw: str):
    """Extrai data de strings como '06/04/2026 13:58:38' ou '01/04/2026'.

    Usa regex para ignorar componente de horário e variações de formato.
    Retorna None se nenhum padrão dd/mm/yyyy for encontrado.
    """
    if not raw:
        return None
    m = _DATE_RE.search(raw.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def filter_records_by_date_from(
    records: list[tuple[str, list[str]]],
    date_col: int,
    start_date: date,
) -> list[tuple[str, list[str]]]:
    """Retorna registros cuja data (date_col) >= start_date.

    Comportamento fail-open: registros com coluna ausente, célula vazia ou
    formato não reconhecido são INCLUÍDOS (benefício da dúvida).
    Apenas registros com data confirmada antes de start_date são excluídos.
    """
    result = []
    for record_hash, row in records:
        # Coluna ausente ou célula vazia → incluir
        if date_col >= len(row) or not row[date_col] or not row[date_col].strip():
            result.append((record_hash, row))
            continue
        parsed = _parse_date(row[date_col])
        # Formato desconhecido → incluir; data antes do corte → excluir
        if parsed is None or parsed >= start_date:
            result.append((record_hash, row))
    return result


def calculate_desafio_pontos(campos: list[dict], valores: dict) -> int:
    """Soma os valores dos campos do tipo 'pontuacao'.

    campos: lista de dicts com {'id': int, 'tipo': str}
    valores: dict com {str(campo_id): valor} — chave é o ID do campo como string
    """
    total = 0
    for campo in campos:
        if campo["tipo"] == "pontuacao":
            val = valores.get(str(campo["id"]), 0)
            try:
                total += int(val)
            except (ValueError, TypeError):
                pass
    return total
