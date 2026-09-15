"""Correção retroativa não-destrutiva de registros de Coaching em
grupo/Empresa presos no antigo esquema de lote de 5 pessoas (issue #42).

Depois da remoção do lote (issue #41), todo registro de `config.GROUP_MODALIDADES`
deve valer `config.POINTS_PER_COACHING_INDIVIDUAL` pontos fixos, `status`/
`status_coach = "contabilizado"` — igual ao Coaching Individual. Registros
importados antes dessa mudança podem estar presos em dois estados antigos:

- `pontos`/`pontos_coach = 0`, `status`/`status_coach = "pendente"` (nunca
  completou um lote);
- `pontos`/`pontos_coach` igual ao valor por-registro de um lote parcial já
  promovido (`POINTS_PER_RECORD_IN_BATCH`, removido do config em #41 — por
  isso o valor 6 é comparado aqui como literal, não como constante).

Este script só corrige os registros individuais (`pontos_ultimate_registros_contabilizados`).
Os totais agregados (`total_pontos`/`total_pagante`) precisam ser recalculados
em seguida com `admin/recalcular_totais_data_inicio.py --apply`, que já lê o
estado corrigido destes registros.

Também zera `pessoas_em_espera` de todos os clãs/coaches — o conceito de
carry-over não existe mais.

Uso (a partir de `backend/`):

    python -m admin.recalcular_grupo_flat            # dry-run
    python -m admin.recalcular_grupo_flat --apply     # aplica de fato

Dry-run é o padrão e não escreve nada.
"""

from __future__ import annotations

import argparse

import config
import points_engine
import supabase_client


def build_plan() -> list[int]:
    """Lê todos os registros e devolve os ids de Coaching em grupo/Empresa
    que ainda precisam ser corrigidos para o valor flat atual. Só leitura."""
    registros = supabase_client.fetch_all_registros_contabilizados()
    return points_engine.get_ids_needing_grupo_correction(
        registros, config.GROUP_MODALIDADES, config.POINTS_PER_COACHING_INDIVIDUAL
    )


def _carry_overs_pendentes() -> tuple[list[str], list[str]]:
    clans = [r["clan"] for r in supabase_client.list_clan_totals() if (r.get("pessoas_em_espera") or 0) != 0]
    coaches = [r["coach"] for r in supabase_client.list_coach_totals() if (r.get("pessoas_em_espera") or 0) != 0]
    return clans, coaches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Aplica de fato (padrão é dry-run)")
    args = parser.parse_args()

    ids = build_plan()
    clans_com_carry, coaches_com_carry = _carry_overs_pendentes()

    print(f"{len(ids)} registro(s) de grupo/empresa precisam de correção para pontos fixos.")
    print(f"{len(clans_com_carry)} clã(s) com pessoas_em_espera != 0: {clans_com_carry}")
    print(f"{len(coaches_com_carry)} coach(es) com pessoas_em_espera != 0: {coaches_com_carry}")

    if not args.apply:
        print("\nDry-run — nada foi escrito. Rode com --apply para aplicar de fato.")
        return 0

    atualizados = supabase_client.apply_grupo_flat_correction(
        ids, config.POINTS_PER_COACHING_INDIVIDUAL
    )
    print(f"\n{atualizados} registro(s) corrigido(s).")

    existing_clans = {r["clan"]: r for r in supabase_client.list_clan_totals()}
    for clan in clans_com_carry:
        row = existing_clans.get(clan, {})
        supabase_client.upsert_clan_total(
            clan, row.get("total_pontos") or 0,
            pessoas_em_espera=0,
            total_pagante=row.get("total_pagante"),
            total_pro_bono=row.get("total_pro_bono"),
        )

    existing_coaches = {r["coach"]: r for r in supabase_client.list_coach_totals()}
    for coach in coaches_com_carry:
        row = existing_coaches.get(coach, {})
        supabase_client.upsert_coach_total(
            coach, row.get("total_pontos") or 0,
            pessoas_em_espera=0,
            total_pagante=row.get("total_pagante"),
            total_pro_bono=row.get("total_pro_bono"),
        )
    print(f"{len(clans_com_carry)} clã(s) e {len(coaches_com_carry)} coach(es) com pessoas_em_espera zerado.")

    print(
        "\nAplicado. Rode 'python -m admin.recalcular_totais_data_inicio --apply' "
        "em seguida para propagar aos totais agregados."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
