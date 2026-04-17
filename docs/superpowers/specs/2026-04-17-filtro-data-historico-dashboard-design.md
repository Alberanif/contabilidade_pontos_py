# Spec: Filtro de Data Histórico no Dashboard

**Data:** 2026-04-17
**Status:** Aprovado

## Resumo

Adicionar um campo "Ver ranking até [data]" no Dashboard para que o usuário visualize o estado cumulativo dos rankings de clãs e coaches como estava até uma data específica. O filtro é baseado na data em que os registros foram adicionados às planilhas do Google Sheets (coluna K para clientes pagantes, coluna J para pro-bono). O mesmo filtro incorpora pontos de desafios cuja data (`desafios.data`) está dentro do corte.

## Comportamento esperado

- **Sem filtro:** comportamento atual — rankings mostram totais pré-computados em `pontos_ultimate_totais_por_clan` e `pontos_ultimate_totais_por_coach`.
- **Com filtro (data corte = X):** rankings são recalculados on-demand somando apenas registros com `data_registro <= X`. Pontos de desafios com `desafios.data <= X` também são somados aos clãs.
- Registros com `data_registro = NULL` (data inválida ou não parseável) são excluídos do histórico filtrado.
- O filtro **não altera** nenhum dado persistido — é somente leitura.

## Fontes de data

| Planilha | ID | Coluna | Índice |
|---|---|---|---|
| Clientes pagantes | `1CHTQqKafa4KBQg93YWPL3_D8DNlrGIPCpywDs1HjRt8` | K | 10 |
| Pro-bono | `1BPrUeE-i5u-DgzvZh6F7cTR95exSSbPZkQaon9sfMIQ` | J | 9 |

Formato de data nas planilhas: `03/03/2026 00:38:24`. A função `_parse_date` em `points_engine.py` já trata esse formato via regex `(\d{1,2})/(\d{1,2})/(\d{4})`.

## Arquitetura

### 1. Banco de dados (Supabase)

**Migração:** Adicionar coluna `data_registro DATE NULL` em `pontos_ultimate_registros_contabilizados`.

**Backfill (endpoint único):** `POST /api/contabilidade/preencher-datas`
- Re-busca ambas as planilhas no Google Sheets
- Para cada linha, computa o hash e localiza o registro no banco
- Atualiza `data_registro` com o valor parseado da col K ou J
- Registros sem correspondência no banco ficam sem alteração
- Idempotente: pode ser executado múltiplas vezes sem efeito colateral

**Going forward:** Todo novo registro inserido via `build_record_data` já carrega `data_registro` populado.

### 2. Backend — `points_engine.py`

Adicionar parâmetro `date_col: int | None = None` em `build_record_data`. Se fornecido, parseia `row[date_col]` com `_parse_date` e inclui `"data_registro"` no dict retornado (como string ISO `"YYYY-MM-DD"` ou omitido se None).

### 3. Backend — `contabilidade.py`

- `_build_and_insert` passa `date_col=config.COL_DATE_PAYING` (índice 10)
- `_build_and_insert_pro_bono` passa `date_col=config.COL_DATE_PRO_BONO` (índice 9)

### 4. Backend — `supabase_client.py`

Três novas funções:

```python
def get_historico_clan_totals(ate: date) -> dict[str, int]:
    # SELECT clan, SUM(pontos) FROM registros
    # WHERE status='contabilizado' AND data_registro <= ate
    # GROUP BY clan

def get_historico_coach_totals(ate: date) -> dict[str, int]:
    # SELECT coach, SUM(pontos_coach) FROM registros
    # WHERE status_coach='contabilizado' AND data_registro <= ate
    # GROUP BY coach

def get_historico_desafio_totals(ate: date) -> dict[str, int]:
    # 1. Busca desafios WHERE data <= ate AND contabilizar_pontos = true
    # 2. Busca desafio_registros WHERE desafio_id IN (ids encontrados)
    # 3. Agrega total_pontos por clan em Python
```

### 5. Backend — novo endpoint

`GET /api/dashboard/historico?ate=YYYY-MM-DD` em `contabilidade.py`:
- Valida o parâmetro `ate` (400 se ausente ou formato inválido)
- Chama as três funções acima
- Combina pontos de registros + desafios por clã
- Retorna:

```json
{
  "clans": { "CLÃ 1": 120, "CLÃ 2": 90 },
  "coaches": { "Nome Coach": 150 }
}
```

### 6. Frontend — `client.ts`

```typescript
export interface HistoricoResponse {
  clans: Record<string, number>;
  coaches: Record<string, number>;
}

export function fetchHistorico(ate: string): Promise<HistoricoResponse> {
  return request(`/api/dashboard/historico?ate=${ate}`);
}
```

### 7. Frontend — `Dashboard.tsx`

- Estado `dataCorte: string` (string ISO ou vazia)
- Campo `<input type="date">` com label "Ver ranking até:" acima dos rankings
- Botão "Limpar" para remover o filtro
- Sem filtro → comportamento atual (`fetchClans()` + `fetchCoaches()`)
- Com filtro → `fetchHistorico(dataCorte)` substitui os dados dos rankings de clãs e coaches
- Os cards "Pontos por Clã" no topo também refletem o filtro
- Banner visual ("Visualizando histórico até DD/MM/YYYY") indica que não é o estado atual
- A aba de desafios não é afetada visualmente (pontos de desafios já são incorporados no total de clãs do histórico)

## Fluxo de dados (modo filtrado)

```
Usuário seleciona data X no Dashboard
  → fetchHistorico("2026-04-15")
    → GET /api/dashboard/historico?ate=2026-04-15
      → get_historico_clan_totals(date(2026,4,15))    → soma pontos de registros
      → get_historico_desafio_totals(date(2026,4,15)) → soma pontos de desafios
      → combina por clã
      → get_historico_coach_totals(date(2026,4,15))   → soma pontos de coaches
    ← { clans: {...}, coaches: {...} }
  → Dashboard atualiza rankings com os valores históricos
```

## Tratamento de edge cases

- Registros com data inválida (`data_registro = NULL`): excluídos do histórico filtrado
- Data futura: retorna os mesmos dados que o estado atual (todos os registros existentes têm data ≤ futuro)
- Parâmetro `ate` mal formatado: retorna HTTP 400
- Sem registros no período: retorna `{"clans": {}, "coaches": {}}` — frontend exibe "Nenhum dado neste período"

## O que não muda

- O processo de contabilidade (`/executar`, `/reprocessar`, etc.) não é alterado
- Totais pré-computados nas tabelas `pontos_ultimate_totais_por_clan` e `pontos_ultimate_totais_por_coach` continuam sendo a fonte de verdade para o dashboard sem filtro
- Nenhuma alteração em `desafios`, `desafio_campos` ou `desafio_registros`
