"""Testes de integração da migração 010 (fase 1 do corte) em PostgreSQL real.

Defina TEST_POSTGRES_DSN para habilitar esta suíte. Cada teste usa um schema
isolado e o remove ao final, sem tocar nas tabelas da aplicação.

Cobre o que só pode ser provado contra um banco real: advisory lock
compartilhado com a sincronização, subtração explícita da contribuição legada
(nunca truncada para zero), aborto integral em caso de total negativo, backup
verificável e imutável, e restauração administrativa a partir desse backup.
"""

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
MIGRATION_010 = (
    MIGRATIONS_DIR / "010_migrate_legacy_desafio_contribution.sql"
).read_text(encoding="utf-8")

# As funções fixam `SET search_path = public, pg_temp` (hardening). Estes testes
# vivem em um schema isolado, então o `search_path` embutido é reescrito para
# apontar para ele — falha alto se a cláusula sumir da migração.
PINNED_SEARCH_PATH = "SET search_path = public, pg_temp"


def _for_schema(migration: str, schema_name: str) -> str:
    assert PINNED_SEARCH_PATH in migration, "a migração precisa fixar search_path"
    return migration.replace(
        PINNED_SEARCH_PATH, f"SET search_path = {schema_name}, pg_temp"
    )


# Estado legado real das tabelas tocadas pela migração.
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

CREATE TABLE desafio_registros (
  id           SERIAL PRIMARY KEY,
  desafio_id   INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  clan         VARCHAR NOT NULL,
  valores      JSONB NOT NULL DEFAULT '{}',
  total_pontos INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE (desafio_id, clan)
);

CREATE TABLE desafio_registros_coach (
  id           SERIAL PRIMARY KEY,
  desafio_id   INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  coach        VARCHAR NOT NULL,
  valores      JSONB NOT NULL DEFAULT '{}',
  total_pontos INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE (desafio_id, coach)
);

CREATE TABLE desafio_importacao_linhas (
  id                 SERIAL PRIMARY KEY,
  desafio_id         INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  clan               VARCHAR NOT NULL,
  nome_participante  VARCHAR NOT NULL,
  validado           BOOLEAN NOT NULL,
  contabilizado      BOOLEAN NOT NULL DEFAULT FALSE,
  submitted_at       TIMESTAMP,
  token_original     VARCHAR NOT NULL,
  coach              VARCHAR,
  created_at         TIMESTAMP DEFAULT NOW(),
  UNIQUE (desafio_id, token_original)
);

CREATE TABLE pontos_ultimate_totais_por_clan (
  clan              VARCHAR PRIMARY KEY,
  total_pontos      INTEGER NOT NULL DEFAULT 0,
  pessoas_em_espera INTEGER NOT NULL DEFAULT 0,
  total_pagante     INTEGER NOT NULL DEFAULT 0,
  total_pro_bono    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE pontos_ultimate_totais_por_coach (
  id                SERIAL PRIMARY KEY,
  coach             VARCHAR NOT NULL UNIQUE,
  total_pontos      INTEGER NOT NULL DEFAULT 0,
  pessoas_em_espera INTEGER NOT NULL DEFAULT 0,
  total_pagante     INTEGER NOT NULL DEFAULT 0,
  total_pro_bono    INTEGER NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);
"""


def _make_schema(connection, schema_name: str) -> None:
    connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
    connection.execute(
        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
    )
    connection.execute(LEGACY_SCHEMA)
    connection.execute(MIGRATION_008)
    connection.execute(_for_schema(MIGRATION_009, schema_name))
    connection.execute(_for_schema(MIGRATION_010, schema_name))


def _seed_legacy(connection) -> None:
    """Dados legados típicos: manual, CSV, um desafio já desligado e um do Sheets."""
    connection.execute(
        """
        INSERT INTO desafios (id, nome, contabilizar_pontos, data, origem, status)
        VALUES
          (1, 'Desafio Manual', TRUE,  CURRENT_DATE, 'manual', 'ativo'),
          (2, 'Desafio CSV',    TRUE,  CURRENT_DATE, 'csv_import', 'ativo'),
          (3, 'Desafio Off',    FALSE, CURRENT_DATE, 'manual', 'ativo');
        INSERT INTO desafios (id, nome, contabilizar_pontos, data, origem, status,
                              nome_normalizado)
        VALUES (4, 'Desafio Sheets', TRUE, CURRENT_DATE, 'google_sheets', 'ativo',
                'desafio sheets');
        SELECT SETVAL(PG_GET_SERIAL_SEQUENCE('desafios', 'id'), 4);

        INSERT INTO desafio_registros (desafio_id, clan, total_pontos) VALUES
          (1, 'CLÃ 1', 20), (1, 'CLÃ 2', 10),
          (2, 'CLÃ 1', 10),
          (3, 'CLÃ 1', 500);

        INSERT INTO desafio_registros_coach (desafio_id, coach, total_pontos) VALUES
          (1, 'Ana', 15),
          (2, 'Ana', 5),
          (2, 'Bia', 7),
          (3, 'Ana', 900);

        INSERT INTO desafio_importacao_linhas
          (desafio_id, clan, nome_participante, validado, token_original)
        VALUES (2, 'CLÃ 1', 'Participante', TRUE, 'TOK-LEGADO');

        INSERT INTO pontos_ultimate_totais_por_clan (clan, total_pontos) VALUES
          ('CLÃ 1', 100), ('CLÃ 2', 50), ('CLÃ 3', 70);

        INSERT INTO pontos_ultimate_totais_por_coach (coach, total_pontos) VALUES
          ('Ana', 60), ('Bia', 30), ('Caio', 40);
        """
    )


def _report(connection) -> dict:
    return connection.execute("SELECT desafio_legacy_migration_report()").fetchone()[0]


def _migrate(connection) -> dict:
    return connection.execute(
        "SELECT migrate_desafio_legacy_contribution()"
    ).fetchone()[0]


def _restore(connection, migracao_id: int, force: bool = False) -> dict:
    return connection.execute(
        "SELECT restore_desafio_legacy_migracao(%s, %s)", (migracao_id, force)
    ).fetchone()[0]


def _clan_totals(connection) -> dict:
    return dict(
        connection.execute(
            "SELECT clan, total_pontos FROM pontos_ultimate_totais_por_clan"
        ).fetchall()
    )


def _coach_totals(connection) -> dict:
    return dict(
        connection.execute(
            "SELECT coach, total_pontos FROM pontos_ultimate_totais_por_coach"
        ).fetchall()
    )


@pytest.fixture
def schema_name():
    return f"desafio_migracao_test_{uuid.uuid4().hex}"


@pytest.fixture
def database(schema_name):
    connection = psycopg.connect(TEST_POSTGRES_DSN, autocommit=True)
    _make_schema(connection, schema_name)
    _seed_legacy(connection)
    try:
        yield connection
    finally:
        connection.execute("RESET search_path")
        connection.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
        )
        connection.close()


# ---------------------------------------------------------------------------
# Relatório (dry-run)
# ---------------------------------------------------------------------------


def test_relatorio_nao_escreve_e_calcula_antes_e_depois(database):
    antes_clan = _clan_totals(database)
    antes_coach = _coach_totals(database)

    report = _report(database)

    assert report["ja_migrado"] is False
    assert report["migracao_id"] is None

    clans = {item["clan"]: item for item in report["clans"]}
    # CLÃ 1: 20 (manual) + 10 (csv) = 30. O desafio 3 não contabiliza.
    assert clans["CLÃ 1"]["contribuicao_legada"] == 30
    assert clans["CLÃ 1"]["total_antes"] == 100
    assert clans["CLÃ 1"]["total_depois"] == 70
    assert clans["CLÃ 2"]["contribuicao_legada"] == 10
    assert clans["CLÃ 3"]["contribuicao_legada"] == 0

    coaches = {item["coach"]: item for item in report["coaches"]}
    assert coaches["Ana"]["contribuicao_legada"] == 20  # 15 + 5, sem os 900
    assert coaches["Ana"]["total_depois"] == 40
    assert coaches["Bia"]["contribuicao_legada"] == 7
    assert "Caio" not in coaches  # nada legado, nada a mostrar

    assert report["negativos"] == []
    assert report["desafios_legados"] == 3
    assert report["desafios_legados_contabilizando"] == 2
    assert report["registros_clan"] == 4
    assert report["registros_coach"] == 4
    assert report["linhas_importacao"] == 1

    # Somente leitura.
    assert _clan_totals(database) == antes_clan
    assert _coach_totals(database) == antes_coach
    assert (
        database.execute("SELECT COUNT(*) FROM desafio_legacy_migracoes").fetchone()[0]
        == 0
    )


def test_relatorio_marca_totais_que_ficariam_negativos(database):
    database.execute(
        "UPDATE pontos_ultimate_totais_por_clan SET total_pontos = 5 WHERE clan = 'CLÃ 1'"
    )

    report = _report(database)
    negativos = {item["chave"]: item for item in report["negativos"]}

    assert negativos["CLÃ 1"]["escopo"] == "clan"
    assert negativos["CLÃ 1"]["total_depois"] == -25


# ---------------------------------------------------------------------------
# Aplicação
# ---------------------------------------------------------------------------


def test_migracao_subtrai_a_contribuicao_legada_de_clas_e_coaches(database):
    result = _migrate(database)

    assert result["status"] == "applied"
    assert _clan_totals(database) == {"CLÃ 1": 70, "CLÃ 2": 40, "CLÃ 3": 70}
    assert _coach_totals(database) == {"Ana": 40, "Bia": 23, "Caio": 40}
    assert result["clan_removido"] == {"CLÃ 1": 30, "CLÃ 2": 10}
    assert result["coach_removido"] == {"Ana": 20, "Bia": 7}


def test_migracao_arquiva_estruturas_legadas_sem_apagar_nada(database):
    _migrate(database)

    legados = database.execute(
        "SELECT id, status, contabilizar_pontos, arquivado_at FROM desafios"
        " WHERE origem <> 'google_sheets' ORDER BY id"
    ).fetchall()
    assert [(row[1], row[2]) for row in legados] == [
        ("arquivado", False),
        ("arquivado", False),
        ("arquivado", False),
    ]
    assert all(row[3] is not None for row in legados)

    # O desafio da Google Sheet não é tocado.
    sheets = database.execute(
        "SELECT status, contabilizar_pontos FROM desafios WHERE origem = 'google_sheets'"
    ).fetchone()
    assert sheets == ("ativo", True)

    # Nenhuma linha filha foi apagada.
    assert database.execute("SELECT COUNT(*) FROM desafio_registros").fetchone() == (4,)
    assert database.execute(
        "SELECT COUNT(*) FROM desafio_registros_coach"
    ).fetchone() == (4,)
    assert database.execute(
        "SELECT COUNT(*) FROM desafio_importacao_linhas"
    ).fetchone() == (1,)


def test_backup_verificavel_cobre_todas_as_tabelas_afetadas(database):
    result = _migrate(database)

    por_tabela = dict(
        database.execute(
            "SELECT tabela, COUNT(*) FROM desafio_legacy_migracao_backup"
            " WHERE migracao_id = %s GROUP BY tabela",
            (result["migracao_id"],),
        ).fetchall()
    )
    assert por_tabela == {
        "desafios": 3,
        "desafio_registros": 4,
        "desafio_registros_coach": 4,
        "desafio_importacao_linhas": 1,
        "pontos_ultimate_totais_por_clan": 3,
        "pontos_ultimate_totais_por_coach": 3,
    }
    assert result["backup_rows"] == sum(por_tabela.values())

    # O checksum é recomputável a partir do próprio backup: é o que o torna
    # verificável muito depois da migração.
    recomputado = database.execute(
        """
        SELECT ENCODE(SHA256(CONVERT_TO(
                 STRING_AGG(tabela || '|' || chave || '|' || conteudo::TEXT,
                            E'\\n' ORDER BY tabela, chave), 'UTF8')), 'hex')
          FROM desafio_legacy_migracao_backup WHERE migracao_id = %s
        """,
        (result["migracao_id"],),
    ).fetchone()[0]
    assert recomputado == result["backup_checksum"]

    # O backup guarda o total ANTES da subtração.
    clan1 = database.execute(
        "SELECT conteudo FROM desafio_legacy_migracao_backup"
        " WHERE migracao_id = %s AND tabela = 'pontos_ultimate_totais_por_clan'"
        "   AND chave = 'CLÃ 1'",
        (result["migracao_id"],),
    ).fetchone()[0]
    assert clan1["total_pontos"] == 100


def test_backup_e_imutavel(database):
    _migrate(database)
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute("UPDATE desafio_legacy_migracao_backup SET chave = 'x'")
    with pytest.raises(psycopg.errors.RaiseException, match="immutable"):
        database.execute("DELETE FROM desafio_legacy_migracao_backup")


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def test_total_negativo_aborta_a_migracao_inteira(database):
    database.execute(
        "UPDATE pontos_ultimate_totais_por_clan SET total_pontos = 5 WHERE clan = 'CLÃ 1'"
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="desafio_legacy_migration_negative_clan_total",
    ):
        _migrate(database)

    # Nada persiste: nem migração, nem backup, nem total alterado, nem
    # arquivamento. E o total nunca é truncado para zero.
    assert _clan_totals(database) == {"CLÃ 1": 5, "CLÃ 2": 50, "CLÃ 3": 70}
    assert _coach_totals(database) == {"Ana": 60, "Bia": 30, "Caio": 40}
    assert (
        database.execute("SELECT COUNT(*) FROM desafio_legacy_migracoes").fetchone()[0]
        == 0
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_legacy_migracao_backup"
        ).fetchone()[0]
        == 0
    )
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafios WHERE status = 'arquivado'"
        ).fetchone()[0]
        == 0
    )


def test_total_de_coach_negativo_tambem_aborta_tudo(database):
    database.execute(
        "UPDATE pontos_ultimate_totais_por_coach SET total_pontos = 1 WHERE coach = 'Ana'"
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="desafio_legacy_migration_negative_coach_total",
    ):
        _migrate(database)

    # Os totais de clã já processados no mesmo laço também voltam atrás.
    assert _clan_totals(database) == {"CLÃ 1": 100, "CLÃ 2": 50, "CLÃ 3": 70}


def test_segunda_migracao_e_recusada(database):
    _migrate(database)

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="desafio_legacy_migration_already_applied",
    ):
        _migrate(database)

    # A contribuição legada não foi subtraída duas vezes.
    assert _clan_totals(database)["CLÃ 1"] == 70


def test_relatorio_sinaliza_migracao_ja_aplicada(database):
    result = _migrate(database)
    report = _report(database)

    assert report["ja_migrado"] is True
    assert report["migracao_id"] == result["migracao_id"]


def test_migracao_concorrente_com_sincronizacao_e_recusada(database, schema_name):
    """A fase 1 e uma sincronização real jamais podem se intercalar."""
    holder = psycopg.connect(TEST_POSTGRES_DSN, autocommit=False)
    try:
        holder.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
        )
        # Transação aberta segurando o mesmo advisory lock da sincronização.
        holder.execute("SELECT pg_advisory_xact_lock(7345901220834561)")

        with pytest.raises(
            psycopg.errors.RaiseException, match="desafio_legacy_migration_locked"
        ):
            _migrate(database)
    finally:
        holder.rollback()
        holder.close()

    assert _clan_totals(database)["CLÃ 1"] == 100


# ---------------------------------------------------------------------------
# Restauração (rollback administrativo)
# ---------------------------------------------------------------------------


def test_restauracao_devolve_totais_e_desafios_ao_estado_anterior(database):
    antes_clan = _clan_totals(database)
    antes_coach = _coach_totals(database)
    result = _migrate(database)

    restored = _restore(database, result["migracao_id"])

    assert restored["status"] == "rolled_back"
    assert _clan_totals(database) == antes_clan
    assert _coach_totals(database) == antes_coach
    assert database.execute(
        "SELECT status, contabilizar_pontos FROM desafios WHERE id = 1"
    ).fetchone() == ("ativo", True)
    assert database.execute(
        "SELECT status, contabilizar_pontos FROM desafios WHERE id = 3"
    ).fetchone() == ("ativo", False)
    assert database.execute(
        "SELECT status FROM desafio_legacy_migracoes WHERE id = %s",
        (result["migracao_id"],),
    ).fetchone() == ("rolled_back",)

    # O backup sobrevive à restauração (retenção indeterminada).
    assert (
        database.execute(
            "SELECT COUNT(*) FROM desafio_legacy_migracao_backup WHERE migracao_id = %s",
            (result["migracao_id"],),
        ).fetchone()[0]
        == result["backup_rows"]
    )


def test_restauracao_liberada_apos_rollback_permite_nova_migracao(database):
    result = _migrate(database)
    _restore(database, result["migracao_id"])

    segunda = _migrate(database)
    assert segunda["status"] == "applied"
    assert _clan_totals(database)["CLÃ 1"] == 70


def test_restauracao_e_bloqueada_quando_ja_houve_sincronizacao(database):
    """Restaurar os totais depois da fase 2 desfaria os pontos da planilha."""
    result = _migrate(database)
    database.execute(
        """
        INSERT INTO desafio_sync_runs (status, points_per_submission)
        VALUES ('succeeded', 10)
        """
    )

    with pytest.raises(
        psycopg.errors.RaiseException,
        match="desafio_legacy_migration_restore_blocked_by_sync",
    ):
        _restore(database, result["migracao_id"])

    assert _clan_totals(database)["CLÃ 1"] == 70

    # Com consentimento explícito, a restauração acontece mesmo assim.
    forced = _restore(database, result["migracao_id"], force=True)
    assert forced["sync_posterior_ignorada"] is not None
    assert _clan_totals(database)["CLÃ 1"] == 100


def test_restaurar_migracao_inexistente_falha(database):
    with pytest.raises(
        psycopg.errors.RaiseException, match="desafio_legacy_migration_not_found"
    ):
        _restore(database, 999)


def test_restaurar_duas_vezes_falha(database):
    result = _migrate(database)
    _restore(database, result["migracao_id"])

    with pytest.raises(
        psycopg.errors.RaiseException, match="desafio_legacy_migration_not_applied"
    ):
        _restore(database, result["migracao_id"])
