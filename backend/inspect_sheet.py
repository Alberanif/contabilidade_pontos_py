"""Utilitário para inspecionar a estrutura das planilhas e validar o mapeamento.

Execute: python inspect_sheet.py
"""

import config
from google_sheets_client import fetch_records, fetch_totals

COL_MODALIDADE = 5
COL_CLAN = 0
KEY_COLUMNS = [11]
MODALIDADE_ALVO = "Coaching Individual"

# Seção PONTUAÇÃO GERAL na planilha de totais
COL_GERAL_CLAN = 8
COL_GERAL_TOTAL = 10


def _normalize_clan(clan_raw: str) -> str:
    try:
        return f"CLÃ {int(clan_raw.strip())}"
    except (ValueError, AttributeError):
        return clan_raw.strip()


def inspect_records():
    print("=" * 60)
    print("PLANILHA DE REGISTROS")
    print("=" * 60)
    rows = fetch_records()
    if not rows:
        print("  Nenhum dado encontrado.")
        return

    header = rows[0]
    data_rows = rows[1:]

    print(f"\nCabeçalho ({len(header)} colunas):")
    for i, col in enumerate(header):
        marker = ""
        if i == COL_MODALIDADE:
            marker = "  ← COL_MODALIDADE"
        elif i == COL_CLAN:
            marker = "  ← COL_CLAN"
        elif i in KEY_COLUMNS:
            marker = "  ← KEY_COLUMNS"
        print(f"  [{i}] {col}{marker}")

    print(f"\nTotal de linhas de dados: {len(data_rows)}")

    # Valores únicos na coluna de modalidade
    modalidades = {}
    for row in data_rows:
        val = row[COL_MODALIDADE].strip() if COL_MODALIDADE < len(row) else "(vazio)"
        modalidades[val] = modalidades.get(val, 0) + 1

    print(f"\nValores encontrados em COL_MODALIDADE [{COL_MODALIDADE}]:")
    for val, count in sorted(modalidades.items(), key=lambda x: -x[1]):
        marker = "  ← ALVO" if val.upper() == MODALIDADE_ALVO.upper() else ""
        print(f"  '{val}': {count} registro(s){marker}")

    # Filtrar registros alvo
    coaching_rows = [
        row for row in data_rows
        if COL_MODALIDADE < len(row) and row[COL_MODALIDADE].strip().upper() == MODALIDADE_ALVO.upper()
    ]

    print(f"\nRegistros de '{MODALIDADE_ALVO}' encontrados: {len(coaching_rows)}")

    # Pontos por clã (normalizado)
    clan_counts: dict[str, int] = {}
    for row in coaching_rows:
        raw = row[COL_CLAN].strip() if COL_CLAN < len(row) else "?"
        clan = _normalize_clan(raw)
        clan_counts[clan] = clan_counts.get(clan, 0) + 1

    print("\nDistribuição por clã (se processados agora):")
    for clan, count in sorted(clan_counts.items()):
        print(f"  {clan}: {count} registro(s) → {count * 30} pontos")

    print("\nPrimeiras 3 linhas de Coaching Individual:")
    for row in coaching_rows[:3]:
        print(f"  Clã: {row[COL_CLAN]} → {_normalize_clan(row[COL_CLAN])} | "
              f"Coach: {row[1]} | Cliente: {row[2]} | Token: {row[11] if len(row) > 11 else 'N/A'}")


def inspect_totals():
    print("\n" + "=" * 60)
    print("PLANILHA DE PONTUAÇÃO — SEÇÃO PONTUAÇÃO GERAL")
    print("=" * 60)
    rows = fetch_totals()
    if not rows:
        print("  Nenhum dado encontrado.")
        return

    print(f"\nColunas monitoradas: [{COL_GERAL_CLAN}] = Clã, [{COL_GERAL_TOTAL}] = Total")
    print("\nEntradas da seção PONTUAÇÃO GERAL (col 8 não vazia):")

    found = False
    for row_idx, row in enumerate(rows, start=1):
        if len(row) <= COL_GERAL_CLAN:
            continue
        clan = row[COL_GERAL_CLAN].strip()
        if not clan or not clan.startswith("CLÃ"):
            continue
        total = row[COL_GERAL_TOTAL].strip() if len(row) > COL_GERAL_TOTAL else "(vazio)"
        print(f"  Linha {row_idx:2d}: {clan} → Total atual: {total}")
        found = True

    if not found:
        print("  Nenhuma entrada encontrada com 'CLÃ' na coluna 8.")


if __name__ == "__main__":
    inspect_records()
    inspect_totals()
