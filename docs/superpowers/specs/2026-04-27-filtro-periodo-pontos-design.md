# Filtro de Período para Ranking de Pontos

**Data:** 2026-04-27  
**Status:** Aprovado

## Contexto

O sistema possui um filtro de data com uma única data de corte (`ate`) que usa uma abordagem de "subtrair do total atual". O usuário precisa de um filtro por **intervalo** (início + fim) que exiba **apenas** os pontos contabilizados dentro do período selecionado. A abordagem de subtração é substituída por uma de **soma direta dentro do intervalo**, que é mais simples, correta e não depende da consistência dos totais acumulados.

Esta mesma regra se aplica aos pontos de desafios: um desafio só contribui para o ranking do período se sua `data` estiver dentro do intervalo selecionado.

## Arquitetura

```
Frontend (Dashboard.tsx)
  ↓ dois date pickers: "De:" e "Até:" (ambos obrigatórios)
  ↓ fetch disparado somente quando os dois estão preenchidos

API endpoint
  GET /api/contabilidade/historico?inicio=YYYY-MM-DD&fim=YYYY-MM-DD

Supabase queries (supabase_client.py)
  SUM pontos WHERE data_registro >= inicio AND data_registro <= fim
  SUM pontos_coach WHERE data_registro >= inicio AND data_registro <= fim
  SUM desafio_registros.total_pontos WHERE desafio.data BETWEEN inicio AND fim
  → HistoricoResponse { clans: dict[str, int], coaches: dict[str, int] }
```

## Backend

### `supabase_client.py`

Substituir as 3 funções `get_historico_*` por 3 funções `get_period_*`:

**`get_period_clan_totals(inicio: date, fim: date) -> dict[str, int]`**
- `SELECT clan, SUM(pontos) FROM pontos_ultimate_registros_contabilizados WHERE data_registro >= inicio AND data_registro <= fim AND status = 'contabilizado' GROUP BY clan`
- Retorna `{}` (dict vazio) se nenhum registro encontrado no período

**`get_period_coach_totals(inicio: date, fim: date) -> dict[str, int]`**
- Mesmo padrão com coluna `pontos_coach` e `status_coach = 'contabilizado'`

**`get_period_desafio_totals(inicio: date, fim: date) -> dict[str, int]`**
- Busca desafios com `data >= inicio AND data <= fim AND contabilizar_pontos = true`
- Busca `desafio_registros` correspondentes
- Agrega `total_pontos` por clan em Python
- Retorna `{}` se nenhum desafio no período

### `routers/contabilidade.py`

Endpoint `/historico` atualizado:

```
GET /api/contabilidade/historico?inicio=YYYY-MM-DD&fim=YYYY-MM-DD
```

- HTTP 400 se `inicio` ou `fim` ausentes ou com formato inválido
- HTTP 400 se `inicio > fim`
- Chama `get_period_clan_totals`, `get_period_desafio_totals`, `get_period_coach_totals`
- Mescla clan points + desafio points (soma os dicts)
- Retorna `HistoricoResponse { clans, coaches }` — clans/coaches sem registros no período **não aparecem** no dict (chaves ausentes); o frontend trata ausência como `0`

## Frontend

### `frontend/src/api/client.ts`

```typescript
// Assinatura atualizada:
export function fetchHistorico(inicio: string, fim: string): Promise<HistoricoResponse>
// URL: /api/contabilidade/historico?inicio=${inicio}&fim=${fim}
```

### `frontend/src/pages/Dashboard.tsx`

- **Estado:** `dataInicio: string` e `dataFim: string` (ambos iniciam vazios)
- **Trigger:** fetch disparado somente quando `dataInicio && dataFim` ambos preenchidos
- **Validação:** se `dataInicio > dataFim`, não dispara o fetch (exibe aviso inline)
- **Layout dos filtros:** `[De: ____] [Até: ____] [Limpar filtro]` na mesma linha
- **Banner:** `"Visualizando período de DD/MM/YYYY até DD/MM/YYYY"`
- **Limpar filtro:** reseta `dataInicio`, `dataFim` e `historicoData` para o estado inicial

## Verificação

1. Selecionar um período de 15 dias com registros conhecidos → ranking exibe apenas pontos desse período
2. Selecionar um período sem nenhum registro → todos os clans aparecem com `0` pontos
3. Selecionar um período que inclui a data de um desafio → pontos do desafio aparecem
4. Selecionar um período que **não** inclui a data de um desafio → pontos do desafio **não** aparecem
5. Preencher apenas uma data → fetch não é disparado
6. `inicio > fim` → aviso inline, sem chamada à API
7. Clicar "Limpar filtro" → volta ao ranking normal (totais acumulados)
