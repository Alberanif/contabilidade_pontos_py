# Design: Floor de Pontos de Grupo Parciais no Filtro por Período

**Data:** 2026-05-12  
**Status:** Aprovado

---

## Contexto

O sistema de coaching em grupo usa lotes de 5 pessoas = 30 pontos. Cada registro promovido para
"contabilizado" recebe `pontos = 6` (POINTS_PER_RECORD_IN_BATCH = 30 ÷ 5). Quando o endpoint
`/historico` filtra por período, a soma de registros parciais dentro do intervalo pode resultar
em totais que não terminam em 0 (ex: 6, 12, 18, 24), gerando "pontos quebrados" no dashboard.

**Regra de negócio:** A pontuação exibida deve SEMPRE terminar em 0. Lotes incompletos de coaching
em grupo não devem ser contabilizados — ou o clã/coach acumula pontos de lotes completos, ou não
acumula nada daquela parcela.

---

## Solução

Modificar as 4 funções de consulta por período em `backend/supabase_client.py` para aplicar
floor de lotes completos aos pontos de coaching em grupo:

- Registros com `pontos == config.POINTS_PER_RECORD_IN_BATCH` (valor 6) são acumulados separadamente
- Ao final: `complete = (soma_grupo // POINTS_PER_BATCH_GROUP) * POINTS_PER_BATCH_GROUP`
- Apenas `complete` é adicionado ao total — pontos parciais são descartados
- Os demais tipos (individual: 30 pts, pro-bono: 10 pts) passam sem alteração

### Exemplos

| Registros de grupo no período | Pontos brutos | Pontos exibidos |
|-------------------------------|---------------|-----------------|
| 1 registro                    | 6             | 0               |
| 4 registros                   | 24            | 0               |
| 5 registros (1 lote)          | 30            | 30              |
| 6 registros                   | 36            | 30              |
| 10 registros (2 lotes)        | 60            | 60              |

---

## Funções Modificadas

Arquivo: `backend/supabase_client.py`

| Função                  | Linha | Campo         |
|-------------------------|-------|---------------|
| `get_period_clan_totals`  | 499   | `pontos`      |
| `get_period_coach_totals` | 522   | `pontos_coach`|
| `get_tipo_clan_totals`    | 584   | `pontos`      |
| `get_tipo_coach_totals`   | 641   | `pontos_coach`|

### Padrão de Modificação (clãs)

```python
group_raw: dict[str, int] = {}
totals: dict[str, int] = {}
for record in records:
    clan = record["clan"]
    p = record["pontos"]
    if p == config.POINTS_PER_RECORD_IN_BATCH:
        group_raw[clan] = group_raw.get(clan, 0) + p
    else:
        totals[clan] = totals.get(clan, 0) + p

for clan, g in group_raw.items():
    complete = (g // config.POINTS_PER_BATCH_GROUP) * config.POINTS_PER_BATCH_GROUP
    if complete:
        totals[clan] = totals.get(clan, 0) + complete
```

O padrão para coaches é idêntico, substituindo `clan` por `coach` e `pontos` por `pontos_coach`.

---

## Fora do Escopo

- `get_period_desafio_totals` — pontuação de desafios é independente de lotes
- Dados armazenados no banco — nenhum registro é alterado, apenas a apresentação
- Frontend/dashboard — nenhuma mudança necessária, a API já retornará valores corretos
- Totais acumulados globais (`pontos_ultimate_totais_por_clan`) — esses já são sempre múltiplos
  de 10 porque são calculados apenas quando lotes completos são fechados

---

## Verificação

1. Executar `pytest backend/tests/` — todos os testes devem passar
2. Testar no dashboard com período que contenha registros de coaching em grupo incompletos:
   - Clã com 1–4 registros de grupo no período → deve mostrar 0 (ou total sem grupo)
   - Clã com 5+ registros de grupo → deve mostrar múltiplo de 30
3. Verificar que totais de coaching individual (30 pts) e pro-bono (10 pts) não são afetados
