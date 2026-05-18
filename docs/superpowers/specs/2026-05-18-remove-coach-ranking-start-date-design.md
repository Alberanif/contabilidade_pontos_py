# Design: Remoção de COACH_RANKING_START_DATE

**Data:** 2026-05-18  
**Contexto:** Sistema de pontos Ultimate Frisbee — backend FastAPI + Supabase

---

## Problema

A constante `COACH_RANKING_START_DATE = date(2026, 4, 1)` em `config.py` restringia a contabilização de pontos de coaches em três fluxos:

1. **Coaching Individual via `importar_inicial`:** registros com data < Abril tinham `pontos_coach = 0`
2. **Pro Bono via `importar_inicial`:** registros com data < Abril tinham `pontos_coach = 0`
3. **Coaching em grupo via `executar`:** registros com data < Abril recebiam `status_coach = "contabilizado"` direto, sem entrar na fila de aprovação por lotes

Isso causava dois sintomas visíveis no filtro de tipo com período:
- **Filtro "Pagantes" com data:** exibia coaches com 10 pts (registros Pro Bono com `pontos_coach = 10` vazavam porque o check antigo `registro_hash.startswith("pro_bono:")` nunca funcionou — o hash é SHA-256, não contém o prefixo)
- **Filtro "Pro Bono" com data:** retornava vazio porque os registros Pro Bono anteriores a Abril tinham `pontos_coach = 0`

---

## Fix já aplicado (independente deste design)

O check de separação pagante/pro_bono no caminho com data foi corrigido de:
```python
h = rec.get("registro_hash", "")
if is_pro_bono != h.startswith("pro_bono:"):
    continue
```
Para:
```python
rec_is_pro_bono = rec.get("modalidade", "") == "Pro-bono"
if is_pro_bono != rec_is_pro_bono:
    continue
```
E o SELECT foi atualizado de `registro_hash` para `modalidade` em ambas as funções (`get_tipo_clan_totals`, `get_tipo_coach_totals`). **Requer reinicialização do servidor para ter efeito.**

---

## Solução: Opção C — Remoção completa

Remove `COACH_RANKING_START_DATE` de todos os 7 locais onde é usado, tornando todos os registros elegíveis para pontuação de coaches independente de data.

---

## Mudanças de dados

### Estado atual

| Tipo de registro | `pontos_coach` | `status_coach` |
|---|---|---|
| Coaching Individual (data < Abril) | `0` | `contabilizado` |
| Coaching Individual (data >= Abril) | `30` | `contabilizado` |
| Pro Bono (data < Abril) | `0` | `contabilizado` |
| Pro Bono (data >= Abril) | `10` | `contabilizado` |
| Grupo via Executar (data < Abril) | `0` | `contabilizado` (bypassa fila) |
| Grupo via Executar (data >= Abril) | `0` | `pendente` |

### Estado desejado

| Tipo de registro | `pontos_coach` | `status_coach` |
|---|---|---|
| Coaching Individual (qualquer data) | `30` | `contabilizado` |
| Pro Bono (qualquer data) | `10` | `contabilizado` |
| Grupo via Executar (qualquer data) | `0` | `pendente` |

A atualização dos registros existentes ocorre via re-execução de `importar_inicial` — os `upsert` por `registro_hash` sobrescrevem `pontos_coach` nos registros já presentes.

**Exceção:** registros de grupo inseridos via `importar_inicial` (não via `executar`) têm `status_coach` calculado por completude de lotes, não por data — não são afetados.

---

## Mudanças no código

### `config.py`

Remover:
```python
from datetime import date as _date
COACH_RANKING_START_DATE = _date(2026, 4, 1)
```

Se `_date` for usado apenas para esta constante, remover o import também.

### `contabilidade.py` — `importar_inicial` Fase 3

```python
# REMOVER: bloco coach_eligible_set (3 linhas)
coach_eligible_set = {
    h for h, _ in points_engine.filter_records_by_date_from(
        coaching_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
    )
}

# MUDAR em extra_fields:
"pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL,
# era: config.POINTS_PER_COACHING_INDIVIDUAL if record_hash in coach_eligible_set else 0
```

### `contabilidade.py` — `importar_inicial` Fase 7

```python
# REMOVER: coach_eligible_seed e usar coaching_records diretamente
pontos_por_coach = points_engine.calculate_points_by_coach(
    coaching_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
)

# REMOVER: coach_eligible_pb_seed, coach_eligible_pb_hashes
# MUDAR: usar pb_records_for_coach diretamente
pro_bono_coach_pts_seed = points_engine.calculate_points_by_coach(
    pb_records_for_coach, COL_COACH, config.POINTS_PER_PRO_BONO
)
```

### `contabilidade.py` — `importar_inicial` Fase 8

```python
# MUDAR em extra_fields:
"pontos_coach": config.POINTS_PER_PRO_BONO,
# era: config.POINTS_PER_PRO_BONO if record_hash in coach_eligible_pb_hashes else 0
```

### `contabilidade.py` — `_process_group_records`

```python
# REMOVER: record_date e coach_elegivel (3 linhas)

# MUDAR em extra_fields:
"status_coach": "pendente",
# era: "pendente" if coach_elegivel else "contabilizado"
```

### `contabilidade.py` — `executar_contabilidade`

```python
# REMOVER: coach_eligible_ci = filter_records_by_date_from(...)
# MUDAR:
pontos_por_coach = points_engine.calculate_points_by_coach(
    new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
)
# era: calculate_points_by_coach(coach_eligible_ci, ...)
```

### `contabilidade.py` — `_process_pro_bono_records`

```python
# REMOVER: coach_eligible_pb e usar new_records diretamente
pontos_por_coach = points_engine.calculate_points_by_coach(
    new_records, COL_COACH, config.POINTS_PER_PRO_BONO
)
# era: calculate_points_by_coach(coach_eligible_pb, ...)
```

### `contabilidade.py` — `reprocessar_contabilidade`

Mesmo padrão do `executar_contabilidade`:
```python
# REMOVER: coach_eligible_ci = filter_records_by_date_from(...)
# MUDAR:
pontos_por_coach = points_engine.calculate_points_by_coach(
    new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
)
```

### `contabilidade.py` — `debug_date_sample` (GET `/debug/date-sample`)

Endpoint de diagnóstico que usa `COACH_RANKING_START_DATE` para exibir estatísticas de registros "elegíveis". Com a remoção da constante, simplificar: remover as variáveis `elegivel`, `ci_elegiveis`, `group_elegiveis_coach`, `pb_elegiveis` e seus contadores — todos os registros são agora elegíveis. Remover também o campo `coach_ranking_start` do retorno.

---

## Testes

### Sem mudança

- `test_tipo_filter_breakdown.py` — caminho sem data, não envolve a restrição
- `test_period_totals_floor.py` — caminho com data, usa `modalidade` após fix

### Novos testes — `tests/test_importar_inicial_coach_points.py`

| Cenário | Assertion |
|---|---|
| Coaching Individual com data pré-Abril | `pontos_coach == 30` |
| Coaching Individual com data Abril+ | `pontos_coach == 30` |
| Pro Bono com data pré-Abril | `pontos_coach == 10` |
| Pro Bono com data Abril+ | `pontos_coach == 10` |
| Grupo via `executar` com data pré-Abril | `status_coach == "pendente"` |

### Verificação de referências

Após remover a constante, executar:
```bash
grep -r "COACH_RANKING_START_DATE" backend/
```
Confirmar que nenhuma referência restante.

---

## Passos operacionais

1. **Reiniciar o servidor FastAPI** — aplica o fix `modalidade` já feito (resolve 10 pts em Pagantes e vazio em Pro Bono imediatamente)
2. **Aplicar as mudanças de código** deste spec
3. **Re-executar "Importar Dados Existentes"** — atualiza `pontos_coach` de todos os registros existentes no banco
4. **Verificar os filtros com período** — Pagantes e Pro Bono com qualquer data devem exibir valores corretos

Não é necessário "Reprocessar Tudo".
