"""Importação administrativa: CSVs de `coaches/` -> `pontos_ultimate_coach_clas`.

Uso (a partir de `backend/`):

    python -m admin.importar_coaches_por_cla                # dry-run
    python -m admin.importar_coaches_por_cla --apply         # grava de fato

Cada arquivo `coaches/*.csv` representa um clã (o número vem do nome do
arquivo, ex.: `... - Clã 3.csv` -> `CLÃ 3`) e tem 6 colunas fixas — Coach,
Coach Action, Coach Pro, Coach Hero, Sem Categoria, Novos ULTIMATES — cujo
nome é a categoria do coach naquela célula. Células vazias são ignoradas
(nem todo clã tem o mesmo número de nomes em cada categoria).

Cada nome bruto é resolvido para seu canônico via
`coach_identity.resolve_coach()` + `supabase_client.get_coach_alias_map()`
antes de gravar, e a gravação é um upsert por `coach_canonico`
(`supabase_client.upsert_coach_cla`) — reimportar o mesmo CSV não duplica, e
reimportar um CSV com um coach movido de clã apenas atualiza o registro.

Dry-run é o padrão e não escreve nada: só lê os CSVs e o estado atual do
banco (para classificar cada linha em inserida/atualizada/inalterada) e
imprime o relatório. `--apply` faz a mesma leitura e, além disso, grava.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import coach_identity
import desafio_sheet_parser
import supabase_client


# As 6 colunas fixas do CSV, na ordem em que aparecem — o nome da coluna é a
# própria categoria. Colunas além da 6ª (algum clã tem cabeçalhos vazios
# sobrando depois de "Novos ULTIMATES") são ignoradas.
_NUM_CATEGORY_COLUMNS = 6

_FILENAME_CLAN_RE = re.compile(r"cl[aã]\s*([1-8])", re.IGNORECASE)

_CSV_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "coaches"

_LINE = "=" * 60


def parse_clan_from_filename(filename: str) -> str:
    """Extrai o clã (``CLÃ 1``..``CLÃ 8``) do nome do arquivo (``... - Clã N.csv``)."""
    match = _FILENAME_CLAN_RE.search(filename)
    if not match:
        raise ValueError(
            f"não foi possível identificar o clã no nome do arquivo: {filename!r}"
        )
    clan = desafio_sheet_parser.normalize_clan(match.group(1))
    if not clan:
        raise ValueError(
            f"clã inválido extraído do nome do arquivo: {filename!r}"
        )
    return clan


def parse_coach_cla_csv(path: Path) -> list[dict]:
    """Lê um CSV de `coaches/` e retorna as linhas não vazias.

    Retorna [{'raw_name': str, 'clan': str, 'categoria': str}, ...]. Só as 6
    primeiras colunas do cabeçalho são consideradas (nome da coluna =
    categoria); qualquer coluna extra depois delas é ignorada. Células vazias
    são puladas.
    """
    clan = parse_clan_from_filename(path.name)
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return rows

        categorias = [h.strip() for h in header[:_NUM_CATEGORY_COLUMNS]]
        for raw_row in reader:
            cells = raw_row[:_NUM_CATEGORY_COLUMNS]
            for categoria, cell in zip(categorias, cells):
                raw_name = (cell or "").strip()
                if not raw_name:
                    continue
                rows.append(
                    {"raw_name": raw_name, "clan": clan, "categoria": categoria}
                )
    return rows


def build_import_plan(rows: list[dict], alias_map: dict[str, str]) -> list[dict]:
    """Resolve cada `raw_name` via `resolve_coach()`.

    Retorna [{'coach_canonico': str, 'clan': str, 'categoria': str}, ...], na
    mesma ordem das linhas de entrada.
    """
    plan: list[dict] = []
    for row in rows:
        coach_canonico = coach_identity.resolve_coach(row["raw_name"], alias_map)
        plan.append(
            {
                "coach_canonico": coach_canonico,
                "clan": row["clan"],
                "categoria": row["categoria"],
            }
        )
    return plan


def run_import(*, apply: bool, csv_dir: Path | None = None) -> dict:
    """Lê todos os CSVs de `coaches/`, monta o plano e (se `apply`) grava.

    Classifica cada linha do plano em inserida/atualizada/inalterada
    comparando com o estado atual de `pontos_ultimate_coach_clas` (lido uma
    única vez, antes de qualquer gravação) — por isso o relatório é o mesmo
    em dry-run e em `--apply`. Retorna
    {'processados', 'inseridos', 'atualizados', 'inalterados'}.
    """
    directory = csv_dir if csv_dir is not None else _CSV_DIR_DEFAULT
    paths = sorted(directory.glob("*.csv"))

    rows: list[dict] = []
    for path in paths:
        rows.extend(parse_coach_cla_csv(path))

    alias_map = supabase_client.get_coach_alias_map()
    plan = build_import_plan(rows, alias_map)

    existing = {
        item["coach_canonico"]: (item.get("clan"), item.get("categoria"))
        for item in supabase_client.list_coach_clas()
    }

    inseridos = 0
    atualizados = 0
    inalterados = 0
    for entry in plan:
        coach_canonico = entry["coach_canonico"]
        depois = (entry["clan"], entry["categoria"])
        antes = existing.get(coach_canonico)

        if antes is None:
            inseridos += 1
        elif antes != depois:
            atualizados += 1
        else:
            inalterados += 1

        if apply:
            supabase_client.upsert_coach_cla(
                coach_canonico, entry["clan"], entry["categoria"]
            )

        # Reflete o efeito desta linha no estado local, para que um mesmo
        # coach aparecendo mais de uma vez no lote (raro, mas possível) seja
        # classificado corretamente contra o resultado das linhas anteriores.
        existing[coach_canonico] = depois

    return {
        "processados": len(plan),
        "inseridos": inseridos,
        "atualizados": atualizados,
        "inalterados": inalterados,
    }


def render_report(report: dict, *, apply: bool) -> str:
    modo = "APLICAÇÃO (--apply)" if apply else "DRY-RUN (nada será escrito)"
    linhas = [
        _LINE,
        "IMPORTAÇÃO DE COACHES POR CLÃ (coaches/*.csv)",
        f"Modo: {modo}",
        _LINE,
        f"  processados ... {report['processados']}",
        f"  inseridos ..... {report['inseridos']}",
        f"  atualizados ... {report['atualizados']}",
        f"  inalterados ... {report['inalterados']}",
    ]
    if not apply:
        linhas += [
            "",
            "DRY-RUN concluído: nada foi escrito. Para aplicar, execute:",
            "  python -m admin.importar_coaches_por_cla --apply",
        ]
    return "\n".join(linhas)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m admin.importar_coaches_por_cla",
        description=(
            "Importa os vínculos coach -> clã a partir dos CSVs de coaches/. "
            "Dry-run por padrão."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="aplica de fato (sem esta flag nada é escrito)",
    )
    return parser.parse_args([] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_import(apply=args.apply)
    print(render_report(report, apply=args.apply))
    return 0


if __name__ == "__main__":  # pragma: no cover - ponto de entrada
    sys.exit(main(sys.argv[1:]))
