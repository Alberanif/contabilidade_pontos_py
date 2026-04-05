import hashlib
import json


def compute_record_hash(row: list[str], key_columns: list[int]) -> str:
    """Calcula hash SHA-256 determinístico a partir das colunas-chave."""
    key_values = []
    for col_idx in key_columns:
        val = row[col_idx].strip() if col_idx < len(row) else ""
        key_values.append(val)
    raw = "|".join(key_values)
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


def find_new_records(
    rows: list[list[str]],
    key_columns: list[int],
    processed_hashes: set[str],
) -> list[tuple[str, list[str]]]:
    """Retorna lista de (hash, row) para registros ainda não processados."""
    new_records = []
    for row in rows:
        record_hash = compute_record_hash(row, key_columns)
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


def build_record_data(
    record_hash: str,
    row: list[str],
    header: list[str],
    modalidade_col: int,
    clan_col: int,
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

    return {
        "registro_hash": record_hash,
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "row_number": row_number,
        "modalidade": row[modalidade_col].strip() if modalidade_col < len(row) else "",
        "clan": row[clan_col].strip() if clan_col < len(row) else "",
        "pontos": pontos,
        "raw_data": json.dumps(raw_data, ensure_ascii=False),
    }
