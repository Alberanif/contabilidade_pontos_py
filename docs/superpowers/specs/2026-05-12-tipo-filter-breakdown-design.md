# Design: Breakdown por Tipo nos Totais Acumulados

**Data:** 2026-05-12
**Status:** Aprovado

---

## Contexto

O endpoint `/api/contabilidade/totais-por-tipo` usa `get_tipo_clan_totals("pagante")` e `get_tipo_coach_totals("pagante")` que re-somam `pontos_ultimate_registros_contabilizados` (TABLE_REGISTROS) para calcular totais por tipo. Entretanto, os totais oficiais exibidos em "Todos" vêm de `pontos_ultimate_totais_por_clan` (TABLE_TOTAIS), que é semeado a partir da planilha de ranking externa.

Após uma recontagem (importar-inicial com planilha de ranking atualizada), TABLE_TOTAIS tem valores corretos (menores), mas TABLE_REGISTROS ainda reflete todos os registros históricos — dando valores mais altos e incorretos ao filtro "Pagantes".

**Regra de negócio:** O filtro "Pagantes" / "Pro Bono" sem intervalo de datas deve exibir valores consistentes com os totais oficiais, não re-somar registros históricos.

---

## Solução

Adicionar colunas `total_pagante` e `total_pro_bono` a `pontos_ultimate_totais_por_clan` e `pontos_ultimate_totais_por_coach`. Todos os caminhos que incrementam TABLE_TOTAIS passam a rastrear a origem pagante/pro-bono dos pontos. O filtro sem datas lê essas colunas; o filtro com datas continua usando TABLE_REGISTROS (comportamento correto para análise de período).

---

## Migração de Schema

```sql
ALTER TABLE pontos_ultimate_totais_por_clan
  ADD COLUMN IF NOT EXISTS total_pagante  INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_pro_bono INT NOT NULL DEFAULT 0;

ALTER TABLE pontos_ultimate_totais_por_coach
  ADD COLUMN IF NOT EXISTS total_pagante  INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS total_pro_bono INT NOT NULL DEFAULT 0;
```

---

## Fórmula de Seed em `importar_inicial`

```
total_pagante = max(0, official_total_from_ranking - pro_bono_records_sum - desafio_sum)
total_pro_bono = pro_bono_records_sum
```

Garante: `total_pagante + total_pro_bono + desafios ≈ official_total`.

---

## Comportamento dos filtros pós-correção

| Cenário | Fonte de dados |
|---|---|
| "Pagantes" sem datas | `TABLE_TOTAIS.total_pagante` |
| "Pro Bono" sem datas | `TABLE_TOTAIS.total_pro_bono` |
| "Pagantes" com datas | `TABLE_REGISTROS` por período (igual a hoje) |
| "Pro Bono" com datas | `TABLE_REGISTROS` por período (igual a hoje) |
| "Desafios" qualquer | Tabelas de desafios (sem mudança) |
| "Todos" qualquer | Igual a hoje |

---

## Funções Modificadas

### `backend/supabase_client.py`

| Função | Mudança |
|---|---|
| `upsert_clan_total` | Novos parâmetros opcionais `total_pagante`, `total_pro_bono` |
| `upsert_coach_total` | Novos parâmetros opcionais `total_pagante`, `total_pro_bono` |
| `get_tipo_clan_totals` | Sem datas: lê `TABLE_TOTAIS.total_pagante/total_pro_bono`; com datas: comportamento atual |
| `get_tipo_coach_totals` | Mesma lógica para coaches |

### `backend/routers/contabilidade.py`

| Endpoint | Mudança |
|---|---|
| `executar_contabilidade` | Separa `pagante_new` de `pro_bono_clan_pts`; passa breakdown para `upsert_clan_total` |
| `aprovar_clan` | Incrementa `total_pagante` (lotes de grupo são sempre pagante) |
| `aprovar_coach` | Incrementa `total_pagante` (lotes de grupo são sempre pagante) |
| `importar_inicial` | Calcula `pro_bono_by_clan` e `desafio_by_clan`; semeia `total_pagante`/`total_pro_bono` |

---

## Fora do Escopo

- Frontend/Dashboard — nenhuma mudança necessária (API já retornará valores corretos)
- Dados armazenados — nenhum registro é alterado, apenas os totais acumulados
- Filtro por período (com datas) — continua usando TABLE_REGISTROS sem alteração
- Desafios — tabelas próprias, sem alteração
