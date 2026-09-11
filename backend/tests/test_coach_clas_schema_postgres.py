"""Testes de integração da migration 011 em PostgreSQL real.

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
    / "011_add_coach_clas.sql"
).read_text(encoding="utf-8")


@pytest.fixture
def database():
    connection = psycopg.connect(TEST_POSTGRES_DSN, autocommit=True)
    schema_name = f"coach_clas_test_{uuid.uuid4().hex}"
    connection.execute(
        sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
    )
    connection.execute(
        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
    )
    try:
        connection.execute(MIGRATION)
        yield connection
    finally:
        connection.execute("RESET search_path")
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
        )
        connection.close()


def test_migration_creates_table_with_correct_schema(database):
    """Valida que a migration cria a tabela com as colunas e constraints esperadas."""
    result = database.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'pontos_ultimate_coach_clas'
        ORDER BY ordinal_position
        """
    ).fetchall()

    expected_columns = [
        ("id", "integer", "NO"),
        ("coach_canonico", "character varying", "NO"),
        ("clan", "character varying", "NO"),
        ("categoria", "character varying", "NO"),
        ("created_at", "timestamp with time zone", "YES"),
        ("updated_at", "timestamp with time zone", "YES"),
    ]

    assert result == expected_columns


def test_unique_constraint_on_coach_canonico(database):
    """Valida que inserir dois registros com o mesmo coach_canonico falha."""
    database.execute(
        """
        INSERT INTO pontos_ultimate_coach_clas (coach_canonico, clan, categoria)
        VALUES ('Coach A', 'Clã 1', 'Coach')
        """
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        database.execute(
            """
            INSERT INTO pontos_ultimate_coach_clas (coach_canonico, clan, categoria)
            VALUES ('Coach A', 'Clã 2', 'Coach Action')
            """
        )


def test_check_constraint_on_categoria(database):
    """Valida que inserir uma categoria fora da lista falha."""
    with pytest.raises(psycopg.errors.CheckViolation):
        database.execute(
            """
            INSERT INTO pontos_ultimate_coach_clas (coach_canonico, clan, categoria)
            VALUES ('Coach A', 'Clã 1', 'Invalid Category')
            """
        )


def test_valid_categoria_values_accepted(database):
    """Valida que todas as 6 categorias válidas são aceitas."""
    valid_categories = [
        "Coach",
        "Coach Action",
        "Coach Pro",
        "Coach Hero",
        "Sem Categoria",
        "Novos ULTIMATES",
    ]

    for i, categoria in enumerate(valid_categories):
        database.execute(
            """
            INSERT INTO pontos_ultimate_coach_clas (coach_canonico, clan, categoria)
            VALUES (%s, 'Clã 1', %s)
            """,
            (f"Coach {i}", categoria),
        )

    result = database.execute(
        "SELECT COUNT(*) FROM pontos_ultimate_coach_clas"
    ).fetchone()[0]

    assert result == 6


def test_index_on_clan_exists(database):
    """Valida que o índice em clan existe."""
    result = database.execute(
        """
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'pontos_ultimate_coach_clas'
        AND indexname = 'idx_coach_clas_clan'
        """
    ).fetchone()

    assert result is not None
