"""Fachada fina de sincronização de desafios via Google Sheets.

Orquestra o ciclo leitura -> parse -> snapshot -> reconciliação -> aplicação
(ou retorno de confirmação pendente), delegando toda regra de negócio para os
módulos que já a implementam:

- `google_sheets_client.fetch_desafio_records` (Task 2, leitura)
- `desafio_sheet_parser.build_parsed_rows` (Task 2, parse)
- `desafio_reconciliation.build_desafio_snapshot` / `reconcile_desafios` (Task 3)
- `desafio_reconciliation_store.apply_reconciliation` /
  `get_current_desafio_submissions` (Task 4, única porta de escrita)

Este módulo não reimplementa nenhuma validação: apenas decide, a partir do
resultado (ou exceção) de cada etapa, qual `DesafioSyncResult` devolver. Em
particular, as guardas de segurança (planilha vazia, remoção em massa,
confirmação de snapshot obsoleta) são detectadas por `apply_reconciliation` —
aqui elas só são traduzidas para o status apropriado.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

import config
import desafio_reconciliation
import desafio_reconciliation_store as store
import desafio_sheet_parser
import google_sheets_client


STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATUS_ALREADY_RUNNING = "already_running"


class DesafioSyncResult(BaseModel):
    """Resultado de uma tentativa de sincronização de desafios.

    `status` cobre os quatro desfechos possíveis: `success` (aplicado),
    `failed` (nada foi escrito), `awaiting_confirmation` (remoção em massa
    exige consentimento explícito antes de aplicar) e `already_running`
    (outra sincronização já detinha o lock). Os campos de impacto
    (`clan_deltas`, `mass_removal_*`, `snapshot_hash`) ficam preenchidos em
    `awaiting_confirmation` para que o chamador possa decidir e confirmar.
    """

    status: str
    run_id: int | None = None
    snapshot_hash: str | None = None
    sheet_row_count: int = 0
    state_counts: dict[str, int] = Field(default_factory=dict)
    clan_deltas: dict[str, int] = Field(default_factory=dict)
    clan_totals_after: dict[str, int] = Field(default_factory=dict)
    challenges_created: int = 0
    challenges_archived: int = 0
    challenges_reactivated: int = 0
    tokens_versioned: int = 0
    duration_seconds: float = 0.0
    mensagem: str = ""
    # Só relevantes quando status == "awaiting_confirmation".
    active_tokens_before: int | None = None
    mass_removal_required: bool = False
    mass_removal_count: int = 0
    mass_removal_ratio: float = 0.0


def sync_desafios(
    *,
    confirm_snapshot_hash: str | None = None,
    confirm_mass_removal: bool = False,
) -> DesafioSyncResult:
    """Executa um ciclo completo de sincronização de desafios.

    Sem argumentos, é uma tentativa de melhor esforço: aplica o plano
    resultante da planilha atual, e devolve `awaiting_confirmation` sempre
    que uma remoção em massa (>20% dos tokens ativos) exigir confirmação
    explícita (RF-17). Para efetivamente aplicar um plano assim, o chamador
    precisa reinvocar com `confirm_mass_removal=True`, tipicamente vinculado
    ao `snapshot_hash` mostrado na prévia via `confirm_snapshot_hash` — o que
    também faz `apply_reconciliation` recusar a aplicação caso a planilha (ou
    o estado persistido) tenha mudado nesse meio-tempo.
    """
    started = time.monotonic()

    try:
        rows = google_sheets_client.fetch_desafio_records()
        parsed_rows = desafio_sheet_parser.build_parsed_rows(rows)
        snapshot = desafio_reconciliation.build_desafio_snapshot(
            parsed_rows, config.POINTS_PER_DESAFIO_SUBMISSION
        )
        current = store.get_current_desafio_submissions()
        plan = desafio_reconciliation.reconcile_desafios(snapshot, current)
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura/parse vira "failed"
        return _failed(str(exc), started)

    try:
        applied = store.apply_reconciliation(
            plan,
            confirmed_snapshot_hash=confirm_snapshot_hash,
            confirm_mass_removal=confirm_mass_removal,
        )
    except store.MassRemovalConfirmationRequiredError:
        return _awaiting_confirmation(plan, started)
    except store.DesafioReconciliationError as exc:
        return _failed(str(exc), started, snapshot_hash=plan.snapshot_hash)
    except Exception as exc:  # noqa: BLE001 - erro inesperado do RPC também vira "failed"
        return _failed(str(exc), started, snapshot_hash=plan.snapshot_hash)

    if applied.already_running:
        return _already_running(applied, started)

    return _success(applied, started)


def _failed(
    message: str, started: float, *, snapshot_hash: str | None = None
) -> DesafioSyncResult:
    return DesafioSyncResult(
        status=STATUS_FAILED,
        snapshot_hash=snapshot_hash,
        duration_seconds=time.monotonic() - started,
        mensagem=message,
    )


def _awaiting_confirmation(
    plan: desafio_reconciliation.ReconciliationPlan, started: float
) -> DesafioSyncResult:
    return DesafioSyncResult(
        status=STATUS_AWAITING_CONFIRMATION,
        snapshot_hash=plan.snapshot_hash,
        sheet_row_count=plan.sheet_row_count,
        state_counts=dict(plan.state_counts),
        clan_deltas=dict(plan.clan_deltas),
        challenges_created=plan.challenges_created,
        challenges_archived=plan.challenges_archived,
        challenges_reactivated=plan.challenges_reactivated,
        duration_seconds=time.monotonic() - started,
        active_tokens_before=plan.active_tokens_before,
        mass_removal_required=plan.mass_removal_required,
        mass_removal_count=plan.mass_removal_count,
        mass_removal_ratio=plan.mass_removal_ratio,
        mensagem=(
            f"Confirmação necessária: {plan.mass_removal_count} token(s) ativo(s) "
            f"deixariam de pontuar ({plan.mass_removal_ratio:.0%} dos ativos). "
            "Reenvie a confirmação com este snapshot_hash para aplicar."
        ),
    )


def _already_running(
    applied: store.AppliedSyncResult, started: float
) -> DesafioSyncResult:
    return DesafioSyncResult(
        status=STATUS_ALREADY_RUNNING,
        run_id=applied.run_id,
        snapshot_hash=applied.snapshot_hash,
        duration_seconds=time.monotonic() - started,
        mensagem="Uma sincronização de desafios já está em andamento.",
    )


def _success(applied: store.AppliedSyncResult, started: float) -> DesafioSyncResult:
    return DesafioSyncResult(
        status=STATUS_SUCCESS,
        run_id=applied.run_id,
        snapshot_hash=applied.snapshot_hash,
        sheet_row_count=applied.sheet_row_count,
        state_counts=dict(applied.state_counts),
        clan_deltas=dict(applied.clan_deltas),
        clan_totals_after=dict(applied.clan_totals_after),
        challenges_created=applied.challenges_created,
        challenges_archived=applied.challenges_archived,
        challenges_reactivated=applied.challenges_reactivated,
        tokens_versioned=applied.tokens_versioned,
        duration_seconds=time.monotonic() - started,
        mensagem=_success_message(applied),
    )


def _success_message(applied: store.AppliedSyncResult) -> str:
    if applied.tokens_versioned == 0:
        return "Desafios sincronizados: nenhuma alteração desde a última execução."

    novos = applied.state_counts.get("new", 0) + applied.state_counts.get(
        "reappeared", 0
    )
    alterados = applied.state_counts.get("changed_with_effect", 0)
    removidos = applied.state_counts.get("missing", 0)

    partes = []
    if novos:
        partes.append(f"{novos} nova(s) submissão(ões) de desafio")
    if alterados:
        partes.append(f"{alterados} alterada(s)")
    if removidos:
        partes.append(f"{removidos} removida(s)")
    if not partes:
        partes.append(f"{applied.tokens_versioned} token(s) de desafio atualizados")

    return ", ".join(partes) + "."
