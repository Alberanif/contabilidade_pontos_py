import os
import re
import sys
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supabase_client


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "008_add_desafio_google_sync.sql"
)


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8")).lower()


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self.data = data
        self.operations = []

    def select(self, columns):
        self.operations.append(("select", columns))
        return self

    def eq(self, column, value):
        self.operations.append(("eq", column, value))
        return self

    def order(self, column, desc=False):
        self.operations.append(("order", column, desc))
        return self

    def range(self, start, end):
        self.operations.append(("range", start, end))
        return self

    def execute(self):
        self.operations.append(("execute",))
        return _Response(self.data)


class _Client:
    def __init__(self, responses):
        self.responses = responses
        self.queries = []

    def table(self, table_name):
        query = _Query(self.responses[table_name])
        self.queries.append((table_name, query))
        return query


def test_migration_creates_global_current_state_and_immutable_versions():
    """Catches loss of global token identity or version/run traceability."""
    sql = _normalized_sql()

    assert "create table if not exists desafio_sync_runs" in sql
    assert "create table if not exists desafio_submissions_current" in sql
    assert "token text primary key" in sql
    assert "raw_cells jsonb not null" in sql
    assert "first_seen_run_id bigint not null references desafio_sync_runs(id)" in sql
    assert "last_seen_run_id bigint not null references desafio_sync_runs(id)" in sql

    assert "create table if not exists desafio_submission_versions" in sql
    assert "sync_run_id bigint not null references desafio_sync_runs(id)" in sql
    assert "token text not null references desafio_submissions_current(token)" in sql
    assert "unique (token, version_number)" in sql
    assert "desafio_submission_versions_status_check check" in sql
    assert "prevent_desafio_submission_version_mutation" in sql


def test_migration_preserves_raw_a_to_i_and_allows_only_domain_states():
    """Catches audit data loss or accepting an undefined accounting state."""
    sql = _normalized_sql()

    for column in (
        "raw_clan_legacy",
        "raw_name",
        "raw_validation",
        "raw_link",
        "raw_observation",
        "raw_challenge",
        "raw_clan_current",
        "raw_submitted_at",
        "raw_token",
    ):
        assert f"{column} text" in sql

    for status in (
        "active_counted",
        "active_not_counted",
        "invalid",
        "conflicted",
        "inactive_missing",
        "blocked_by_guardrail",
    ):
        assert f"'{status}'" in sql


def test_migration_adds_challenge_lifecycle_without_deleting_legacy_data():
    """Catches destructive replacement of desafios or missing archive support."""
    sql = _normalized_sql()

    assert "drop table" not in sql
    assert "truncate table" not in sql
    assert "alter table desafios add column if not exists nome_normalizado text" in sql
    assert "alter table desafios add column if not exists status text" in sql
    assert "alter table desafios add column if not exists arquivado_at timestamptz" in sql
    assert "alter table desafios add column if not exists reativado_at timestamptz" in sql
    assert "where origem = 'google_sheets'" in sql
    assert re.search(
        r"check \(\s*origem <> 'google_sheets'\s+or "
        r"nullif\(btrim\(nome_normalizado\), ''\) is not null\s*\)",
        sql,
    )
    assert sql.count("conrelid = 'desafios'::regclass") >= 3


def test_migration_indexes_expected_read_paths():
    """Catches a migration that makes token audit and dashboard filters scan tables."""
    sql = _normalized_sql()

    for fragment in (
        "desafio_submissions_current (desafio_id)",
        "desafio_submissions_current (clan)",
        "desafio_submissions_current (status)",
        "desafio_submissions_current (submitted_at)",
        "desafio_submission_versions (sync_run_id)",
        "desafio_submission_versions (token, version_number desc)",
        "desafio_sync_runs (status)",
        "desafio_sync_runs (snapshot_hash)",
        "desafio_sync_runs (started_at desc)",
    ):
        assert fragment in sql


def test_migration_blocks_all_mutations_of_submission_versions():
    """Catches TRUNCATE bypassing row-level UPDATE/DELETE immutability guards."""
    sql = _normalized_sql()

    assert "before update or delete on desafio_submission_versions" in sql
    assert "before truncate on desafio_submission_versions" in sql
    assert "for each statement" in sql


def test_list_current_submissions_applies_filters_and_pagination():
    """Catches filters being ignored or applied to the wrong current-state query."""
    rows = [{"token": "Token-A", "clan": "CLÃ 2", "status": "active_counted"}]
    client = _Client({"desafio_submissions_current": rows})

    with patch.object(supabase_client, "_get_client", return_value=client):
        result = supabase_client.list_desafio_submissions_current(
            desafio_id=7,
            clan="CLÃ 2",
            status="active_counted",
            limit=25,
            offset=50,
        )

    assert result == rows
    table, query = client.queries[0]
    assert table == "desafio_submissions_current"
    assert query.operations == [
        ("select", "*"),
        ("eq", "desafio_id", 7),
        ("eq", "clan", "CLÃ 2"),
        ("eq", "status", "active_counted"),
        ("order", "submitted_at", True),
        ("range", 50, 74),
        ("execute",),
    ]


def test_get_current_submission_uses_case_sensitive_token():
    """Catches token normalization that would merge distinct case-sensitive IDs."""
    rows = [{"token": "Token-A"}]
    client = _Client({"desafio_submissions_current": rows})

    with patch.object(supabase_client, "_get_client", return_value=client):
        result = supabase_client.get_desafio_submission_current("Token-A")

    assert result == rows[0]
    _, query = client.queries[0]
    assert ("eq", "token", "Token-A") in query.operations


def test_list_versions_returns_immutable_history_in_version_order():
    """Catches history being read from current state or returned out of order."""
    rows = [{"token": "T1", "version_number": 2}]
    client = _Client({"desafio_submission_versions": rows})

    with patch.object(supabase_client, "_get_client", return_value=client):
        result = supabase_client.list_desafio_submission_versions("T1")

    assert result == rows
    table, query = client.queries[0]
    assert table == "desafio_submission_versions"
    assert query.operations == [
        ("select", "*"),
        ("eq", "token", "T1"),
        ("order", "version_number", False),
        ("execute",),
    ]


def test_list_sync_runs_returns_newest_first():
    """Catches operational history being returned in an unusable order."""
    rows = [{"id": 9, "status": "succeeded"}]
    client = _Client({"desafio_sync_runs": rows})

    with patch.object(supabase_client, "_get_client", return_value=client):
        result = supabase_client.list_desafio_sync_runs(limit=10, offset=20)

    assert result == rows
    table, query = client.queries[0]
    assert table == "desafio_sync_runs"
    assert query.operations == [
        ("select", "*"),
        ("order", "started_at", True),
        ("range", 20, 29),
        ("execute",),
    ]
