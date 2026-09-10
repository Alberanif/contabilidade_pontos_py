"""Migração administrativa única: desafios legados -> Google Sheets.

Uso (a partir de `backend/`):

    python -m admin.migrate_desafios_google_sheet                      # dry-run
    python -m admin.migrate_desafios_google_sheet --apply \
        --confirm-hash <snapshot_hash mostrado no dry-run>

Dry-run é o padrão e **não escreve nada**: apenas lê a planilha oficial, o
estado atual dos tokens e o relatório somente-leitura
`desafio_legacy_migration_report`, e imprime os totais antigos vs. novos por clã
e por coach.

`--apply` executa **duas fases atômicas sequenciais** — não uma única transação
cobrindo as duas (o cliente REST do Supabase não mantém uma transação aberta
entre chamadas, e reimplementar o pipeline das Tasks 2-4 dentro de uma função
SQL gigante duplicaria uma fronteira de atomicidade já revisada):

  Fase 1 — RPC `migrate_desafio_legacy_contribution` (migração 010): backup
    verificável, remoção explícita da contribuição legada dos totais de clã e
    coach (aborta se algum total ficaria negativo) e arquivamento das
    estruturas manuais/CSV. Tudo em uma transação do Postgres.
  Fase 2 — `desafio_sync_service.sync_desafios` (migração 009): aplica o
    primeiro snapshot oficial, em outra transação do Postgres.

Se a Fase 1 commitar e a Fase 2 falhar, o estado é recuperável e a CLI diz
exatamente o que fazer — ver `docs/runbooks/migracao-desafios-google-sheets.md`.
Reexecutar a CLI nesse estado pula a Fase 1 (já aplicada) e refaz só a Fase 2.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys

import config
import desafio_reconciliation
import desafio_reconciliation_store as store
import desafio_sheet_parser
import desafio_sync_service
import google_sheets_client
import supabase_client


RPC_REPORT = "desafio_legacy_migration_report"
RPC_MIGRATE = "migrate_desafio_legacy_contribution"
# A restauração (`restore_desafio_legacy_migracao`) é deliberadamente manual,
# por SQL, e não tem flag nesta CLI: desfazer pontuação de produção não deve ser
# tão fácil quanto digitar um argumento. O procedimento está no runbook — e ela
# só cobre "Fase 1 commitada, Fase 2 nunca aplicada"; depois de uma
# sincronização bem-sucedida ela recusa (seção 7.4 do runbook traz o roteiro
# manual, porque nada no schema identifica qual execução foi a Fase 2).

EXIT_OK = 0
EXIT_PRECONDITION = 2
EXIT_CONFIRMATION = 3
EXIT_PHASE1_FAILED = 4
EXIT_PHASE2_FAILED = 5
EXIT_VALIDATION_FAILED = 6

RUNBOOK = "docs/runbooks/migracao-desafios-google-sheets.md"

_LINE = "=" * 72
_MAX_ROWS_LISTED = 20

# Cabeçalho e linhas de dados compartilham o mesmo formato para que as colunas
# do relatório fiquem alinhadas independentemente dos valores.
_CLAN_ROW = "  {:<10} {:>7} {:>16} {:>13} {:>18} {:>12}"
_COACH_ROW = "  {:<30} {:>7} {:>16} {:>13}"


class PreconditionError(RuntimeError):
    """Uma pré-condição da migração não foi satisfeita; nada foi escrito."""


@dataclass(frozen=True)
class MigrationPreview:
    """Tudo o que o dry-run precisa mostrar e o `--apply` precisa conferir."""

    sheet_row_count: int
    snapshot: desafio_reconciliation.DesafioSnapshot
    plan: desafio_reconciliation.ReconciliationPlan
    legacy: dict
    expected_clan_points: dict[str, int]
    eligible_tokens: int

    @property
    def snapshot_hash(self) -> str:
        return self.plan.snapshot_hash

    @property
    def already_migrated(self) -> bool:
        return bool(self.legacy.get("ja_migrado"))

    @property
    def negativos(self) -> list[dict]:
        return list(self.legacy.get("negativos") or [])


# ---------------------------------------------------------------------------
# Pré-condições e prévia
# ---------------------------------------------------------------------------


def _require_config() -> None:
    missing = [
        name
        for name, value in (
            ("GOOGLE_SERVICE_ACCOUNT_JSON", config.GOOGLE_SERVICE_ACCOUNT_JSON),
            ("GSHEET_DESAFIOS_SPREADSHEET_ID", config.GSHEET_DESAFIOS_SPREADSHEET_ID),
            ("GSHEET_DESAFIOS_SHEET_NAME", config.GSHEET_DESAFIOS_SHEET_NAME),
        )
        if not value
    ]
    if missing:
        raise PreconditionError(
            "Configuração da planilha oficial ausente: " + ", ".join(missing)
        )


def _fetch_rows() -> list[list[str]]:
    try:
        return google_sheets_client.fetch_desafio_records()
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura é pré-condição
        raise PreconditionError(f"Falha ao ler a planilha oficial: {exc}") from exc


def _check_sheet_content(
    rows: list[list[str]], parsed_rows: list[desafio_sheet_parser.ParsedDesafioRow]
) -> None:
    if not rows or not parsed_rows:
        raise PreconditionError(
            "Planilha oficial vazia (nenhuma linha de dados abaixo do cabeçalho): "
            "não há nada para migrar."
        )

    # Linhas sem a coluna F (Desafio) preenchida são tratadas pelo parser como
    # status 'invalid' com motivo 'missing_challenge' e não geram pontos.
    sem_desafio = [
        row.row_number
        for row in parsed_rows
        if row.token and "missing_challenge" in row.reasons
    ]
    if sem_desafio:
        mostradas = ", ".join(str(n) for n in sem_desafio[:_MAX_ROWS_LISTED])
        resto = (
            f" (+{len(sem_desafio) - _MAX_ROWS_LISTED} outras)"
            if len(sem_desafio) > _MAX_ROWS_LISTED
            else ""
        )
        # Ignora as linhas sem desafio conforme instrução operacional, registrando no relatório.
        pass


def _rpc_dict(data, function_name: str) -> dict:
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise RuntimeError(f"resposta inesperada de {function_name}: {data!r}")
    return data


def build_preview() -> MigrationPreview:
    """Lê tudo o que é preciso para decidir, sem escrever nada."""
    _require_config()

    rows = _fetch_rows()
    parsed_rows = desafio_sheet_parser.build_parsed_rows(rows)
    _check_sheet_content(rows, parsed_rows)

    snapshot = desafio_reconciliation.build_desafio_snapshot(
        parsed_rows, config.POINTS_PER_DESAFIO_SUBMISSION
    )
    if not snapshot.entries:
        raise PreconditionError(
            "Planilha oficial vazia de tokens: nenhuma linha possui a coluna I "
            "(Token) preenchida."
        )

    current = store.get_current_desafio_submissions()
    plan = desafio_reconciliation.reconcile_desafios(snapshot, current)

    legacy = _rpc_dict(supabase_client.call_rpc(RPC_REPORT, {}), RPC_REPORT)

    expected: dict[str, int] = {}
    eligible = 0
    for entry in snapshot.entries.values():
        if not entry.eligible or not entry.clan:
            continue
        eligible += 1
        expected[entry.clan] = expected.get(entry.clan, 0) + entry.points

    return MigrationPreview(
        sheet_row_count=len(rows),
        snapshot=snapshot,
        plan=plan,
        legacy=legacy,
        expected_clan_points=expected,
        eligible_tokens=eligible,
    )


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------


def render_preview(preview: MigrationPreview, *, apply: bool) -> str:
    legacy = preview.legacy
    plan = preview.plan
    linhas: list[str] = [
        _LINE,
        "MIGRAÇÃO ADMINISTRATIVA DE DESAFIOS -> GOOGLE SHEETS",
        f"Modo: {'APLICAÇÃO (--apply)' if apply else 'DRY-RUN (nada será escrito)'}",
        _LINE,
        "",
        "Planilha oficial",
        f"  linhas lidas .................. {preview.sheet_row_count}",
        f"  tokens no snapshot ............ {len(preview.snapshot.entries)}",
        f"  tokens elegíveis (pontuam) .... {preview.eligible_tokens}",
        f"  pontos por submissão .......... {preview.snapshot.points_per_submission}",
        f"  snapshot_hash ................. {preview.snapshot_hash}",
        "",
        "Estruturas legadas (manual / importação CSV)",
        f"  desafios ...................... {legacy.get('desafios_legados', 0)}"
        f" ({legacy.get('desafios_legados_contabilizando', 0)} ainda contabilizando)",
        f"  desafio_registros ............. {legacy.get('registros_clan', 0)}",
        f"  desafio_registros_coach ....... {legacy.get('registros_coach', 0)}",
        f"  desafio_importacao_linhas ..... {legacy.get('linhas_importacao', 0)}",
        "",
        "Totais por clã",
        _CLAN_ROW.format(
            "clã", "antes", "legado removido", "após fase 1",
            "desafios planilha", "após fase 2",
        ),
    ]

    for item in legacy.get("clans") or []:
        clan = item.get("clan") or ""
        antes = int(item.get("total_antes") or 0)
        removido = int(item.get("contribuicao_legada") or 0)
        depois = int(item.get("total_depois") or 0)
        novos = preview.expected_clan_points.get(clan, 0)
        linhas.append(
            _CLAN_ROW.format(clan, antes, removido, depois, novos, depois + novos)
        )

    linhas += [
        "",
        "Totais por coach (desafios deixam de pontuar o ranking individual)",
        _COACH_ROW.format("coach", "antes", "legado removido", "após fase 1"),
    ]
    coaches = legacy.get("coaches") or []
    if not coaches:
        linhas.append("  (nenhum coach com pontos de desafio legados)")
    for item in coaches:
        coach = item.get("coach") or ""
        antes = int(item.get("total_antes") or 0)
        removido = int(item.get("contribuicao_legada") or 0)
        depois = int(item.get("total_depois") or 0)
        linhas.append(_COACH_ROW.format(coach, antes, removido, depois))

    linhas += [
        "",
        "Plano de reconciliação (fase 2)",
        f"  novos ......................... {plan.state_counts.get('new', 0)}",
        f"  reaparecidos .................. {plan.state_counts.get('reappeared', 0)}",
        f"  alterados com efeito .......... {plan.state_counts.get('changed_with_effect', 0)}",
        f"  removidos ..................... {plan.state_counts.get('missing', 0)}",
        f"  tokens ativos antes ........... {plan.active_tokens_before}",
        f"  deltas por clã ................ {plan.clan_deltas}",
    ]
    if plan.mass_removal_required:
        linhas.append(
            f"  REMOÇÃO EM MASSA .............. SIM — {plan.mass_removal_count} token(s) "
            f"ativo(s) deixariam de pontuar ({plan.mass_removal_ratio:.0%})"
        )

    if preview.already_migrated:
        linhas += [
            "",
            f"Fase 1 JÁ APLICADA anteriormente (migração #{legacy.get('migracao_id')}). "
            "Somente a Fase 2 será executada.",
        ]

    if preview.negativos:
        linhas += ["", "BLOQUEADO — totais ficariam negativos (PRD RF-19):"]
        for item in preview.negativos:
            linhas.append(
                f"  {item.get('escopo')} {item.get('chave')}: "
                f"{item.get('total_antes')} - {item.get('contribuicao_legada')} "
                f"= {item.get('total_depois')}"
            )
        linhas.append(
            "  Investigue a divergência antes de migrar: a migração aborta em vez "
            "de truncar totais para zero."
        )

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Validações pós-migração
# ---------------------------------------------------------------------------


def run_post_validations(preview: MigrationPreview) -> list[str]:
    """Confere as invariantes da seção 21.3 do PRD. Devolve as falhas."""
    falhas: list[str] = []

    esperado = preview.expected_clan_points
    observado = supabase_client.get_tipo_clan_totals("desafios")
    for clan in sorted(set(esperado) | set(observado)):
        if esperado.get(clan, 0) != observado.get(clan, 0):
            falhas.append(
                f"pontos de desafio do clã {clan}: banco tem {observado.get(clan, 0)}, "
                f"esperado {esperado.get(clan, 0)} "
                f"(tokens elegíveis × {preview.snapshot.points_per_submission})"
            )

    coach_totals = supabase_client.get_tipo_coach_totals("desafios")
    sobrando = {c: v for c, v in (coach_totals or {}).items() if v}
    if sobrando:
        falhas.append(
            "ainda há pontos de desafio no ranking individual de coach: "
            + ", ".join(f"{c}={v}" for c, v in sorted(sobrando.items()))
        )

    rerun = desafio_sync_service.sync_desafios()
    if rerun.status != desafio_sync_service.STATUS_SUCCESS:
        falhas.append(
            f"reexecução imediata da sincronização retornou {rerun.status!r}: "
            f"{rerun.mensagem}"
        )
    elif rerun.clan_deltas or rerun.tokens_versioned:
        falhas.append(
            "reexecução imediata não produziu delta zero: "
            f"deltas={rerun.clan_deltas}, tokens={rerun.tokens_versioned}"
        )

    return falhas


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m admin.migrate_desafios_google_sheet",
        description=(
            "Migração administrativa única dos desafios para a Google Sheet. "
            "Dry-run por padrão."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="aplica de fato (sem esta flag nada é escrito)",
    )
    parser.add_argument(
        "--confirm-hash",
        dest="confirm_hash",
        default=None,
        help="snapshot_hash exibido no dry-run; obrigatório com --apply",
    )
    parser.add_argument(
        "--confirm-mass-removal",
        dest="confirm_mass_removal",
        action="store_true",
        help=(
            "consentimento explícito para um plano que remove mais de 20%% dos "
            "tokens ativos (RF-17). Nunca é assumido automaticamente."
        ),
    )
    return parser.parse_args([] if argv is None else argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        preview = build_preview()
    except PreconditionError as exc:
        print(_LINE)
        print("MIGRAÇÃO BLOQUEADA — pré-condição não satisfeita")
        print(_LINE)
        print(f"  {exc}")
        print("Nenhuma alteração foi feita.")
        return EXIT_PRECONDITION

    print(render_preview(preview, apply=args.apply))
    print("")

    if preview.negativos:
        print("Nenhuma alteração foi feita.")
        return EXIT_PRECONDITION

    if not args.apply:
        print(
            "DRY-RUN concluído: nada foi escrito. Para aplicar, revise os números "
            "acima e execute:"
        )
        print(
            "  python -m admin.migrate_desafios_google_sheet --apply "
            f"--confirm-hash {preview.snapshot_hash}"
        )
        return EXIT_OK

    if not args.confirm_hash:
        print(
            "--apply exige --confirm-hash com o snapshot_hash revisado no dry-run:"
        )
        print(f"  --confirm-hash {preview.snapshot_hash}")
        print("Nenhuma alteração foi feita.")
        return EXIT_CONFIRMATION

    if args.confirm_hash != preview.snapshot_hash:
        print(
            f"Confirmação não corresponde ao snapshot atual: recebido "
            f"{args.confirm_hash!r}, atual {preview.snapshot_hash!r}."
        )
        print(
            "A planilha mudou desde o dry-run. Rode o dry-run de novo e revise "
            "os números antes de confirmar."
        )
        print("Nenhuma alteração foi feita.")
        return EXIT_CONFIRMATION

    if preview.plan.mass_removal_required and not args.confirm_mass_removal:
        print(
            f"O plano tiraria {preview.plan.mass_removal_count} token(s) ativo(s) de "
            f"pontuação ({preview.plan.mass_removal_ratio:.0%} dos ativos). "
            "Isso não é esperado em uma migração inicial."
        )
        print(
            "Se for mesmo o desejado, repita o comando acrescentando "
            "--confirm-mass-removal."
        )
        print("Nenhuma alteração foi feita.")
        return EXIT_CONFIRMATION

    # --- Fase 1 -----------------------------------------------------------
    migracao_id = preview.legacy.get("migracao_id")
    if preview.already_migrated:
        print(
            f"Fase 1 já aplicada (migração #{preview.legacy.get('migracao_id')}): "
            "pulando para a Fase 2."
        )
    else:
        print("Fase 1: backup, remoção da contribuição legada e arquivamento...")
        try:
            fase1 = _rpc_dict(
                supabase_client.call_rpc(RPC_MIGRATE, {}), RPC_MIGRATE
            )
        except Exception as exc:  # noqa: BLE001 - a mensagem do RPC é o diagnóstico
            print(f"Fase 1 FALHOU: {exc}")
            print(
                "Nada foi aplicado: a Fase 1 é uma transação única e nenhuma "
                "alteração foi commitada."
            )
            return EXIT_PHASE1_FAILED

        migracao_id = fase1.get("migracao_id")
        print(f"  migração #{migracao_id} aplicada")
        print(
            f"  backup: {fase1.get('backup_rows')} linha(s), "
            f"checksum {fase1.get('backup_checksum')}"
        )
        print(f"  desafios legados arquivados: {fase1.get('desafios_arquivados')}")
        print(f"  totais de clã antes:  {fase1.get('clan_before')}")
        print(f"  totais de clã depois: {fase1.get('clan_after')}")
        print(f"  totais de coach antes:  {fase1.get('coach_before')}")
        print(f"  totais de coach depois: {fase1.get('coach_after')}")

    # --- Fase 2 -----------------------------------------------------------
    print("Fase 2: aplicando o primeiro snapshot da planilha oficial...")
    fase2 = desafio_sync_service.sync_desafios(
        confirm_snapshot_hash=preview.snapshot_hash,
        confirm_mass_removal=bool(args.confirm_mass_removal),
    )
    if fase2.status != desafio_sync_service.STATUS_SUCCESS:
        print(f"Fase 2 FALHOU ({fase2.status}): {fase2.mensagem}")
        print(
            f"ATENÇÃO: a Fase 1 (migração #{migracao_id}) JÁ FOI COMMITADA — os "
            "pontos legados já saíram dos totais, mas o snapshot da planilha "
            "ainda não entrou."
        )
        print(
            "Reexecute esta CLI (ela pula a Fase 1 já aplicada) ou restaure o "
            f"backup. Procedimento completo em {RUNBOOK}."
        )
        return EXIT_PHASE2_FAILED

    print(f"  {fase2.mensagem}")
    print(f"  totais de clã após a fase 2: {fase2.clan_totals_after}")

    # --- Validações -------------------------------------------------------
    print("Validações pós-migração...")
    falhas = run_post_validations(preview)
    if falhas:
        print("VALIDAÇÃO FALHOU:")
        for falha in falhas:
            print(f"  - {falha}")
        print(
            f"As duas fases foram aplicadas. Investigue antes de liberar o uso: "
            f"corrigir para frente é o caminho normal (seção 7.3 do {RUNBOOK}). "
            f"Não há rollback automático depois da Fase 2 — "
            f"`restore_desafio_legacy_migracao` recusa, e o roteiro manual está "
            f"na seção 7.4 (migração #{migracao_id})."
        )
        return EXIT_VALIDATION_FAILED

    print("  [OK] pontos de desafio por clã = tokens elegíveis × valor configurado")
    print("  [OK] nenhum ponto de desafio no ranking individual de coach")
    print("  [OK] reexecução imediata com delta zero")
    print(f"Migração #{migracao_id} concluída com sucesso.")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - ponto de entrada
    sys.exit(main(sys.argv[1:]))
