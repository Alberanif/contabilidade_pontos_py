"""Testes de integração da migration 008 em PostgreSQL real.

Defina TEST_POSTGRES_DSN para habilitar esta suíte. Cada teste usa um schema
isolado e o remove ao final, sem tocar nas tabelas da aplicação.
"""

import os
from pathlib import Path
import uuid

import pytest


TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
if not TEST_POSTGRES_DSN:
    pytest.skip(
        "TEST_POSTGRES_DSN não configurado para testes reais de migration",
        allow_module_level=True,
    )

psycopg = pytest.importorskip("psycopg")
from psycopg import sql


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "008_add_desafio_google_sync.sql"
).read_text(encoding="utf-8")

LEGACY_SCHEMA = """
CREATE TABLE desafios (
  id                  SERIAL PRIMARY KEY,
  nome                VARCHAR NOT NULL,
  contabilizar_pontos BOOLEAN NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMP DEFAULT NOW()
);
INSERT INTO desafios (nome) VALUES ('Desafio legado');
"""


@pytest.fixture
def database():
    connection = psycopg.connect(TEST_POSTGRES_DSN, autocommit=True)
    schema_name = f"desafio_sync_test_{uuid.uuid4().hex}"
    connection.execute(
        sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
    )
    connection.execute(
        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
    )
    try:
        connection.execute(LEGACY_SCHEMA)
        connection.execute(MIGRATION)
        yield connection
    finally:
        connection.execute("RESET search_path")
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
        )
        connection.close()


def _create_run(connection) -> int:
    return connection.execute(
        """
        INSERT INTO desafio_sync_runs (status, points_per_submission)
        VALUES ('running', 10)
        RETURNING id
        """
    ).fetchone()[0]


def _create_current_submission(connection, run_id: int, token: str = "Token-A"):
    connection.execute(
        """
        INSERT INTO desafio_submissions_current (
          token, raw_cells, status, content_hash,
          first_seen_run_id, last_seen_run_id
        ) VALUES (
          %s, '["1", "Ana", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "Token-A"]'::JSONB,
          'active_counted', 'hash-a', %s, %s
        )
        """,
        (token, run_id, run_id),
    )


def _create_version(connection, run_id: int, token: str = "Token-A"):
    connection.execute(
        """
        INSERT INTO desafio_submission_versions (
          token, sync_run_id, version_number, raw_cells,
          current_state, current_status, change_reason
        ) VALUES (
          %s, %s, 1,
          '["1", "Ana", "Sim", "", "", "Desafio A", "", "19/08/2026 10:00:00", "Token-A"]'::JSONB,
          '{}'::JSONB, 'active_counted', 'initial_snapshot'
        )
        """,
        (token, run_id),
    )


def test_migration_preserves_legacy_challenges_and_adds_lifecycle(database):
    legacy = database.execute(
        "SELECT nome, origem, status FROM desafios WHERE nome = 'Desafio legado'"
    ).fetchone()
    assert legacy == ("Desafio legado", "manual", "ativo")

    with pytest.raises(psycopg.errors.CheckViolation):
        database.execute(
            "INSERT INTO desafios (nome, origem) VALUES ('Sem chave', 'google_sheets')"
        )

    database.execute(
        """
        INSERT INTO desafios (nome, nome_normalizado, origem)
        VALUES ('Desafio Google', 'desafio google', 'google_sheets')
        """
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        database.execute(
            """
            INSERT INTO desafios (nome, nome_normalizado, origem)
            VALUES ('DESAFIO GOOGLE', 'desafio google', 'google_sheets')
            """
        )


def test_current_token_is_global_and_references_valid_runs(database):
    run_id = _create_run(database)
    _create_current_submission(database, run_id)

    with pytest.raises(psycopg.errors.UniqueViolation):
        _create_current_submission(database, run_id)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _create_current_submission(database, run_id + 9999, token="Token-B")


def test_versions_reference_run_and_reject_update_delete_and_truncate(database):
    run_id = _create_run(database)
    _create_current_submission(database, run_id)
    _create_version(database, run_id)

    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute(
            "UPDATE desafio_submission_versions SET point_delta = 10"
        )
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute("DELETE FROM desafio_submission_versions")
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute("TRUNCATE desafio_submission_versions")


def test_status_and_raw_cell_constraints_are_enforced(database):
    run_id = _create_run(database)

    with pytest.raises(psycopg.errors.CheckViolation):
        database.execute(
            """
            INSERT INTO desafio_submissions_current (
              token, raw_cells, status, content_hash,
              first_seen_run_id, last_seen_run_id
            ) VALUES ('T-invalid-status', '["1", "2", "3", "4", "5", "6", "7", "8", "9"]',
                      'unknown', 'hash', %s, %s)
            """,
            (run_id, run_id),
        )

    with pytest.raises(psycopg.errors.CheckViolation):
        database.execute(
            """
            INSERT INTO desafio_submissions_current (
              token, raw_cells, status, content_hash,
              first_seen_run_id, last_seen_run_id
            ) VALUES ('T-short', '["1", "2"]', 'invalid', 'hash', %s, %s)
            """,
            (run_id, run_id),
        )
