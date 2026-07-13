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


@dataclass(frozen=True)
class ImportRow:
    clan: str
    nome: str
    nome_normalizado: str
    validado: bool
    submitted_at: datetime | None
    token: str


def parse_row(raw_row: dict, mapping: dict) -> ImportRow:
    """Extrai e normaliza uma linha do CSV usando o mapeamento de colunas escolhido no wizard."""
    nome = raw_row.get(mapping["nome"], "").strip()
    return ImportRow(
        clan=normalizar_clan(raw_row.get(mapping["clan"], "")),
        nome=nome,
        nome_normalizado=normalizar_nome(nome),
        validado=normalizar_validado(raw_row.get(mapping["validado"], "")),
        submitted_at=parse_submitted_at(raw_row.get(mapping["submitted_at"], "")),
        token=raw_row.get(mapping["token"], "").strip(),
    )


def filtrar_por_periodo(
    rows: list[ImportRow], data_inicio: date, data_fim: date
) -> tuple[list[ImportRow], list[ImportRow]]:
    """Separa linhas dentro de [data_inicio, data_fim] (inclusive) das demais.

    Fail-closed: linha sem data parseável é tratada como fora do período
    (diferente do fail-open de points_engine.filter_by_date_range — aqui o
    risco de inflar pontos por engano pesa mais que perder uma linha ambígua).
    """
    dentro, fora = [], []
    for row in rows:
        if row.submitted_at is not None and data_inicio <= row.submitted_at.date() <= data_fim:
            dentro.append(row)
        else:
            fora.append(row)
    return dentro, fora


def filtrar_clans_validos(
    rows: list[ImportRow], clans_validos: set[str]
) -> tuple[list[ImportRow], list[ImportRow]]:
    """Separa linhas com clã reconhecido (presente no ranking atual) das demais."""
    ok = [r for r in rows if r.clan in clans_validos]
    invalidos = [r for r in rows if r.clan not in clans_validos]
    return ok, invalidos


def filtrar_tokens_novos(
    rows: list[ImportRow], tokens_ja_importados: set[str]
) -> tuple[list[ImportRow], list[ImportRow]]:
    """Separa linhas com token inédito das que já foram importadas em execução anterior."""
    novos = [r for r in rows if r.token not in tokens_ja_importados]
    repetidos = [r for r in rows if r.token in tokens_ja_importados]
    return novos, repetidos


@dataclass(frozen=True)
class ContabilizacaoRow:
    row: ImportRow
    contabilizado: bool


def deduplicar_por_pessoa(rows: list[ImportRow]) -> list[ContabilizacaoRow]:
    """Agrupa por (clã, nome normalizado); só a submissão mais recente de cada
    pessoa conta para a pontuação. As demais são marcadas contabilizado=False
    (permanecem na auditoria, mas não somam pontos)."""
    mais_recente_por_pessoa: dict[tuple[str, str], ImportRow] = {}
    for row in rows:
        chave = (row.clan, row.nome_normalizado)
        atual = mais_recente_por_pessoa.get(chave)
        if atual is None or (row.submitted_at or datetime.min) > (atual.submitted_at or datetime.min):
            mais_recente_por_pessoa[chave] = row

    vencedores = set(mais_recente_por_pessoa.values())
    return [ContabilizacaoRow(row=row, contabilizado=row in vencedores) for row in rows]
