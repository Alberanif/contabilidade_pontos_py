"""Testes de integração do RPC `apply_desafio_reconciliation` em PostgreSQL real.

Defina TEST_POSTGRES_DSN para habilitar esta suíte. Cada teste usa um schema
isolado e o remove ao final, sem tocar nas tabelas da aplicação.

Cobre o que só pode ser provado contra um banco real: lock exclusivo
não-bloqueante (`already_running`), atomicidade (rollback integral), rejeição de
total de clã negativo, imutabilidade das versões e transições de desafio.
"""

import json
import os
from pathlib import Path
import uuid

import pytest


TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
if not TEST_POSTGRES_DSN:
    pytest.skip(
        "TEST_POSTGRES_DSN não configurado para testes reais de RPC",
        allow_module_level=True,
    )

psycopg = pytest.importorskip("psycopg")
from psycopg import sql

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
MIGRATION_008 = (MIGRATIONS_DIR / "008_add_desafio_google_sync.sql").read_text(
    encoding="utf-8"
)
MIGRATION_009 = (MIGRATIONS_DIR / "009_apply_desafio_reconciliation.sql").read_text(
    encoding="utf-8"
)

# Reproduz o estado legado real das tabelas tocadas pelo RPC. `desafios.data` é
# NOT NULL sem default em produção (migração 2026-04-16), por isso aparece aqui.
LEGACY_SCHEMA = """
CREATE TABLE desafios (
  id                       SERIAL PRIMARY KEY,
  nome                     VARCHAR NOT NULL,
  contabilizar_pontos      BOOLEAN NOT NULL DEFAULT TRUE,
  data                     DATE NOT NULL,
  data_inicio              DATE,
  data_fim                 DATE,
  pontos_por_participacao  INTEGER,
  created_at               TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pontos_ultimate_totais_por_clan (
  clan              VARCHAR PRIMARY KEY,
  total_pontos      INTEGER NOT NULL DEFAULT 0,
  pessoas_em_espera INTEGER NOT NULL DEFAULT 0,
  total_pagante     INTEGER NOT NULL DEFAULT 0,
  total_pro_bono    INTEGER NOT NULL DEFAULT 0
);
"""

RAW_CELLS = ["1", "Ana", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "TOK-1"]


def _current_state(
    status: str = "active_counted",
    points: int = 10,
    clan: str | None = "CLÃ 1",
    raw_cells: list[str] | None = None,
) -> dict:
    cells = RAW_CELLS if raw_cells is None else raw_cells
    return {
        "status": status,
        "eligible": status == "active_counted",
        "clan": clan,
        "challenge_display": "Desafio A",
        "challenge_normalized": "desafio a",
        "submitted_at": "2026-08-19T10:00:00-03:00",
        "name": cells[1],
        "points": points,
        "row_numbers": [2],
        "variants": [cells],
    }


_DEFAULT = object()


def _token_version(
    token: str = "TOK-1",
    change_reason: str = "new",
    current_status: str = "active_counted",
    current_state=_DEFAULT,
    previous_status: str | None = None,
    previous_state: dict | None = None,
    point_delta: int = 10,
    clan_deltas: dict | None = None,
    content_hash: str | None = "hash-tok-1",
) -> dict:
    return {
        "token": token,
        "change_reason": change_reason,
        "previous_status": previous_status,
        "current_status": current_status,
        "previous_state": previous_state,
        "current_state": _current_state() if current_state is _DEFAULT else current_state,
        "content_hash": content_hash,
        "point_delta": point_delta,
        "clan_deltas": {"CLÃ 1": 10} if clan_deltas is None else clan_deltas,
        "challenge_normalized": "desafio a",
        "challenge_display": "Desafio A",
        "row_numbers": [2],
    }


def _payload(
    token_versions: list[dict] | None = None,
    clan_deltas: dict | None = None,
    challenge_transitions: list[dict] | None = None,
    snapshot_hash: str = "hash-abc",
) -> str:
    transitions = challenge_transitions or []
    return json.dumps(
        {
            "snapshot_hash": snapshot_hash,
            "sheet_row_count": 5,
            "state_counts": {"new": len(token_versions or [])},
            "clan_deltas": clan_deltas or {},
            "points_per_submission": 10,
            "mass_removal_required": False,
            "mass_removal_confirmed": False,
            "mass_removal_count": 0,
            "challenges_created": sum(
                1 for t in transitions if t["transition"] == "create"
            ),
            "challenges_archived": sum(
                1 for t in transitions if t["transition"] == "archive"
            ),
            "challenges_reactivated": sum(
                1 for t in transitions if t["transition"] == "reactivate"
            ),
            "challenge_transitions": transitions,
            "token_versions": token_versions or [],
        }
    )


def _apply(connection, payload: str) -> dict:
    return connection.execute(
        "SELECT apply_desafio_reconciliation(%s::JSONB)", (payload,)
    ).fetchone()[0]


def _make_schema(connection, schema_name: str) -> None:
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
    connection.execute(
        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
    )
    connection.execute(LEGACY_SCHEMA)
    connection.execute(MIGRATION_008)
    connection.execute(MIGRATION_009)


@pytest.fixture
def schema_name():
    return f"desafio_apply_test_{uuid.uuid4().hex}"


@pytest.fixture
def database(schema_name):
    connection = psycopg.connect(TEST_POSTGRES_DSN, autocommit=True)
    _make_schema(connection, schema_name)
    try:
        yield connection
    finally:
        connection.execute("RESET search_path")
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
        )
        connection.close()


# ---------------------------------------------------------------------------
# Aplicação bem-sucedida
# ---------------------------------------------------------------------------


def test_aplica_token_novo_criando_estado_versao_desafio_e_total(database):
    result = _apply(
        database,
        _payload(
            token_versions=[_token_version()],
            clan_deltas={"CLÃ 1": 10},
            challenge_transitions=[
                {
                    "challenge_normalized": "desafio a",
                    "challenge_display": "Desafio A",
                    "transition": "create",
                }
            ],
        ),
    )

    assert result["status"] == "applied"
    assert result["tokens_versioned"] == 1
    assert result["clan_totals_after"] == {"CLÃ 1": 10}

    run = database.execute(
        "SELECT status, snapshot_hash, finished_at FROM desafio_sync_runs WHERE id = %s",
        (result["run_id"],),
    ).fetchone()
    assert run[0] == "succeeded"
    assert run[1] == "hash-abc"
    assert run[2] is not None

    current = database.execute(
        """
        SELECT status, points, clan, content_hash, raw_name, raw_token,
               row_numbers, desafio_id, first_seen_run_id, last_seen_run_id,
               inactivated_at
        FROM desafio_submissions_current WHERE token = 'TOK-1'
        """
    ).fetchone()
    assert current[0] == "active_counted"
    assert current[1] == 10
    assert current[2] == "CLÃ 1"
    assert current[3] == "hash-tok-1"
    assert current[4] == "Ana"
    assert current[5] == "TOK-1"
    assert current[6] == [2]
    assert current[7] is not None
    assert current[8] == result["run_id"]
    assert current[9] == result["run_id"]
    assert current[10] is None

    version = database.execute(
        """
        SELECT version_number, change_reason, previous_status, current_status,
               point_delta, sync_run_id
        FROM desafio_submission_versions WHERE token = 'TOK-1'
        """
    ).fetchone()
    assert version == (1, "new", None, "active_counted", 10, result["run_id"])

    desafio = database.execute(
        "SELECT nome, nome_normalizado, origem, status FROM desafios"
    ).fetchone()
    assert desafio == ("Desafio A", "desafio a", "google_sheets", "ativo")

    total = database.execute(
        "SELECT total_pontos FROM pontos_ultimate_totais_por_clan WHERE clan = 'CLÃ 1'"
    ).fetchone()
    assert total == (10,)


def test_reaplicar_snapshot_ja_aplicado_com_plano_vazio_nao_altera_totais(database):
    _apply(
        database,
        _payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),
    )

    result = _apply(database, _payload())

    assert result["status"] == "applied"
    assert result["tokens_versioned"] == 0
    assert result["clan_deltas"] == {}
    total = database.execute(
        "SELECT total_pontos FROM pontos_ultimate_totais_por_clan WHERE clan = 'CLÃ 1'"
    ).fetchone()
    assert total == (10,)
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_submission_versions"
        ).fetchone()[0]
        == 1
    )


def test_token_ausente_inativa_estorna_e_preserva_historico(database):
    _apply(
        database,
        _payload(
            token_versions=[_token_version()],
            clan_deltas={"CLÃ 1": 10},
            challenge_transitions=[
                {
                    "challenge_normalized": "desafio a",
                    "challenge_display": "Desafio A",
                    "transition": "create",
                }
            ],
        ),
    )

    result = _apply(
        database,
        _payload(
            token_versions=[
                _token_version(
                    change_reason="missing",
                    current_status="inactive_missing",
                    current_state=None,
                    previous_status="active_counted",
                    previous_state={
                        "status": "active_counted",
                        "clan": "CLÃ 1",
                        "points": 10,
                    },
                    point_delta=-10,
                    clan_deltas={"CLÃ 1": -10},
                    content_hash=None,
                )
            ],
            clan_deltas={"CLÃ 1": -10},
            challenge_transitions=[
                {
                    "challenge_normalized": "desafio a",
                    "challenge_display": None,
                    "transition": "archive",
                }
            ],
            snapshot_hash="hash-vazio",
        ),
    )

    assert result["status"] == "applied"
    current = database.execute(
        """
        SELECT status, points, content_hash, raw_token, inactivated_at
        FROM desafio_submissions_current WHERE token = 'TOK-1'
        """
    ).fetchone()
    assert current[0] == "inactive_missing"
    assert current[1] == 0
    # O hash anterior é preservado: nada da história do token é apagado.
    assert current[2] == "hash-tok-1"
    assert current[3] == "TOK-1"
    assert current[4] is not None

    versions = database.execute(
        "SELECT version_number, change_reason, point_delta"
        " FROM desafio_submission_versions WHERE token = 'TOK-1'"
        " ORDER BY version_number"
    ).fetchall()
    assert versions == [(1, "new", 10), (2, "missing", -10)]

    desafio = database.execute(
        "SELECT status, arquivado_at FROM desafios WHERE nome_normalizado = 'desafio a'"
    ).fetchone()
    assert desafio[0] == "arquivado"
    assert desafio[1] is not None

    total = database.execute(
        "SELECT total_pontos FROM pontos_ultimate_totais_por_clan WHERE clan = 'CLÃ 1'"
    ).fetchone()
    assert total == (0,)


def test_reaparecimento_reativa_desafio_arquivado(database):
    database.execute(
        """
        INSERT INTO desafios (nome, nome_normalizado, origem, status, data)
        VALUES ('Desafio A', 'desafio a', 'google_sheets', 'arquivado', CURRENT_DATE)
        """
    )

    result = _apply(
        database,
        _payload(
            token_versions=[_token_version(change_reason="reappeared")],
            clan_deltas={"CLÃ 1": 10},
            challenge_transitions=[
                {
                    "challenge_normalized": "desafio a",
                    "challenge_display": "Desafio A",
                    "transition": "reactivate",
                }
            ],
        ),
    )

    assert result["challenge_transitions"][0]["transition"] == "reactivate"
    desafio = database.execute(
        "SELECT status, reativado_at FROM desafios WHERE nome_normalizado = 'desafio a'"
    ).fetchone()
    assert desafio[0] == "ativo"
    assert desafio[1] is not None
    assert (
        database.execute("SELECT COUNT(*) FROM desafios").fetchone()[0] == 1
    ), "reativação nunca duplica o desafio"


# ---------------------------------------------------------------------------
# Guardas contábeis e atomicidade
# ---------------------------------------------------------------------------


def test_total_negativo_aborta_e_preserva_estado_anterior(database):
    _apply(
        database,
        _payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),
    )
    runs_before = database.execute(
        "SELECT COUNT(*) FROM desafio_sync_runs"
    ).fetchone()[0]

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="desafio_reconciliation_negative_clan_total",
    ):
        _apply(
            database,
            _payload(
                token_versions=[
                    _token_version(
                        token="TOK-2",
                        content_hash="hash-tok-2",
                        current_state=_current_state(
                            raw_cells=RAW_CELLS[:8] + ["TOK-2"]
                        ),
                        point_delta=-50,
                        clan_deltas={"CLÃ 1": -50},
                    )
                ],
                clan_deltas={"CLÃ 1": -50},
                snapshot_hash="hash-negativo",
            ),
        )

    # Nada da transação abortada permanece: nem run, nem token, nem versão.
    assert (
        database.execute("SELECT COUNT(*) FROM desafio_sync_runs").fetchone()[0]
        == runs_before
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_submissions_current WHERE token = 'TOK-2'"
        ).fetchone()[0]
        == 0
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_submission_versions"
        ).fetchone()[0]
        == 1
    )
    assert database.execute(
        "SELECT total_pontos FROM pontos_ultimate_totais_por_clan WHERE clan = 'CLÃ 1'"
    ).fetchone() == (10,)


def test_total_negativo_nunca_e_truncado_para_zero(database):
    with pytest.raises(psycopg.errors.RaiseException):
        _apply(database, _payload(clan_deltas={"CLÃ 1": -1}))
    assert (
        database.execute(
            "SELECT COUNT(*) FROM pontos_ultimate_totais_por_clan"
        ).fetchone()[0]
        == 0
    )


def test_falha_no_meio_da_operacao_faz_rollback_integral(database):
    runs_before = database.execute(
        "SELECT COUNT(*) FROM desafio_sync_runs"
    ).fetchone()[0]

    # Segundo token com raw_cells inválido (menos de 9 colunas) viola a CHECK
    # constraint depois que o primeiro token já foi gravado na mesma transação.
    with pytest.raises(psycopg.errors.CheckViolation):
        _apply(
            database,
            _payload(
                token_versions=[
                    _token_version(),
                    _token_version(
                        token="TOK-BAD",
                        content_hash="hash-bad",
                        current_state=_current_state(raw_cells=["so", "duas"]),
                    ),
                ],
                clan_deltas={"CLÃ 1": 20},
            ),
        )

    assert (
        database.execute("SELECT COUNT(*) FROM desafio_sync_runs").fetchone()[0]
        == runs_before
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_submissions_current"
        ).fetchone()[0]
        == 0
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_submission_versions"
        ).fetchone()[0]
        == 0
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM pontos_ultimate_totais_por_clan"
        ).fetchone()[0]
        == 0
    )


def test_plano_obsoleto_e_rejeitado(database):
    _apply(
        database,
        _payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),
    )

    # Replay do mesmo plano: o token já não está no estado que o plano esperava.
    with pytest.raises(
        psycopg.errors.RaiseException, match="desafio_reconciliation_stale_plan"
    ):
        _apply(
            database,
            _payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),
        )

    assert database.execute(
        "SELECT total_pontos FROM pontos_ultimate_totais_por_clan WHERE clan = 'CLÃ 1'"
    ).fetchone() == (10,)


def test_versoes_gravadas_pelo_rpc_continuam_imutaveis(database):
    _apply(
        database,
        _payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),
    )
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute("UPDATE desafio_submission_versions SET point_delta = 0")
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute("DELETE FROM desafio_submission_versions")


# ---------------------------------------------------------------------------
# Concorrência
# ---------------------------------------------------------------------------


def test_segunda_tentativa_concorrente_recebe_already_running(database, schema_name):
    """A segunda chamada não pode bloquear nem aplicar: responde already_running."""
    holder = psycopg.connect(TEST_POSTGRES_DSN, autocommit=False)
    try:
        holder.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
        )
        # Transação aberta segurando o advisory lock da sincronização.
        first = holder.execute(
            "SELECT apply_desafio_reconciliation(%s::JSONB)",
            (_payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),),
        ).fetchone()[0]
        assert first["status"] == "applied"

        second = _apply(
            database,
            _payload(
                token_versions=[
                    _token_version(
                        token="TOK-2",
                        content_hash="hash-tok-2",
                        current_state=_current_state(
                            raw_cells=RAW_CELLS[:8] + ["TOK-2"]
                        ),
                    )
                ],
                clan_deltas={"CLÃ 1": 10},
                snapshot_hash="hash-concorrente",
            ),
        )
        assert second["status"] == "already_running"
        assert second["run_id"] is None
        assert second["tokens_versioned"] == 0

        holder.commit()
    finally:
        holder.close()

    # Somente a primeira execução aplicou alguma coisa.
    assert database.execute(
        "SELECT COUNT(*) FROM desafio_submissions_current"
    ).fetchone() == (1,)
    assert database.execute(
        "SELECT total_pontos FROM pontos_ultimate_totais_por_clan WHERE clan = 'CLÃ 1'"
    ).fetchone() == (10,)


def test_lock_e_liberado_ao_fim_da_transacao(database):
    first = _apply(
        database,
        _payload(token_versions=[_token_version()], clan_deltas={"CLÃ 1": 10}),
    )
    second = _apply(database, _payload(snapshot_hash="hash-seguinte"))
    assert first["status"] == "applied"
    assert second["status"] == "applied"
