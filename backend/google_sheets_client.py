import json

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _get_service():
    info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
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
    """Escrita na planilha desativada — o sistema opera em modo estritamente de leitura."""
    return {}


def update_clan_totals(clan_points: dict[str, int]) -> dict[str, int]:
    """Escrita na planilha desativada — o sistema opera em modo estritamente de leitura."""
    return {}
