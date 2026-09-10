# Design — Pontos de Desafio para Coaches (Fase 2)

**Data:** 2026-09-10
**Status:** Aprovado para planejamento técnico
**Base:** PR #26 (`codex/desafios-google-sheets`) — Fase 1, contabilidade de desafios via Google Sheets
**Fonte da Fase 1:** `docs/superpowers/specs/2026-08-19-contabilidade-desafios-google-sheets-prd.md`

---

## 1. Contexto

A Fase 1 fez os pontos de desafio serem lidos exclusivamente de uma Google Sheet
oficial, reconciliados por `token`. Cada token elegível (`status='active_counted'`)
vale `POINTS_PER_DESAFIO_SUBMISSION` pontos **para o clã**. O nome bruto do coach
(coluna B da planilha) já é persistido por token em `desafio_submissions_current.raw_name`,
mas **não pontua** — a Fase 1 deferiu explicitamente a pontuação individual de coach
(PRD §6, RF-14, §19.6).

Esta fase liga os pontos de desafio ao **ranking individual dos coaches**.

### 1.1 Premissa confirmada

A coluna B ("Nome") da planilha oficial de desafios é o **nome do coach** — cada
submissão validada é feita pelo próprio coach. Portanto os `POINTS_PER_DESAFIO_SUBMISSION`
pontos de um token elegível vão para o clã **e** para esse coach.

---

## 2. Princípio de design

**Resolução de identidade de coach em tempo de leitura.** O sistema de identidade de
coach já é "recalcula tudo quando um alias muda" (`reprocessar_coaches`,
`sugerir-aliases-llm` → `reprocessar_coaches`). Persistir um coach canônico por token
e reconciliar `coach_deltas` a cada ajuste de alias brigaria com esse grão.

Consequências:

- **Sem coluna nova** em `desafio_submissions_current`. Sem migração de schema.
- **Sem mudança no motor de reconciliação** (`desafio_reconciliation.py`,
  `desafio_reconciliation_store.py`, `desafio_sync_service.py`, RPC `apply_desafio_reconciliation`).
- **Sem `coach_deltas`** em `desafio_submission_versions` / `desafio_sync_runs`.
- A cada leitura, os tokens `active_counted` são agrupados por
  `coach_identity.resolve_coach(raw_name, alias_map)` — reusando
  `coach_identity.aggregate_by_canonical`.

**Fonte da verdade:** os tokens (`desafio_submissions_current`). A tabela legada
`desafio_registros_coach` deixa de ser lida em qualquer caminho.

**Datação (histórico / filtro de período):** por `submitted_at` do token, convertido
para data local de `America/Sao_Paulo` (reusa `supabase_client._submitted_at_local_date`),
tolerando `fim=None` (compat com "Travar Início"). Idêntico ao clã da Fase 1.

**Consistência do total geral do coach:** `totais_por_coach.total_pontos` (a aba
"todos" do ranking de Coaches) passa a incluir a fatia de desafio. Mantido exato por
`/executar` (após o sync) e por `/reprocessar`, simétrico ao que a Fase 1 faz para o clã.

---

## 3. Backend

### 3.1 `supabase_client.py`

**Reescritas** (hoje leem a tabela legada `desafio_registros_coach`; passam a ler tokens):

- `get_tipo_coach_totals("desafios", inicio=None, fim=None)`
  - Sem `inicio`: soma `points` de todos os tokens `active_counted`, agrupando o
    `raw_name` pelo canônico via `aggregate_by_canonical(raw_por_nome, get_coach_alias_map())`.
  - Com `inicio`: delega para `get_period_desafio_coach_totals(inicio, fim)`.
- `get_period_desafio_coach_totals(inicio, fim=None)`
  - Itera `fetch_active_counted_desafio_submissions()`; para cada linha calcula
    `local_date = _submitted_at_local_date(row["submitted_at"])`; inclui se
    `local_date is not None and local_date >= inicio and (fim is None or local_date <= fim)`.
  - Acumula `{raw_name: points}` e ao final resolve pelos canônicos.

**Nova:**

- `get_all_desafio_token_coach_names() -> set[str]` — `raw_name` distintos, não vazios,
  dos tokens `active_counted` (pagina até o fim, mesmo padrão de
  `fetch_active_counted_desafio_submissions`). Substitui `get_all_desafio_coach_names()`
  (removida na Fase 1).

**Nada volta:** `get_desafio_coach_total`, `merge_desafio_registros_coach`,
`update_desafio_importacao_linhas_coach` permanecem removidas.

### 3.2 `routers/contabilidade.py`

- **`reprocessar_coaches`**
  - `raw_coaches |= supabase_client.get_all_desafio_token_coach_names()` — redescobre
    um coach que só aparece em desafios.
  - No recálculo por coach canônico afetado:
    `desafio_pts = supabase_client.get_tipo_coach_totals("desafios").get(canonical, 0)`
    (buscar o dict uma vez, fora do laço) e
    `total_pontos = total_pagante + pb_pts + desafio_pts`.
  - `total_pagante` **não** inclui desafio (desafio é tipo próprio, como pro-bono).

- **`reprocessar_contabilidade`**
  - `desafio_totals_coach = supabase_client.get_tipo_coach_totals("desafios")`.
  - Une `set(all_coach_points) | set(desafio_totals_coach)` e
    `total = all_coach_points.get(coach, 0) + desafio_totals_coach.get(coach, 0)`.
  - Simétrico ao `desafio_totals_clan` que já existe nessa função.

- **`importar_inicial`**
  - Mesma dobra na fase de seed dos coaches (Fase 7): somar
    `get_tipo_coach_totals("desafios")` ao total de cada coach; incluir na união de coaches.

- **`sugerir_aliases_llm`**
  - `raw_coaches |= supabase_client.get_all_desafio_token_coach_names()` — nomes brutos
    de desafio entram na avaliação de alias / fila de pendentes.

- **`executar_contabilidade`**
  - Chama, **no fim** (depois de todos os upserts de coach pagante/pro-bono/grupo),
    um helper novo `_refresh_desafio_coach_totals()`, apenas quando
    `desafios_result.status == "success"` e `desafios_result.tokens_versioned > 0`.
  - Isolamento: `_refresh_desafio_coach_totals()` é envolto em `try/except` que só
    loga — uma falha aqui não derruba o `/executar` (as demais fontes já foram aplicadas).

- **`_refresh_desafio_coach_totals()`** (helper novo, chamado por `executar_contabilidade`)
  - `desafio_coach = supabase_client.get_tipo_coach_totals("desafios")`.
  - Itera **todas** as linhas de `supabase_client.list_coach_totals()` unidas às chaves
    de `desafio_coach` (para pegar coach que só existe em desafio). Para cada coach:
    `novo_total = (total_pagante or 0) + (total_pro_bono or 0) + desafio_coach.get(coach, 0)`
    e `upsert_coach_total(coach, novo_total, total_pagante=..., total_pro_bono=...,
    pessoas_em_espera=...)` preservando os breakdowns e o carry-over.
  - É idempotente e auto-corretivo: reconstrói `total_pontos` a partir dos dois
    breakdowns estáveis + a fatia de desafio recém-lida. Um coach cuja contribuição de
    desafio caiu a zero também é corrigido, porque a iteração é sobre todos os coaches,
    não só sobre `desafio_coach`.

### 3.3 `routers/desafio_auditoria.py`

- `DesafioSubmissionResponse`: `+ coach: str | None` — `resolve_coach(raw_name, alias_map)`
  resolvido na borda (buscar `get_coach_alias_map()` uma vez por request).
- `DesafioSubmissionVersionResponse`: `+ coach: str | None` — idem, a partir do
  `raw_name` da versão.
- `DesafioDetailResponse`: `+ pontos_por_coach: dict[str, int]` — soma `points` dos
  tokens `active_counted` daquele `desafio_id`, agrupados por canônico. Espelha o
  `pontos_por_clan` que já existe.

---

## 4. Frontend

### 4.1 `src/api/client.ts`

- `DesafioSubmission`, `DesafioSubmissionVersion`: `+ coach?: string | null`.
- `DesafioDetail`: `+ pontos_por_coach: Record<string, number>`.

### 4.2 `src/pages/Desafios.tsx`

- Tabela de submissões: coluna **"Coach"** entre "Clã" e "Status" (`s.coach ?? "—"`).
  Sem filtro por coach.
- Detalhe do desafio: seção **"Pontos por coach"** logo abaixo de "Pontos por clã",
  mesma estrutura de tabela (`Coach` / `Pontos`), lendo `desafioDetalhe.pontos_por_coach`.

### 4.3 `src/components/SubmissionDetail.tsx`

- Linha "Coach" (canônico) ao lado de "Nome" (bruto).

### 4.4 `src/pages/Dashboard.tsx`

- Sem mudança. A aba Coaches já tem o filtro "Desafios" e já chama
  `fetchTotaisPorTipo("desafios")`; passa a vir preenchido.

---

## 5. Migração e rollout

**Não há migração de schema** (modelo de leitura, sem coluna nova).

**Backfill dos totais existentes:** após o deploy da Fase 2, os `totais_por_coach`
ainda não têm a fatia de desafio. O procedimento é rodar **`POST /api/contabilidade/reprocessar`**
uma vez — ele reconstrói todos os totais do zero e passa a dobrar `get_tipo_coach_totals("desafios")`.
`reprocessar-coaches` sozinho só cobre coaches afetados por mudança de alias, então
não serve como backfill completo.

**Ordem em relação à migração administrativa da Fase 1**
(`admin/migrate_desafios_google_sheet --apply`): a Fase 2 é indiferente à Fase 1 já
ter migrado ou não — ela lê `desafio_submissions_current`, que só é populado pela
sincronização da Fase 1. Recomendação operacional: Fase 1 migrada e ao menos uma
sincronização bem-sucedida **antes** de rodar o `/reprocessar` da Fase 2, senão o
backfill de desafio-coach vem zerado.

**Runbook:** adicionar seção "Fase 2 — pontos de desafio para coaches" em
`docs/runbooks/sincronizacao-desafios.md` com o passo do `/reprocessar` e a validação
(soma de `pontos_por_coach` de todos os desafios == `points_per_submission` × tokens
`active_counted` com `raw_name` não vazio).

---

## 6. Testes

### 6.1 Unitários (`backend/tests/`)

- `test_desafio_token_totals.py` (existe, cobre clã) — adicionar classe para
  `get_tipo_coach_totals("desafios")` e `get_period_desafio_coach_totals`:
  - soma por canônico (dois `raw_name` → mesmo alias);
  - filtro de período por `submitted_at` em São Paulo, com `fim=None`;
  - tokens não-`active_counted` ignorados;
  - `raw_name` vazio ignorado.
- `test_reprocessar_coaches.py` — **reescrever** os testes de "blindagem" da Fase 1
  (`test_coach_que_so_existe_em_desafio_legado_nao_e_mais_fundido`,
  `test_reprocessar_coaches_nao_referencia_nenhuma_fonte_de_desafio`): agora
  `reprocessar_coaches` **deve** ler `get_all_desafio_token_coach_names()` e
  `get_tipo_coach_totals("desafios")`, e **não deve** tocar `desafio_registros_coach`.
- `test_reprocessar_inclui_desafio.py` — adicionar caso coach (hoje só clã +
  `test_reprocessar_nao_consulta_desafios_para_coach`, que passa a ser o oposto).
- `test_tipo_filter_breakdown.py` — atualizar
  `TestGetTipoCoachTotalsDesafios*` para a fonte de tokens.
- Novo `test_executar_recomputa_desafio_coach.py` — após um sync com
  `tokens_versioned > 0`, `totais_por_coach` reflete a fatia de desafio.
- `test_desafio_auditoria_router.py` — `coach` nas submissões/versões;
  `pontos_por_coach` no detalhe do desafio.

### 6.2 Integração / e2e

- `test_desafio_e2e.py` — estender o fluxo: token elegível de um coach conhecido →
  `/executar` → `totais_por_coach` e `/totais-por-tipo?tipo=desafios` (coaches)
  refletem os pontos; mudança de alias + `reprocessar-coaches` funde corretamente.

### 6.3 Frontend (`vitest`)

- `Desafios.test.tsx` — coluna "Coach" na tabela; seção "Pontos por coach" no detalhe.

### 6.4 Postgres (gated, sem infra local)

- Nenhum teste `*_postgres` novo — não há schema nem RPC novos.

---

## 7. Fora de escopo

- Coluna `coach` persistida em `desafio_submissions_current` e `coach_deltas` no
  motor de reconciliação (modelo B da P2, rejeitado).
- Filtro por coach e drill-down por coach na auditoria (P5, opção C).
- `coach` nos resultados de sincronização (`DesafioSyncResult`, `ExecutionResult.tsx`).
- Qualquer alteração no layout ou na leitura da planilha oficial.
- Reintrodução dos endpoints/UI legados de lançamento manual e CSV de desafios.

---

## 8. Riscos

| Risco | Mitigação |
|---|---|
| Nome de coach na coluna B com grafia nova → não resolve para canônico | Já coberto: entra em `sugerir_aliases_llm` e na fila de pendentes; até resolver, pontua sob o nome bruto (não some) |
| `totais_por_coach` defasado entre deploy e `/reprocessar` | Runbook obriga o `/reprocessar`; a aba "Desafios" (leitura direta) já fica exata antes disso |
| Custo de `resolve_coach` por token a cada request de total | `fetch_active_counted_desafio_submissions` já pagina tudo; resolução é dict-lookup em memória. Mesma ordem de custo do clã |
| Divergência entre `pontos_por_coach` (soma de desafios) e a fatia no `totais_por_coach` | Ambos derivam da mesma função `get_tipo_coach_totals("desafios")`; teste e2e trava |
