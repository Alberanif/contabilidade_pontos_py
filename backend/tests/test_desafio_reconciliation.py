import os
import sys
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desafio_sheet_parser import ParsedDesafioRow, parse_desafio_row
from desafio_reconciliation import (
    ChallengeTransition,
    CurrentSubmission,
    DesafioSnapshot,
    DesafioSnapshotEntry,
    ReconciliationPlan,
    TokenVersion,
    build_desafio_snapshot,
    reconcile_desafios,
)


SAO_PAULO = ZoneInfo("America/Sao_Paulo")
POINTS = 10


def _cells(
    clan_legacy="1",
    name="Ana Maria",
    validation="Sim",
    link="https://example.test/evidence",
    observation="Observação preservada",
    challenge="Desafio Pontual A",
    clan_current="",
    submitted_at="19/08/2026 14:35:20",
    token="Token-X",
):
    return [
        clan_legacy,
        name,
        validation,
        link,
        observation,
        challenge,
        clan_current,
        submitted_at,
        token,
    ]


def _row(row_number=2, **overrides) -> ParsedDesafioRow:
    return parse_desafio_row(row_number, _cells(**overrides))


def _current(
    token="Token-X",
    clan="CLÃ 1",
    challenge_normalized="desafio pontual a",
    desafio_id=1,
    status="active_counted",
    points=10,
    submitted_at=datetime(2026, 8, 19, 14, 35, 20, tzinfo=SAO_PAULO),
    content_hash="seed-hash",
    raw_clan_legacy="1",
    raw_name="Ana Maria",
    raw_validation="Sim",
    raw_link="https://example.test/evidence",
    raw_observation="Observação preservada",
    raw_challenge="Desafio Pontual A",
    raw_clan_current="",
    raw_submitted_at="19/08/2026 14:35:20",
    raw_token="Token-X",
) -> CurrentSubmission:
    return CurrentSubmission(
        token=token,
        raw_clan_legacy=raw_clan_legacy,
        raw_name=raw_name,
        raw_validation=raw_validation,
        raw_link=raw_link,
        raw_observation=raw_observation,
        raw_challenge=raw_challenge,
        raw_clan_current=raw_clan_current,
        raw_submitted_at=raw_submitted_at,
        raw_token=raw_token,
        clan=clan,
        challenge_normalized=challenge_normalized,
        desafio_id=desafio_id,
        submitted_at=submitted_at,
        status=status,
        points=points,
        content_hash=content_hash,
    )


def _apply_plan(current, snapshot, plan, desafio_ids):
    """Simula o que a Task 4 faria: projeta o plano em um novo `current`."""
    updated = dict(current)

    for transition in plan.challenge_transitions:
        if transition.transition == "create":
            desafio_ids[transition.challenge_normalized] = len(desafio_ids) + 1

    for version in plan.token_versions:
        if version.change_reason == "missing":
            existing = updated[version.token]
            updated[version.token] = replace(
                existing, status="inactive_missing", clan=None, points=0
            )
            continue

        entry = snapshot.entries[version.token]
        variant = entry.variant_rows[0]
        updated[version.token] = CurrentSubmission(
            token=entry.token,
            raw_clan_legacy=variant.raw_clan_legacy,
            raw_name=variant.raw_name,
            raw_validation=variant.raw_validation,
            raw_link=variant.raw_link,
            raw_observation=variant.raw_observation,
            raw_challenge=variant.raw_challenge,
            raw_clan_current=variant.raw_clan_current,
            raw_submitted_at=variant.raw_submitted_at,
            raw_token=variant.raw_token,
            clan=entry.clan,
            challenge_normalized=entry.challenge_normalized,
            desafio_id=desafio_ids.get(entry.challenge_normalized),
            submitted_at=entry.submitted_at,
            status=entry.status,
            points=entry.points,
            content_hash=entry.content_hash,
        )
    return updated


# ---------------------------------------------------------------------------
# build_desafio_snapshot
# ---------------------------------------------------------------------------


def test_ca01_new_valid_token_becomes_active_counted_entry_worth_configured_points():
    """CA-01: token válido gera exatamente os pontos configurados para o clã."""
    snapshot = build_desafio_snapshot([_row(token="T1")], POINTS)

    entry = snapshot.entries["T1"]
    assert entry.status == "active_counted"
    assert entry.eligible is True
    assert entry.clan == "CLÃ 1"
    assert entry.points == POINTS


def test_ca02_distinct_tokens_same_name_clan_and_challenge_score_separately():
    """CA-02: três tokens diferentes, mesmo nome/clã/desafio, pontuam separadamente."""
    rows = [
        _row(row_number=2, token="T1"),
        _row(row_number=3, token="T2"),
        _row(row_number=4, token="T3"),
    ]
    snapshot = build_desafio_snapshot(rows, POINTS)

    assert len(snapshot.entries) == 3
    assert {e.points for e in snapshot.entries.values()} == {POINTS}

    plan = reconcile_desafios(snapshot, {})
    assert plan.clan_deltas == {"CLÃ 1": 30}


def test_ca04_identical_duplicate_token_counts_once():
    """CA-04: mesmo token repetido em duas linhas idênticas conta uma vez."""
    rows = [
        _row(row_number=2, token="T1"),
        _row(row_number=5, token="T1"),
    ]
    snapshot = build_desafio_snapshot(rows, POINTS)

    assert len(snapshot.entries) == 1
    entry = snapshot.entries["T1"]
    assert entry.points == POINTS
    assert entry.status == "active_counted"
    assert entry.row_numbers == (2, 5)

    plan = reconcile_desafios(snapshot, {})
    assert plan.clan_deltas == {"CLÃ 1": 10}


def test_ca05_conflicting_duplicate_token_does_not_score_and_is_flagged():
    """CA-05: mesmo token com clãs diferentes não pontua e aparece como conflito."""
    rows = [
        _row(row_number=2, token="T1", clan_legacy="1"),
        _row(row_number=5, token="T1", clan_legacy="2"),
    ]
    snapshot = build_desafio_snapshot(rows, POINTS)

    entry = snapshot.entries["T1"]
    assert entry.status == "conflicted"
    assert entry.eligible is False
    assert entry.points == 0
    assert entry.clan is None
    assert "duplicate_token_conflict" in entry.reasons
    assert entry.row_numbers == (2, 5)


def test_three_or_more_conflicting_variants_are_all_preserved_for_audit():
    """Edge case: 3+ grafias divergentes do mesmo token continuam auditáveis."""
    rows = [
        _row(row_number=2, token="T1", clan_legacy="1"),
        _row(row_number=5, token="T1", clan_legacy="2"),
        _row(row_number=9, token="T1", clan_legacy="3"),
    ]
    snapshot = build_desafio_snapshot(rows, POINTS)

    entry = snapshot.entries["T1"]
    assert entry.status == "conflicted"
    assert entry.points == 0
    assert len(entry.variant_rows) == 3
    assert entry.row_numbers == (2, 5, 9)


def test_ca09_second_clan_column_used_alone_and_conflicting_columns_flagged():
    """CA-09: A vazia/G=5 pontua CLÃ 5; A=1 e G=2 conflitam e não pontuam."""
    snapshot = build_desafio_snapshot(
        [
            _row(row_number=2, token="T1", clan_legacy="", clan_current="5"),
            _row(row_number=3, token="T2", clan_legacy="1", clan_current="2"),
        ],
        POINTS,
    )

    assert snapshot.entries["T1"].clan == "CLÃ 5"
    assert snapshot.entries["T1"].eligible is True

    assert snapshot.entries["T2"].status == "conflicted"
    assert snapshot.entries["T2"].eligible is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "   "),
        ("clan_legacy", "9"),
        ("challenge", ""),
        ("submitted_at", "31/02/2026 10:00:00"),
    ],
)
def test_ca10_incomplete_row_does_not_score_and_reports_reason(field, value):
    """CA-10: linha incompleta não pontua e informa o motivo."""
    snapshot = build_desafio_snapshot(
        [_row(row_number=2, token="T1", **{field: value})], POINTS
    )

    entry = snapshot.entries["T1"]
    assert entry.status == "invalid"
    assert entry.eligible is False
    assert entry.points == 0
    assert entry.reasons != ()


def test_ca10_blank_token_row_has_no_identity_and_is_excluded_from_entries():
    """CA-10 (token vazio): linha sem token não cria uma entrada endereçável."""
    snapshot = build_desafio_snapshot(
        [_row(row_number=2, token=""), _row(row_number=3, token="T2")], POINTS
    )

    assert snapshot.entries.keys() == {"T2"}
    assert len(snapshot.blank_token_rows) == 1
    assert "missing_token" in snapshot.blank_token_rows[0].reasons
    assert snapshot.sheet_row_count == 2


def test_ca14_submitted_at_is_preserved_for_historical_reporting():
    """CA-14: a data de submissão do token é preservada para relatórios históricos."""
    snapshot = build_desafio_snapshot(
        [_row(token="T1", submitted_at="12/05/2026 09:00:00")], POINTS
    )

    entry = snapshot.entries["T1"]
    assert entry.submitted_at == datetime(2026, 5, 12, 9, 0, 0, tzinfo=SAO_PAULO)

    plan = reconcile_desafios(snapshot, {})
    version = plan.token_versions[0]
    assert version.current_state["submitted_at"] == "2026-05-12T09:00:00-03:00"


def test_snapshot_hash_is_deterministic_and_sensitive_to_content():
    """Hash determinístico: mesmo conteúdo -> mesmo hash; conteúdo diferente -> hash diferente."""
    rows_a = [_row(token="T1"), _row(row_number=3, token="T2")]
    rows_b = [_row(token="T1"), _row(row_number=3, token="T2")]
    rows_c = [_row(token="T1"), _row(row_number=3, token="T2", name="Outro Nome")]

    snap_a = build_desafio_snapshot(rows_a, POINTS)
    snap_b = build_desafio_snapshot(rows_b, POINTS)
    snap_c = build_desafio_snapshot(rows_c, POINTS)

    assert snap_a.snapshot_hash == snap_b.snapshot_hash
    assert snap_a.snapshot_hash != snap_c.snapshot_hash


def test_build_desafio_snapshot_rejects_non_positive_points_configuration():
    with pytest.raises(ValueError):
        build_desafio_snapshot([_row(token="T1")], 0)


# ---------------------------------------------------------------------------
# reconcile_desafios: novo / inalterado / alterado / ausente / reaparecido
# ---------------------------------------------------------------------------


def test_ca03_reconciling_an_already_synced_snapshot_again_produces_zero_delta():
    """CA-03: idempotência — sem alterações, delta zero."""
    snapshot = build_desafio_snapshot([_row(token="T1")], POINTS)
    plan_one = reconcile_desafios(snapshot, {})
    current_after = _apply_plan({}, snapshot, plan_one, {})

    plan_two = reconcile_desafios(snapshot, current_after)

    assert plan_two.token_versions == ()
    assert plan_two.clan_deltas == {}
    assert plan_two.state_counts["unchanged"] == 1
    assert plan_two.challenge_transitions == ()


def test_property_two_reconciliations_of_the_identical_snapshot_yield_zero_delta_for_every_clan():
    """Propriedade: reconciliar o mesmo snapshot duas vezes nunca produz delta líquido."""
    rows = [
        _row(row_number=2, token="T1", clan_legacy="1", challenge="Desafio A"),
        _row(row_number=3, token="T2", clan_legacy="2", validation="Não", challenge="Desafio B"),
        _row(row_number=4, token="T3", clan_legacy="9", challenge="Desafio C"),
        _row(row_number=5, token="T4", clan_legacy="3", clan_current="4", challenge="Desafio D"),
        _row(row_number=6, token="T5", clan_legacy="1", challenge="Desafio A"),
        _row(row_number=7, token="T5", clan_legacy="1", challenge="Desafio A"),
    ]
    snapshot = build_desafio_snapshot(rows, POINTS)

    desafio_ids: dict[str, int] = {}
    plan_one = reconcile_desafios(snapshot, {})
    current_after = _apply_plan({}, snapshot, plan_one, desafio_ids)

    plan_two = reconcile_desafios(snapshot, current_after)

    assert plan_two.clan_deltas == {}
    for clan_delta in plan_two.token_versions:
        assert clan_delta.clan_deltas == {}
    assert plan_two.challenges_created == 0
    assert plan_two.challenges_archived == 0
    assert plan_two.challenges_reactivated == 0


def test_ca06_clan_correction_reverses_old_clan_and_credits_new_clan():
    """CA-06: Clã 1 -> Clã 2 estorna 10 do Clã 1 e credita 10 ao Clã 2."""
    current = {"T1": _current(clan="CLÃ 1", points=10, status="active_counted")}
    snapshot = build_desafio_snapshot([_row(token="T1", clan_legacy="2")], POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.clan_deltas == {"CLÃ 1": -10, "CLÃ 2": 10}
    version = plan.token_versions[0]
    assert version.change_reason == "changed_with_effect"
    assert version.point_delta == 0


def test_ca07_validation_flip_to_nao_reverses_points_retroactively():
    """CA-07: Sim -> Não estorna os pontos do token."""
    current = {"T1": _current(status="active_counted", points=10, clan="CLÃ 1")}
    snapshot = build_desafio_snapshot([_row(token="T1", validation="Não")], POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.clan_deltas == {"CLÃ 1": -10}
    version = plan.token_versions[0]
    assert version.change_reason == "changed_with_effect"
    assert version.current_status == "active_not_counted"
    assert version.point_delta == -10


def test_validation_toggles_sim_nao_sim_reproduce_correct_deltas_each_time():
    """Edge case: alternar Sim -> Não -> Sim reaplica e estorna corretamente a cada ciclo."""
    desafio_ids: dict[str, int] = {}

    snap_sim = build_desafio_snapshot([_row(token="T1", validation="Sim")], POINTS)
    plan_1 = reconcile_desafios(snap_sim, {})
    assert plan_1.clan_deltas == {"CLÃ 1": 10}
    current = _apply_plan({}, snap_sim, plan_1, desafio_ids)

    snap_nao = build_desafio_snapshot([_row(token="T1", validation="Não")], POINTS)
    plan_2 = reconcile_desafios(snap_nao, current)
    assert plan_2.clan_deltas == {"CLÃ 1": -10}
    current = _apply_plan(current, snap_nao, plan_2, desafio_ids)

    plan_3 = reconcile_desafios(snap_sim, current)
    assert plan_3.clan_deltas == {"CLÃ 1": 10}


def test_unrelated_audit_only_field_change_produces_zero_delta_version():
    """Alteração apenas em link/observação: nova versão, delta contábil zero."""
    current = {
        "T1": _current(
            status="active_counted",
            points=10,
            clan="CLÃ 1",
            content_hash="old-hash",
        )
    }
    snapshot = build_desafio_snapshot(
        [_row(token="T1", observation="Nova observação")], POINTS
    )

    plan = reconcile_desafios(snapshot, current)

    assert plan.clan_deltas == {}
    version = plan.token_versions[0]
    assert version.change_reason == "changed_without_effect"
    assert version.point_delta == 0


def test_ca08_missing_token_is_reversed_and_kept_for_audit():
    """CA-08: token ativo ausente é inativado, estornado e mantido em auditoria."""
    current = {"T1": _current(status="active_counted", points=10, clan="CLÃ 1")}
    snapshot = build_desafio_snapshot([], POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.clan_deltas == {"CLÃ 1": -10}
    version = plan.token_versions[0]
    assert version.token == "T1"
    assert version.change_reason == "missing"
    assert version.current_status == "inactive_missing"
    assert version.previous_state is not None
    assert version.previous_state["clan"] == "CLÃ 1"


def test_reappeared_token_scores_again_without_double_counting():
    """Reaparecido: token antes inativo reaparece e volta a pontuar."""
    current = {
        "T1": _current(status="inactive_missing", points=0, clan=None)
    }
    snapshot = build_desafio_snapshot([_row(token="T1")], POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.clan_deltas == {"CLÃ 1": 10}
    version = plan.token_versions[0]
    assert version.change_reason == "reappeared"
    assert version.point_delta == 10


# ---------------------------------------------------------------------------
# Ciclo de vida de desafios: CA-11, CA-12, CA-13
# ---------------------------------------------------------------------------


def test_ca11_challenge_is_created_automatically_on_first_eligible_token():
    """CA-11: primeiro token elegível de um desafio cria o desafio automaticamente."""
    snapshot = build_desafio_snapshot(
        [_row(token="T1", challenge="Desafio Pontual C")], POINTS
    )

    plan = reconcile_desafios(snapshot, {})

    assert plan.challenges_created == 1
    transition = plan.challenge_transitions[0]
    assert transition.transition == "create"
    assert transition.challenge_normalized == "desafio pontual c"
    assert transition.challenge_display == "Desafio Pontual C"


def test_ca12_challenge_with_only_ineligible_rows_is_never_created():
    """CA-12: desafio presente só em linhas inválidas/Não não é criado."""
    snapshot = build_desafio_snapshot(
        [
            _row(row_number=2, token="T1", validation="Não", challenge="Desafio Vazio"),
            _row(row_number=3, token="T2", clan_legacy="9", challenge="Desafio Vazio"),
        ],
        POINTS,
    )

    plan = reconcile_desafios(snapshot, {})

    assert plan.challenges_created == 0
    assert plan.challenge_transitions == ()


def test_ca13_challenge_is_archived_then_reactivated_across_syncs():
    """CA-13: desafio sem tokens pontuáveis é arquivado; reaparece elegível, reativa."""
    desafio_ids: dict[str, int] = {}

    snap_1 = build_desafio_snapshot(
        [_row(token="T1", challenge="Desafio Pontual C")], POINTS
    )
    plan_1 = reconcile_desafios(snap_1, {})
    assert plan_1.challenges_created == 1
    current = _apply_plan({}, snap_1, plan_1, desafio_ids)
    assert current["T1"].desafio_id is not None

    snap_2 = build_desafio_snapshot(
        [_row(token="T1", challenge="Desafio Pontual C", validation="Não")], POINTS
    )
    plan_2 = reconcile_desafios(snap_2, current)
    assert plan_2.challenges_archived == 1
    assert plan_2.challenge_transitions[0].transition == "archive"
    current = _apply_plan(current, snap_2, plan_2, desafio_ids)
    assert current["T1"].desafio_id is not None  # FK preservado ao arquivar

    snap_3 = build_desafio_snapshot(
        [_row(token="T1", challenge="Desafio Pontual C", validation="Sim")], POINTS
    )
    plan_3 = reconcile_desafios(snap_3, current)
    assert plan_3.challenges_reactivated == 1
    assert plan_3.challenge_transitions[0].transition == "reactivate"


def test_challenge_rename_that_also_changes_clan_archives_old_and_creates_new():
    """Edge case: renomear desafio e trocar de clã simultaneamente."""
    desafio_ids: dict[str, int] = {}
    snap_1 = build_desafio_snapshot(
        [_row(token="T1", challenge="Desafio A", clan_legacy="1")], POINTS
    )
    plan_1 = reconcile_desafios(snap_1, {})
    current = _apply_plan({}, snap_1, plan_1, desafio_ids)

    snap_2 = build_desafio_snapshot(
        [_row(token="T1", challenge="Desafio B", clan_legacy="2")], POINTS
    )
    plan_2 = reconcile_desafios(snap_2, current)

    assert plan_2.clan_deltas == {"CLÃ 1": -10, "CLÃ 2": 10}
    kinds = {t.challenge_normalized: t.transition for t in plan_2.challenge_transitions}
    assert kinds == {"desafio a": "archive", "desafio b": "create"}
    version = plan_2.token_versions[0]
    assert version.change_reason == "changed_with_effect"


# ---------------------------------------------------------------------------
# Guardas: CA-16, CA-17
# ---------------------------------------------------------------------------


def test_ca16_empty_snapshot_with_active_tokens_is_flagged_but_deltas_still_exposed():
    """CA-16: leitura vazia com tokens ativos não estorna automaticamente, mas sinaliza."""
    current = {
        "T1": _current(token="T1", status="active_counted", points=10, clan="CLÃ 1"),
        "T2": _current(token="T2", status="active_counted", points=10, clan="CLÃ 2"),
    }
    snapshot = build_desafio_snapshot([], POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.is_empty_snapshot is True
    # O plano ainda expõe o que seria estornado, para exibição/confirmação;
    # a aplicação automática é responsabilidade da Task 4/5.
    assert plan.mass_removal_count == 2
    assert len(plan.token_versions) == 2
    assert plan.clan_deltas == {"CLÃ 1": -10, "CLÃ 2": -10}


def test_empty_snapshot_without_prior_active_tokens_does_not_trigger_guard():
    current = {}
    snapshot = build_desafio_snapshot([], POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.is_empty_snapshot is False


def test_ca17_mass_removal_above_twenty_percent_requires_confirmation():
    """CA-17: remoção acima de 20% dos tokens ativos exige confirmação."""
    current = {
        f"T{i}": _current(token=f"T{i}", status="active_counted", points=10, clan="CLÃ 1")
        for i in range(10)
    }
    # 3 de 10 tokens ativos desaparecem (30% > 20%).
    remaining_rows = [_row(row_number=i + 2, token=f"T{i}") for i in range(7)]
    snapshot = build_desafio_snapshot(remaining_rows, POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.mass_removal_required is True
    assert plan.mass_removal_count == 3
    assert plan.mass_removal_ratio == pytest.approx(0.3)
    # Continua expondo os deltas calculados para a tela de confirmação: os 3
    # tokens ausentes estornam 10 pontos cada; os 7 restantes ficam
    # inalterados (mesmo conteúdo já persistido) e não geram delta algum.
    assert plan.clan_deltas == {"CLÃ 1": -30}


def test_mass_removal_exactly_twenty_percent_does_not_trigger_guard():
    current = {
        f"T{i}": _current(token=f"T{i}", status="active_counted", points=10, clan="CLÃ 1")
        for i in range(10)
    }
    remaining_rows = [_row(row_number=i + 2, token=f"T{i}") for i in range(8)]
    snapshot = build_desafio_snapshot(remaining_rows, POINTS)

    plan = reconcile_desafios(snapshot, current)

    assert plan.mass_removal_required is False
    assert plan.mass_removal_ratio == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# CA-22: mudança do valor configurado
# ---------------------------------------------------------------------------


def test_ca22_changing_points_configuration_recomputes_all_active_tokens():
    """CA-22: mudar o valor de pontos recalcula retroativamente todos os ativos."""
    current = {
        "T1": _current(token="T1", status="active_counted", points=10, clan="CLÃ 1"),
        "T2": _current(
            token="T2",
            status="active_counted",
            points=10,
            clan="CLÃ 2",
            challenge_normalized="desafio pontual a",
            content_hash="hash-t2",
        ),
    }
    rows = [
        _row(row_number=2, token="T1"),
        _row(row_number=3, token="T2", clan_legacy="2"),
    ]
    # T2 tem conteúdo idêntico ao já persistido (mesmo content_hash simulável),
    # mas o novo valor de pontos ainda deve recalcular seu delta.
    snapshot = build_desafio_snapshot(rows, 25)
    current["T2"] = replace(current["T2"], content_hash=snapshot.entries["T2"].content_hash)

    plan = reconcile_desafios(snapshot, current)

    assert plan.clan_deltas == {"CLÃ 1": 15, "CLÃ 2": 15}
    assert len(plan.token_versions) == 2
    for version in plan.token_versions:
        assert version.change_reason == "changed_with_effect"
        assert version.point_delta == 15


def test_ca22_unchanged_config_and_content_produces_no_version():
    """Contraprova do CA-22: sem mudança de config nem conteúdo, nada é versionado."""
    snapshot = build_desafio_snapshot([_row(token="T1")], POINTS)
    plan_seed = reconcile_desafios(snapshot, {})
    current = _apply_plan({}, snapshot, plan_seed, {})

    plan = reconcile_desafios(snapshot, current)

    assert plan.token_versions == ()
    assert plan.clan_deltas == {}


# ---------------------------------------------------------------------------
# state_counts / contadores agregados
# ---------------------------------------------------------------------------


def test_state_counts_reflect_row_status_and_change_kind_together():
    rows = [
        _row(row_number=2, token="T1"),
        _row(row_number=3, token="T2", validation="Não"),
        _row(row_number=4, token="T3", name=""),
        _row(row_number=5, token="T4", clan_legacy="1", clan_current="2"),
    ]
    snapshot = build_desafio_snapshot(rows, POINTS)

    plan = reconcile_desafios(snapshot, {})

    assert plan.state_counts["active_counted"] == 1
    assert plan.state_counts["active_not_counted"] == 1
    assert plan.state_counts["invalid"] == 1
    assert plan.state_counts["conflicted"] == 1
    assert plan.state_counts["new"] == 4
    assert plan.sheet_row_count == 4


def test_dataclasses_are_importable_and_frozen():
    """Confirma o contrato público exportado pelo módulo."""
    assert DesafioSnapshot.__dataclass_params__.frozen is True
    assert DesafioSnapshotEntry.__dataclass_params__.frozen is True
    assert CurrentSubmission.__dataclass_params__.frozen is True
    assert TokenVersion.__dataclass_params__.frozen is True
    assert ChallengeTransition.__dataclass_params__.frozen is True
    assert ReconciliationPlan.__dataclass_params__.frozen is True


def test_module_has_no_io_dependencies():
    """Verifica que o motor de reconciliação não importa clientes de I/O."""
    import desafio_reconciliation

    source = open(desafio_reconciliation.__file__, encoding="utf-8").read()
    assert "google_sheets_client" not in source
    assert "supabase_client" not in source
