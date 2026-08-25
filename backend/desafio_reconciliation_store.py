"""Persistência transacional do plano de reconciliação de desafios.

Este módulo é a **única** porta de escrita da contabilização de desafios via
Google Sheets. Toda a aplicação de um `ReconciliationPlan` acontece dentro de
uma só chamada ao RPC `apply_desafio_reconciliation` (migração 009), que roda
em uma única transação do Postgres com advisory lock não-bloqueante. Nada é
escrito aqui fora dessa chamada: qualquer gravação adicional pelo lado Python
quebraria a atomicidade exigida pelo PRD (RNF-01, RNF-04, CA-19).

O lado de leitura (`get_current_desafio_submissions`) devolve o estado
persistido no formato que `desafio_reconciliation.reconcile_desafios` espera,
fechando o ciclo ler → reconciliar → aplicar.
"""

from dataclasses import dataclass
from datetime import datetime

import config
import supabase_client
from desafio_reconciliation import (
    CurrentSubmission,
    ReconciliationPlan,
    TokenVersion,
    compute_content_hash,
)


RPC_APPLY_DESAFIO_RECONCILIATION = "apply_desafio_reconciliation"

STATUS_APPLIED = "applied"
STATUS_ALREADY_RUNNING = "already_running"

# Marcadores levantados pelo RPC; traduzidos para erros de domínio.
_NEGATIVE_TOTAL_MARKER = "desafio_reconciliation_negative_clan_total"
_STALE_PLAN_MARKER = "desafio_reconciliation_stale_plan"


class DesafioReconciliationError(Exception):
    """Falha de domínio ao aplicar um plano de reconciliação."""


class SnapshotConfirmationMismatchError(DesafioReconciliationError):
    """A confirmação recebida não corresponde ao snapshot que seria aplicado."""


class MassRemovalConfirmationRequiredError(DesafioReconciliationError):
    """O plano remove mais de 20% dos tokens ativos e não foi confirmado."""


class EmptySnapshotBlockedError(DesafioReconciliationError):
    """A planilha veio vazia havendo tokens ativos: nada pode ser estornado."""


class NegativeClanTotalError(DesafioReconciliationError):
    """O plano deixaria o total de um clã negativo; a transação foi abortada."""


class StalePlanError(DesafioReconciliationError):
    """O estado mudou entre a leitura e a aplicação; o plano não vale mais."""


@dataclass(frozen=True)
class AppliedChallengeTransition:
    """Transição de ciclo de vida efetivamente gravada."""

    challenge_normalized: str
    transition: str
    desafio_id: int | None


@dataclass(frozen=True)
class AppliedSyncResult:
    """Resultado de uma tentativa de aplicação do plano."""

    status: str
    run_id: int | None
    snapshot_hash: str | None
    sheet_row_count: int
    state_counts: dict[str, int]
    clan_deltas: dict[str, int]
    clan_totals_after: dict[str, int]
    challenge_transitions: tuple[AppliedChallengeTransition, ...]
    challenges_created: int
    challenges_archived: int
    challenges_reactivated: int
    tokens_versioned: int
    started_at: datetime | None
    finished_at: datetime | None

    @property
    def already_running(self) -> bool:
        return self.status == STATUS_ALREADY_RUNNING


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


def apply_reconciliation(
    plan: ReconciliationPlan,
    *,
    confirmed_snapshot_hash: str | None = None,
    points_per_submission: int | None = None,
) -> AppliedSyncResult:
    """Aplica o plano inteiro em uma única transação do banco.

    `confirmed_snapshot_hash`, quando informado, precisa bater com o hash do
    próprio plano: uma confirmação só vale para o snapshot que o operador viu.
    Planos que a planilha esvaziaria (RF-18) ou que removem em massa sem
    confirmação (RF-17) são recusados antes de qualquer escrita.

    Levanta `NegativeClanTotalError` quando o delta deixaria algum clã com
    total negativo — nesse caso nada do plano é aplicado (RF-19); o total nunca
    é truncado para zero.
    """
    if confirmed_snapshot_hash is not None and confirmed_snapshot_hash != plan.snapshot_hash:
        raise SnapshotConfirmationMismatchError(
            "confirmação não corresponde ao snapshot atual "
            f"(confirmado {confirmed_snapshot_hash!r}, plano {plan.snapshot_hash!r})"
        )

    if plan.is_empty_snapshot:
        raise EmptySnapshotBlockedError(
            "planilha vazia com "
            f"{plan.active_tokens_before} token(s) ativo(s): nenhuma alteração aplicada"
        )

    if plan.mass_removal_required and confirmed_snapshot_hash is None:
        raise MassRemovalConfirmationRequiredError(
            f"{plan.mass_removal_count} token(s) ativo(s) sumiriam "
            f"({plan.mass_removal_ratio:.0%}): confirmação explícita obrigatória"
        )

    payload = _plan_payload(
        plan,
        points_per_submission=(
            config.POINTS_PER_DESAFIO_SUBMISSION
            if points_per_submission is None
            else points_per_submission
        ),
        mass_removal_confirmed=confirmed_snapshot_hash is not None,
    )

    try:
        data = supabase_client.call_rpc(
            RPC_APPLY_DESAFIO_RECONCILIATION, {"p_payload": payload}
        )
    except Exception as exc:  # noqa: BLE001 - só traduz o que reconhece
        message = str(exc)
        if _NEGATIVE_TOTAL_MARKER in message:
            raise NegativeClanTotalError(message) from exc
        if _STALE_PLAN_MARKER in message:
            raise StalePlanError(message) from exc
        raise

    return _result_from_rpc(data)


def _plan_payload(
    plan: ReconciliationPlan,
    *,
    points_per_submission: int,
    mass_removal_confirmed: bool,
) -> dict:
    return {
        "snapshot_hash": plan.snapshot_hash,
        "sheet_row_count": plan.sheet_row_count,
        "state_counts": dict(plan.state_counts),
        "clan_deltas": dict(plan.clan_deltas),
        "points_per_submission": points_per_submission,
        "mass_removal_required": plan.mass_removal_required,
        "mass_removal_confirmed": mass_removal_confirmed,
        "mass_removal_count": plan.mass_removal_count,
        "challenges_created": plan.challenges_created,
        "challenges_archived": plan.challenges_archived,
        "challenges_reactivated": plan.challenges_reactivated,
        "challenge_transitions": [
            {
                "challenge_normalized": transition.challenge_normalized,
                "challenge_display": transition.challenge_display,
                "transition": transition.transition,
            }
            for transition in plan.challenge_transitions
        ],
        "token_versions": [
            _token_version_payload(version) for version in plan.token_versions
        ],
    }


def _token_version_payload(version: TokenVersion) -> dict:
    state = version.current_state
    return {
        "token": version.token,
        "change_reason": version.change_reason,
        "previous_status": version.previous_status,
        "current_status": version.current_status,
        "previous_state": version.previous_state,
        "current_state": state,
        # Recalculado a partir do mesmo estado bruto que o snapshot usou, para
        # que a próxima reconciliação compare hashes equivalentes.
        "content_hash": (
            compute_content_hash(version.token, state["status"], state["variants"])
            if state
            else None
        ),
        "point_delta": version.point_delta,
        "clan_deltas": dict(version.clan_deltas),
        "challenge_normalized": version.challenge_normalized,
        "challenge_display": version.challenge_display,
        "row_numbers": list(version.row_numbers),
    }


def _result_from_rpc(data) -> AppliedSyncResult:
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        raise DesafioReconciliationError(
            f"resposta inesperada de {RPC_APPLY_DESAFIO_RECONCILIATION}: {data!r}"
        )

    return AppliedSyncResult(
        status=data.get("status", STATUS_APPLIED),
        run_id=data.get("run_id"),
        snapshot_hash=data.get("snapshot_hash"),
        sheet_row_count=data.get("sheet_row_count") or 0,
        state_counts=data.get("state_counts") or {},
        clan_deltas=data.get("clan_deltas") or {},
        clan_totals_after=data.get("clan_totals_after") or {},
        challenge_transitions=tuple(
            AppliedChallengeTransition(
                challenge_normalized=item.get("challenge_normalized"),
                transition=item.get("transition"),
                desafio_id=item.get("desafio_id"),
            )
            for item in data.get("challenge_transitions") or []
        ),
        challenges_created=data.get("challenges_created") or 0,
        challenges_archived=data.get("challenges_archived") or 0,
        challenges_reactivated=data.get("challenges_reactivated") or 0,
        tokens_versioned=data.get("tokens_versioned") or 0,
        started_at=_parse_timestamp(data.get("started_at")),
        finished_at=_parse_timestamp(data.get("finished_at")),
    )


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def get_current_desafio_submissions() -> dict[str, CurrentSubmission]:
    """Lê o estado atual de todos os tokens no formato aceito pela reconciliação."""
    return {
        row["token"]: _current_submission_from_row(row)
        for row in supabase_client.fetch_all_desafio_submissions_current()
    }


def _current_submission_from_row(row: dict) -> CurrentSubmission:
    return CurrentSubmission(
        token=row["token"],
        raw_clan_legacy=row.get("raw_clan_legacy"),
        raw_name=row.get("raw_name"),
        raw_validation=row.get("raw_validation"),
        raw_link=row.get("raw_link"),
        raw_observation=row.get("raw_observation"),
        raw_challenge=row.get("raw_challenge"),
        raw_clan_current=row.get("raw_clan_current"),
        raw_submitted_at=row.get("raw_submitted_at"),
        raw_token=row.get("raw_token"),
        clan=row.get("clan"),
        challenge_normalized=row.get("challenge_normalized"),
        desafio_id=row.get("desafio_id"),
        submitted_at=_parse_timestamp(row.get("submitted_at")),
        status=row["status"],
        points=row.get("points") or 0,
        content_hash=row.get("content_hash") or "",
    )


def _parse_timestamp(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    return datetime.fromisoformat(text)
