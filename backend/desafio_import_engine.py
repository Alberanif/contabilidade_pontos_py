"""Lógica pura de importação de desafios via CSV. Zero I/O — sem chamadas a Supabase/rede."""

from dataclasses import dataclass, field
from datetime import date, datetime

import coach_identity


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
    coach: str
    validado: bool
    submitted_at: datetime | None
    token: str


def parse_row(raw_row: dict, mapping: dict, coach_alias_map: dict[str, str]) -> ImportRow:
    """Extrai e normaliza uma linha do CSV usando o mapeamento de colunas escolhido no wizard.

    coach = mesma coluna 'Nome' já mapeada, resolvida para o nome canônico via
    coach_identity (quem preenche o formulário é o próprio coach)."""
    nome = raw_row.get(mapping["nome"], "").strip()
    return ImportRow(
        clan=normalizar_clan(raw_row.get(mapping["clan"], "")),
        nome=nome,
        nome_normalizado=normalizar_nome(nome),
        coach=coach_identity.resolve_coach(nome, coach_alias_map),
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


@dataclass
class ImportResult:
    pontos_por_clan: dict[str, int] = field(default_factory=dict)
    participacoes_por_clan: dict[str, int] = field(default_factory=dict)
    pontos_por_coach: dict[str, int] = field(default_factory=dict)
    participacoes_por_coach: dict[str, int] = field(default_factory=dict)
    linhas_auditoria: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def processar_importacao(
    raw_rows: list[dict],
    mapping: dict,
    clans_validos: set[str],
    tokens_ja_importados: set[str],
    data_inicio: date,
    data_fim: date,
    pontos_por_participacao: int,
    coach_alias_map: dict[str, str],
) -> ImportResult:
    """Pipeline completo: parse → período → clã válido → token novo → dedup de pessoa → agregação.

    Ordem deliberada: período primeiro (é o filtro mais barato/fundamental — decide
    se a linha pertence a este desafio), depois clã (senão avisos de clã inválido
    incluiriam linhas de outros desafios), depois dedup entre importações (token),
    e por último dedup dentro do lote (pessoa), que só faz sentido sobre o conjunto final.

    Pontos de coach usam a mesma submissão vencedora (contabilizado=True) que já
    decide os pontos de clã — coach = a mesma coluna 'Nome', resolvida ao canônico.
    """
    parsed = [parse_row(r, mapping, coach_alias_map) for r in raw_rows]

    dentro_periodo, fora_periodo = filtrar_por_periodo(parsed, data_inicio, data_fim)
    validos, invalidos = filtrar_clans_validos(dentro_periodo, clans_validos)
    novos, repetidos = filtrar_tokens_novos(validos, tokens_ja_importados)
    contabilizacao = deduplicar_por_pessoa(novos)

    result = ImportResult()

    for item in contabilizacao:
        row = item.row
        result.linhas_auditoria.append({
            "clan": row.clan,
            "nome_participante": row.nome,
            "coach": row.coach,
            "validado": row.validado,
            "contabilizado": row.validado and item.contabilizado,
            "submitted_at": row.submitted_at,
            "token_original": row.token,
        })
        if row.validado and item.contabilizado:
            result.participacoes_por_clan[row.clan] = result.participacoes_por_clan.get(row.clan, 0) + 1
            result.pontos_por_clan[row.clan] = result.participacoes_por_clan[row.clan] * pontos_por_participacao

            result.participacoes_por_coach[row.coach] = result.participacoes_por_coach.get(row.coach, 0) + 1
            result.pontos_por_coach[row.coach] = result.participacoes_por_coach[row.coach] * pontos_por_participacao

    if invalidos:
        clans_desconhecidos = sorted({r.clan for r in invalidos})
        result.avisos.append(
            f"{len(invalidos)} linha(s) ignorada(s) por clã não reconhecido: {', '.join(clans_desconhecidos)}"
        )
    if fora_periodo:
        result.avisos.append(f"{len(fora_periodo)} linha(s) fora do período informado foram ignoradas")

    return result
