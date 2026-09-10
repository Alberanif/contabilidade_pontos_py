"""Parser puro do contrato posicional A-I da aba oficial de desafios."""

from dataclasses import dataclass, replace
from datetime import datetime
import re
import unicodedata
from zoneinfo import ZoneInfo


SHEET_COLUMN_COUNT = 9
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class ParsedDesafioRow:
    row_number: int
    source_cell_count: int
    raw_cells: tuple[str, ...]
    raw_clan_legacy: str
    raw_name: str
    raw_validation: str
    raw_link: str
    raw_observation: str
    raw_challenge: str
    raw_clan_current: str
    raw_submitted_at: str
    raw_token: str
    token: str
    name: str
    clan: str | None
    challenge_display: str
    challenge_normalized: str
    submitted_at: datetime | None
    status: str
    structurally_valid: bool
    eligible: bool
    reasons: tuple[str, ...]


def _without_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_clan(raw: str) -> str | None:
    """Normaliza as grafias aprovadas para ``CLÃ 1`` até ``CLÃ 8``."""
    value = re.sub(r"\s+", " ", _without_accents(str(raw)).strip()).upper()
    match = re.fullmatch(r"(?:CLA\s*)?0*([1-8])", value)
    if not match:
        return None
    return f"CLÃ {match.group(1)}"


def normalize_challenge(raw: str) -> tuple[str, str]:
    """Retorna a grafia de exibição limpa e a chave case-insensitive."""
    display = re.sub(r"\s+", " ", str(raw).strip())
    return display, display.casefold()


def _parse_submitted_at(raw: str) -> datetime | None:
    try:
        parsed = datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M:%S")
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=SAO_PAULO)


def _resolve_clan(raw_legacy: str, raw_current: str) -> tuple[str | None, list[str]]:
    reasons: list[str] = []
    legacy_present = bool(raw_legacy.strip())
    current_present = bool(raw_current.strip())
    legacy = normalize_clan(raw_legacy) if legacy_present else None
    current = normalize_clan(raw_current) if current_present else None

    if legacy_present and legacy is None:
        reasons.append("invalid_clan_legacy")
    if current_present and current is None:
        reasons.append("invalid_clan_current")
    if not legacy_present and not current_present:
        reasons.append("missing_clan")

    if legacy is not None and current is not None:
        if legacy != current:
            reasons.append("conflicting_clans")
            return None, reasons
        return legacy, reasons

    if reasons:
        return None, reasons
    return legacy or current, reasons


def parse_desafio_row(row_number: int, cells: list[str]) -> ParsedDesafioRow:
    """Converte uma linha em estado auditável sem realizar qualquer I/O."""
    source_cell_count = len(cells)
    raw_cells = ["" if cell is None else str(cell) for cell in cells[:SHEET_COLUMN_COUNT]]
    raw_cells.extend([""] * (SHEET_COLUMN_COUNT - len(raw_cells)))

    (
        raw_clan_legacy,
        raw_name,
        raw_validation,
        raw_link,
        raw_observation,
        raw_challenge,
        raw_clan_current,
        raw_submitted_at,
        raw_token,
    ) = raw_cells

    reasons: list[str] = []
    if source_cell_count < SHEET_COLUMN_COUNT:
        reasons.append("missing_columns")

    token = raw_token.strip()
    name = raw_name.strip()
    challenge_display, challenge_normalized = normalize_challenge(raw_challenge)
    submitted_at = _parse_submitted_at(raw_submitted_at)
    clan, clan_reasons = _resolve_clan(raw_clan_legacy, raw_clan_current)
    reasons.extend(clan_reasons)

    if not name:
        reasons.append("missing_name")
    if not challenge_display:
        reasons.append("missing_challenge")
    if submitted_at is None:
        reasons.append("invalid_submitted_at")
    if not token:
        reasons.append("missing_token")

    if "conflicting_clans" in reasons:
        status = "conflicted"
    elif reasons:
        status = "invalid"
    elif raw_validation.strip().casefold() == "sim":
        status = "active_counted"
    else:
        status = "active_not_counted"

    structurally_valid = status in {"active_counted", "active_not_counted"}
    eligible = status == "active_counted"

    return ParsedDesafioRow(
        row_number=row_number,
        source_cell_count=source_cell_count,
        raw_cells=tuple(raw_cells),
        raw_clan_legacy=raw_clan_legacy,
        raw_name=raw_name,
        raw_validation=raw_validation,
        raw_link=raw_link,
        raw_observation=raw_observation,
        raw_challenge=raw_challenge,
        raw_clan_current=raw_clan_current,
        raw_submitted_at=raw_submitted_at,
        raw_token=raw_token,
        token=token,
        name=name,
        clan=clan,
        challenge_display=challenge_display,
        challenge_normalized=challenge_normalized,
        submitted_at=submitted_at,
        status=status,
        structurally_valid=structurally_valid,
        eligible=eligible,
        reasons=tuple(reasons),
    )


def build_parsed_rows(rows: list[list[str]]) -> list[ParsedDesafioRow]:
    """Ignora a linha 1 de cabeçalho e processa as demais por posição."""
    parsed_rows = [
        parse_desafio_row(row_number, cells)
        for row_number, cells in enumerate(rows[1:], start=2)
    ]
    first_valid_spelling: dict[str, str] = {}
    for row in parsed_rows:
        if row.structurally_valid:
            first_valid_spelling.setdefault(
                row.challenge_normalized, row.challenge_display
            )
    return [
        replace(
            row,
            challenge_display=first_valid_spelling.get(
                row.challenge_normalized, row.challenge_display
            ),
        )
        for row in parsed_rows
    ]
