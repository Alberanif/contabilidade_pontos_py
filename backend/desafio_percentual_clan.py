"""Motor de cálculo de apuração de desafios por clã baseada em percentual de engajamento.

Implementa a especificação das regras de negócio (§4, §7 do PRD):
- Tabela de faixas de pontuação por percentual de participação.
- Resolução de clãs priorizando a tabela `pontos_ultimate_coach_clas`.
- Deduplicação de participantes (1 por coach único por desafio).
- Truncamento/Cap em 100% se participantes > tamanho do grupo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def normalize_clan(clan_raw: str | None) -> str:
    """Normaliza o nome do clã para o formato padrão 'CLÃ X'."""
    if not clan_raw:
        return "CLÃ DESCONHECIDO"
    clean = clan_raw.strip()
    try:
        return f"CLÃ {int(clean)}"
    except (ValueError, AttributeError):
        return clean.upper() if clean.lower().startswith("clã") else clean


def calcular_pontos_por_percentual(percentual: float) -> int:
    """Calcula os pontos obtidos por um clã de acordo com seu percentual de participação.

    Regra de negócio (PRD §4):
    - 0% a <10%: 0 pontos
    - 10% a 30%: 300 pontos
    - 31% a 40%: 400 pontos
    - 41% a 50%: 500 pontos
    - 51% a 60%: 600 pontos
    - 61% a 70%: 700 pontos
    - 71% a 80%: 800 pontos
    - 81% a 90%: 900 pontos
    - >90%: 1000 pontos (faixa máxima)
    """
    if percentual < 10.0:
        return 0
    if 10.0 <= percentual <= 30.0:
        return 300
    if 30.0 < percentual <= 40.0:
        return 400
    if 40.0 < percentual <= 50.0:
        return 500
    if 50.0 < percentual <= 60.0:
        return 600
    if 60.0 < percentual <= 70.0:
        return 700
    if 70.0 < percentual <= 80.0:
        return 800
    if 80.0 < percentual <= 90.0:
        return 900
    return 1000


@dataclass
class ApuracaoClan:
    clan: str
    participantes: int
    total_grupo: int
    percentual: float
    pontos: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "clan": self.clan,
            "participantes": self.participantes,
            "total_grupo": self.total_grupo,
            "percentual": round(self.percentual, 2),
            "pontos": self.pontos,
        }


def apurar_desafio(
    submissoes_aprovadas: list[dict[str, Any]],
    coach_clas: dict[str, str],
    tamanho_grupo_por_clan: dict[str, int],
    todos_os_clas: list[str] | None = None,
) -> dict[str, ApuracaoClan]:
    """Apura a pontuação por percentual de cada clã num desafio.

    Args:
        submissoes_aprovadas: Lista de dicts contendo 'coach' (canônico) e 'clan_planilha'.
        coach_clas: Mapeamento de coach (canônico) -> clã cadastrado em `pontos_ultimate_coach_clas`.
        tamanho_grupo_por_clan: Mapeamento de clã -> total de coaches cadastrados naquele clã.
        todos_os_clas: Lista opcional dos 8 clãs para garantir que clãs sem submissões fiquem zerados.

    `participantes` conta cada submissão aprovada, sem deduplicar por coach: um
    reenvio do mesmo coach soma de novo. A defesa contra reenvio indevido é a
    reprovação manual da submissão (`revisar_submissao`), não uma deduplicação
    automática — que estava descartando reenvios legítimos (ex.: correção de
    link) junto com os indevidos.

    Returns:
        Dict mapeando nome do clã -> ApuracaoClan.
    """
    clas_alvo = set(todos_os_clas or [])
    clas_alvo.update(tamanho_grupo_por_clan.keys())

    submissoes_por_clan: dict[str, int] = {}

    for sub in submissoes_aprovadas:
        coach = (sub.get("coach") or sub.get("raw_name") or "").strip()
        if not coach:
            continue

        # Regra de precedência (§7.3): Clã do cadastro sempre vence. Se não cadastrado, usa planilha.
        if coach in coach_clas:
            clan = normalize_clan(coach_clas[coach])
        else:
            clan_raw = sub.get("clan_planilha") or sub.get("clan") or sub.get("raw_clan_current") or sub.get("raw_clan_legacy")
            clan = normalize_clan(clan_raw)

        clas_alvo.add(clan)
        submissoes_por_clan[clan] = submissoes_por_clan.get(clan, 0) + 1

    resultados: dict[str, ApuracaoClan] = {}

    for clan in sorted(clas_alvo):
        participantes = submissoes_por_clan.get(clan, 0)
        total_grupo = tamanho_grupo_por_clan.get(clan, 0)

        if total_grupo <= 0:
            percentual = 0.0
            pontos = 0
        else:
            percentual_real = (participantes / total_grupo) * 100.0
            # Cap de 100% se houver mais participantes aprovados que o total cadastrado
            percentual = min(percentual_real, 100.0)
            pontos = calcular_pontos_por_percentual(percentual)

        resultados[clan] = ApuracaoClan(
            clan=clan,
            participantes=participantes,
            total_grupo=total_grupo,
            percentual=percentual,
            pontos=pontos,
        )

    return resultados
