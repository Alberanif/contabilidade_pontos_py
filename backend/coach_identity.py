import re
import unicodedata


def normalize_key(raw: str) -> str:
    """Chave de comparação insensível a caixa, acento e espaçamento."""
    no_accents = "".join(
        c for c in unicodedata.normalize("NFD", raw.strip())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", no_accents).upper()


def resolve_coach(coach_raw: str, alias_map: dict[str, str]) -> str:
    """Resolve o nome canônico de um coach a partir de um mapa {alias: canonico}.

    A comparação usa normalize_key nos dois lados, então uma grafia nunca
    vista antes (variação de caixa/acento/espaço de um alias já cadastrado)
    ainda resolve corretamente, sem precisar de uma linha própria na tabela.
    Sem alias correspondente, retorna o próprio nome (aparado).
    """
    coach_raw = (coach_raw or "").strip()
    if not coach_raw:
        return "DESCONHECIDO"
    key = normalize_key(coach_raw)
    by_key = {normalize_key(alias): canonico for alias, canonico in alias_map.items()}
    return by_key.get(key, coach_raw)


def aggregate_by_canonical(raw_points: dict[str, int], alias_map: dict[str, str]) -> dict[str, int]:
    """Reagrupa um dict {nome_bruto: valor} pelo nome canônico, somando colisões."""
    result: dict[str, int] = {}
    for raw_name, value in raw_points.items():
        canonical = resolve_coach(raw_name, alias_map)
        result[canonical] = result.get(canonical, 0) + value
    return result


def detect_alias_chains(alias_map: dict[str, str]) -> list[str]:
    """Detecta aliases cujo coach_canonico também é, ele mesmo, alias de outra
    linha (cadeia de 2+ saltos) — não resolvidos automaticamente, só reportados
    para o usuário corrigir a tabela apontando direto para o canônico final."""
    by_key = {normalize_key(alias): canonico for alias, canonico in alias_map.items()}
    warnings: list[str] = []
    for alias, canonico in alias_map.items():
        canonico_key = normalize_key(canonico)
        if canonico_key in by_key and by_key[canonico_key] != canonico:
            warnings.append(f"{alias} -> {canonico} -> {by_key[canonico_key]}")
    return warnings
