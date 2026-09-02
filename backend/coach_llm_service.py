import json
import logging
import re
from rapidfuzz import fuzz

import config
from coach_identity import normalize_key

logger = logging.getLogger(__name__)

# Tenta importar o SDK do Groq
try:
    from groq import Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False
    logger.warning("SDK groq não instalado.")


def fuzzy_match(raw_name: str, canonical_list: list[str]) -> tuple[str | None, float]:
    """Calcula a melhor correspondência de similaridade entre raw_name e canonical_list.

    Retorna (best_canonical, score) em uma escala de 0.0 a 100.0.
    """
    if not raw_name or not canonical_list:
        return None, 0.0

    raw_norm = normalize_key(raw_name)
    best_match: str | None = None
    best_score: float = 0.0

    for canon in canonical_list:
        canon_norm = normalize_key(canon)
        # Calcula similaridade ponderada com WRatio
        score = float(fuzz.WRatio(raw_norm, canon_norm))
        if score > best_score:
            best_score = score
            best_match = canon

    return best_match, round(best_score, 2)


def llm_match_groq(
    raw_name: str, canonical_list: list[str], groq_api_key: str | None = None
) -> tuple[str | None, float]:
    """Consulta a API Groq (llama-3.3-70b-versatile) para identificar o nome canônico do coach.

    Retorna (coach_sugerido, confianca) em float (0.0 a 100.0).
    """
    api_key = groq_api_key or config.GROQ_API_KEY
    if not api_key or not _GROQ_AVAILABLE:
        logger.info("GROQ_API_KEY não configurada ou biblioteca indisponível. Pulando chamada ao LLM.")
        return None, 0.0

    if not raw_name or not canonical_list:
        return None, 0.0

    client = Groq(api_key=api_key)
    model = config.GROQ_MODEL

    prompt = f"""Você é um assistente especialista em unificação de nomes e normalização de dados de coaches.
Dada uma lista de nomes de coaches oficiais cadastrados e um nome de coach digitado (com possível erro de digitação, apelido, variação de maiúsculas/minúsculas, acentos ou sobrenome omitido):

Nome digitado (raw): "{raw_name}"
Lista de coaches oficiais: {json.dumps(canonical_list, ensure_ascii=False)}

Determine se "{raw_name}" corresponde a algum dos coaches da lista oficial.
Responda EXCLUSIVAMENTE um objeto JSON estrito com o formato:
{{
  "coach_sugerido": "NOME_EXATO_DA_LISTA_OFICIAL ou null se não houver correspondência",
  "confianca": 95.0
}}

Exemplo 1:
Se raw="Vini Marini" e a lista contém "Vinicius Marini", responda:
{{"coach_sugerido": "Vinicius Marini", "confianca": 95.0}}

Exemplo 2:
Se raw="Nome Completamente Estranho" e não há correspondente na lista, responda:
{{"coach_sugerido": null, "confianca": 0.0}}
"""

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.GROQ_TEMPERATURE,
            response_format={"type": "json_object"},
            timeout=10.0,
        )

        response_text = completion.choices[0].message.content or "{}"
        data = json.loads(response_text)

        coach_sugerido = data.get("coach_sugerido")
        confianca = float(data.get("confianca", 0.0))

        # Valida se o coach sugerido existe de fato na lista oficial
        if coach_sugerido and coach_sugerido in canonical_list:
            return coach_sugerido, min(100.0, max(0.0, confianca))
        else:
            # Tenta encontrar correspondência exata insensível à caixa se o LLM retornou versão diferente
            if coach_sugerido:
                sug_key = normalize_key(coach_sugerido)
                for canon in canonical_list:
                    if normalize_key(canon) == sug_key:
                        return canon, min(100.0, max(0.0, confianca))

            return None, 0.0
    except Exception as e:
        logger.error(f"Erro ao consultar a API Groq para '{raw_name}': {e}")
        return None, 0.0


def evaluate_coach_identity(raw_name: str, canonical_list: list[str]) -> dict:
    """Avalia o nome digitado usando a arquitetura em camadas (Exact Match -> RapidFuzz -> Groq LLM).

    Retorna um dict no formato:
    {
        "action": "exact_match" | "auto_approve" | "pending_queue" | "no_match",
        "coach_canonico": str,
        "confianca": float,
        "origem": "exact" | "rapidfuzz" | "groq-llm"
    }
    """
    raw_clean = (raw_name or "").strip()
    if not raw_clean or not canonical_list:
        return {
            "action": "no_match",
            "coach_canonico": raw_clean,
            "confianca": 0.0,
            "origem": "none",
        }

    raw_key = normalize_key(raw_clean)
    canonical_map_by_key = {normalize_key(c): c for c in canonical_list}

    # Camada 1: Exact / Normalized Match
    if raw_key in canonical_map_by_key:
        return {
            "action": "exact_match",
            "coach_canonico": canonical_map_by_key[raw_key],
            "confianca": 100.0,
            "origem": "exact",
        }

    # Camada 2: RapidFuzz Match
    fuzzy_canon, fuzzy_score = fuzzy_match(raw_clean, canonical_list)
    if fuzzy_canon and fuzzy_score >= 95.0:
        return {
            "action": "auto_approve",
            "coach_canonico": fuzzy_canon,
            "confianca": fuzzy_score,
            "origem": "rapidfuzz",
        }

    # Camada 3: Groq LLM Agent
    llm_canon, llm_conf = llm_match_groq(raw_clean, canonical_list)

    if llm_canon and llm_conf >= 95.0:
        return {
            "action": "auto_approve",
            "coach_canonico": llm_canon,
            "confianca": llm_conf,
            "origem": "groq-llm",
        }

    if llm_canon and 70.0 <= llm_conf < 95.0:
        return {
            "action": "pending_queue",
            "coach_canonico": llm_canon,
            "confianca": llm_conf,
            "origem": "groq-llm",
        }

    # Fallback: Se o LLM não respondeu ou teve baixa confiança, mas o fuzzy teve confiança intermediária (70-94%)
    if fuzzy_canon and 70.0 <= fuzzy_score < 95.0:
        return {
            "action": "pending_queue",
            "coach_canonico": fuzzy_canon,
            "confianca": fuzzy_score,
            "origem": "rapidfuzz",
        }

    return {
        "action": "no_match",
        "coach_canonico": raw_clean,
        "confianca": 0.0,
        "origem": "none",
    }
