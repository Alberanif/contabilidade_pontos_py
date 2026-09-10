# Pontos de Desafio para Coaches (Fase 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer os pontos de desafio (tokens `active_counted` da Google Sheet oficial) contarem para o ranking individual dos coaches, resolvendo a identidade do coach a partir do nome bruto da coluna B.

**Architecture:** Resolução de identidade de coach **em tempo de leitura** sobre `desafio_submissions_current` — sem coluna nova, sem mudança no motor de reconciliação (`desafio_reconciliation*.py`, RPC `apply_desafio_reconciliation`), sem `coach_deltas`. As funções de agregação de totais de coach por tipo `desafios` passam a ler os tokens e agrupar por `coach_identity.resolve_coach(raw_name, alias_map)`. O total geral do coach (`totais_por_coach.total_pontos`) é mantido exato por um helper chamado ao fim de `/executar` e `/confirmar-desafios`, e pelas rotinas de rebuild (`/reprocessar`, `/importar-inicial`).

**Tech Stack:** Python 3.12 / FastAPI, Supabase (PostgREST via `supabase-py`), React + TypeScript + Vite, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-09-10-desafios-coach-pontos-fase2-design.md`

## Global Constraints

- **Branch:** `codex/desafios-google-sheets-fase2` (já criada, a partir do topo do PR #26). Todo commit vai nela.
- **Python de teste:** `"C:/Users/artif/Documents/IGT/CONTABILIDADE PONTOS/contabilidade_pontos_py/venv/Scripts/python.exe"` — referido abaixo como `$PY`. Rodar pytest a partir de `backend/` no worktree (`.../.worktrees/desafios-google-sheets/backend`).
- **Frontend:** rodar a partir de `frontend/` no worktree. `npx --no-install vitest run <arquivo>` e `npx --no-install tsc -b`.
- **Fonte da verdade dos pontos de desafio (clã e coach):** os tokens em `desafio_submissions_current` com `status='active_counted'`. A tabela legada `desafio_registros_coach` **não** é lida em nenhum caminho novo.
- **Datação de período:** `submitted_at` do token → data de calendário em `America/Sao_Paulo` via `supabase_client._submitted_at_local_date`. `fim=None` significa "sem limite superior".
- **Resolução de coach:** sempre `coach_identity.resolve_coach(raw_name.strip(), alias_map)`; `raw_name` vazio → o token não pontua para coach algum (é ignorado, não vira "DESCONHECIDO").
- **`total_pagante` do coach nunca inclui desafio** — desafio é um tipo próprio, como pro-bono. `total_pontos = total_pagante + total_pro_bono + desafio`.
- **Motor de reconciliação permanece sem `coach_deltas`.** Nada em `desafio_reconciliation.py` / `desafio_reconciliation_store.py` / `desafio_sync_service.py` / migrations muda.
- Commits frequentes, um por task no mínimo. Mensagens em português, prefixo `feat:` / `test:` / `docs:`.
- Rodapé de commit (obrigatório em todo commit):
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss
  ```

---

## Mapa de arquivos

| Arquivo | Responsabilidade | Tasks |
|---|---|---|
| `backend/supabase_client.py` | Agregações de leitura: coach-desafio a partir de tokens; descoberta de nomes brutos; total por desafio | 1, 2 |
| `backend/routers/contabilidade.py` | Dobrar desafio-coach nos rebuilds; descoberta de coach; helper de refresh; merge no histórico | 3, 4, 5, 6, 7 |
| `backend/routers/desafio_auditoria.py` | Expor `coach` (canônico) por submissão/versão e `pontos_por_coach` no detalhe | 8 |
| `frontend/src/api/client.ts` | Tipos `coach` / `pontos_por_coach` | 9 |
| `frontend/src/pages/Desafios.tsx` | Coluna "Coach" e seção "Pontos por coach" | 10 |
| `frontend/src/components/SubmissionDetail.tsx` | Linha "Coach" (canônico) no detalhe do token | 11 |
| `backend/tests/test_desafio_e2e.py` | Fluxo e2e coach | 12 |
| `docs/runbooks/sincronizacao-desafios.md` | Seção de rollout da Fase 2 | 13 |

---

## Task 1: `supabase_client` — agregação coach-desafio a partir dos tokens

**Files:**
- Modify: `backend/supabase_client.py` (imports no topo ~linha 1-5; `get_period_desafio_coach_totals` linhas 1098-1132; `get_tipo_coach_totals` bloco `tipo == "desafios"` linhas 1211-1235; adicionar helper e `get_all_desafio_token_coach_names` perto de `fetch_active_counted_desafio_submissions`)
- Test: `backend/tests/test_desafio_token_totals.py` (classe `TestNenhumaContribuicaoDeCoachNessesRelatorios` linhas 356-429 é **substituída**; adicionar classe nova de agregação de coach)

**Interfaces:**
- Consumes: `fetch_active_counted_desafio_submissions() -> list[dict]` (existe), `_submitted_at_local_date(raw) -> date | None` (existe), `get_coach_alias_map() -> dict[str,str]` (existe), `coach_identity.aggregate_by_canonical(raw_points: dict[str,int], alias_map) -> dict[str,int]` (existe).
- Produces:
  - `get_period_desafio_coach_totals(inicio: date, fim: date | None = None) -> dict[str, int]` — canônico → pontos, tokens `active_counted` cuja data local SP cai em `[inicio, fim]`.
  - `get_tipo_coach_totals("desafios", inicio=None, fim=None)` — sem `inicio`: todos os ativos; com `inicio`: delega.
  - `get_all_desafio_token_coach_names() -> set[str]` — `raw_name` distintos, não vazios (aparados), dos tokens `active_counted`.

- [ ] **Step 1: Escrever os testes que falham**

Substituir a classe `TestNenhumaContribuicaoDeCoachNessesRelatorios` (linhas 356-429 de `backend/tests/test_desafio_token_totals.py`) por:

```python
class TestGetTipoCoachTotalsDesafiosLeDosTokens:
    """Fase 2: get_tipo_coach_totals('desafios') e get_period_desafio_coach_totals
    agregam os tokens active_counted de desafio_submissions_current por coach
    canônico (coluna B / raw_name), e nunca tocam a tabela legada
    desafio_registros_coach."""

    def _rows(self):
        return [
            {"token": "T1", "raw_name": "Ana Albertim", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-10T13:00:00-03:00"},
            {"token": "T2", "raw_name": "ana  albertim", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-20T13:00:00-03:00"},
            {"token": "T3", "raw_name": "Bruno Costa", "points": 10,
             "status": "active_counted", "submitted_at": "2026-06-01T13:00:00-03:00"},
            {"token": "T4", "raw_name": "", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-15T13:00:00-03:00"},
        ]

    def test_sem_data_soma_todos_agrupando_por_canonico(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}):
            result = supabase_client.get_tipo_coach_totals("desafios")
        assert result == {"Ana Albertim": 20, "Bruno Costa": 10}

    def test_raw_name_vazio_e_ignorado(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[{"token": "X", "raw_name": "   ", "points": 10,
                                  "status": "active_counted",
                                  "submitted_at": "2026-05-10T13:00:00-03:00"}]), \
             patch("supabase_client.get_coach_alias_map", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {}

    def test_com_data_delega_e_filtra_por_submitted_at_local(self):
        from datetime import date
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}):
            result = supabase_client.get_tipo_coach_totals(
                "desafios", date(2026, 5, 1), date(2026, 5, 31)
            )
        assert result == {"Ana Albertim": 20}

    def test_periodo_sem_fim_conta_tudo_a_partir_do_inicio(self):
        from datetime import date
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"ana albertim": "Ana Albertim"}):
            result = supabase_client.get_period_desafio_coach_totals(date(2026, 6, 1), None)
        assert result == {"Bruno Costa": 10}

    def test_nunca_consulta_desafio_registros_coach(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=self._rows()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client._get_client",
                   side_effect=AssertionError("não deve tocar o banco legado")):
            supabase_client.get_tipo_coach_totals("desafios")


class TestGetAllDesafioTokenCoachNames:

    def test_nomes_brutos_distintos_nao_vazios(self):
        rows = [
            {"token": "A", "raw_name": "Ana", "points": 10, "status": "active_counted"},
            {"token": "B", "raw_name": "Ana", "points": 10, "status": "active_counted"},
            {"token": "C", "raw_name": "  Bruno  ", "points": 10, "status": "active_counted"},
            {"token": "D", "raw_name": "", "points": 10, "status": "active_counted"},
        ]
        with patch("supabase_client.fetch_active_counted_desafio_submissions", return_value=rows):
            assert supabase_client.get_all_desafio_token_coach_names() == {"Ana", "Bruno"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_desafio_token_totals.py -q`
Expected: FAIL — `get_period_desafio_coach_totals` ainda lê o banco legado; `get_all_desafio_token_coach_names` não existe (`AttributeError`).

- [ ] **Step 3: Implementar**

Em `backend/supabase_client.py`, no topo (junto de `import config` / `from desafio_sheet_parser import SAO_PAULO`):

```python
import coach_identity
```

Adicionar, logo após `fetch_active_counted_desafio_submissions` (linha ~487):

```python
def get_all_desafio_token_coach_names() -> set[str]:
    """Nomes brutos de coach (coluna B) distintos, não vazios, dos tokens
    `active_counted`. Base de descoberta de coach para `reprocessar_coaches`
    e `sugerir_aliases_llm` — a fonte de desafios não escreve mais em
    `desafio_registros_coach`."""
    return {
        (row.get("raw_name") or "").strip()
        for row in fetch_active_counted_desafio_submissions()
        if (row.get("raw_name") or "").strip()
    }


def _aggregate_desafio_tokens_by_coach(
    rows: list[dict], inicio: "date | None" = None, fim: "date | None" = None
) -> dict[str, int]:
    """Agrupa `points` de tokens de desafio pelo coach canônico (coluna B
    resolvida via `pontos_ultimate_coach_aliases`). Quando `inicio` é dado,
    inclui só os tokens cuja data local (São Paulo) de `submitted_at` cai em
    `[inicio, fim]` (`fim=None` = sem limite superior)."""
    raw: dict[str, int] = {}
    for row in rows:
        name = (row.get("raw_name") or "").strip()
        if not name:
            continue
        if inicio is not None:
            local_date = _submitted_at_local_date(row.get("submitted_at"))
            if local_date is None or local_date < inicio:
                continue
            if fim is not None and local_date > fim:
                continue
        raw[name] = raw.get(name, 0) + (row.get("points") or 0)
    return coach_identity.aggregate_by_canonical(raw, get_coach_alias_map())
```

Substituir o corpo inteiro de `get_period_desafio_coach_totals` (linhas 1098-1132) por:

```python
def get_period_desafio_coach_totals(inicio: date, fim: date | None = None) -> dict[str, int]:
    """
    Soma os pontos de desafio por coach a partir dos tokens `active_counted`
    de `desafio_submissions_current` cujo `submitted_at`, convertido para a data
    de calendário em América/São_Paulo, cai em `[inicio, fim]`. O coach é a
    coluna B (`raw_name`) resolvida ao nome canônico. Fase 2 — antes lia a
    tabela legada `desafio_registros_coach`.
    """
    return _aggregate_desafio_tokens_by_coach(
        fetch_active_counted_desafio_submissions(), inicio, fim
    )
```

No `get_tipo_coach_totals`, substituir o bloco `if tipo == "desafios":` (linhas 1211-1235) por:

```python
    if tipo == "desafios":
        if inicio:
            return get_period_desafio_coach_totals(inicio, fim)
        return _aggregate_desafio_tokens_by_coach(
            fetch_active_counted_desafio_submissions()
        )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_desafio_token_totals.py -q`
Expected: PASS.

- [ ] **Step 5: Regressão do módulo inteiro de totais**

Run: `cd backend && $PY -m pytest tests/test_tipo_filter_breakdown.py -q`
Expected: as classes `TestGetTipoCoachTotalsDesafios*` (linhas 152-199) vão **falhar** — elas ainda esperam a leitura do banco legado. Deixá-las falhando; a Task correspondente é o Step 6 abaixo (mesma task, mesmo commit).

- [ ] **Step 6: Atualizar `test_tipo_filter_breakdown.py`**

Substituir `TestGetTipoCoachTotalsDesafiosNoDate` e `TestGetTipoCoachTotalsDesafiosComData` (linhas 152-199) por:

```python
class TestGetTipoCoachTotalsDesafiosLeTokens:
    def test_soma_pontos_dos_tokens_por_coach_canonico(self):
        rows = [
            {"token": "T1", "raw_name": "Ana", "points": 10, "status": "active_counted",
             "submitted_at": "2026-05-10T13:00:00-03:00"},
            {"token": "T2", "raw_name": "ANA", "points": 10, "status": "active_counted",
             "submitted_at": "2026-05-11T13:00:00-03:00"},
        ]
        with patch("supabase_client.fetch_active_counted_desafio_submissions", return_value=rows), \
             patch("supabase_client.get_coach_alias_map", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 20}

    def test_com_data_delega_para_get_period_desafio_coach_totals(self):
        with patch("supabase_client.get_period_desafio_coach_totals",
                   return_value={"Ana": 30}) as mock_period:
            result = supabase_client.get_tipo_coach_totals(
                "desafios", date(2026, 5, 1), date(2026, 5, 31)
            )
        mock_period.assert_called_once_with(date(2026, 5, 1), date(2026, 5, 31))
        assert result == {"Ana": 30}
```

(o `import` de `date` já existe no topo do arquivo — confirmar; se não, `from datetime import date`.)

- [ ] **Step 7: Rodar os dois arquivos**

Run: `cd backend && $PY -m pytest tests/test_desafio_token_totals.py tests/test_tipo_filter_breakdown.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/supabase_client.py backend/tests/test_desafio_token_totals.py backend/tests/test_tipo_filter_breakdown.py
git commit -m "feat: totais de desafio por coach lidos dos tokens (Fase 2)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 2: `supabase_client.get_desafio_coach_totals(desafio_id)`

**Files:**
- Modify: `backend/supabase_client.py` (adicionar logo após `get_desafio_clan_totals`)
- Test: `backend/tests/test_desafio_auditoria_router.py` (adicionar teste unitário da função; ver também Task 8)

**Interfaces:**
- Consumes: `_get_client()`, `get_coach_alias_map()`, `coach_identity.aggregate_by_canonical`.
- Produces: `get_desafio_coach_totals(desafio_id: int) -> dict[str, int]` — coach canônico → pontos, tokens `active_counted` daquele `desafio_id`.

- [ ] **Step 1: Teste que falha**

Adicionar em `backend/tests/test_desafio_auditoria_router.py` (no fim do arquivo):

```python
def test_get_desafio_coach_totals_agrupa_por_canonico(monkeypatch):
    import supabase_client

    class _Chain:
        def __init__(self, data): self._data = data
        def select(self, *_): return self
        def eq(self, *_): return self
        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=self._data)

    rows = [
        {"raw_name": "Ana", "points": 10},
        {"raw_name": "ana", "points": 10},
        {"raw_name": "", "points": 10},
    ]
    monkeypatch.setattr(supabase_client, "_get_client",
                        lambda: SimpleNamespace(table=lambda _t: _Chain(rows)))
    monkeypatch.setattr(supabase_client, "get_coach_alias_map", lambda: {})
    from types import SimpleNamespace
    assert supabase_client.get_desafio_coach_totals(7) == {"Ana": 20}
```

(Ajustar o `import SimpleNamespace` para o topo do arquivo se o linter reclamar.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_desafio_auditoria_router.py::test_get_desafio_coach_totals_agrupa_por_canonico -q`
Expected: FAIL — `AttributeError: get_desafio_coach_totals`.

- [ ] **Step 3: Implementar**

Em `backend/supabase_client.py`, logo após `get_desafio_clan_totals`:

```python
def get_desafio_coach_totals(desafio_id: int) -> dict[str, int]:
    """Soma os pontos das submissões `active_counted` de um desafio, agrupadas
    pelo coach canônico (coluna B / `raw_name` resolvida via
    `pontos_ultimate_coach_aliases`). Espelha `get_desafio_clan_totals` no eixo
    coach (Fase 2)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_SUBMISSIONS_CURRENT)
        .select("raw_name, points")
        .eq("desafio_id", desafio_id)
        .eq("status", "active_counted")
        .execute()
    )
    raw: dict[str, int] = {}
    for row in result.data:
        name = (row.get("raw_name") or "").strip()
        if not name:
            continue
        raw[name] = raw.get(name, 0) + (row.get("points") or 0)
    return coach_identity.aggregate_by_canonical(raw, get_coach_alias_map())
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_desafio_auditoria_router.py::test_get_desafio_coach_totals_agrupa_por_canonico -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/supabase_client.py backend/tests/test_desafio_auditoria_router.py
git commit -m "feat: get_desafio_coach_totals(desafio_id) a partir dos tokens

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 3: `reprocessar_contabilidade` dobra desafio-coach

**Files:**
- Modify: `backend/routers/contabilidade.py` (`reprocessar_contabilidade`, bloco de coach linhas 983-991)
- Test: `backend/tests/test_reprocessar_inclui_desafio.py`

**Interfaces:**
- Consumes: `supabase_client.get_tipo_coach_totals("desafios") -> dict[str,int]` (Task 1).
- Produces: nenhum símbolo novo; comportamento — `totais_por_coach.total_pontos` passa a incluir a fatia de desafio.

- [ ] **Step 1: Ajustar o teste existente**

Em `backend/tests/test_reprocessar_inclui_desafio.py`, substituir `test_reprocessar_nao_consulta_desafios_para_coach` (linha ~32) por:

```python
    def test_reprocessar_soma_desafio_no_total_final_do_coach(self):
        """Fase 2: reprocessar_contabilidade mescla get_tipo_coach_totals('desafios')
        no total geral do coach (mesmo padrão do clã)."""
        with patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=[["h"]]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=[]), \
             patch("google_sheets_client.fetch_ranking", return_value=[]), \
             patch("routers.contabilidade._process_group_records",
                   return_value=(0, {}, {}, {})), \
             patch("routers.contabilidade._process_pro_bono_records",
                   return_value=(0, {}, {})), \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.get_tipo_coach_totals",
                   return_value={"Ana Albertim": 40}) as mock_tipo_coach, \
             patch("supabase_client.upsert_clan_total"), \
             patch("supabase_client.upsert_coach_total") as mock_upsert_coach:
            from routers.contabilidade import reprocessar_contabilidade
            reprocessar_contabilidade()

        mock_tipo_coach.assert_any_call("desafios")
        mock_upsert_coach.assert_any_call(
            "Ana Albertim", 40, total_pagante=0, total_pro_bono=0
        )
```

(Se as assinaturas de `_process_group_records` / `_process_pro_bono_records` no teste divergirem do arquivo, alinhar pelo que o arquivo retorna — checar `backend/routers/contabilidade.py`.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_reprocessar_inclui_desafio.py -q`
Expected: FAIL — `upsert_coach_total` não é chamado com a fatia de desafio.

- [ ] **Step 3: Implementar**

Em `backend/routers/contabilidade.py`, substituir o bloco de coach de `reprocessar_contabilidade` (linhas 983-991) por:

```python
        desafio_totals_coach = supabase_client.get_tipo_coach_totals("desafios")
        totais_finais_coach: dict[str, int] = {}
        for coach in set(all_coach_points.keys()) | set(desafio_totals_coach.keys()):
            total = all_coach_points.get(coach, 0) + desafio_totals_coach.get(coach, 0)
            totais_finais_coach[coach] = total
            supabase_client.upsert_coach_total(
                coach, total,
                total_pagante=pontos_por_coach.get(coach, 0),
                total_pro_bono=pro_bono_coach_pts.get(coach, 0),
            )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_reprocessar_inclui_desafio.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_reprocessar_inclui_desafio.py
git commit -m "feat: reprocessar_contabilidade soma pontos de desafio no total do coach

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 4: `reprocessar_coaches` + `sugerir_aliases_llm` descobrem coach dos tokens; recálculo inclui desafio

**Files:**
- Modify: `backend/routers/contabilidade.py` (`reprocessar_coaches` linhas 469-538; `sugerir_aliases_llm` linhas 602-607)
- Test: `backend/tests/test_reprocessar_coaches.py`

**Interfaces:**
- Consumes: `supabase_client.get_all_desafio_token_coach_names() -> set[str]` (Task 1), `supabase_client.get_tipo_coach_totals("desafios") -> dict[str,int]` (Task 1).
- Produces: nenhum símbolo novo. Comportamento: um coach que só aparece em desafios entra em `raw_coaches`; o recálculo de um coach afetado passa a incluir `desafio_pts`.

- [ ] **Step 1: Testes que falham**

Em `backend/tests/test_reprocessar_coaches.py`:

(a) Substituir `test_coach_que_so_existe_em_desafio_legado_nao_e_mais_fundido` (linha ~90) por:

```python
    def test_coach_que_so_existe_em_desafio_e_descoberto_e_fundido(self):
        """Fase 2: um coach cujo nome bruto só aparece nos tokens de desafio é
        descoberto por get_all_desafio_token_coach_names e resolvido ao canônico."""
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.list_all_registros", return_value=[]), \
             patch("supabase_client.list_coach_totals", return_value=[]), \
             patch("supabase_client.get_all_desafio_token_coach_names",
                   return_value={"Vini Marini"}), \
             patch("supabase_client.get_tipo_coach_totals",
                   return_value={"Vinicius Marini": 20}), \
             patch("supabase_client.update_registros_coach", return_value=0), \
             patch("supabase_client.delete_coach_total"), \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert:
            resultado = reprocessar_coaches()

        assert resultado.coaches_afetados == ["Vinicius Marini"]
        mock_upsert.assert_any_call(
            "Vinicius Marini", 20,
            pessoas_em_espera=0, total_pagante=0, total_pro_bono=0,
        )
```

(b) Substituir `test_reprocessar_coaches_nao_referencia_nenhuma_fonte_de_desafio` (linha ~110) por:

```python
    def test_reprocessar_coaches_le_tokens_de_desafio_nao_a_tabela_legada(self):
        """Fase 2: a descoberta e o recálculo de coach usam os tokens
        (get_all_desafio_token_coach_names, get_tipo_coach_totals('desafios')),
        nunca desafio_registros_coach."""
        regs_antes = [_registro("Vivian Gaspar", "Coaching Individual", 30)]
        regs_depois = [_registro("Vivian Gaspar Canonico", "Coaching Individual", 30)]

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vivian Gaspar": "Vivian Gaspar Canonico"}), \
             patch("supabase_client.list_all_registros", side_effect=[regs_antes, regs_depois]), \
             patch("supabase_client.list_coach_totals", return_value=[]), \
             patch("supabase_client.get_all_desafio_token_coach_names", return_value=set()), \
             patch("supabase_client.get_tipo_coach_totals", return_value={"Vivian Gaspar Canonico": 10}), \
             patch("supabase_client.update_registros_coach", return_value=1), \
             patch("supabase_client.delete_coach_total"), \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert:
            resultado = reprocessar_coaches()

        # 30 (CI) + 10 (desafio) = 40
        assert resultado.totais_recalculados == {"Vivian Gaspar Canonico": 40}
        mock_upsert.assert_any_call(
            "Vivian Gaspar Canonico", 40,
            pessoas_em_espera=0, total_pagante=30, total_pro_bono=0,
        )
```

(c) Nos demais testes da classe que hoje **não** mockam `get_all_desafio_token_coach_names` nem `get_tipo_coach_totals`, adicionar:
```python
             patch("supabase_client.get_all_desafio_token_coach_names", return_value=set()), \
             patch("supabase_client.get_tipo_coach_totals", return_value={}), \
```
junto dos outros `patch(...)` (testes: `test_funde_dois_alias_e_recalcula_totais`, `test_sem_alias_correspondente_nao_altera_nada`, `test_detecta_cadeia_de_alias_e_reporta_aviso`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_reprocessar_coaches.py -q`
Expected: FAIL — `get_all_desafio_token_coach_names` não é chamada; `desafio_pts` não somado.

- [ ] **Step 3: Implementar**

Em `reprocessar_coaches`, após a linha `raw_coaches |= {t["coach"] for t in supabase_client.list_coach_totals() ...}` (linha 477), substituir o comentário das linhas 475-477 e adicionar a descoberta:

```python
        all_regs = supabase_client.list_all_registros()
        raw_coaches = {r["coach"] for r in all_regs if r.get("coach")}
        raw_coaches |= {t["coach"] for t in supabase_client.list_coach_totals() if t.get("coach")}
        # Fase 2: um coach cujo nome bruto só aparece nos tokens de desafio
        # também precisa ser resolvido ao canônico.
        raw_coaches |= supabase_client.get_all_desafio_token_coach_names()
```

Antes do laço `for canonical in coaches_afetados:` (linha 508), adicionar:

```python
        desafio_coach_totals = supabase_client.get_tipo_coach_totals("desafios")
```

Dentro do laço, substituir as linhas 530-531:

```python
            total_pagante = ci_pts + group_pts
            total_pontos = total_pagante + pb_pts
```
por:
```python
            total_pagante = ci_pts + group_pts
            desafio_pts = desafio_coach_totals.get(canonical, 0)
            total_pontos = total_pagante + pb_pts + desafio_pts
```

Em `sugerir_aliases_llm`, após a linha 606 (`raw_coaches |= {t["coach"] for t in totais ...}`), adicionar:

```python
        raw_coaches |= supabase_client.get_all_desafio_token_coach_names()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_reprocessar_coaches.py tests/test_coach_identity_resolution_e2e.py tests/test_coach_llm_router.py -q`
Expected: PASS. Se `test_coach_identity_resolution_e2e.py` ou `test_coach_llm_router.py` falharem por falta do mock `get_all_desafio_token_coach_names`, adicionar `patch("supabase_client.get_all_desafio_token_coach_names", return_value=set())` no `with` desses testes.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_reprocessar_coaches.py backend/tests/test_coach_identity_resolution_e2e.py backend/tests/test_coach_llm_router.py
git commit -m "feat: reprocessar_coaches e sugerir_aliases_llm descobrem coach dos tokens de desafio

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 5: `importar_inicial` dobra desafio-coach

**Files:**
- Modify: `backend/routers/contabilidade.py` (`importar_inicial`, Fase 7, linhas 1166-1200)
- Test: `backend/tests/test_importar_inicial_coach_points.py`

**Interfaces:**
- Consumes: `supabase_client.get_tipo_coach_totals("desafios")` (Task 1).
- Produces: comportamento — o seed inicial do total do coach inclui a fatia de desafio.

- [ ] **Step 1: Teste que falha**

Ver `backend/tests/test_importar_inicial_coach_points.py` para o padrão de mock existente. Adicionar:

```python
def test_importar_inicial_soma_desafio_no_total_do_coach(...):
    # mesmo esqueleto de mock dos outros testes do arquivo, adicionando:
    #   patch("supabase_client.get_tipo_coach_totals", return_value={"Ana": 20})
    # e afirmando que upsert_coach_total foi chamado para "Ana" com total incluindo +20.
```

Reproduzir a estrutura exata de um teste vizinho do arquivo (mesmos `patch`), trocando só a asserção final para conferir que o total do coach `"Ana"` recebeu `+20` de desafio e que `get_tipo_coach_totals` foi chamada com `"desafios"`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_importar_inicial_coach_points.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Em `importar_inicial`, Fase 7. Após a linha 1171 (`pontos_por_coach = coach_identity.aggregate_by_canonical(raw_pontos_por_coach, coach_alias_map)`), adicionar:

```python
        desafio_coach_totals = supabase_client.get_tipo_coach_totals("desafios")
```

Substituir a linha 1187:
```python
        all_coaches = set(pontos_por_coach.keys()) | set(coach_group_people.keys()) | set(pro_bono_coach_pts_seed.keys())
```
por:
```python
        all_coaches = (
            set(pontos_por_coach.keys())
            | set(coach_group_people.keys())
            | set(pro_bono_coach_pts_seed.keys())
            | set(desafio_coach_totals.keys())
        )
```

Substituir as linhas 1189-1191:
```python
            ci_pts = pontos_por_coach.get(coach, 0)
            pb_pts = pro_bono_coach_pts_seed.get(coach, 0)
            total = ci_pts + pb_pts
```
por:
```python
            ci_pts = pontos_por_coach.get(coach, 0)
            pb_pts = pro_bono_coach_pts_seed.get(coach, 0)
            desafio_pts = desafio_coach_totals.get(coach, 0)
            total = ci_pts + pb_pts + desafio_pts
```

(`total_pagante=ci_pts` e `total_pro_bono=pb_pts` no `upsert_coach_total` continuam iguais — desafio não entra em nenhum breakdown.)

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_importar_inicial_coach_points.py tests/test_importar_inicial_pontos.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_importar_inicial_coach_points.py
git commit -m "feat: importar_inicial semeia pontos de desafio no total do coach

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 6: `historico` volta a mesclar desafio-coach

**Files:**
- Modify: `backend/routers/contabilidade.py` (`historico`, linhas 1391-1404)
- Test: `backend/tests/test_historico_merge_coach_desafio.py`, `backend/tests/test_travar_inicio_period.py`

**Interfaces:**
- Consumes: `supabase_client.get_period_desafio_coach_totals(inicio, fim) -> dict[str,int]` (Task 1).
- Produces: `HistoricoResponse.coaches` volta a incluir a fatia de desafio do período.

- [ ] **Step 1: Ajustar testes**

`backend/tests/test_historico_merge_coach_desafio.py` — hoje afirma que coaches **não** recebem desafio. Inverter: com `get_period_desafio_coach_totals` retornando `{"Ana": 15}` e `get_period_coach_totals` retornando `{"Ana": 30}`, o resultado deve ser `{"Ana": 45}`. Manter os patches de `get_period_clan_totals` / `get_period_desafio_totals` como estão.

`backend/tests/test_travar_inicio_period.py::test_historico_com_travar_inicio_apenas_data_inicio` — adicionar `patch("supabase_client.get_period_desafio_coach_totals", return_value={})` se ainda não houver, e conferir que é chamada com `fim=None`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_historico_merge_coach_desafio.py tests/test_travar_inicio_period.py -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Em `historico`, substituir as linhas 1402-1404:
```python
        # Pontos de coach: nenhuma fonte de desafio contribui (Global Constraint —
        # ver issue #17). merged_coaches é apenas os totais pagante/pro-bono do coach.
        merged_coaches = dict(coach_totals)
```
por:
```python
        coach_desafio_totals = supabase_client.get_period_desafio_coach_totals(
            inicio_date, fim_date
        )
        all_coaches = set(coach_totals.keys()) | set(coach_desafio_totals.keys())
        merged_coaches = {
            coach: coach_totals.get(coach, 0) + coach_desafio_totals.get(coach, 0)
            for coach in all_coaches
        }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_historico_merge_coach_desafio.py tests/test_travar_inicio_period.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_historico_merge_coach_desafio.py backend/tests/test_travar_inicio_period.py
git commit -m "feat: historico volta a mesclar pontos de desafio no total do coach por periodo

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 7: `_refresh_desafio_coach_totals` + wiring em `/executar` e `/confirmar-desafios`

**Files:**
- Modify: `backend/routers/contabilidade.py` (novo helper perto de `_sync_desafios_isolado` linha 557; `executar_contabilidade` antes do `return` da linha ~859; `confirmar_desafios` linhas 889-895)
- Test: `backend/tests/test_executar_refresh_desafio_coach.py` (novo)

**Interfaces:**
- Consumes: `supabase_client.get_tipo_coach_totals("desafios")`, `supabase_client.list_coach_totals()`, `supabase_client.upsert_coach_total(...)`.
- Produces: `_refresh_desafio_coach_totals() -> None` — módulo-privado; reconstrói `totais_por_coach.total_pontos = total_pagante + total_pro_bono + desafio` para todos os coaches.

- [ ] **Step 1: Teste que falha**

Criar `backend/tests/test_executar_refresh_desafio_coach.py`:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import patch

from routers.contabilidade import _refresh_desafio_coach_totals


def test_refresh_reconstroi_total_a_partir_dos_breakdowns_mais_desafio():
    coach_totals = [
        {"coach": "Ana", "total_pontos": 30, "total_pagante": 30,
         "total_pro_bono": 0, "pessoas_em_espera": 2},
        {"coach": "Bruno", "total_pontos": 50, "total_pagante": 40,
         "total_pro_bono": 10, "pessoas_em_espera": 0},
    ]
    with patch("supabase_client.get_tipo_coach_totals", return_value={"Ana": 20}), \
         patch("supabase_client.list_coach_totals", return_value=coach_totals), \
         patch("supabase_client.upsert_coach_total") as mock_upsert:
        _refresh_desafio_coach_totals()

    mock_upsert.assert_any_call(
        "Ana", 50, pessoas_em_espera=2, total_pagante=30, total_pro_bono=0
    )
    # Bruno não tem desafio -> total = 40 + 10 + 0, também é reescrito (auto-correção)
    mock_upsert.assert_any_call(
        "Bruno", 50, pessoas_em_espera=0, total_pagante=40, total_pro_bono=10
    )


def test_refresh_inclui_coach_que_so_tem_desafio():
    with patch("supabase_client.get_tipo_coach_totals", return_value={"Carla": 10}), \
         patch("supabase_client.list_coach_totals", return_value=[]), \
         patch("supabase_client.upsert_coach_total") as mock_upsert:
        _refresh_desafio_coach_totals()
    mock_upsert.assert_any_call(
        "Carla", 10, pessoas_em_espera=0, total_pagante=0, total_pro_bono=0
    )
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_executar_refresh_desafio_coach.py -q`
Expected: FAIL — `ImportError: cannot import name '_refresh_desafio_coach_totals'`.

- [ ] **Step 3: Implementar**

Em `backend/routers/contabilidade.py`, adicionar antes de `_sync_desafios_isolado` (linha 557):

```python
def _refresh_desafio_coach_totals() -> None:
    """Recompõe `totais_por_coach.total_pontos` incluindo a fatia de desafio
    lida ao vivo dos tokens (`get_tipo_coach_totals('desafios')`). Idempotente e
    auto-corretivo: `total = total_pagante + total_pro_bono + desafio`, iterado
    sobre todos os coaches (um coach cuja contribuição de desafio caiu a zero
    também é corrigido). Chamado ao fim de `/executar` e `/confirmar-desafios`;
    o desafio nunca entra em `total_pagante`/`total_pro_bono`."""
    desafio_coach = supabase_client.get_tipo_coach_totals("desafios")
    existentes = {r["coach"]: r for r in supabase_client.list_coach_totals()}
    for coach in set(existentes.keys()) | set(desafio_coach.keys()):
        row = existentes.get(coach, {})
        pagante = row.get("total_pagante") or 0
        pro_bono = row.get("total_pro_bono") or 0
        supabase_client.upsert_coach_total(
            coach,
            pagante + pro_bono + desafio_coach.get(coach, 0),
            pessoas_em_espera=row.get("pessoas_em_espera") or 0,
            total_pagante=pagante,
            total_pro_bono=pro_bono,
        )
```

Em `executar_contabilidade`, imediatamente antes do `return ExecutarResponse(` da linha ~859 (o `return` do caminho principal, **não** o early-return da planilha vazia):

```python
        if desafios_result.status == "success" and desafios_result.tokens_versioned > 0:
            try:
                _refresh_desafio_coach_totals()
            except Exception as e:  # noqa: BLE001 - isolamento: não derruba /executar
                print(f"[AVISO] Falha ao recompor totais de desafio-coach: {e}")

        return ExecutarResponse(
```

Em `confirmar_desafios`, substituir o corpo do `try` (linhas 889-893):

```python
    try:
        result = desafio_sync_service.sync_desafios(
            confirm_snapshot_hash=body.snapshot_hash,
            confirm_mass_removal=body.confirmar_remocao_em_massa,
        )
        if result.status == "success" and result.tokens_versioned > 0:
            try:
                _refresh_desafio_coach_totals()
            except Exception as e:  # noqa: BLE001
                print(f"[AVISO] Falha ao recompor totais de desafio-coach: {e}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_executar_refresh_desafio_coach.py tests/test_contabilidade_integration.py -q`
Expected: PASS. Se algum teste de integração de `/executar` falhar por não mockar `get_tipo_coach_totals`/`list_coach_totals` no caminho novo, adicionar os mocks (retornos `{}` / `[]`).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_executar_refresh_desafio_coach.py
git commit -m "feat: /executar e /confirmar-desafios recompoem o total de desafio do coach

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 8: Auditoria — `coach` por submissão/versão e `pontos_por_coach` no detalhe

**Files:**
- Modify: `backend/routers/desafio_auditoria.py` (imports; `DesafioSubmissionResponse` linhas 53-78; `DesafioSubmissionVersionResponse` linhas 81-104; `DesafioDetailResponse` linhas 49-50; handlers `obter_submissao` 173-179, `listar_versoes_submissao` 182-193, `obter_desafio` 199-206, `listar_submissoes_do_desafio` 209-223)
- Test: `backend/tests/test_desafio_auditoria_router.py`

**Interfaces:**
- Consumes: `coach_identity.resolve_coach`, `supabase_client.get_coach_alias_map`, `supabase_client.get_desafio_coach_totals` (Task 2).
- Produces: campos de resposta `coach: str | None` (submissão e versão) e `pontos_por_coach: dict[str,int]` (detalhe do desafio).

- [ ] **Step 1: Testes que falham**

Em `backend/tests/test_desafio_auditoria_router.py`, adicionar:

```python
def test_obter_submissao_inclui_coach_canonico(...):
    # mockar supabase_client.get_desafio_submission_current -> dict com raw_name="vini marini"
    # mockar supabase_client.get_coach_alias_map -> {"vini marini": "Vinicius Marini"}
    # GET /api/desafios/submissoes/TOK -> resp.json()["coach"] == "Vinicius Marini"

def test_obter_submissao_sem_raw_name_tem_coach_none(...):
    # raw_name="" -> resp.json()["coach"] is None

def test_obter_desafio_inclui_pontos_por_coach(...):
    # mockar get_desafio -> dict; get_desafio_clan_totals -> {}; get_desafio_coach_totals -> {"Ana": 20}
    # GET /api/desafios/1 -> resp.json()["pontos_por_coach"] == {"Ana": 20}
```

Seguir o padrão de mock/`TestClient` já usado nos testes vizinhos do arquivo.

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_desafio_auditoria_router.py -q -k coach`
Expected: FAIL — campo `coach` ausente / `pontos_por_coach` ausente.

- [ ] **Step 3: Implementar**

Em `backend/routers/desafio_auditoria.py`, nos imports:

```python
import coach_identity
```

Adicionar helper de módulo (após `_status_filtro_banco`, linha ~137):

```python
def _com_coach(row: dict, alias_map: dict[str, str]) -> dict:
    """Injeta `coach` (nome canônico da coluna B) numa linha de submissão/versão.
    `raw_name` vazio → `coach` None (não vira "DESCONHECIDO")."""
    nome = (row.get("raw_name") or "").strip()
    row["coach"] = coach_identity.resolve_coach(nome, alias_map) if nome else None
    return row
```

Modelos:
- `DesafioSubmissionResponse`: adicionar `coach: str | None = None` (após `raw_name`).
- `DesafioSubmissionVersionResponse`: adicionar `coach: str | None = None` (após `raw_name`).
- `DesafioDetailResponse`: passar a ser
  ```python
  class DesafioDetailResponse(DesafioResponse):
      pontos_por_clan: dict[str, int] = {}
      pontos_por_coach: dict[str, int] = {}
  ```

Handlers:

```python
@router.get("/submissoes/{token}", response_model=DesafioSubmissionResponse)
def obter_submissao(token: str):
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    return _com_coach(submissao, supabase_client.get_coach_alias_map())


@router.get("/submissoes/{token}/versoes", response_model=list[DesafioSubmissionVersionResponse])
def listar_versoes_submissao(token: str):
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    alias_map = supabase_client.get_coach_alias_map()
    return [_com_coach(v, alias_map) for v in supabase_client.list_desafio_submission_versions(token)]


@router.get("/{desafio_id:int}", response_model=DesafioDetailResponse)
def obter_desafio(desafio_id: int):
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return {
        **desafio,
        "pontos_por_clan": supabase_client.get_desafio_clan_totals(desafio_id),
        "pontos_por_coach": supabase_client.get_desafio_coach_totals(desafio_id),
    }


@router.get("/{desafio_id:int}/submissoes", response_model=list[DesafioSubmissionResponse])
def listar_submissoes_do_desafio(desafio_id: int, clan: str | None = None,
                                 status: str | None = None, limit: int = 100, offset: int = 0):
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    alias_map = supabase_client.get_coach_alias_map()
    return [
        _com_coach(s, alias_map)
        for s in supabase_client.list_desafio_submissions_current(
            desafio_id=desafio_id, clan=clan, status=status, limit=limit, offset=offset
        )
    ]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_desafio_auditoria_router.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/desafio_auditoria.py backend/tests/test_desafio_auditoria_router.py
git commit -m "feat: auditoria de desafios expoe coach canonico e pontos_por_coach

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 9: Tipos do frontend

**Files:**
- Modify: `frontend/src/api/client.ts` (`DesafioAuditoriaDetalhe` linha 301-303; `DesafioSubmissao` linha 308-334; `DesafioSubmissaoVersao` linha 336+)
- Test: `npx --no-install tsc -b` (sem teste dedicado; o compilador é o gate)

**Interfaces:**
- Produces: `DesafioSubmissao.coach: string | null`, `DesafioSubmissaoVersao.coach: string | null`, `DesafioAuditoriaDetalhe.pontos_por_coach: Record<string, number>`.

- [ ] **Step 1: Editar os tipos**

```ts
export interface DesafioAuditoriaDetalhe extends DesafioAuditoria {
  pontos_por_clan: Record<string, number>;
  pontos_por_coach: Record<string, number>;
}
```

Em `DesafioSubmissao`, após `raw_name: string | null;`:
```ts
  coach: string | null;
```

Em `DesafioSubmissaoVersao`, após `raw_name: string | null;`:
```ts
  coach: string | null;
```

- [ ] **Step 2: Compilar**

Run: `cd frontend && npx --no-install tsc -b`
Expected: FAIL — `Desafios.tsx` / mocks de teste que constroem `DesafioSubmissao` sem `coach` agora quebram. Isso é esperado; as Tasks 10-11 corrigem os consumidores. Se preferir, deixar este commit para o fim da Task 11 (ver Step 3).

- [ ] **Step 3: Commit (junto da Task 11)**

Não commitar isoladamente — `tsc -b` só volta a passar após as Tasks 10 e 11. Deixar as edições de tipo em stage e seguir para a Task 10.

---

## Task 10: `Desafios.tsx` — coluna "Coach" e seção "Pontos por coach"

**Files:**
- Modify: `frontend/src/pages/Desafios.tsx` (tabela de submissões ~linhas 574-604; detalhe do desafio ~linhas 518-547)
- Test: `frontend/src/pages/Desafios.test.tsx`

**Interfaces:**
- Consumes: `DesafioSubmissao.coach`, `DesafioAuditoriaDetalhe.pontos_por_coach` (Task 9).

- [ ] **Step 1: Testes que falham**

Em `frontend/src/pages/Desafios.test.tsx`:

(a) No mock de detalhe (linha ~56, onde há `pontos_por_clan: {...}`), adicionar `pontos_por_coach: { "Ana Albertim": 40 }`.

(b) No mock de submissões, adicionar `coach: "Ana Albertim"` (e `coach: null` em uma linha sem nome).

(c) Novo caso no teste de drill-in (`"drills into a desafio to show pontos_por_clan totals..."`, linha ~239):
```ts
    const pontosPorCoach = await screen.findByTestId("pontos-por-coach");
    expect(within(pontosPorCoach).getByText("Ana Albertim")).toBeInTheDocument();
    expect(within(pontosPorCoach).getByText("40")).toBeInTheDocument();
```

(d) Novo caso: a tabela de submissões mostra a coluna Coach:
```ts
  it("shows the resolved coach for each submission", async () => {
    // ... renderiza, drill-in ...
    expect(await screen.findByRole("columnheader", { name: "Coach" })).toBeInTheDocument();
    expect(screen.getByText("Ana Albertim")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx --no-install vitest run src/pages/Desafios.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Seção "Pontos por coach" — logo após o `</div>` que fecha o bloco "Pontos por clã" (linha ~547), adicionar um bloco irmão:

```tsx
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">Pontos por coach</h4>
              {Object.keys(desafioDetalhe.pontos_por_coach).length === 0 ? (
                <p className="text-gray-500 text-sm">Nenhum ponto de coach contabilizado ainda.</p>
              ) : (
                <div
                  className="bg-white rounded-xl border border-gray-200 overflow-hidden"
                  data-testid="pontos-por-coach"
                >
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                        <th className="py-2 px-4 font-medium">Coach</th>
                        <th className="py-2 px-4 font-medium text-right">Pontos</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(desafioDetalhe.pontos_por_coach).map(([coach, pontos]) => (
                        <tr key={coach} className="border-b border-gray-100">
                          <td className="py-2 px-4 font-medium text-gray-700">{coach}</td>
                          <td className="py-2 px-4 text-right font-bold text-indigo-600">
                            {pontos.toLocaleString("pt-BR")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
```

Coluna "Coach" na tabela de submissões — no `<thead>` (linha ~577-583), entre "Clã" e "Status":
```tsx
                        <th className="py-2 px-4 font-medium">Coach</th>
```
E na linha do `<tbody>` (após a `<td>` do clã, linha ~596):
```tsx
                          <td className="py-2 px-4 text-gray-700">{s.coach ?? "—"}</td>
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && npx --no-install vitest run src/pages/Desafios.test.tsx`
Expected: PASS.

- [ ] **Step 5: Não commitar ainda** — `tsc -b` ainda falha em `SubmissionDetail`/mocks. Seguir para a Task 11.

---

## Task 11: `SubmissionDetail.tsx` — linha "Coach"

**Files:**
- Modify: `frontend/src/components/SubmissionDetail.tsx` (grid de estado atual, linhas 67-84)
- Test: `frontend/src/pages/Desafios.test.tsx` (o teste de detalhe do token, linha ~292)

**Interfaces:**
- Consumes: `DesafioSubmissao.coach` (Task 9).

- [ ] **Step 1: Teste que falha**

No teste `"shows the token detail with the 9 raw A-I fields..."` (linha ~292), garantir que o mock de submissão tem `coach: "Ana Albertim"` e adicionar:
```ts
    const currentState = screen.getByTestId("current-state");
    expect(within(currentState).getByText("Coach")).toBeInTheDocument();
    expect(within(currentState).getByText("Ana Albertim")).toBeInTheDocument();
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx --no-install vitest run src/pages/Desafios.test.tsx -t "token detail"`
Expected: FAIL.

- [ ] **Step 3: Implementar**

No `<dl ... data-testid="current-state">` de `SubmissionDetail.tsx`, adicionar como primeiro item (antes de "Clã"):

```tsx
          <div>
            <dt className="text-gray-500">Coach</dt>
            <dd className="font-medium text-gray-800">{submissao.coach ?? "—"}</dd>
          </div>
```

(O grid é `sm:grid-cols-4` — com 5 itens ele quebra para 2 linhas no desktop, o que é aceitável; não mudar as classes.)

- [ ] **Step 4: Rodar tudo do frontend + typecheck**

Run: `cd frontend && npx --no-install tsc -b && npx --no-install vitest run`
Expected: PASS (tsc sem saída, vitest todos verdes). Corrigir qualquer mock de teste que ainda construa `DesafioSubmissao`/`DesafioSubmissaoVersao` sem `coach`.

- [ ] **Step 5: Commit (Tasks 9 + 10 + 11 juntas)**

```bash
git add frontend/src/api/client.ts frontend/src/pages/Desafios.tsx frontend/src/components/SubmissionDetail.tsx frontend/src/pages/Desafios.test.tsx
git commit -m "feat: UI de auditoria de desafios mostra coach e pontos por coach

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 12: Teste e2e — pontos de desafio no ranking de coach

**Files:**
- Modify: `backend/tests/test_desafio_e2e.py` (docstring do módulo linha 12; renomear/ajustar `test_ca13_nenhum_ponto_de_desafio_atribuido_a_coaches` linha 259; adicionar teste novo)
- Test: o próprio arquivo.

**Interfaces:**
- Consumes: nada novo — exercita `get_tipo_coach_totals("desafios")` e `get_period_desafio_coach_totals` de ponta a ponta via `supabase_client` mockado no nível de `fetch_active_counted_desafio_submissions`.

- [ ] **Step 1: Ajustar o que existe**

Docstring do módulo (linha 12): trocar
`9. Ausência total de pontuação por coach em desafios`
por
`9. Motor de reconciliação sem coach_deltas (identidade de coach resolvida em leitura — Fase 2)`.

`test_ca13_nenhum_ponto_de_desafio_atribuido_a_coaches` (linha 259) — **mantém a asserção** (`not hasattr(plan, "coach_deltas")` continua verdadeiro no modelo de leitura), só renomear para `test_ca13_reconciliacao_nao_produz_coach_deltas` e ajustar o comentário para "Fase 2: a identidade de coach é resolvida em tempo de leitura, o motor de reconciliação segue só com clan_deltas".

- [ ] **Step 2: Teste novo que falha**

Adicionar na classe `TestCriteriosDeAceitacaoPRD11`:

```python
    def test_fase2_pontos_de_desafio_no_total_e_no_periodo_do_coach(self):
        import supabase_client
        from datetime import date

        tokens = [
            {"token": "TOK-A", "raw_name": "Vini Marini", "points": 10,
             "status": "active_counted", "submitted_at": "2026-05-10T13:00:00-03:00"},
            {"token": "TOK-B", "raw_name": "vinicius marini", "points": 10,
             "status": "active_counted", "submitted_at": "2026-06-10T13:00:00-03:00"},
        ]
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=tokens), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"vini marini": "Vinicius Marini",
                                 "vinicius marini": "Vinicius Marini"}):
            total = supabase_client.get_tipo_coach_totals("desafios")
            maio = supabase_client.get_period_desafio_coach_totals(
                date(2026, 5, 1), date(2026, 5, 31)
            )

        assert total == {"Vinicius Marini": 20}
        assert maio == {"Vinicius Marini": 10}
```

- [ ] **Step 3: Rodar**

Run: `cd backend && $PY -m pytest tests/test_desafio_e2e.py -q`
Expected: PASS (o teste novo passa porque as Tasks 1 já implementaram; se falhar, é regressão de uma task anterior).

- [ ] **Step 4: Suíte inteira do backend (sem os `*_postgres`, que auto-skipam)**

Run: `cd backend && $PY -m pytest -q`
Expected: PASS — `N passed, 4 skipped` (os 3 `*_postgres` + 1 pré-existente). Zero falhas.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_desafio_e2e.py
git commit -m "test: e2e — pontos de desafio no total e no periodo do coach (Fase 2)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

---

## Task 13: Runbook + abrir o PR

**Files:**
- Modify: `docs/runbooks/sincronizacao-desafios.md` (adicionar seção)
- (nenhum teste)

- [ ] **Step 1: Adicionar seção ao runbook**

No fim de `docs/runbooks/sincronizacao-desafios.md`:

```markdown
## Fase 2 — pontos de desafio para coaches

A partir da Fase 2, cada token `active_counted` também pontua para o **coach**
(coluna B da planilha, resolvida ao nome canônico via
`pontos_ultimate_coach_aliases`). Não há schema novo nem migração de banco.

### Após o deploy da Fase 2

1. Garanta que a Fase 1 já foi migrada e que houve ao menos uma sincronização
   bem-sucedida (`POST /api/contabilidade/executar`) — senão o backfill vem zerado.
2. Rode **uma vez** `POST /api/contabilidade/reprocessar`. Ele reconstrói todos
   os totais do zero e passa a somar `get_tipo_coach_totals("desafios")` no total
   de cada coach. `reprocessar-coaches` sozinho **não** serve de backfill (só
   cobre coaches afetados por mudança de alias).
3. Validação: para cada desafio, a soma de `pontos_por_coach` (em
   `GET /api/desafios/{id}`) deve ser igual a
   `points_per_submission × (nº de tokens active_counted com coluna B não vazia)`.

### Manutenção contínua

- `POST /api/contabilidade/executar` e `POST /api/contabilidade/confirmar-desafios`
  recompõem automaticamente a fatia de desafio no total dos coaches ao fim do sync
  (`_refresh_desafio_coach_totals`).
- A aba "Desafios" do ranking de Coaches (Dashboard) e `GET /api/contabilidade/totais-por-tipo?tipo=desafios`
  leem os tokens ao vivo — sempre exatos, mesmo antes de um `/reprocessar`.
- Um nome de coach com grafia nova na coluna B pontua sob o nome bruto até ser
  resolvido; ele aparece em `POST /api/contabilidade/sugerir-aliases-llm` e na fila
  de aliases pendentes.
```

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/sincronizacao-desafios.md
git commit -m "docs: runbook da Fase 2 (pontos de desafio para coaches)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss"
```

- [ ] **Step 3: Rodar as duas suítes uma última vez**

Run: `cd backend && $PY -m pytest -q`
Run: `cd frontend && npx --no-install tsc -b && npx --no-install vitest run`
Expected: ambas verdes.

- [ ] **Step 4: Push e PR**

```bash
git push -u origin codex/desafios-google-sheets-fase2
```

Abrir PR com `gh pr create --base codex/desafios-google-sheets --head codex/desafios-google-sheets-fase2` (base = a branch da Fase 1 enquanto o PR #26 não mergeia; trocar para `master` e rebasear depois que #26 entrar). Corpo:

```markdown
## O que é

Fase 2 dos desafios via Google Sheets: os pontos de desafio (tokens `active_counted`)
passam a contar para o **ranking individual dos coaches**, resolvendo a identidade
do coach a partir da coluna B da planilha em **tempo de leitura**.

Spec: `docs/superpowers/specs/2026-09-10-desafios-coach-pontos-fase2-design.md`
Base: PR #26 (Fase 1).

## Mudança de comportamento

- `get_tipo_coach_totals("desafios")` e `get_period_desafio_coach_totals` passam a
  ler `desafio_submissions_current` (tokens) em vez da tabela legada
  `desafio_registros_coach`, agrupando por `resolve_coach(raw_name, alias_map)`.
- `reprocessar_contabilidade`, `importar_inicial`, `reprocessar_coaches` e
  `historico` voltam a dobrar a fatia de desafio no total do coach.
- `/executar` e `/confirmar-desafios` recompõem o total de desafio-coach ao fim do sync.
- Auditoria: `coach` (canônico) por submissão/versão; `pontos_por_coach` no detalhe.
- Frontend: coluna "Coach" e seção "Pontos por coach" em `Desafios.tsx`.

**Sem migração de schema.** Backfill = rodar `POST /api/contabilidade/reprocessar` uma
vez pós-deploy (ver `docs/runbooks/sincronizacao-desafios.md`).

## Fora de escopo

Coluna `coach` persistida / `coach_deltas` no motor de reconciliação; filtro e
drill-down por coach na auditoria; `coach` nos resultados de sincronização.

## Testes

- Backend: `pytest -q` verde (4 skips de infra).
- Frontend: `tsc -b` limpo, `vitest` verde.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01X195xv9nCbiFwcdgxhY4ss
```

---

## Self-review

**Cobertura do spec:**
- §3.1 reescrita `get_tipo_coach_totals`/`get_period_desafio_coach_totals` → Task 1 ✓
- §3.1 `get_all_desafio_token_coach_names` → Task 1 ✓
- §3.2 `reprocessar_coaches` (discovery + desafio_pts) → Task 4 ✓
- §3.2 `reprocessar_contabilidade` → Task 3 ✓
- §3.2 `importar_inicial` → Task 5 ✓
- §3.2 `sugerir_aliases_llm` → Task 4 ✓
- §3.2 `executar_contabilidade` + `_refresh_desafio_coach_totals` → Task 7 ✓ (também `/confirmar-desafios`, coberto por simetria — o spec não citava mas é o mesmo sync)
- §3.2 `historico` → Task 6 ✓
- §3.3 auditoria (`coach`, `pontos_por_coach`, `get_desafio_coach_totals`) → Tasks 2, 8 ✓
- §4 frontend (client.ts, Desafios.tsx, SubmissionDetail.tsx, Dashboard sem mudança) → Tasks 9-11 ✓
- §5 rollout (sem migração; backfill via `/reprocessar`; runbook) → Task 13 ✓
- §6 testes (token_totals, reprocessar_coaches, reprocessar_inclui_desafio, tipo_filter_breakdown, executar novo, auditoria, e2e, vitest) → Tasks 1, 3, 4, 7, 8, 10-12 ✓

**Consistência de tipos:**
- `get_all_desafio_token_coach_names() -> set[str]` — mesma assinatura em Tasks 1, 4.
- `get_tipo_coach_totals("desafios", inicio, fim) -> dict[str,int]` — Tasks 1, 3, 4, 5, 7.
- `get_period_desafio_coach_totals(inicio, fim=None) -> dict[str,int]` — Tasks 1, 6.
- `get_desafio_coach_totals(desafio_id: int) -> dict[str,int]` — Tasks 2, 8 (distinto do removido `get_desafio_coach_total` singular).
- `_refresh_desafio_coach_totals() -> None` — Task 7, chamado em `executar_contabilidade` e `confirmar_desafios`.
- `_com_coach(row, alias_map) -> dict` — Task 8, uso interno ao router.
- Campo `coach: str | None` — modelos Pydantic (Task 8) e interfaces TS (Task 9) batem.
- `pontos_por_coach: dict[str,int]` / `Record<string, number>` — Task 8 / Task 9 batem.

**Sem placeholders de código:** os únicos "seguir o padrão do arquivo vizinho" são nas Tasks 5, 8 e 10 para reaproveitar esqueletos de mock já existentes nos testes — o comportamento a afirmar está explícito em cada caso.
