"""Lógica pura de importação de desafios via CSV. Zero I/O — sem chamadas a Supabase/rede."""

from dataclasses import dataclass, field
from datetime import date, datetime


def normalizar_validado(raw: str) -> bool:
    """Só conta como validado um valor cuja forma normalizada seja exatamente 'sim'."""
    return raw.strip().lower() == "sim"


def normalizar_nome(raw: str) -> str:
    """Normaliza nome para comparação de dedup: trim + lowercase."""
    return raw.strip().lower()


def normalizar_clan(raw: str) -> str:
    """Converte '2' em 'CLÃ 2'. Valores não numéricos são mantidos como estão (trim)."""
    try:
        return f"CLÃ {int(raw.strip())}"
    except (ValueError, AttributeError):
        return raw.strip()


def parse_submitted_at(raw: str) -> datetime | None:
    """Faz parse de 'dd/mm/yyyy HH:MM:SS'. Retorna None se ilegível ou vazio."""
    if not raw or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None
