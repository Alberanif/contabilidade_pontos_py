import json
import logging
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
    """Calcula a melhor correspondência de similaridade estrita entre raw_name e canonical_list.

    Usa a combinação de ratio estrito e token_sort_ratio para evitar falsos positivos
    baseados apenas em sobrenomes genéricos comuns (ex: Santos, Silva, Batista).
    Retorna (best_canonical, score) em uma escala de 0.0 a 100.0.
    """
    if not raw_name or not canonical_list:
        return None, 0.0

    raw_norm = normalize_key(raw_name)
    best_match: str | None = None
    best_score: float = 0.0

    for canon in canonical_list:
        canon_norm = normalize_key(canon)
        # Ratio estrito e token sort ratio protegem contra falsos positivos de sobrenomes isolados
        score = float(max(fuzz.ratio(raw_norm, canon_norm), fuzz.token_sort_ratio(raw_norm, canon_norm)))
        if score > best_score:
            best_score = score
            best_match = canon

    return best_match, round(best_score, 2)


def llm_match_groq(
    raw_name: str, canonical_list: list[str], groq_api_key: str | None = None
) -> tuple[str | None, float]:
    """Consulta a API Groq com pré-filtragem estrita e prompt auditado contra alucinações.

    Retorna (coach_sugerido, confianca) em float (0.0 a 100.0).
    """
    api_key = groq_api_key or config.GROQ_API_KEY
    if not api_key or not _GROQ_AVAILABLE:
        logger.info("GROQ_API_KEY não configurada ou biblioteca indisponível. Pulando chamada ao LLM.")
        return None, 0.0

    if not raw_name or not canonical_list:
        return None, 0.0

    raw_key = normalize_key(raw_name)

    # 1. Pré-filtragem de candidatos plausíveis (score de similaridade >= 45%)
    scored_candidates: list[tuple[str, float]] = []
    for c in canonical_list:
        ckey = normalize_key(c)
        if ckey == raw_key:
            continue
        score = max(fuzz.ratio(raw_key, ckey), fuzz.token_sort_ratio(raw_key, ckey))
        if score >= 45:
            scored_candidates.append((c, float(score)))

    if not scored_candidates:
        # Nenhum candidato oficial possui semelhança razoável com o nome digitado
        return None, 0.0

    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    top_candidates = [c[0] for c in scored_candidates[:5]]

    client = Groq(api_key=api_key)
    model = config.GROQ_MODEL

    prompt = f"""Você é um auditor estrito de identidade e unificação de nomes de coaches.
Sua função é verificar se o nome digitado "{raw_name}" é a MESMA PESSOA REAL que algum dos coaches da lista oficial fornecida.

Nome digitado (raw): "{raw_name}"
Lista de candidatos oficiais plausíveis: {json.dumps(top_candidates, ensure_ascii=False)}

REGRAS RÍGIDAS DE AUDITORIA:
1. ATENÇÃO: Nomes que compartilham apenas sobrenomes genéricos (como "Santos", "Silva", "Batista", "Oliveira", "Pereira", "Lemos") mas possuem primeiros nomes DIFERENTES são PESSOAS DIFERENTES! (Exemplo: "Viviane Santos" e "Ana Silva" são pessoas diferentes -> responda null).
2. Responda com um coach da lista APENAS se for uma variação clara de grafia, erro de digitação, diminutivo/apelido direto (ex: "Vini" = "Vinicius", "Tati" = "Tatiane") ou inclusão/omissão de um sobrenome intermediário mantendo o mesmo primeiro nome.
3. Se o nome digitado for uma pessoa visivelmente diferente de todos os candidatos da lista, você DEVE retornar "coach_sugerido": null e "confianca": 0.0.

Responda EXCLUSIVAMENTE um objeto JSON estrito com o formato:
{{
  "coach_sugerido": "NOME_EXATO_DA_LISTA ou null",
  "confianca": 95.0
}}
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

        # Valida se o coach sugerido existe de fato na lista de top candidatos
        if coach_sugerido and coach_sugerido in top_candidates:
            return coach_sugerido, min(100.0, max(0.0, confianca))
        else:
            if coach_sugerido:
                sug_key = normalize_key(coach_sugerido)
                for canon in top_candidates:
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

    # Camada 2: RapidFuzz Match Estrito (Similaridade extrema >= 95%)
    fuzzy_canon, fuzzy_score = fuzzy_match(raw_clean, canonical_list)
    if fuzzy_canon and fuzzy_score >= 95.0:
        return {
            "action": "auto_approve",
            "coach_canonico": fuzzy_canon,
            "confianca": fuzzy_score,
            "origem": "rapidfuzz",
        }

    # Camada 3: Agente IA Groq Auditado
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

    # Se a IA avaliou e retornou null (ou não houve match estrito), o nome é um Coach Novo Independente.
    return {
        "action": "no_match",
        "coach_canonico": raw_clean,
        "confianca": 0.0,
        "origem": "none",
    }
