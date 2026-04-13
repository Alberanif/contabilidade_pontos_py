from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def fetch_records() -> list[list[str]]:
    """Busca todas as linhas da planilha de registros."""
    service = _get_service()
    sheet_name = f"'{config.GSHEET_RECORDS_SHEET_NAME}'"
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=config.GSHEET_RECORDS_SPREADSHEET_ID,
            range=sheet_name,
        )
        .execute()
    )
    return result.get("values", [])


def fetch_records_pro_bono() -> list[list[str]]:
    """Busca todas as linhas da planilha de registros Pro-bono.

    Retorna lista vazia se as variáveis de ambiente da planilha Pro-bono
    não estiverem configuradas.
    """
    if not config.GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID:
        return []
    service = _get_service()
    sheet_name = f"'{config.GSHEET_RECORDS_PRO_BONO_SHEET_NAME}'"
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=config.GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID,
            range=sheet_name,
        )
        .execute()
    )
    return result.get("values", [])


def fetch_ranking() -> list[dict]:
    """Lê a seção PONTUAÇÃO GERAL (colunas I-L) e retorna o ranking dos clãs.

    Colunas: I(8)=clã, J(9)=nome completo, K(10)=total pontos, L(11)=posição.
    """
    service = _get_service()
    sheet_name = f"'{config.GSHEET_TOTALS_SHEET_NAME}'"
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=config.GSHEET_TOTALS_SPREADSHEET_ID, range=sheet_name)
        .execute()
    )
    rows = result.get("values", [])

    ranking = []
    for row in rows:
        if len(row) <= 8:
            continue
        clan = row[8].strip()
        if not clan.upper().startswith("CLÃ") and not clan.upper().startswith("CLA"):
            continue
        nome_completo = row[9].strip() if len(row) > 9 else ""
        total_pontos = 0
        if len(row) > 10:
            try:
                total_pontos = int(str(row[10]).strip().replace(".", "").replace(",", ""))
            except ValueError:
                total_pontos = 0
        posicao = 0
        if len(row) > 11:
            try:
                posicao = int(str(row[11]).strip())
            except ValueError:
                posicao = 0
        ranking.append({
            "clan": clan,
            "nome_completo": nome_completo,
            "total_pontos": total_pontos,
            "posicao": posicao,
        })

    ranking.sort(key=lambda x: x["posicao"] if x["posicao"] > 0 else 999)
    return ranking


def fetch_totals() -> list[list[str]]:
    """Busca todas as linhas da planilha de pontuação."""
    service = _get_service()
    sheet_name = f"'{config.GSHEET_TOTALS_SHEET_NAME}'"
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=config.GSHEET_TOTALS_SPREADSHEET_ID,
            range=sheet_name,
        )
        .execute()
    )
    return result.get("values", [])


def sync_clan_totals_to_sheet(totals: dict[str, int]) -> dict[str, int]:
    """Sobrescreve a seção PONTUAÇÃO GERAL com os valores absolutos do banco.

    Diferente de update_clan_totals (que incrementa), esta função escreve
    diretamente o valor total sem somar ao valor atual da planilha.

    Retorna o dicionário {clan: total_escrito} após a atualização.
    """
    service = _get_service()
    sheet_name = f"'{config.GSHEET_TOTALS_SHEET_NAME}'"

    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=config.GSHEET_TOTALS_SPREADSHEET_ID,
            range=sheet_name,
        )
        .execute()
    )
    rows = result.get("values", [])

    if not rows:
        return {}

    COL_GERAL_CLAN = 8
    COL_GERAL_TOTAL = 10

    written_totals = {}
    updates = []

    for row_idx, row in enumerate(rows, start=1):
        if len(row) <= COL_GERAL_CLAN:
            continue
        clan_name = row[COL_GERAL_CLAN].strip()
        if clan_name not in totals:
            continue

        new_total = totals[clan_name]
        written_totals[clan_name] = new_total

        cell_range = f"{sheet_name}!K{row_idx}"
        updates.append({
            "range": cell_range,
            "values": [[new_total]],
        })

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=config.GSHEET_TOTALS_SPREADSHEET_ID,
            body={
                "valueInputOption": "RAW",
                "data": updates,
            },
        ).execute()

    return written_totals


def update_clan_totals(clan_points: dict[str, int]) -> dict[str, int]:
    """Atualiza a seção PONTUAÇÃO GERAL da planilha de totais.

    A seção PONTUAÇÃO GERAL ocupa as colunas I (índice 8) e K (índice 10):
      - Coluna I: nome do clã ("CLÃ 1", "CLÃ 2", ...)
      - Coluna K: total acumulado de pontos

    Retorna o dicionário {clan: novo_total} após a atualização.
    """
    service = _get_service()
    sheet_name = f"'{config.GSHEET_TOTALS_SHEET_NAME}'"

    # Ler planilha de totais
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=config.GSHEET_TOTALS_SPREADSHEET_ID,
            range=sheet_name,
        )
        .execute()
    )
    rows = result.get("values", [])

    if not rows:
        return {}

    # Seção PONTUAÇÃO GERAL: coluna I (índice 8) = clã, coluna K (índice 10) = total
    COL_GERAL_CLAN = 8
    COL_GERAL_TOTAL = 10

    # Mapeamento de letras de coluna (0=A, 8=I, 10=K)
    col_letter = {8: "I", 10: "K"}

    updated_totals = {}
    updates = []

    for row_idx, row in enumerate(rows, start=1):  # 1-indexed para a API
        if len(row) <= COL_GERAL_CLAN:
            continue
        clan_name = row[COL_GERAL_CLAN].strip()
        if clan_name not in clan_points:
            continue

        current_total = 0
        if len(row) > COL_GERAL_TOTAL:
            try:
                current_total = int(str(row[COL_GERAL_TOTAL]).strip().replace(".", "").replace(",", ""))
            except (ValueError, IndexError):
                current_total = 0

        new_total = current_total + clan_points[clan_name]
        updated_totals[clan_name] = new_total

        cell_range = f"{sheet_name}!{col_letter[COL_GERAL_TOTAL]}{row_idx}"
        updates.append({
            "range": cell_range,
            "values": [[new_total]],
        })

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=config.GSHEET_TOTALS_SPREADSHEET_ID,
            body={
                "valueInputOption": "RAW",
                "data": updates,
            },
        ).execute()

    return updated_totals
