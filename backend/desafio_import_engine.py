"""Lógica pura de importação de desafios via CSV. Zero I/O — sem chamadas a Supabase/rede."""

from dataclasses import dataclass, field
from datetime import date, datetime


def normalizar_validado(raw: str) -> bool:
    """Só conta como validado um valor cuja forma normalizada seja exatamente 'sim'."""
    return raw.strip().lower() == "sim"
