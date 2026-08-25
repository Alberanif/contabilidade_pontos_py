"""Motor puro de snapshot e reconciliação de desafios (Google Sheets).

Este módulo não realiza nenhuma leitura/escrita externa (Google Sheets,
Supabase, etc.). Ele apenas converte linhas já parseadas
(``desafio_sheet_parser.ParsedDesafioRow``) em um snapshot agrupado por
token e, em seguida, compara esse snapshot com o estado atualmente
persistido para produzir um plano de reconciliação determinístico. A
aplicação transacional desse plano é responsabilidade de uma etapa
posterior (Task 4).
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from desafio_sheet_parser import ParsedDesafioRow


# Estados de linha considerados "presentes e estruturalmente lidos" na
# planilha (independentemente de pontuarem ou não), usados para calcular a
# base das guardas de segurança (planilha vazia / remoção em massa).
ACTIVE_STATUSES = ("active_counted", "active_not_counted")

MASS_REMOVAL_THRESHOLD = 0.20


def _hash_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_content_hash(
    token: str, status: str, variants: list[list[str]] | tuple
) -> str:
    """Hash canônico do conteúdo bruto de um token.

    É a única definição do ``content_hash`` persistido em
    ``desafio_submissions_current``: tanto o snapshot quanto a camada de
    persistência derivam o valor daqui, para que a comparação
    ``entry.content_hash != existing.content_hash`` seja confiável entre
    execuções.
    """
    return _hash_payload(
        {
            "token": token,
            "status": status,
            "variants": [list(variant) for variant in variants],
        }
    )


@dataclass(frozen=True)
class DesafioSnapshotEntry:
    """Estado consolidado de um único token dentro de um snapshot."""

    token: str
    variant_rows: tuple[ParsedDesafioRow, ...]
    row_numbers: tuple[int, ...]
    status: str
    eligible: bool
    clan: str | None
    challenge_display: str
    challenge_normalized: str
    submitted_at: datetime | None
    name: str
    points: int
    reasons: tuple[str, ...]
    content_hash: str


@dataclass(frozen=True)
class DesafioSnapshot:
    """Projeção agrupada por token do estado atual da planilha oficial."""

    sheet_row_count: int
    entries: dict[str, DesafioSnapshotEntry]
    blank_token_rows: tuple[ParsedDesafioRow, ...]
    snapshot_hash: str


@dataclass(frozen=True)
class CurrentSubmission:
    """Shape de leitura equivalente a uma linha de ``desafio_submissions_current``."""

    token: str
    raw_clan_legacy: str | None
    raw_name: str | None
    raw_validation: str | None
    raw_link: str | None
    raw_observation: str | None
    raw_challenge: str | None
    raw_clan_current: str | None
    raw_submitted_at: str | None
    raw_token: str | None
    clan: str | None
    challenge_normalized: str | None
    desafio_id: int | None
    submitted_at: datetime | None
    status: str
    points: int
    content_hash: str


@dataclass(frozen=True)
class TokenVersion:
    """Uma versão de auditoria imutável a ser criada para um token que mudou."""

    token: str
    change_reason: str
    previous_status: str | None
    current_status: str
    previous_state: dict | None
    current_state: dict | None
    point_delta: int
    clan_deltas: dict[str, int]
    challenge_normalized: str | None
    challenge_display: str | None
    row_numbers: tuple[int, ...]


@dataclass(frozen=True)
class ChallengeTransition:
    """Transição automática de ciclo de vida de um desafio."""

    challenge_normalized: str
    challenge_display: str | None
    transition: str  # "create" | "archive" | "reactivate"


@dataclass(frozen=True)
class ReconciliationPlan:
    """Plano determinístico de reconciliação, pronto para aplicação transacional."""

    snapshot_hash: str
    sheet_row_count: int
    state_counts: dict[str, int]
    token_versions: tuple[TokenVersion, ...]
    clan_deltas: dict[str, int]
    challenge_transitions: tuple[ChallengeTransition, ...]
    challenges_created: int
    challenges_archived: int
    challenges_reactivated: int
    active_tokens_before: int
    is_empty_snapshot: bool
    mass_removal_required: bool
    mass_removal_ratio: float
    mass_removal_count: int


# ---------------------------------------------------------------------------
# build_desafio_snapshot
# ---------------------------------------------------------------------------


def build_desafio_snapshot(
    rows: list[ParsedDesafioRow], points_per_submission: int
) -> DesafioSnapshot:
    """Consolida linhas já parseadas em um snapshot agrupado por token.

    Duplicatas idênticas (mesmo token, mesmos valores em A-I) são
    consolidadas em uma única entrada. Duplicatas conflitantes (mesmo
    token, qualquer diferença) são marcadas como ``conflicted`` e nunca
    pontuam. Linhas sem token não possuem identidade endereçável e ficam
    disponíveis apenas em ``blank_token_rows`` para auditoria.
    """
    if points_per_submission <= 0:
        raise ValueError("points_per_submission deve ser positivo")

    grouped: dict[str, list[ParsedDesafioRow]] = {}
    blank_token_rows: list[ParsedDesafioRow] = []
    for row in rows:
        if not row.token:
            blank_token_rows.append(row)
            continue
        grouped.setdefault(row.token, []).append(row)

    entries: dict[str, DesafioSnapshotEntry] = {
        token: _build_entry(token, tuple(variant_rows), points_per_submission)
        for token, variant_rows in grouped.items()
    }

    snapshot_hash = _compute_snapshot_hash(entries, len(blank_token_rows))

    return DesafioSnapshot(
        sheet_row_count=len(rows),
        entries=entries,
        blank_token_rows=tuple(blank_token_rows),
        snapshot_hash=snapshot_hash,
    )


def _build_entry(
    token: str,
    variant_rows: tuple[ParsedDesafioRow, ...],
    points_per_submission: int,
) -> DesafioSnapshotEntry:
    row_numbers = tuple(row.row_number for row in variant_rows)
    distinct_raw = {row.raw_cells for row in variant_rows}

    if len(distinct_raw) == 1:
        canonical = variant_rows[0]
        status = canonical.status
        eligible = canonical.eligible
        clan = canonical.clan
        challenge_display = canonical.challenge_display
        challenge_normalized = canonical.challenge_normalized
        submitted_at = canonical.submitted_at
        name = canonical.name
        reasons = canonical.reasons
    else:
        first = variant_rows[0]
        status = "conflicted"
        eligible = False
        clan = None
        challenge_display = first.challenge_display
        challenge_normalized = first.challenge_normalized
        submitted_at = first.submitted_at
        name = first.name
        reasons = ("duplicate_token_conflict",)

    points = points_per_submission if eligible else 0
    content_hash = compute_content_hash(
        token, status, [list(row.raw_cells) for row in variant_rows]
    )

    return DesafioSnapshotEntry(
        token=token,
        variant_rows=variant_rows,
        row_numbers=row_numbers,
        status=status,
        eligible=eligible,
        clan=clan,
        challenge_display=challenge_display,
        challenge_normalized=challenge_normalized,
        submitted_at=submitted_at,
        name=name,
        points=points,
        reasons=reasons,
        content_hash=content_hash,
    )


def _compute_snapshot_hash(
    entries: dict[str, DesafioSnapshotEntry], blank_token_row_count: int
) -> str:
    payload = {
        "blank_token_rows": blank_token_row_count,
        "tokens": {token: entry.content_hash for token, entry in entries.items()},
    }
    return _hash_payload(payload)


# ---------------------------------------------------------------------------
# reconcile_desafios
# ---------------------------------------------------------------------------


def _entry_state_dict(entry: DesafioSnapshotEntry) -> dict:
    return {
        "status": entry.status,
        "eligible": entry.eligible,
        "clan": entry.clan,
        "challenge_display": entry.challenge_display,
        "challenge_normalized": entry.challenge_normalized,
        "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
        "name": entry.name,
        "points": entry.points,
        "row_numbers": list(entry.row_numbers),
        "variants": [list(row.raw_cells) for row in entry.variant_rows],
    }


def _current_state_dict(current: CurrentSubmission) -> dict:
    return {
        "status": current.status,
        "clan": current.clan,
        "challenge_normalized": current.challenge_normalized,
        "submitted_at": current.submitted_at.isoformat()
        if current.submitted_at
        else None,
        "points": current.points,
        "raw_cells": [
            current.raw_clan_legacy,
            current.raw_name,
            current.raw_validation,
            current.raw_link,
            current.raw_observation,
            current.raw_challenge,
            current.raw_clan_current,
            current.raw_submitted_at,
            current.raw_token,
        ],
    }


def _effect_tuple_from_entry(entry: DesafioSnapshotEntry) -> tuple:
    clan_for_points = entry.clan if entry.eligible else None
    return (clan_for_points, entry.points, entry.challenge_normalized, entry.submitted_at)


def _effect_tuple_from_current(current: CurrentSubmission) -> tuple:
    clan_for_points = current.clan if current.points else None
    return (
        clan_for_points,
        current.points,
        current.challenge_normalized,
        current.submitted_at,
    )


def _clan_deltas_for(
    old_clan: str | None, old_points: int, new_clan: str | None, new_points: int
) -> dict[str, int]:
    deltas: dict[str, int] = {}
    if old_points and old_clan:
        deltas[old_clan] = deltas.get(old_clan, 0) - old_points
    if new_points and new_clan:
        deltas[new_clan] = deltas.get(new_clan, 0) + new_points
    return {clan: delta for clan, delta in deltas.items() if delta != 0}


def _fresh_contribution_version(
    entry: DesafioSnapshotEntry,
    *,
    change_reason: str,
    existing: CurrentSubmission | None,
) -> TokenVersion:
    """Versão para um token sem contribuição anterior ativa (novo ou reaparecido)."""
    old_clan = existing.clan if existing and existing.points else None
    old_points = existing.points if existing else 0
    new_clan = entry.clan if entry.eligible else None
    new_points = entry.points

    return TokenVersion(
        token=entry.token,
        change_reason=change_reason,
        previous_status=existing.status if existing else None,
        current_status=entry.status,
        previous_state=_current_state_dict(existing) if existing else None,
        current_state=_entry_state_dict(entry),
        point_delta=new_points - old_points,
        clan_deltas=_clan_deltas_for(old_clan, old_points, new_clan, new_points),
        challenge_normalized=entry.challenge_normalized,
        challenge_display=entry.challenge_display,
        row_numbers=entry.row_numbers,
    )


def _changed_token_version(
    entry: DesafioSnapshotEntry, existing: CurrentSubmission, change_reason: str
) -> TokenVersion:
    old_clan = existing.clan if existing.points else None
    old_points = existing.points
    new_clan = entry.clan if entry.eligible else None
    new_points = entry.points

    return TokenVersion(
        token=entry.token,
        change_reason=change_reason,
        previous_status=existing.status,
        current_status=entry.status,
        previous_state=_current_state_dict(existing),
        current_state=_entry_state_dict(entry),
        point_delta=new_points - old_points,
        clan_deltas=_clan_deltas_for(old_clan, old_points, new_clan, new_points),
        challenge_normalized=entry.challenge_normalized,
        challenge_display=entry.challenge_display,
        row_numbers=entry.row_numbers,
    )


def _missing_token_version(token: str, existing: CurrentSubmission) -> TokenVersion:
    old_clan = existing.clan if existing.points else None
    old_points = existing.points

    return TokenVersion(
        token=token,
        change_reason="missing",
        previous_status=existing.status,
        current_status="inactive_missing",
        previous_state=_current_state_dict(existing),
        current_state=None,
        point_delta=-old_points,
        clan_deltas=_clan_deltas_for(old_clan, old_points, None, 0),
        challenge_normalized=existing.challenge_normalized,
        challenge_display=None,
        row_numbers=(),
    )


def _reconcile_token(
    entry: DesafioSnapshotEntry, existing: CurrentSubmission | None
) -> TokenVersion | None:
    if existing is None:
        return _fresh_contribution_version(entry, change_reason="new", existing=None)

    if existing.status == "inactive_missing":
        return _fresh_contribution_version(
            entry, change_reason="reappeared", existing=existing
        )

    if _effect_tuple_from_current(existing) != _effect_tuple_from_entry(entry):
        return _changed_token_version(entry, existing, "changed_with_effect")

    if entry.content_hash != existing.content_hash:
        return _changed_token_version(entry, existing, "changed_without_effect")

    return None


def _challenge_transitions(
    entries: dict[str, DesafioSnapshotEntry], current: dict[str, CurrentSubmission]
) -> tuple[ChallengeTransition, ...]:
    after_scorable: dict[str, str] = {}
    for entry in entries.values():
        if entry.eligible:
            after_scorable.setdefault(entry.challenge_normalized, entry.challenge_display)

    before_scorable: set[str] = set()
    known_challenges: set[str] = set()
    for existing in current.values():
        if not existing.challenge_normalized:
            continue
        if existing.desafio_id is not None:
            known_challenges.add(existing.challenge_normalized)
        if existing.status == "active_counted":
            before_scorable.add(existing.challenge_normalized)

    transitions: list[ChallengeTransition] = []
    for key in sorted(set(after_scorable) | before_scorable):
        was_scorable = key in before_scorable
        is_scorable = key in after_scorable
        if not was_scorable and is_scorable:
            kind = "reactivate" if key in known_challenges else "create"
            transitions.append(ChallengeTransition(key, after_scorable[key], kind))
        elif was_scorable and not is_scorable:
            transitions.append(ChallengeTransition(key, None, "archive"))

    return tuple(transitions)


def reconcile_desafios(
    snapshot: DesafioSnapshot, current: dict[str, CurrentSubmission]
) -> ReconciliationPlan:
    """Compara o snapshot atual com o estado persistido e produz um plano de deltas.

    As guardas operacionais (``is_empty_snapshot`` e remoção em massa acima
    de 20%) são apenas detectadas e expostas no plano resultante — a
    decisão de aplicar, bloquear ou exigir confirmação é responsabilidade
    da etapa de persistência transacional (fora deste módulo).
    """
    token_versions: list[TokenVersion] = []
    clan_deltas: dict[str, int] = {}
    state_counts: dict[str, int] = {
        "new": 0,
        "unchanged": 0,
        "changed_without_effect": 0,
        "changed_with_effect": 0,
        "missing": 0,
        "reappeared": 0,
        "active_counted": 0,
        "active_not_counted": 0,
        "invalid": 0,
        "conflicted": 0,
    }

    for token, entry in snapshot.entries.items():
        state_counts[entry.status] += 1
        version = _reconcile_token(entry, current.get(token))
        if version is None:
            state_counts["unchanged"] += 1
            continue
        state_counts[version.change_reason] += 1
        token_versions.append(version)
        for clan, delta in version.clan_deltas.items():
            clan_deltas[clan] = clan_deltas.get(clan, 0) + delta

    mass_removal_count = 0
    for token, existing in current.items():
        if existing.status == "inactive_missing" or token in snapshot.entries:
            continue
        version = _missing_token_version(token, existing)
        token_versions.append(version)
        state_counts["missing"] += 1
        if existing.status in ACTIVE_STATUSES:
            mass_removal_count += 1
        for clan, delta in version.clan_deltas.items():
            clan_deltas[clan] = clan_deltas.get(clan, 0) + delta

    clan_deltas = {clan: delta for clan, delta in clan_deltas.items() if delta != 0}

    active_tokens_before = sum(
        1 for c in current.values() if c.status in ACTIVE_STATUSES
    )
    is_empty_snapshot = len(snapshot.entries) == 0 and active_tokens_before > 0
    mass_removal_ratio = (
        mass_removal_count / active_tokens_before if active_tokens_before else 0.0
    )
    mass_removal_required = (
        active_tokens_before > 0 and mass_removal_ratio > MASS_REMOVAL_THRESHOLD
    )

    transitions = _challenge_transitions(snapshot.entries, current)
    challenges_created = sum(1 for t in transitions if t.transition == "create")
    challenges_archived = sum(1 for t in transitions if t.transition == "archive")
    challenges_reactivated = sum(1 for t in transitions if t.transition == "reactivate")

    return ReconciliationPlan(
        snapshot_hash=snapshot.snapshot_hash,
        sheet_row_count=snapshot.sheet_row_count,
        state_counts=state_counts,
        token_versions=tuple(token_versions),
        clan_deltas=clan_deltas,
        challenge_transitions=transitions,
        challenges_created=challenges_created,
        challenges_archived=challenges_archived,
        challenges_reactivated=challenges_reactivated,
        active_tokens_before=active_tokens_before,
        is_empty_snapshot=is_empty_snapshot,
        mass_removal_required=mass_removal_required,
        mass_removal_ratio=mass_removal_ratio,
        mass_removal_count=mass_removal_count,
    )
