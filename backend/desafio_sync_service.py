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

## Observabilidade (Task 12)

Cada execução emite eventos estruturados em `logger` (`logging.getLogger
("desafio_sync")`), um por fase, carregados em `extra={"desafio_sync": {...}}`
para não colidir com os atributos padrão de `LogRecord` e para que um
`Formatter` (ou o `caplog` de um teste) consiga ler o payload inteiro em
`record.desafio_sync`, sem parsear texto.

**Correlação entre fases sem `run_id`.** `desafio_sync_runs.id` só existe
depois que a fase de aplicação já rodou — é o RPC `apply_desafio_reconciliation`
(migração 009) que gera o `run_id`, inserindo a linha *dentro* da própria
transação. As fases 1-5 (leitura, parse, snapshot, reconciliação) acontecem
antes disso e não têm nenhum `run_id` para carregar. Por isso todo evento desta
função carrega, desde o primeiro, um `correlation_id` gerado localmente (um
`uuid4` hex) — é ele, não o `run_id`, que amarra os eventos de uma mesma
chamada a `sync_desafios`. A partir da fase "snapshot" (quando
`build_desafio_snapshot` calcula o hash), os eventos passam a carregar também
`snapshot_hash` — o mesmo valor que acaba persistido em
`desafio_sync_runs.snapshot_hash` — o que dá a um operador um segundo eixo de
junção, desta vez ligado à linha que a fase de aplicação eventualmente grava.
O evento final da fase de aplicação carrega os três: `correlation_id`,
`snapshot_hash` e `run_id` (quando existe), fechando o elo entre "o que os
logs registraram" e "o que o banco persistiu".

**Segredos.** Nenhum evento carrega `config.GOOGLE_SERVICE_ACCOUNT_JSON` nem
qualquer token OAuth/de acesso derivado dele — só contagens e metadados
(duração, status, categoria de erro, `state_counts`, deltas de clã). O
identificador de negócio da planilha (`token`, coluna I) não é segredo — já é
público via `desafio_auditoria` — então contagens por estado que o citam
indiretamente (`state_counts["new"]`, `tokens_versioned`) não são vazamento;
o que nunca aparece é o *conteúdo* do JSON da service account.
"""

from __future__ import annotations

import logging
import time
import uuid

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

logger = logging.getLogger("desafio_sync")

# Rótulos de fase alinhados ao vocabulário do PRD/Task 12 ("leitura, parse,
# snapshot, reconciliação, aplicação"). A leitura do estado atual persistido
# (`get_current_desafio_submissions`) é medida dentro da fase "reconciliacao":
# é uma leitura rápida e puramente instrumental para a reconciliação em
# memória que a segue, sem valor de observabilidade isolado que justifique
# inflar a lista de fases além da que o PRD já nomeia.
PHASE_LEITURA = "leitura"
PHASE_PARSE = "parse"
PHASE_SNAPSHOT = "snapshot"
PHASE_RECONCILIACAO = "reconciliacao"
PHASE_APLICACAO = "aplicacao"

STATUS_EVENT_OK = "ok"
STATUS_EVENT_FAILED = "failed"


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

    Emite um evento estruturado por fase em `logger` (ver docstring do
    módulo) — correlacionados por `correlation_id` e, a partir da fase
    "snapshot", também por `snapshot_hash`.
    """
    started = time.monotonic()
    correlation_id = uuid.uuid4().hex
    snapshot_hash: str | None = None
    phase = PHASE_LEITURA
    phase_started = started

    try:
        phase = PHASE_LEITURA
        phase_started = time.monotonic()
        rows = google_sheets_client.fetch_desafio_records()
        _log_phase_ok(
            correlation_id,
            PHASE_LEITURA,
            phase_started,
            snapshot_hash=None,
            sheet_row_count=max(len(rows) - 1, 0) if rows else 0,
        )

        phase = PHASE_PARSE
        phase_started = time.monotonic()
        parsed_rows = desafio_sheet_parser.build_parsed_rows(rows)
        _log_phase_ok(
            correlation_id,
            PHASE_PARSE,
            phase_started,
            snapshot_hash=None,
            parsed_row_count=len(parsed_rows),
        )

        phase = PHASE_SNAPSHOT
        phase_started = time.monotonic()
        snapshot = desafio_reconciliation.build_desafio_snapshot(
            parsed_rows, config.POINTS_PER_DESAFIO_SUBMISSION
        )
        snapshot_hash = snapshot.snapshot_hash
        _log_phase_ok(
            correlation_id,
            PHASE_SNAPSHOT,
            phase_started,
            snapshot_hash=snapshot_hash,
            token_count=len(snapshot.entries),
            sheet_row_count=snapshot.sheet_row_count,
        )

        phase = PHASE_RECONCILIACAO
        phase_started = time.monotonic()
        current = store.get_current_desafio_submissions()
        plan = desafio_reconciliation.reconcile_desafios(snapshot, current)
        _log_phase_ok(
            correlation_id,
            PHASE_RECONCILIACAO,
            phase_started,
            snapshot_hash=plan.snapshot_hash,
            current_token_count=len(current),
            state_counts=dict(plan.state_counts),
            clan_deltas=dict(plan.clan_deltas),
            mass_removal_required=plan.mass_removal_required,
            mass_removal_ratio=plan.mass_removal_ratio,
        )
    except Exception as exc:  # noqa: BLE001 - qualquer falha de leitura/parse vira "failed"
        _log_phase_failed(correlation_id, phase, phase_started, snapshot_hash, exc)
        return _failed(str(exc), started)

    phase = PHASE_APLICACAO
    phase_started = time.monotonic()
    try:
        applied = store.apply_reconciliation(
            plan,
            confirmed_snapshot_hash=confirm_snapshot_hash,
            confirm_mass_removal=confirm_mass_removal,
        )
    except store.MassRemovalConfirmationRequiredError:
        logger.warning(
            "desafio_sync.aguardando_confirmacao",
            extra=_event(
                correlation_id,
                PHASE_APLICACAO,
                status=STATUS_AWAITING_CONFIRMATION,
                duration_seconds=time.monotonic() - phase_started,
                snapshot_hash=plan.snapshot_hash,
                mass_removal_count=plan.mass_removal_count,
                mass_removal_ratio=plan.mass_removal_ratio,
                active_tokens_before=plan.active_tokens_before,
            ),
        )
        return _awaiting_confirmation(plan, started)
    except store.DesafioReconciliationError as exc:
        _log_phase_failed(correlation_id, PHASE_APLICACAO, phase_started, plan.snapshot_hash, exc)
        return _failed(str(exc), started, snapshot_hash=plan.snapshot_hash)
    except Exception as exc:  # noqa: BLE001 - erro inesperado do RPC também vira "failed"
        _log_phase_failed(correlation_id, PHASE_APLICACAO, phase_started, plan.snapshot_hash, exc)
        return _failed(str(exc), started, snapshot_hash=plan.snapshot_hash)

    if applied.already_running:
        logger.warning(
            "desafio_sync.ja_em_andamento",
            extra=_event(
                correlation_id,
                PHASE_APLICACAO,
                status=STATUS_ALREADY_RUNNING,
                duration_seconds=time.monotonic() - phase_started,
                snapshot_hash=applied.snapshot_hash,
                run_id=applied.run_id,
            ),
        )
        return _already_running(applied, started)

    logger.info(
        "desafio_sync.concluido",
        extra=_event(
            correlation_id,
            PHASE_APLICACAO,
            status=STATUS_SUCCESS,
            duration_seconds=time.monotonic() - started,
            snapshot_hash=applied.snapshot_hash,
            run_id=applied.run_id,
            sheet_row_count=applied.sheet_row_count,
            state_counts=dict(applied.state_counts),
            clan_deltas=dict(applied.clan_deltas),
            challenges_created=applied.challenges_created,
            challenges_archived=applied.challenges_archived,
            challenges_reactivated=applied.challenges_reactivated,
            tokens_versioned=applied.tokens_versioned,
        ),
    )
    return _success(applied, started)


# ---------------------------------------------------------------------------
# Observabilidade — eventos estruturados por fase
# ---------------------------------------------------------------------------


def _event(correlation_id: str, phase: str, **fields) -> dict:
    """Monta o payload de `extra={"desafio_sync": ...}` de um evento.

    Sempre sob a chave única `"desafio_sync"`, para nunca colidir com um
    atributo padrão de `LogRecord` (`message`, `asctime`, `module`, ...) — o
    risco de colisão existiria se os campos fossem passados soltos em
    `extra`.
    """
    return {"desafio_sync": {"correlation_id": correlation_id, "phase": phase, **fields}}


def _log_phase_ok(
    correlation_id: str,
    phase: str,
    phase_started: float,
    *,
    snapshot_hash: str | None,
    **counts,
) -> None:
    logger.info(
        "desafio_sync.fase_concluida",
        extra=_event(
            correlation_id,
            phase,
            status=STATUS_EVENT_OK,
            duration_seconds=time.monotonic() - phase_started,
            snapshot_hash=snapshot_hash,
            **counts,
        ),
    )


def _log_phase_failed(
    correlation_id: str,
    phase: str,
    phase_started: float,
    snapshot_hash: str | None,
    exc: Exception,
) -> None:
    logger.error(
        "desafio_sync.fase_falhou",
        extra=_event(
            correlation_id,
            phase,
            status=STATUS_EVENT_FAILED,
            duration_seconds=time.monotonic() - phase_started,
            snapshot_hash=snapshot_hash,
            error_type=type(exc).__name__,
            error_category=_error_category(exc),
            # A mensagem da exceção nunca inclui o conteúdo de
            # `GOOGLE_SERVICE_ACCOUNT_JSON` — nenhum ponto do pipeline
            # interpola o segredo em texto de erro — mas registrá-la é
            # necessário para diagnosticar a falha real.
            error_message=str(exc),
        ),
    )


def _error_category(exc: Exception) -> str:
    """Classifica a exceção em um pequeno vocabulário estável para o runbook.

    Cada categoria aqui tem uma seção de investigação dedicada em
    `docs/runbooks/sincronizacao-desafios.md`.
    """
    if isinstance(exc, google_sheets_client.DesafioSheetConfigurationError):
        return "configuracao"
    if isinstance(exc, store.EmptySnapshotBlockedError):
        return "planilha_vazia"
    if isinstance(exc, store.NegativeClanTotalError):
        return "total_negativo"
    if isinstance(exc, store.StalePlanError):
        return "plano_obsoleto"
    if isinstance(exc, store.SnapshotConfirmationMismatchError):
        return "confirmacao_divergente"
    if isinstance(exc, store.MassRemovalConfirmationRequiredError):
        return "confirmacao_pendente"
    if isinstance(exc, store.DesafioReconciliationError):
        return "aplicacao"
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return "rede"
    if isinstance(exc, ValueError):
        return "dados"
    return "desconhecido"


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
