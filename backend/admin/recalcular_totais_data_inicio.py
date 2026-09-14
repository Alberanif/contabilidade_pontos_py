"""Correção retroativa não-destrutiva dos totais de clã e coach.

Recalcula `totais_por_clan`/`totais_por_coach` somando só registros
(Coaching Individual, Coaching em Grupo/Empresa, Pro-bono) com
`data_registro >= config.DATA_INICIO_CONTABILIZACAO`.

Não apaga nem altera nenhuma linha de `pontos_ultimate_registros_contabilizados`
— só relê o que já está lá (`supabase_client.fetch_all_registros_contabilizados`)
e sobrescreve os totais agregados. Desafios não são tocados: já são
recalculados ao vivo a cada `/executar` a partir dos tokens `active_counted`
(`get_tipo_clan_totals`/`get_tipo_coach_totals("desafios")`), e nenhuma
submissão ativa hoje é anterior ao corte.

A partir de `config.DATA_INICIO_CONTABILIZACAO`, todo registro novo (mesmo
que ainda não processado) já é ignorado permanentemente por `/executar` e
`/reprocessar` (`points_engine.filter_records_by_date_from`) — este script
só corrige o que já foi contabilizado antes dessa regra existir.

Uso (a partir de `backend/`):

    python -m admin.recalcular_totais_data_inicio            # dry-run
    python -m admin.recalcular_totais_data_inicio --apply    # aplica de fato

Dry-run é o padrão e não escreve nada: só lê e imprime o relatório
antes/depois (uma linha por clã/coach cujo total mudaria).
"""

from __future__ import annotations

import argparse

import config
import points_engine
import supabase_client


def build_plan() -> tuple[dict[str, dict], dict[str, dict]]:
    """Lê o estado atual (registros, desafios, totais persistidos) e devolve
    o plano de recálculo (clã, coach). Só leitura."""
    registros = supabase_client.fetch_all_registros_contabilizados()
    por_clan, por_coach = points_engine.sum_registros_pontos_from_date(
        registros, config.DATA_INICIO_CONTABILIZACAO
    )

    desafio_clan = supabase_client.get_tipo_clan_totals("desafios")
    desafio_coach = supabase_client.get_tipo_coach_totals("desafios")

    existing_clan = {r["clan"]: r for r in supabase_client.list_clan_totals()}
    existing_coach = {r["coach"]: r for r in supabase_client.list_coach_totals()}

    clan_plan = points_engine.build_totais_recalculo_plan(por_clan, desafio_clan, existing_clan)
    coach_plan = points_engine.build_totais_recalculo_plan(por_coach, desafio_coach, existing_coach)
    return clan_plan, coach_plan


def _print_plan(label: str, plan: dict[str, dict]) -> int:
    mudancas = {nome: row for nome, row in plan.items() if row["delta"] != 0}
    print(f"\n{label} — {len(mudancas)} de {len(plan)} com mudança")
    if mudancas:
        print(f"  {'nome':<30} {'antigo':>10} {'novo':>10} {'delta':>10}")
        for nome in sorted(mudancas, key=lambda n: mudancas[n]["delta"]):
            row = mudancas[nome]
            print(f"  {nome:<30} {row['antigo']:>10} {row['novo']:>10} {row['delta']:>10}")
    return sum(row["delta"] for row in mudancas.values())


def apply_plan(clan_plan: dict[str, dict], coach_plan: dict[str, dict]) -> None:
    for clan, row in clan_plan.items():
        if row["delta"] == 0:
            continue
        supabase_client.upsert_clan_total(
            clan, row["novo"],
            pessoas_em_espera=row["pessoas_em_espera"],
            total_pagante=row["total_pagante"],
            total_pro_bono=row["total_pro_bono"],
        )
    for coach, row in coach_plan.items():
        if row["delta"] == 0:
            continue
        supabase_client.upsert_coach_total(
            coach, row["novo"],
            pessoas_em_espera=row["pessoas_em_espera"],
            total_pagante=row["total_pagante"],
            total_pro_bono=row["total_pro_bono"],
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Aplica de fato (padrão é dry-run)")
    args = parser.parse_args()

    print(f"Corte: registros a partir de {config.DATA_INICIO_CONTABILIZACAO} contam; antes, não.")
    clan_plan, coach_plan = build_plan()
    delta_clan = _print_plan("Totais por clã", clan_plan)
    delta_coach = _print_plan("Totais por coach", coach_plan)
    print(f"\nDelta total de clã: {delta_clan}")
    print(f"Delta total de coach: {delta_coach}")

    if not args.apply:
        print("\nDry-run — nada foi escrito. Rode com --apply para aplicar de fato.")
        return 0

    apply_plan(clan_plan, coach_plan)
    print("\nAplicado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
