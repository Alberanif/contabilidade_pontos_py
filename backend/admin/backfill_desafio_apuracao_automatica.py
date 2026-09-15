"""Backfill administrativo único: reapura desafios pós-corte já congelados
sob a regra de elegibilidade nova (toda submissão conta por padrão, só
reprovado exclui — ver
docs/superpowers/specs/2026-09-14-desafios-aprovacao-automatica-design.md).

Uso (a partir de `backend/`):

    python -m admin.backfill_desafio_apuracao_automatica            # dry-run
    python -m admin.backfill_desafio_apuracao_automatica --apply

Dry-run (padrão) não escreve nada: lista os desafios já apurados
(`apurado_em` não nulo — só esses usam a apuração por percentual) e mostra,
por clã, o delta que `--apply` aplicaria ao total do clã.
"""

from __future__ import annotations

import argparse
import sys

import supabase_client


def desafios_para_backfill() -> list[dict]:
    """Desafios já apurados (`apurado_em` não nulo) — únicos candidatos a
    reapuração sob a regra nova. Um desafio nunca apurado usa sempre a
    prévia ao vivo (`get_desafio_apuracao`), que já reflete a regra nova sem
    precisar de backfill."""
    return [d for d in supabase_client.list_desafios() if d.get("apurado_em")]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica de fato (padrão: dry-run)")
    args = parser.parse_args(argv)

    alvos = desafios_para_backfill()
    if not alvos:
        print("Nenhum desafio apurado encontrado — nada a fazer.")
        return

    for d in alvos:
        preview = supabase_client.reapurar_desafio_e_aplicar_delta(d["id"], dry_run=True)
        deltas = {clan: item["delta"] for clan, item in preview.items() if item["delta"] != 0}
        if not deltas:
            print(f"Desafio {d['id']} ({d.get('nome')}): sem mudança.")
            continue
        print(f"Desafio {d['id']} ({d.get('nome')}): delta por clã = {deltas}")
        if args.apply:
            supabase_client.reapurar_desafio_e_aplicar_delta(d["id"])
            print("  -> aplicado.")

    if not args.apply:
        print("\nDry-run — nada foi gravado. Rode com --apply para persistir.")


if __name__ == "__main__":
    main(sys.argv[1:])
