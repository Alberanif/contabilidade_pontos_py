import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
import google_sheets_client
from desafio_sheet_parser import (
    build_parsed_rows,
    normalize_challenge,
    normalize_clan,
    parse_desafio_row,
)


def _cells(
    clan_legacy="1",
    name="Ana Maria",
    validation="Sim",
    link="https://example.test/evidence",
    observation="Observação preservada",
    challenge="  Desafio   Pontual A  ",
    clan_current="",
    submitted_at="19/08/2026 14:35:20",
    token=" Token-X ",
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


def test_parse_uses_fixed_a_to_i_positions_and_preserves_raw_values():
    """Catches accidental header-based mapping or loss of link/observation audit data."""
    cells = _cells()

    parsed = parse_desafio_row(17, cells)

    assert parsed.row_number == 17
    assert parsed.raw_cells == tuple(cells)
    assert parsed.raw_clan_legacy == "1"
    assert parsed.raw_name == "Ana Maria"
    assert parsed.raw_validation == "Sim"
    assert parsed.raw_link == "https://example.test/evidence"
    assert parsed.raw_observation == "Observação preservada"
    assert parsed.raw_challenge == "  Desafio   Pontual A  "
    assert parsed.raw_clan_current == ""
    assert parsed.raw_submitted_at == "19/08/2026 14:35:20"
    assert parsed.raw_token == " Token-X "
    assert parsed.token == "Token-X"
    assert parsed.clan == "CLÃ 1"
    assert parsed.challenge_display == "Desafio Pontual A"
    assert parsed.challenge_normalized == "desafio pontual a"
    assert parsed.status == "active_counted"
    assert parsed.structurally_valid is True
    assert parsed.eligible is True
    assert parsed.reasons == ()


def test_build_rows_always_skips_sheet_header_without_using_its_labels():
    """Catches duplicate clan headers changing the positional mapping."""
    arbitrary_header = ["x"] * 9
    data = _cells(token="T1")

    parsed = build_parsed_rows([arbitrary_header, data])

    assert len(parsed) == 1
    assert parsed[0].row_number == 2
    assert parsed[0].token == "T1"


def test_build_rows_preserves_first_valid_challenge_spelling_for_snapshot():
    """Catches equivalent challenges exposing whichever later casing was observed."""
    first = _cells(challenge="Desafio Pontual A", token="T1")
    later = _cells(challenge="  DESAFIO   PONTUAL A ", token="T2")

    parsed = build_parsed_rows([["header"] * 9, first, later])

    assert [row.challenge_normalized for row in parsed] == [
        "desafio pontual a",
        "desafio pontual a",
    ]
    assert [row.challenge_display for row in parsed] == [
        "Desafio Pontual A",
        "Desafio Pontual A",
    ]


def test_short_row_is_padded_for_audit_and_marked_invalid():
    """Catches short Google API rows throwing or being treated as complete."""
    parsed = parse_desafio_row(8, ["1", "Ana"])

    assert len(parsed.raw_cells) == 9
    assert parsed.raw_cells[:2] == ("1", "Ana")
    assert parsed.source_cell_count == 2
    assert parsed.status == "invalid"
    assert parsed.structurally_valid is False
    assert "missing_columns" in parsed.reasons


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", "CLÃ 1"),
        ("01", "CLÃ 1"),
        ("Clã 1", "CLÃ 1"),
        ("CLA 1", "CLÃ 1"),
        ("CLÃ 1", "CLÃ 1"),
        ("  clã   8 ", "CLÃ 8"),
        ("0", None),
        ("9", None),
        ("CLÃ 2 extra", None),
        ("", None),
    ],
)
def test_normalize_clan_accepts_only_unambiguous_clans_one_to_eight(raw, expected):
    """Catches accepting out-of-range or ambiguous clan labels."""
    assert normalize_clan(raw) == expected


def test_matching_a_and_g_values_use_one_normalized_clan():
    """Catches equivalent historical/current clan spellings being flagged as conflict."""
    parsed = parse_desafio_row(3, _cells(clan_legacy="01", clan_current="Clã 1"))

    assert parsed.clan == "CLÃ 1"
    assert parsed.status == "active_counted"
    assert "conflicting_clans" not in parsed.reasons


def test_different_a_and_g_values_are_explicit_conflict():
    """Catches an arbitrary clan being selected when both source columns disagree."""
    parsed = parse_desafio_row(3, _cells(clan_legacy="1", clan_current="2"))

    assert parsed.clan is None
    assert parsed.status == "conflicted"
    assert parsed.eligible is False
    assert "conflicting_clans" in parsed.reasons


@pytest.mark.parametrize("validation", ["Não", "nao", "", "Talvez"])
def test_only_sim_counts_but_other_answers_remain_structurally_auditable(validation):
    """Catches a non-Sim answer scoring or being discarded as malformed."""
    parsed = parse_desafio_row(4, _cells(validation=validation))

    assert parsed.status == "active_not_counted"
    assert parsed.structurally_valid is True
    assert parsed.eligible is False


@pytest.mark.parametrize("validation", ["Sim", " sim ", "SIM", "sIm"])
def test_sim_is_case_and_whitespace_insensitive(validation):
    """Catches official Sim submissions losing points due to presentation differences."""
    assert parse_desafio_row(4, _cells(validation=validation)).eligible is True


def test_token_trims_edges_without_changing_case_or_internal_characters():
    """Catches token normalization merging globally distinct opaque IDs."""
    upper = parse_desafio_row(2, _cells(token="  Ab C-1  "))
    lower = parse_desafio_row(3, _cells(token="ab C-1"))

    assert upper.token == "Ab C-1"
    assert lower.token == "ab C-1"
    assert upper.token != lower.token


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("name", "   ", "missing_name"),
        ("challenge", "", "missing_challenge"),
        ("submitted_at", "31/02/2026 10:00:00", "invalid_submitted_at"),
        ("token", " ", "missing_token"),
        ("clan_legacy", "9", "invalid_clan_legacy"),
    ],
)
def test_missing_or_invalid_required_data_invalidates_row(field, value, reason):
    """Catches an incomplete token becoming an active contribution."""
    parsed = parse_desafio_row(9, _cells(**{field: value}))

    assert parsed.status == "invalid"
    assert parsed.eligible is False
    assert reason in parsed.reasons


def test_submitted_at_is_timezone_aware_in_sao_paulo():
    """Catches naive or UTC-assumed dates shifting historical accounting periods."""
    parsed = parse_desafio_row(6, _cells(submitted_at="19/08/2026 23:15:00"))

    assert parsed.submitted_at == datetime(
        2026, 8, 19, 23, 15, 0, tzinfo=ZoneInfo("America/Sao_Paulo")
    )
    assert parsed.submitted_at.utcoffset().total_seconds() == -3 * 60 * 60


def test_challenge_normalization_collapses_spaces_and_casefolds():
    """Catches display-only differences creating duplicate challenges."""
    assert normalize_challenge("  DeSaFiO   Pontual   Ç  ") == (
        "DeSaFiO Pontual Ç",
        "desafio pontual ç",
    )


class _ValuesResource:
    def __init__(self, rows):
        self.rows = rows
        self.get_args = None

    def get(self, **kwargs):
        self.get_args = kwargs
        return self

    def execute(self):
        return {"values": self.rows}


class _SpreadsheetsResource:
    def __init__(self, values_resource):
        self.values_resource = values_resource

    def values(self):
        return self.values_resource


class _SheetsService:
    def __init__(self, rows):
        self.values_resource = _ValuesResource(rows)

    def spreadsheets(self):
        return _SpreadsheetsResource(self.values_resource)


def test_fetch_desafio_records_reads_only_fixed_a_to_i_range():
    """Catches fetching a header-mapped or mutable range instead of the positional contract."""
    service = _SheetsService([["header"], ["1", "Ana"]])
    received_scopes = []

    def service_factory(*, scopes):
        received_scopes.append(scopes)
        return service

    with patch.object(config, "GSHEET_DESAFIOS_SPREADSHEET_ID", "sheet-123"), patch.object(
        config, "GSHEET_DESAFIOS_SHEET_NAME", "Desafios Pontuais"
    ), patch.object(google_sheets_client, "_get_service", side_effect=service_factory):
        result = google_sheets_client.fetch_desafio_records()

    assert result == [["header"], ["1", "Ana"]]
    assert service.values_resource.get_args == {
        "spreadsheetId": "sheet-123",
        "range": "'Desafios Pontuais'!A:I",
    }
    assert received_scopes == [
        ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    ]


def test_fetch_desafio_records_fails_locally_when_dedicated_config_is_missing():
    """Catches missing challenge config breaking unrelated accounting at import time."""
    with patch.object(config, "GSHEET_DESAFIOS_SPREADSHEET_ID", None), patch.object(
        config, "GSHEET_DESAFIOS_SHEET_NAME", None
    ):
        with pytest.raises(
            google_sheets_client.DesafioSheetConfigurationError,
            match="GSHEET_DESAFIOS_SPREADSHEET_ID, GSHEET_DESAFIOS_SHEET_NAME",
        ):
            google_sheets_client.fetch_desafio_records()


def _read_points_config_in_isolated_process(value: str | None) -> int:
    env = os.environ.copy()
    if value is None:
        env.pop("POINTS_PER_DESAFIO_SUBMISSION", None)
    else:
        env["POINTS_PER_DESAFIO_SUBMISSION"] = value
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config; print(config.POINTS_PER_DESAFIO_SUBMISSION)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return int(completed.stdout.strip())


def test_default_points_per_submission_is_ten():
    """Catches the approved default depending on the developer's shell."""
    assert _read_points_config_in_isolated_process(None) == 10


def test_points_per_submission_accepts_environment_override():
    """Catches deploy configuration being ignored after the initial default."""
    assert _read_points_config_in_isolated_process("25") == 25
