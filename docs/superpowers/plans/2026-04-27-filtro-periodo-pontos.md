# Filtro de Período para Ranking de Pontos — Plano de Implementação

> **Para agentes:** Use superpowers:subagent-driven-development ou superpowers:executing-plans para implementar este plano task-by-task.

**Objetivo:** Substituir o filtro de data única (`ate`) por um filtro de período (início + fim) que soma pontos dentro do intervalo selecionado.

**Arquitetura:** Substituir as 3 funções `get_historico_*` por 3 funções `get_period_*` que somam diretamente no intervalo (ao invés de subtrair do total atual). O endpoint `/historico` será atualizado para aceitar `inicio` e `fim`. O frontend passa a ter dois date pickers obrigatórios.

**Tech Stack:** Python/FastAPI, Supabase PostgREST, React/TypeScript, TailwindCSS

---

### Task 1: Implementar `get_period_clan_totals` em supabase_client.py

**Arquivos:**
- Modificar: `backend/supabase_client.py`

- [ ] **Passo 1: Ler a função `get_historico_clan_totals` atual (linhas ~499-520)**

Verificar estrutura: como faz a query, como estrutura o retorno.

- [ ] **Passo 2: Adicionar nova função `get_period_clan_totals`**

Adicionar após as funções `get_historico_*` existentes:

```python
def get_period_clan_totals(self, inicio: date, fim: date) -> dict[str, int]:
    """
    Sum all pontos for records within the period [inicio, fim].
    Returns dict[clan_name, total_pontos].
    """
    query = (
        self.client.table("pontos_ultimate_registros_contabilizados")
        .select("clan, pontos")
        .gte("data_registro", inicio.isoformat())
        .lte("data_registro", fim.isoformat())
        .eq("status", "contabilizado")
    )
    records = query.execute().data
    
    totals = {}
    for record in records:
        clan = record["clan"]
        totals[clan] = totals.get(clan, 0) + record["pontos"]
    
    return totals
```

- [ ] **Passo 3: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat(supabase): add get_period_clan_totals function"
```

---

### Task 2: Implementar `get_period_coach_totals` em supabase_client.py

**Arquivos:**
- Modificar: `backend/supabase_client.py`

- [ ] **Passo 1: Adicionar função `get_period_coach_totals`**

Adicionar após `get_period_clan_totals`:

```python
def get_period_coach_totals(self, inicio: date, fim: date) -> dict[str, int]:
    """
    Sum all pontos_coach for records within the period [inicio, fim].
    Returns dict[coach_name, total_pontos_coach].
    """
    query = (
        self.client.table("pontos_ultimate_registros_contabilizados")
        .select("coach, pontos_coach")
        .gte("data_registro", inicio.isoformat())
        .lte("data_registro", fim.isoformat())
        .eq("status_coach", "contabilizado")
    )
    records = query.execute().data
    
    totals = {}
    for record in records:
        coach = record["coach"]
        if coach:  # Ignore null coaches
            totals[coach] = totals.get(coach, 0) + record["pontos_coach"]
    
    return totals
```

- [ ] **Passo 2: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat(supabase): add get_period_coach_totals function"
```

---

### Task 3: Implementar `get_period_desafio_totals` em supabase_client.py

**Arquivos:**
- Modificar: `backend/supabase_client.py`

- [ ] **Passo 1: Adicionar função `get_period_desafio_totals`**

Adicionar após `get_period_coach_totals`:

```python
def get_period_desafio_totals(self, inicio: date, fim: date) -> dict[str, int]:
    """
    Sum desafio points for desafios within the period [inicio, fim].
    Only includes desafios with contabilizar_pontos=true.
    Returns dict[clan_name, total_pontos].
    """
    # Fetch desafios in the period
    desafios_query = (
        self.client.table("desafios")
        .select("id")
        .gte("data", inicio.isoformat())
        .lte("data", fim.isoformat())
        .eq("contabilizar_pontos", True)
    )
    desafios = desafios_query.execute().data
    desafio_ids = [d["id"] for d in desafios]
    
    if not desafio_ids:
        return {}
    
    # Fetch desafio_registros for those desafios
    registros_query = (
        self.client.table("desafio_registros")
        .select("clan, total_pontos")
        .in_("desafio_id", desafio_ids)
    )
    registros = registros_query.execute().data
    
    totals = {}
    for registro in registros:
        clan = registro["clan"]
        totals[clan] = totals.get(clan, 0) + registro["total_pontos"]
    
    return totals
```

- [ ] **Passo 2: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat(supabase): add get_period_desafio_totals function"
```

---

### Task 4: Atualizar endpoint `/historico` em contabilidade.py

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py` (linhas ~952-976)

- [ ] **Passo 1: Ler o endpoint atual `/historico`**

Verificar assinatura, validação, retorno.

- [ ] **Passo 2: Substituir implementação do endpoint**

Trocar:

```python
@router.get("/historico")
async def historico(ate: str = Query(...)):
    # Old implementation: subtract-from-current
```

Por:

```python
@router.get("/historico")
async def historico(inicio: str = Query(...), fim: str = Query(...)):
    """
    Get ranking for a date period [inicio, fim].
    Both dates required, ISO format (YYYY-MM-DD).
    Returns summed points within period for clans and coaches.
    """
    # Validate both params present
    if not inicio or not fim:
        raise HTTPException(status_code=400, detail="inicio and fim are required")
    
    try:
        inicio_date = datetime.fromisoformat(inicio).date()
        fim_date = datetime.fromisoformat(fim).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Validate inicio <= fim
    if inicio_date > fim_date:
        raise HTTPException(status_code=400, detail="inicio must be <= fim")
    
    # Get period totals
    clan_totals = supabase.get_period_clan_totals(inicio_date, fim_date)
    desafio_totals = supabase.get_period_desafio_totals(inicio_date, fim_date)
    coach_totals = supabase.get_period_coach_totals(inicio_date, fim_date)
    
    # Merge clan points + desafio points
    all_clans = set(clan_totals.keys()) | set(desafio_totals.keys())
    merged_clans = {}
    for clan in all_clans:
        merged_clans[clan] = clan_totals.get(clan, 0) + desafio_totals.get(clan, 0)
    
    return HistoricoResponse(clans=merged_clans, coaches=coach_totals)
```

- [ ] **Passo 3: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat(contabilidade): update /historico endpoint to period-based filtering"
```

---

### Task 5: Remover funções `get_historico_*` antigas

**Arquivos:**
- Modificar: `backend/supabase_client.py`

- [ ] **Passo 1: Encontrar e remover as 3 funções antigas**

Procurar por `get_historico_clan_totals`, `get_historico_coach_totals`, `get_historico_desafio_totals` e deletar.

- [ ] **Passo 2: Verificar se algum arquivo ainda as referencia**

```bash
grep -r "get_historico" backend/
```

Se houver referências, atualizar para as novas funções.

- [ ] **Passo 3: Commit**

```bash
git add backend/supabase_client.py
git commit -m "refactor(supabase): remove old get_historico_* functions"
```

---

### Task 6: Testar endpoint `/historico` no backend

**Arquivos:**
- Nenhum (manual testing)

- [ ] **Passo 1: Iniciar o servidor backend localmente**

```bash
cd backend
python main.py
```

(ou conforme o projeto está configurado para dev)

- [ ] **Passo 2: Testar com curl ou Postman**

```bash
# Test with a known period (adjust dates to your test data)
curl "http://localhost:8000/api/contabilidade/historico?inicio=2026-04-01&fim=2026-04-30"
```

Verificar:
- Status 200
- Response: `{ "clans": { "clan1": 100, ... }, "coaches": { "coach1": 50, ... } }`
- Se período vazio: `{ "clans": {}, "coaches": {} }`

- [ ] **Passo 3: Testar validação (deve retornar 400)**

```bash
# Missing fim
curl "http://localhost:8000/api/contabilidade/historico?inicio=2026-04-01"

# inicio > fim
curl "http://localhost:8000/api/contabilidade/historico?inicio=2026-04-30&fim=2026-04-01"

# Invalid date format
curl "http://localhost:8000/api/contabilidade/historico?inicio=01-04-2026&fim=30-04-2026"
```

Todos devem retornar 400.

- [ ] **Passo 4: Commit (nenhum arquivo mudou, mas registra conclusão)**

```bash
git commit --allow-empty -m "test: verify /historico endpoint with period filtering"
```

---

### Task 7: Atualizar `fetchHistorico` em client.ts

**Arquivos:**
- Modificar: `frontend/src/api/client.ts` (linhas ~202-208)

- [ ] **Passo 1: Encontrar a função atual `fetchHistorico`**

```typescript
export function fetchHistorico(ate: string): Promise<HistoricoResponse> {
  return request(`/api/contabilidade/historico?ate=${encodeURIComponent(ate)}`);
}
```

- [ ] **Passo 2: Substituir assinatura e implementação**

```typescript
export function fetchHistorico(inicio: string, fim: string): Promise<HistoricoResponse> {
  return request(
    `/api/contabilidade/historico?inicio=${encodeURIComponent(inicio)}&fim=${encodeURIComponent(fim)}`
  );
}
```

- [ ] **Passo 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(client): update fetchHistorico to accept period (inicio, fim)"
```

---

### Task 8: Atualizar UI de filtro de data em Dashboard.tsx

**Arquivos:**
- Modificar: `frontend/src/pages/Dashboard.tsx`

- [ ] **Passo 1: Atualizar estado para duas datas**

Encontrar onde está `dataCorte` (lines ~33-92) e substituir por:

```typescript
const [dataInicio, setDataInicio] = useState<string>("");
const [dataFim, setDataFim] = useState<string>("");
```

- [ ] **Passo 2: Substituir o único date input por dois**

Encontrar o `<input type="date">` atual (lines ~151-182) e substituir o bloco inteiro por:

```tsx
<div className="flex gap-4 items-end">
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-2">
      De:
    </label>
    <input
      type="date"
      value={dataInicio}
      onChange={(e) => setDataInicio(e.target.value)}
      className="px-4 py-2 border border-gray-300 rounded-lg"
    />
  </div>
  <div>
    <label className="block text-sm font-medium text-gray-700 mb-2">
      Até:
    </label>
    <input
      type="date"
      value={dataFim}
      onChange={(e) => setDataFim(e.target.value)}
      className="px-4 py-2 border border-gray-300 rounded-lg"
    />
  </div>
  <button
    onClick={() => {
      setDataInicio("");
      setDataFim("");
      setHistoricoData(null);
    }}
    className="px-4 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400"
  >
    Limpar filtro
  </button>
</div>
```

- [ ] **Passo 3: Atualizar lógica de fetch**

Encontrar onde `loadHistorico(val)` é chamado e substituir por:

```typescript
const applyPeriodFilter = async () => {
  if (!dataInicio || !dataFim) {
    return; // Don't fetch if either date is empty
  }
  
  if (dataInicio > dataFim) {
    // Optionally show an error, but don't fetch
    console.warn("Data início deve ser anterior a data fim");
    return;
  }
  
  try {
    const data = await fetchHistorico(dataInicio, dataFim);
    setHistoricoData(data);
  } catch (error) {
    console.error("Erro ao buscar histórico:", error);
  }
};

// Call this whenever either date changes
useEffect(() => {
  applyPeriodFilter();
}, [dataInicio, dataFim]);
```

(Ou implementar sem useEffect, disparando diretamente nos onChange se preferir)

- [ ] **Passo 4: Atualizar banner de período**

Encontrar o banner atual:

```tsx
{historicoData && (
  <div className="mb-4 p-3 bg-amber-100 border border-amber-400 rounded text-amber-900">
    Visualizando histórico até {formatDate(dataCorte)}
  </div>
)}
```

Substituir por:

```tsx
{historicoData && (
  <div className="mb-4 p-3 bg-amber-100 border border-amber-400 rounded text-amber-900">
    Visualizando período de {formatDate(dataInicio)} até {formatDate(dataFim)}
  </div>
)}
```

- [ ] **Passo 5: Substituir `historicoData.clans` e `historicoData.coaches` nas tabelas**

Verificar se há linhas como:

```tsx
const displayClans = historicoData ? historicoData.clans : clans;
const displayCoaches = historicoData ? historicoData.coaches : coaches;
```

Se não existirem, adicionar (para garantir que o Frontend trata chaves ausentes como 0):

```tsx
// Helper para acessar rankings com fallback a 0
const getHistoricoValue = (clan: string, isCoach: boolean = false) => {
  if (!historicoData) return null;
  if (isCoach) {
    return historicoData.coaches[clan] ?? 0;
  } else {
    return historicoData.clans[clan] ?? 0;
  }
};
```

- [ ] **Passo 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): replace single date picker with period filter (inicio/fim)"
```

---

### Task 9: Testar feature completa no navegador

**Arquivos:**
- Nenhum (manual testing)

- [ ] **Passo 1: Iniciar frontend e backend**

```bash
# Terminal 1: Backend
cd backend && python main.py

# Terminal 2: Frontend
cd frontend && npm run dev
```

- [ ] **Passo 2: Abrir Dashboard no navegador**

`http://localhost:5173` (ou porta configurada)

- [ ] **Passo 3: Testar casos (golden path)**

1. **Preenchimento obrigatório:** Preencher apenas "De:" → nenhum fetch deve ser feito (sem mudança no ranking)
2. **Período válido:** Preencher "De: 2026-04-01" e "Até: 2026-04-30" → ranking deve atualizar com pontos do período
3. **Período sem registros:** Preencher "De: 2026-01-01" e "Até: 2026-01-05" → ranking deve mostrar todos os clans com 0 pontos (ou estar vazio se nenhum desafio)
4. **Validação no frontend:** Preencher "De: 2026-04-30" e "Até: 2026-04-01" (invertido) → não deve fazer fetch, exibir aviso
5. **Limpar filtro:** Clicar "Limpar filtro" → volta ao ranking normal (totais acumulados)

- [ ] **Passo 4: Testar desafios especificamente**

1. Criar um desafio com `data = 2026-04-15` e registrar pontos
2. Filtrar "De: 2026-04-01" até "2026-04-30" → pontos do desafio devem aparecer
3. Filtrar "De: 2026-04-16" até "2026-04-30" → pontos do desafio NÃO devem aparecer
4. Filtrar "De: 2026-04-01" até "2026-04-14" → pontos do desafio NÃO devem aparecer

- [ ] **Passo 5: Testar regressão (golden path sem filtro)**

1. Remover ambas as datas (ou clicar "Limpar filtro")
2. Ranking deve voltar ao estado original (totais acumulados sem filtro)
3. Verificar se cards de clans e coaches permanecem corretos

- [ ] **Passo 6: Commit (conclusão)**

```bash
git commit --allow-empty -m "test: verify period filter feature end-to-end in browser"
```

---

## Verificação contra Spec

✅ **Arquitetura:** Três funções `get_period_*` + endpoint `/historico` atualizado  
✅ **Backend:** Validação de params, soma dentro do intervalo, mesma `HistoricoResponse`  
✅ **Frontend:** Dois date pickers obrigatórios, fetch disparado quando ambos preenchidos  
✅ **Desafios:** `get_period_desafio_totals` filtra por `data` do desafio  
✅ **Clans sem pontos:** Dict não contém chaves ausentes; frontend trata como 0  
✅ **Banner:** "Visualizando período de X até Y"  
✅ **Limpar filtro:** Reseta ambos os campos e `historicoData`  
✅ **Commits frequentes:** Um commit por função/feature major  

---

## Próximos Passos

Plano completo e salvo em `docs/superpowers/plans/2026-04-27-filtro-periodo-pontos.md`.

**Duas opções de execução:**

**1. Subagent-Driven (recomendado)** — Despacho um subagent fresco por task, review entre tasks, iteração rápida

**2. Inline Execution** — Executo tasks nesta sessão com checkpoints de review

Qual prefere?