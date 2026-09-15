# Aprovação Automática de Submissões de Desafio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inverter a regra de elegibilidade das submissões de desafio pós-corte (01/08/2026): toda submissão `active_counted` passa a contar por padrão — tanto para os 100 pontos individuais do coach quanto para a apuração de percentual de engajamento do clã — e só `revisao_status == "reprovado"` exclui. Remove o conceito de "aprovar" manualmente.

**Architecture:** Duas funções de elegibilidade em `backend/supabase_client.py` (`_submissao_conta_para_pontos_individuais_coach` e a lógica interna de `get_desafio_apuracao`) trocam `revisao_status == "aprovado"` por `revisao_status != "reprovado"`. Uma nova função `reapurar_desafio_e_aplicar_delta(desafio_id, dry_run=False)` centraliza "recalcular a apuração de um desafio e aplicar o delta ao total do clã", reaproveitada por três chamadores: o sweep de prazo vencido (`processar_desafios_apuracao_prazo`, já existente), o endpoint de revisão (`POST /submissoes/{token}/revisar`, quando o desafio da submissão já estiver apurado) e um script de backfill administrativo único. No frontend, `Desafios.tsx` troca o badge de 3 estados + 2 botões por um badge de 2 estados (VÁLIDO/REPROVADO) + 1 botão que alterna.

**Tech Stack:** Python 3.12 / FastAPI, Supabase (PostgREST via `supabase-py`), React + TypeScript + Vite, pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-09-14-desafios-aprovacao-automatica-design.md`

## Global Constraints

- **Branch:** criar `feature/desafios-aprovacao-automatica` a partir de `master` antes do primeiro commit (padrão do repo — ver `feature/desafios-percentual-por-cla`, `feature/desafios-pontos-coach-e-corte-data` no histórico).
- **Python de teste:** `"C:/Users/artif/Documents/IGT/CONTABILIDADE PONTOS/contabilidade_pontos_py/venv/Scripts/python.exe"` — referido abaixo como `$PY`. Rodar pytest a partir de `backend/`.
- **Frontend:** rodar a partir de `frontend/`. `npx --no-install vitest run <arquivo>` e `npx --no-install tsc -b`.
- **Escopo do corte:** só submissões pós-corte (`submitted_at >= config.DESAFIO_PERCENTUAL_CLAN_CORTE`, hoje `date(2026, 8, 1)`) mudam de comportamento. Pré-corte não muda em nada (sem UI de revisão, sempre conta) — nenhuma task deste plano toca o caminho pré-corte.
- **Única exclusão:** `revisao_status == "reprovado"`. Os valores `"pendente"` (linha ausente em `desafio_submissao_revisoes`) e `"aprovado"` (legado) contam igual — nenhuma task deste plano deve reintroduzir uma distinção funcional entre eles.
- **`revisao_status` continua um enum de 3 valores no banco** (`pendente`/`aprovado`/`reprovado`, `desafio_submissao_revisoes.status`) — não há migração de schema neste plano. Só a UI para de expor "aprovar".
- Commits frequentes, um por task no mínimo. Mensagens em português, prefixo `feat:` / `test:` / `docs:`.
- Rodapé de commit (obrigatório em todo commit):
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e
  ```

---

## Mapa de arquivos

| Arquivo | Responsabilidade | Tasks |
|---|---|---|
| `backend/supabase_client.py` | Inversão de elegibilidade (coach e clã); extração de `_calcular_apuracao_atual_desafio`; nova `reapurar_desafio_e_aplicar_delta` | 1, 2, 3 |
| `backend/routers/contabilidade.py` | `processar_desafios_apuracao_prazo` passa a delegar para `reapurar_desafio_e_aplicar_delta` | 3 |
| `backend/routers/desafio_auditoria.py` | `revisar_submissao` dispara reapuração quando o desafio já está apurado | 3 |
| `backend/admin/backfill_desafio_apuracao_automatica.py` | Script de backfill (novo) | 4 |
| `frontend/src/pages/Desafios.tsx` | Badge de 2 estados + botão único (reprovar/desfazer) | 5 |
| `backend/tests/test_desafio_token_totals.py` | Inversão dos testes de elegibilidade — pontos individuais do coach | 1 |
| `backend/tests/test_desafio_auditoria_router.py` | Inversão dos testes de elegibilidade — resposta de submissão; novo teste de disparo de reapuração | 1, 3 |
| `backend/tests/test_desafio_percentual_clan_e2e.py` | Inversão do e2e — apuração de clã conta por padrão | 2 |
| `backend/tests/test_reapurar_desafio_delta.py` | Testes novos de `reapurar_desafio_e_aplicar_delta` (novo arquivo) | 3 |
| `backend/tests/test_backfill_desafio_apuracao_automatica.py` | Testes do script de backfill (novo arquivo) | 4 |
| `frontend/src/pages/Desafios.test.tsx` | Testes novos do toggle reprovar/desfazer | 5 |

---

## Task 1: Pontos individuais do coach — inverter elegibilidade

**Files:**
- Modify: `backend/supabase_client.py:572-582` (`_submissao_conta_para_pontos_individuais_coach`)
- Test: `backend/tests/test_desafio_token_totals.py:433-481` (`TestPontosIndividuaisCoachValorEGateDeCorte`)
- Test: `backend/tests/test_desafio_auditoria_router.py:308-352` (`TestListarSubmissoesDoDesafio`), `:392-410` (`TestObterSubmissao`)

**Interfaces:**
- Consumes: `config.DESAFIO_PERCENTUAL_CLAN_CORTE` (existe), `_submitted_at_local_date` (existe).
- Produces: `_submissao_conta_para_pontos_individuais_coach(submitted_at, revisao_status: str) -> bool` — mesma assinatura, regra invertida. Todo chamador existente (`desafio_submission_pontos_individuais_coach`, `_aggregate_desafio_tokens_by_coach`, `get_desafio_coach_totals`) não muda.

- [ ] **Step 1: Inverter os testes de `test_desafio_token_totals.py`**

Substituir a classe `TestPontosIndividuaisCoachValorEGateDeCorte` (linhas 433-481 de `backend/tests/test_desafio_token_totals.py`) por:

```python
class TestPontosIndividuaisCoachValorEGateDeCorte:
    """Pontos individuais do coach por desafio: valor fixo de
    `config.POINTS_PER_DESAFIO_SUBMISSION_COACH` (não o `points` gravado, que
    continua só alimentando o lado clã). A partir do corte de vigência
    (`config.DESAFIO_PERCENTUAL_CLAN_CORTE`), toda submissão `active_counted`
    conta por padrão — só `revisao_status == "reprovado"` exclui."""

    def _row(self, submitted_at, token="T1"):
        return {"token": token, "raw_name": "Ana", "points": 10,
                "status": "active_counted", "submitted_at": submitted_at}

    def test_pre_corte_conta_automaticamente_sem_revisao(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-07-31T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}

    def test_pos_corte_sem_registro_de_revisao_conta_por_padrao(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}

    def test_pos_corte_com_revisao_pendente_conta(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"T1": {"status": "pendente"}}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}

    def test_pos_corte_com_revisao_reprovada_nao_conta(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"T1": {"status": "reprovado"}}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {}

    def test_pos_corte_com_revisao_aprovada_legado_ainda_conta(self):
        with patch("supabase_client.fetch_active_counted_desafio_submissions",
                   return_value=[self._row("2026-08-01T13:00:00-03:00")]), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"T1": {"status": "aprovado"}}):
            assert supabase_client.get_tipo_coach_totals("desafios") == {"Ana": 100}
```

- [ ] **Step 2: Inverter os testes de `test_desafio_auditoria_router.py`**

Em `backend/tests/test_desafio_auditoria_router.py`, renomear e inverter a asserção de `test_points_reflete_pontos_individuais_do_coach_nao_o_gravado` (linhas 308-318):

```python
    def test_points_pos_corte_sem_revisao_conta_por_padrao(self):
        """`_submission()` tem `points: 10` gravado (taxa de clã) e
        `submitted_at` pós-corte sem revisão registrada — a resposta deve
        mostrar 100 (conta por padrão), não o 10 gravado nem 0."""
        with patch("supabase_client.get_desafio", return_value=_desafio()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}), \
             patch("supabase_client.list_desafio_submissions_current", return_value=[_submission()]):
            response = client.get("/api/desafios/1/submissoes")
        assert response.status_code == 200
        assert response.json()[0]["points"] == 100
```

Adicionar um teste novo logo abaixo de `test_points_pos_corte_com_revisao_aprovada_mostra_valor_do_coach` (linha 320-328), para cobrir a exclusão explícita (não havia teste de reprovado nesta classe):

```python
    def test_points_pos_corte_com_revisao_reprovada_mostra_zero(self):
        with patch("supabase_client.get_desafio", return_value=_desafio()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes",
                   return_value={"TOK-1": {"status": "reprovado"}}), \
             patch("supabase_client.list_desafio_submissions_current", return_value=[_submission()]):
            response = client.get("/api/desafios/1/submissoes")
        assert response.status_code == 200
        assert response.json()[0]["points"] == 0
```

Renomear e inverter `test_obter_submissao_points_reflete_pontos_individuais_do_coach` (linhas 392-400):

```python
    def test_obter_submissao_points_pos_corte_sem_revisao_conta_por_padrao(self):
        with patch(
            "supabase_client.get_desafio_submission_current", return_value=_submission()
        ), patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_submissoes_revisoes", return_value={}):
            response = client.get("/api/desafios/submissoes/TOK-1")
        assert response.status_code == 200
        # _submission() é pós-corte (19/08/2026) sem revisão registrada: conta por padrão.
        assert response.json()["points"] == 100
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_desafio_token_totals.py::TestPontosIndividuaisCoachValorEGateDeCorte tests/test_desafio_auditoria_router.py -q`
Expected: FAIL nos casos invertidos (o código ainda exige `revisao_status == "aprovado"`).

- [ ] **Step 4: Implementar**

Em `backend/supabase_client.py`, substituir o corpo de `_submissao_conta_para_pontos_individuais_coach` (linhas 572-582):

```python
def _submissao_conta_para_pontos_individuais_coach(
    submitted_at, revisao_status: str
) -> bool:
    """Mesma regra de corte usada por `get_desafio_apuracao` no eixo clã
    (`config.DESAFIO_PERCENTUAL_CLAN_CORTE`): antes do corte, `active_counted`
    já basta. A partir do corte, toda submissão conta por padrão — só
    `revisao_status == "reprovado"` exclui (não há mais exigência de
    aprovação manual explícita)."""
    sub_date = _submitted_at_local_date(submitted_at)
    if sub_date and sub_date >= config.DESAFIO_PERCENTUAL_CLAN_CORTE:
        return revisao_status != "reprovado"
    return True
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_desafio_token_totals.py tests/test_desafio_auditoria_router.py -q`
Expected: PASS.

- [ ] **Step 6: Regressão do módulo de contabilidade completo**

Run: `cd backend && $PY -m pytest tests/ -q -k "coach or desafio"`
Expected: PASS. Nenhum outro teste depende do valor antigo de `_submissao_conta_para_pontos_individuais_coach` (a busca por `_submissao_conta_para\|desafio_submission_pontos_individuais_coach\|get_desafio_apuracao\|get_desafio_coach_totals` em `backend/tests/` só retorna os três arquivos já tratados neste plano — Tasks 1 e 2).

- [ ] **Step 7: Commit**

```bash
git add backend/supabase_client.py backend/tests/test_desafio_token_totals.py backend/tests/test_desafio_auditoria_router.py
git commit -m "feat: pontos individuais do coach contam por padrao pos-corte, so reprovado exclui

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e"
```

---

## Task 2: Apuração de clã — inverter elegibilidade e extrair `_calcular_apuracao_atual_desafio`

**Files:**
- Modify: `backend/supabase_client.py:1528-1600` (`get_desafio_apuracao`)
- Test: `backend/tests/test_desafio_percentual_clan_e2e.py:20-139` (`test_fluxo_e2e_apuracao_desafio_pos_corte`)

**Interfaces:**
- Consumes: `list_desafio_submissions_current(desafio_id, status="active_counted") -> list[dict]` (existe), `list_submissoes_revisoes(desafio_id) -> dict[str, dict]` (existe), `get_coach_alias_map()` (existe), `coach_identity.resolve_coach` (existe), `list_coach_clas()` (existe), `desafio_percentual_clan.apurar_desafio(...)` (existe, não muda).
- Produces:
  - `_calcular_apuracao_atual_desafio(desafio_id: int) -> dict[str, ApuracaoClan]` — **novo**, módulo-privado. Extrai o corpo de cálculo "ao vivo" (submissões elegíveis → `apurar_desafio`) que hoje só existia dentro do branch `else` de `get_desafio_apuracao`. Task 3 também consome esta função.
  - `get_desafio_apuracao(desafio_id: int) -> dict` — assinatura e formato de retorno inalterados; internamente delega a `_calcular_apuracao_atual_desafio` quando não apurado.

- [ ] **Step 1: Inverter o e2e existente**

Em `backend/tests/test_desafio_percentual_clan_e2e.py`, `test_fluxo_e2e_apuracao_desafio_pos_corte` (linhas 20-139) hoje assume que nada conta antes de aprovar explicitamente. Substituir os passos 1 e 2 (linhas 115-128) por:

```python
        # 1. Antes de qualquer revisão: as duas submissões (Ana e Bruno) já
        # contam por padrão -> 2 participantes de 4 cadastrados = 50% -> 500 pts
        res_prev = client.get(f"/api/desafios/{desafio_id}/apuracao")
        assert res_prev.status_code == 200
        prev_data = res_prev.json()
        assert prev_data["provisorio"] is True
        cla1_prev = next(c for c in prev_data["clas"] if c["clan"] == "CLÃ 1")
        assert cla1_prev["participantes"] == 2
        assert cla1_prev["pontos"] == 500

        # 2. Reprovar a submissão da Ana -> só Bruno conta -> 1 de 4 = 25% -> 300 pts
        rev1 = client.post(f"/api/desafios/submissoes/{token_1}/revisar", json={"status": "reprovado"})
        assert rev1.status_code == 200
```

E o passo 4 (linhas 136-138), que hoje espera 500 pts (2 aprovados manualmente), passa a esperar 300 pts (só Bruno, depois da reprovação de Ana):

```python
        # 4. Verificar que a apuração foi gravada e o total do Clã 1 recebeu 300 pts
        assert desafio_mock["apurado_em"] is not None
        assert totais_clan_db["CLÃ 1"] == 300
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_desafio_percentual_clan_e2e.py::test_fluxo_e2e_apuracao_desafio_pos_corte -q`
Expected: FAIL — a prévia ainda mostra 0 participantes (código exige `rev_status == "aprovado"`).

- [ ] **Step 3: Implementar — extrair `_calcular_apuracao_atual_desafio` e inverter a regra**

Em `backend/supabase_client.py`, substituir o corpo de `get_desafio_apuracao` a partir da linha do `if apurado_em:` até o fim da função (linhas 1537-1599) por:

```python
    if apurado_em:
        apuracoes = get_desafio_clan_apuracoes(desafio_id)
        return {
            "desafio_id": desafio_id,
            "prazo_apuracao": prazo_apuracao,
            "apurado_em": apurado_em,
            "provisorio": False,
            "clas": apuracoes,
        }

    res_dict = _calcular_apuracao_atual_desafio(desafio_id)
    clas_list = [ap.to_dict() for ap in res_dict.values()]
    return {
        "desafio_id": desafio_id,
        "prazo_apuracao": prazo_apuracao,
        "apurado_em": None,
        "provisorio": True,
        "clas": clas_list,
    }


def _calcular_apuracao_atual_desafio(desafio_id: int) -> dict[str, "ApuracaoClan"]:
    """Calcula a apuração por percentual de clã de um desafio a partir do
    estado *atual* de revisões — ignora se o desafio já está `apurado_em`
    (quem decide se usa o resultado congelado ou recalcula ao vivo é o
    chamador: `get_desafio_apuracao` para a prévia, `reapurar_desafio_e_aplicar_delta`
    para reabrir um desafio já congelado). Pós-corte, toda submissão conta por
    padrão — só `revisao_status == "reprovado"` exclui (mesma regra de
    `_submissao_conta_para_pontos_individuais_coach`)."""
    submissoes = list_desafio_submissions_current(desafio_id=desafio_id, status="active_counted")
    revisoes_map = list_submissoes_revisoes(desafio_id)
    alias_map = get_coach_alias_map()

    aprovadas = []
    for s in submissoes:
        sub_date = _submitted_at_local_date(s.get("submitted_at"))
        token = s.get("token")
        rev_status = revisoes_map.get(token, {}).get("status", "pendente")

        if sub_date and sub_date >= config.DESAFIO_PERCENTUAL_CLAN_CORTE:
            conta = rev_status != "reprovado"
        else:
            # Pré-corte conta se active_counted, sem qualquer critério de revisão.
            conta = True

        if not conta:
            continue

        raw_name = (s.get("raw_name") or "").strip()
        canonical = coach_identity.resolve_coach(raw_name, alias_map) if raw_name else None
        aprovadas.append({
            "coach": canonical or raw_name,
            "clan_planilha": s.get("clan") or s.get("raw_clan_current") or s.get("raw_clan_legacy"),
        })

    from desafio_percentual_clan import apurar_desafio
    rows_clas = list_coach_clas()
    coach_clas = {r["coach_canonico"]: r["clan"] for r in rows_clas}
    tamanho_grupo: dict[str, int] = {}
    for r in rows_clas:
        c = r["clan"]
        tamanho_grupo[c] = tamanho_grupo.get(c, 0) + 1

    todos_clas = ["CLÃ 1", "CLÃ 2", "CLÃ 3", "CLÃ 4", "CLÃ 5", "CLÃ 6", "CLÃ 7", "CLÃ 8"]
    return apurar_desafio(
        submissoes_aprovadas=aprovadas,
        coach_clas=coach_clas,
        tamanho_grupo_por_clan=tamanho_grupo,
        todos_os_clas=todos_clas,
    )
```

(A variável `aprovadas` mantém o nome por compatibilidade com o parâmetro `submissoes_aprovadas` de `apurar_desafio` — semanticamente agora é "submissões que contam", não "submissões aprovadas manualmente".)

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_desafio_percentual_clan_e2e.py tests/test_desafio_percentual_clan.py tests/test_desafio_apuracao_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/supabase_client.py backend/tests/test_desafio_percentual_clan_e2e.py
git commit -m "feat: apuracao de cla por percentual conta submissoes por padrao pos-corte

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e"
```

---

## Task 3: `reapurar_desafio_e_aplicar_delta` — recálculo após apuração congelada

**Files:**
- Modify: `backend/supabase_client.py` (nova função, logo após `_calcular_apuracao_atual_desafio` da Task 2)
- Modify: `backend/routers/contabilidade.py:794-851` (`processar_desafios_apuracao_prazo`)
- Modify: `backend/routers/desafio_auditoria.py:239-247` (`revisar_submissao`)
- Test: `backend/tests/test_reapurar_desafio_delta.py` (novo)
- Test: `backend/tests/test_desafio_apuracao_api.py` (novos casos de `test_revisar_submissao_*`)

**Interfaces:**
- Consumes: `_calcular_apuracao_atual_desafio(desafio_id)` (Task 2), `get_desafio(desafio_id)`, `get_desafio_clan_apuracoes(desafio_id)`, `get_clan_totals()`, `upsert_clan_total(clan, total)`, `salvar_apuracao_clan(desafio_id, resultados)` (todas já existem, inalteradas).
- Produces: `reapurar_desafio_e_aplicar_delta(desafio_id: int, dry_run: bool = False) -> dict[str, dict]` — chave clã, valor `ApuracaoClan.to_dict()` **mais** a chave `"delta"` (int, `pontos_novo - pontos_antigo`). `dry_run=True` não grava nada (nem `upsert_clan_total` nem `salvar_apuracao_clan`) — só calcula e retorna, incluindo o `delta`. Retorna `{}` se `desafio_id` não existir.

- [ ] **Step 1: Escrever os testes que falham**

Criar `backend/tests/test_reapurar_desafio_delta.py`:

```python
"""Testes de `supabase_client.reapurar_desafio_e_aplicar_delta` — recálculo
da apuração por percentual de um desafio (congelado ou não) e aplicação do
delta resultante ao total do clã."""

import os
import sys
from unittest.mock import patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supabase_client
from desafio_percentual_clan import ApuracaoClan


def _apuracao(clan, pontos, participantes=1, total_grupo=4, percentual=25.0):
    return ApuracaoClan(clan=clan, participantes=participantes, total_grupo=total_grupo,
                         percentual=percentual, pontos=pontos)


def test_desafio_inexistente_retorna_dict_vazio():
    with patch("supabase_client.get_desafio", return_value=None):
        assert supabase_client.reapurar_desafio_e_aplicar_delta(999) == {}


def test_aplica_delta_positivo_ao_total_do_cla_e_regrava_apuracao():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 500)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 300}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan") as mock_salvar:
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5)

    mock_upsert.assert_called_once_with(clan="CLÃ 1", total=500)
    mock_salvar.assert_called_once()
    assert resultado["CLÃ 1"]["pontos"] == 500
    assert resultado["CLÃ 1"]["delta"] == 200


def test_aplica_delta_negativo_sem_deixar_total_negativo():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 0)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 100}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan"):
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5)

    # total atual (100) + delta (0 - 300 = -300) = -200 -> travado em 0
    mock_upsert.assert_called_once_with(clan="CLÃ 1", total=0)
    assert resultado["CLÃ 1"]["delta"] == -300


def test_sem_mudanca_nao_chama_upsert():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 300)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 300}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan") as mock_salvar:
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5)

    mock_upsert.assert_not_called()
    mock_salvar.assert_called_once()  # ainda regrava (idempotente), só não move o total
    assert resultado["CLÃ 1"]["delta"] == 0


def test_dry_run_nao_grava_nada_mas_retorna_delta():
    with patch("supabase_client.get_desafio", return_value={"id": 5}), \
         patch("supabase_client._calcular_apuracao_atual_desafio",
               return_value={"CLÃ 1": _apuracao("CLÃ 1", 500)}), \
         patch("supabase_client.get_desafio_clan_apuracoes",
               return_value=[{"clan": "CLÃ 1", "pontos": 300}]), \
         patch("supabase_client.get_clan_totals", return_value={"CLÃ 1": 300}), \
         patch("supabase_client.upsert_clan_total") as mock_upsert, \
         patch("supabase_client.salvar_apuracao_clan") as mock_salvar:
        resultado = supabase_client.reapurar_desafio_e_aplicar_delta(5, dry_run=True)

    mock_upsert.assert_not_called()
    mock_salvar.assert_not_called()
    assert resultado["CLÃ 1"]["delta"] == 200
```

Em `backend/tests/test_desafio_apuracao_api.py`, adicionar (o `revisar_submissao` da API precisa checar se o desafio já está apurado e, se sim, disparar `reapurar_desafio_e_aplicar_delta`):

```python
def test_revisar_submissao_desafio_ja_apurado_dispara_reapuracao():
    with patch("supabase_client.get_desafio_submission_current") as mock_get_sub, \
         patch("supabase_client.revisar_submissao") as mock_rev, \
         patch("supabase_client.get_desafio") as mock_get_desafio, \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_get_sub.return_value = {"token": "tok1", "desafio_id": 7}
        mock_rev.return_value = {"token": "tok1", "status": "reprovado"}
        mock_get_desafio.return_value = {"id": 7, "apurado_em": "2026-09-01T00:00:00+00:00"}

        response = client.post(
            "/api/desafios/submissoes/tok1/revisar", json={"status": "reprovado"}
        )

        assert response.status_code == 200
        mock_reapurar.assert_called_once_with(7)


def test_revisar_submissao_desafio_nao_apurado_nao_dispara_reapuracao():
    with patch("supabase_client.get_desafio_submission_current") as mock_get_sub, \
         patch("supabase_client.revisar_submissao") as mock_rev, \
         patch("supabase_client.get_desafio") as mock_get_desafio, \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_get_sub.return_value = {"token": "tok1", "desafio_id": 7}
        mock_rev.return_value = {"token": "tok1", "status": "reprovado"}
        mock_get_desafio.return_value = {"id": 7, "apurado_em": None}

        response = client.post(
            "/api/desafios/submissoes/tok1/revisar", json={"status": "reprovado"}
        )

        assert response.status_code == 200
        mock_reapurar.assert_not_called()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_reapurar_desafio_delta.py tests/test_desafio_apuracao_api.py -q`
Expected: FAIL — `AttributeError: reapurar_desafio_e_aplicar_delta` não existe; o endpoint ainda não chama `get_desafio`/`reapurar_desafio_e_aplicar_delta`.

- [ ] **Step 3: Implementar `reapurar_desafio_e_aplicar_delta`**

Em `backend/supabase_client.py`, logo após `_calcular_apuracao_atual_desafio` (Task 2):

```python
def reapurar_desafio_e_aplicar_delta(desafio_id: int, dry_run: bool = False) -> dict[str, dict]:
    """Recalcula a apuração por percentual de clã de um desafio a partir do
    estado *atual* de revisões (`_calcular_apuracao_atual_desafio`) e aplica o
    delta resultante ao total de cada clã (`pontos_ultimate_totais_por_clan`),
    regravando o resultado em `desafio_clan_apuracoes`/`desafios.apurado_em`
    via `salvar_apuracao_clan`.

    Funciona tanto para um desafio ainda não apurado quanto para um já
    congelado — reabre e refecha a apuração daquele desafio especificamente,
    sem exigir edição de prazo (chamado por `revisar_submissao`, na API, toda
    vez que uma submissão de um desafio já apurado é reprovada ou tem a
    reprovação desfeita) e pelo sweep de prazo vencido
    (`routers.contabilidade.processar_desafios_apuracao_prazo`).

    `dry_run=True` calcula e retorna o resultado (incluindo o delta por clã)
    sem gravar nada — usado pelo backfill administrativo para preview.

    Retorna `{}` se o desafio não existir; caso contrário, dict clã ->
    `ApuracaoClan.to_dict()` acrescido da chave `"delta"` (pontos novos menos
    pontos gravados anteriormente para aquele clã)."""
    desafio = get_desafio(desafio_id)
    if not desafio:
        return {}

    res_dict = _calcular_apuracao_atual_desafio(desafio_id)
    apuracoes_anteriores = get_desafio_clan_apuracoes(desafio_id)
    pontos_antigos = {a["clan"]: a["pontos"] for a in apuracoes_anteriores}

    saida: dict[str, dict] = {}
    for clan, ap in res_dict.items():
        delta = ap.pontos - pontos_antigos.get(clan, 0)
        if delta != 0 and not dry_run:
            totais = get_clan_totals()
            atual = totais.get(clan, 0)
            upsert_clan_total(clan=clan, total=max(0, atual + delta))
        saida[clan] = {**ap.to_dict(), "delta": delta}

    if not dry_run:
        salvar_apuracao_clan(desafio_id, res_dict)

    return saida
```

- [ ] **Step 4: Rodar e ver passar (novo arquivo)**

Run: `cd backend && $PY -m pytest tests/test_reapurar_desafio_delta.py -q`
Expected: PASS.

- [ ] **Step 5: Refatorar `processar_desafios_apuracao_prazo` para reusar a função nova**

Em `backend/routers/contabilidade.py`, substituir o corpo do `if precisa_apurar:` (linhas 832-850) por:

```python
                if precisa_apurar:
                    supabase_client.reapurar_desafio_e_aplicar_delta(desafio_id)
```

(Remove a duplicação de "calcular clas_novos, comparar com pontos_antigos, aplicar delta, salvar" — agora vive só em `reapurar_desafio_e_aplicar_delta`.)

- [ ] **Step 6: Wire no endpoint de revisão**

Em `backend/routers/desafio_auditoria.py`, substituir `revisar_submissao` (linhas 239-247):

```python
@router.post("/submissoes/{token}/revisar")
def revisar_submissao(token: str, req: RevisarSubmissaoRequest):
    """Aprova ou reprova uma submissão individual. Se o desafio dessa
    submissão já estiver apurado (`apurado_em` não nulo), reabre e refecha a
    apuração daquele desafio na mesma chamada (`reapurar_desafio_e_aplicar_delta`)
    — reprovar/desfazer depois de apurado não fica congelado."""
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    resultado = supabase_client.revisar_submissao(
        token=token, status=req.status, revisado_por=req.revisado_por
    )
    desafio_id = submissao.get("desafio_id")
    if desafio_id is not None:
        desafio = supabase_client.get_desafio(desafio_id)
        if desafio and desafio.get("apurado_em"):
            supabase_client.reapurar_desafio_e_aplicar_delta(desafio_id)
    return resultado
```

- [ ] **Step 7: Rodar e ver passar (suite completa de desafios)**

Run: `cd backend && $PY -m pytest tests/test_desafio_apuracao_api.py tests/test_desafio_percentual_clan_e2e.py tests/test_contabilidade_integration.py tests/test_reapurar_desafio_delta.py -q`
Expected: PASS. Se algum teste de `/executar` em `test_contabilidade_integration.py` falhar por não mockar `supabase_client.reapurar_desafio_e_aplicar_delta` no caminho de `processar_desafios_apuracao_prazo`, adicionar `patch("supabase_client.reapurar_desafio_e_aplicar_delta")` (sem `return_value`, já que o chamador não usa o retorno) ao `with` desse teste.

- [ ] **Step 8: Commit**

```bash
git add backend/supabase_client.py backend/routers/contabilidade.py backend/routers/desafio_auditoria.py backend/tests/test_reapurar_desafio_delta.py backend/tests/test_desafio_apuracao_api.py
git commit -m "feat: reprovar submissao de desafio ja apurado reabre e refecha a apuracao do cla

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e"
```

---

## Task 4: Backfill administrativo

**Files:**
- Create: `backend/admin/backfill_desafio_apuracao_automatica.py`
- Test: `backend/tests/test_backfill_desafio_apuracao_automatica.py` (novo)

**Interfaces:**
- Consumes: `supabase_client.list_desafios() -> list[dict]` (existe), `supabase_client.reapurar_desafio_e_aplicar_delta(desafio_id, dry_run=...)` (Task 3).
- Produces: `desafios_para_backfill() -> list[dict]`, `main() -> None` (CLI, `--apply`).

- [ ] **Step 1: Escrever o teste que falha**

Criar `backend/tests/test_backfill_desafio_apuracao_automatica.py`:

```python
"""Testes do backfill administrativo único de apuração automática (Task 4)."""

import os
import sys
from unittest.mock import patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from admin.backfill_desafio_apuracao_automatica import desafios_para_backfill, main


def test_desafios_para_backfill_so_retorna_apurados():
    desafios = [
        {"id": 1, "nome": "A", "apurado_em": "2026-08-20T00:00:00+00:00"},
        {"id": 2, "nome": "B", "apurado_em": None},
    ]
    with patch("supabase_client.list_desafios", return_value=desafios):
        assert desafios_para_backfill() == [desafios[0]]


def test_main_dry_run_nao_aplica_por_padrao(capsys):
    desafios = [{"id": 1, "nome": "A", "apurado_em": "2026-08-20T00:00:00+00:00"}]
    with patch("supabase_client.list_desafios", return_value=desafios), \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_reapurar.return_value = {"CLÃ 1": {"pontos": 500, "delta": 200}}
        main([])

    mock_reapurar.assert_called_once_with(1, dry_run=True)
    assert "Dry-run" in capsys.readouterr().out


def test_main_apply_grava_de_verdade():
    desafios = [{"id": 1, "nome": "A", "apurado_em": "2026-08-20T00:00:00+00:00"}]
    with patch("supabase_client.list_desafios", return_value=desafios), \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_reapurar.return_value = {"CLÃ 1": {"pontos": 500, "delta": 200}}
        main(["--apply"])

    mock_reapurar.assert_any_call(1, dry_run=True)   # preview
    mock_reapurar.assert_any_call(1)                 # aplicação de fato


def test_main_sem_alvos_nao_chama_reapurar(capsys):
    with patch("supabase_client.list_desafios", return_value=[]), \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        main([])

    mock_reapurar.assert_not_called()
    assert "Nenhum desafio" in capsys.readouterr().out
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && $PY -m pytest tests/test_backfill_desafio_apuracao_automatica.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'admin.backfill_desafio_apuracao_automatica'`.

- [ ] **Step 3: Implementar**

Criar `backend/admin/backfill_desafio_apuracao_automatica.py`:

```python
"""Backfill administrativo único: reapura desafios pós-corte já congelados
sob a regra de elegibilidade nova (toda submissão conta por padrão, só
reprovado exclui — ver
docs/superpowers/specs/2026-09-14-desafios-aprovacao-automatica-design.md).

Uso (a partir de `backend/`):

    python -m admin.backfill_desafio_apuracao_automatica            # dry-run
    python -m admin.backfill_desafio_apuracao_automatica --apply

Dry-run (padrão) não escreve nada: lista os desafios já apurados
(`apurado_em` não nulo — só esses usam a apuração por percentual) e mostra,
por clã, o delta que `--apply` aplicaria ao total do clã.
"""

from __future__ import annotations

import argparse
import sys

import supabase_client


def desafios_para_backfill() -> list[dict]:
    """Desafios já apurados (`apurado_em` não nulo) — únicos candidatos a
    reapuração sob a regra nova. Um desafio nunca apurado usa sempre a
    prévia ao vivo (`get_desafio_apuracao`), que já reflete a regra nova sem
    precisar de backfill."""
    return [d for d in supabase_client.list_desafios() if d.get("apurado_em")]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Aplica de fato (padrão: dry-run)")
    args = parser.parse_args(argv)

    alvos = desafios_para_backfill()
    if not alvos:
        print("Nenhum desafio apurado encontrado — nada a fazer.")
        return

    for d in alvos:
        preview = supabase_client.reapurar_desafio_e_aplicar_delta(d["id"], dry_run=True)
        deltas = {clan: item["delta"] for clan, item in preview.items() if item["delta"] != 0}
        if not deltas:
            print(f"Desafio {d['id']} ({d.get('nome')}): sem mudança.")
            continue
        print(f"Desafio {d['id']} ({d.get('nome')}): delta por clã = {deltas}")
        if args.apply:
            supabase_client.reapurar_desafio_e_aplicar_delta(d["id"])
            print("  -> aplicado.")

    if not args.apply:
        print("\nDry-run — nada foi gravado. Rode com --apply para persistir.")


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd backend && $PY -m pytest tests/test_backfill_desafio_apuracao_automatica.py -q`
Expected: PASS.

- [ ] **Step 5: Rodar o dry-run de verdade contra o Supabase de produção (validação manual, não é parte da suite automatizada)**

Run: `cd backend && $PY -m admin.backfill_desafio_apuracao_automatica`
Expected: `Nenhum desafio apurado encontrado — nada a fazer.` (confirmado por consulta direta em 14/09/2026: 0 desafios com `apurado_em` setado). Se esse número mudou entre o levantamento e a execução deste plano, revisar a lista de deltas impressa com o usuário antes de rodar `--apply`.

- [ ] **Step 6: Commit**

```bash
git add backend/admin/backfill_desafio_apuracao_automatica.py backend/tests/test_backfill_desafio_apuracao_automatica.py
git commit -m "feat: script de backfill para reapurar desafios sob a regra de aprovacao automatica

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e"
```

---

## Task 5: Frontend — badge de 2 estados e botão único (reprovar/desfazer)

**Files:**
- Modify: `frontend/src/pages/Desafios.tsx:242-252` (`handleRevisarSubmissao`), `:628-686` (célula de revisão manual na tabela de submissões)
- Test: `frontend/src/pages/Desafios.test.tsx`

**Interfaces:**
- Consumes: `revisarSubmissao(token: string, status: "aprovado" | "reprovado" | "pendente") -> Promise<{token: string; status: string}>` (existe, `frontend/src/api/client.ts:552-560`, assinatura não muda). `DesafioSubmissao.revisao_status?: "pendente" | "aprovado" | "reprovado"` (existe, `frontend/src/api/client.ts:334`, não muda).
- Produces: nenhuma interface nova — só comportamento de UI.

- [ ] **Step 1: Escrever os testes que falham**

Em `frontend/src/pages/Desafios.test.tsx`, adicionar (após o `describe` existente, usando os mesmos helpers `buildDesafio`/`buildSubmissao` já definidos no arquivo):

```typescript
  it("shows VÁLIDO by default and REPROVADO after rejecting a post-corte submission, with a single toggle button", async () => {
    const submissao = buildSubmissao({
      token: "tok-abc123",
      submitted_at: "2026-08-05T10:00:00",
      revisao_status: undefined,
    });
    vi.mocked(fetchSubmissoesDoDesafio).mockResolvedValue([submissao]);
    vi.mocked(revisarSubmissao).mockResolvedValue({ token: "tok-abc123", status: "reprovado" });

    render(<Desafios />);
    await waitFor(() => expect(fetchDesafiosAuditoria).toHaveBeenCalled());
    await userEvent.click(await screen.findByText("Semana de Treinos"));
    await waitFor(() => expect(fetchSubmissoesDoDesafio).toHaveBeenCalled());

    expect(await screen.findByText("VÁLIDO")).toBeInTheDocument();
    expect(screen.queryByText(/aprovar/i)).not.toBeInTheDocument();

    const reprovarBtn = screen.getByTitle("Reprovar submissão");
    vi.mocked(fetchSubmissoesDoDesafio).mockResolvedValue([
      { ...submissao, revisao_status: "reprovado" },
    ]);
    await userEvent.click(reprovarBtn);

    expect(revisarSubmissao).toHaveBeenCalledWith("tok-abc123", "reprovado");
    expect(await screen.findByText("REPROVADO")).toBeInTheDocument();
  });

  it("undoes a rejection by sending status pendente", async () => {
    const submissaoReprovada = buildSubmissao({
      token: "tok-abc123",
      submitted_at: "2026-08-05T10:00:00",
      revisao_status: "reprovado",
    });
    vi.mocked(fetchSubmissoesDoDesafio).mockResolvedValue([submissaoReprovada]);
    vi.mocked(revisarSubmissao).mockResolvedValue({ token: "tok-abc123", status: "pendente" });

    render(<Desafios />);
    await waitFor(() => expect(fetchDesafiosAuditoria).toHaveBeenCalled());
    await userEvent.click(await screen.findByText("Semana de Treinos"));
    await waitFor(() => expect(fetchSubmissoesDoDesafio).toHaveBeenCalled());

    const desfazerBtn = await screen.findByTitle("Desfazer reprovação");
    vi.mocked(fetchSubmissoesDoDesafio).mockResolvedValue([
      { ...submissaoReprovada, revisao_status: "pendente" },
    ]);
    await userEvent.click(desfazerBtn);

    expect(revisarSubmissao).toHaveBeenCalledWith("tok-abc123", "pendente");
    expect(await screen.findByText("VÁLIDO")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd frontend && npx --no-install vitest run src/pages/Desafios.test.tsx`
Expected: FAIL — a UI ainda mostra "PENDENTE"/dois botões "✓ Aprovar"/"✗ Reprovar".

- [ ] **Step 3: Implementar**

Em `frontend/src/pages/Desafios.tsx`, substituir `handleRevisarSubmissao` (linhas 242-252):

```typescript
  const handleToggleReprovacao = async (token: string, reprovarAgora: boolean) => {
    try {
      await revisarSubmissao(token, reprovarAgora ? "reprovado" : "pendente");
      if (desafioDetalheId) {
        carregarSubmissoes(desafioDetalheId);
        carregarApuracao(desafioDetalheId);
      }
    } catch (err) {
      alert(`Erro ao revisar submissão: ${err instanceof Error ? err.message : String(err)}`);
    }
  };
```

Substituir a célula de "Revisão Manual" (linhas 649-681):

```tsx
                              <td className="py-2 px-4 text-center">
                                {isPostCorte ? (
                                  <div className="flex items-center justify-center gap-1.5">
                                    <span
                                      className={`px-2 py-0.5 rounded text-xs font-semibold ${
                                        revStatus === "reprovado"
                                          ? "bg-red-100 text-red-700"
                                          : "bg-green-100 text-green-700"
                                      }`}
                                    >
                                      {revStatus === "reprovado" ? "REPROVADO" : "VÁLIDO"}
                                    </span>
                                    {revStatus === "reprovado" ? (
                                      <button
                                        title="Desfazer reprovação"
                                        onClick={() => handleToggleReprovacao(s.token, false)}
                                        className="p-1 text-xs font-bold bg-gray-500 hover:bg-gray-600 text-white rounded transition-colors"
                                      >
                                        ↶
                                      </button>
                                    ) : (
                                      <button
                                        title="Reprovar submissão"
                                        onClick={() => handleToggleReprovacao(s.token, true)}
                                        className="p-1 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded transition-colors"
                                      >
                                        ✗
                                      </button>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-xs text-gray-400">N/A (Legado)</span>
                                )}
                              </td>
```

(`revStatus` continua vindo de `const revStatus = s.revisao_status || "pendente";`, linha 632 — não muda; só a interpretação visual, que agora trata qualquer valor diferente de `"reprovado"` como VÁLIDO.)

- [ ] **Step 4: Rodar e ver passar**

Run: `cd frontend && npx --no-install vitest run src/pages/Desafios.test.tsx`
Expected: PASS.

- [ ] **Step 5: Checagem de tipos**

Run: `cd frontend && npx --no-install tsc -b`
Expected: sem erros novos.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Desafios.tsx frontend/src/pages/Desafios.test.tsx
git commit -m "feat: badge de 2 estados (valido/reprovado) e botao unico de reprovar/desfazer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e"
```

---

## Task 6: Regressão final e atualização do runbook

**Files:**
- Modify: `docs/runbooks/sincronizacao-desafios.md` (seção de revisão manual, se existir referência a "aprovar")

**Interfaces:** nenhuma — task de fechamento.

- [ ] **Step 1: Suite completa do backend**

Run: `cd backend && $PY -m pytest tests/ -q`
Expected: PASS (0 failures). Investigar e corrigir qualquer regressão restante antes de prosseguir — nenhuma task anterior tenta prever 100% dos testes vizinhos que citam `revisao_status`/`aprovado`/`pendente`; se a busca abaixo encontrar algo não coberto pelas Tasks 1-3, tratar aqui.

Run: `cd backend && grep -rn "revisao_status\|\"aprovado\"\|'aprovado'" tests/ | grep -v ".pyc"`
Expected: só ocorrências já tratadas (Tasks 1-3) ou testes que seguem válidos sem mudança (ex.: `test_pos_corte_com_revisao_aprovada_legado_ainda_conta`).

- [ ] **Step 2: Suite completa do frontend**

Run: `cd frontend && npx --no-install vitest run`
Expected: PASS (0 failures).

- [ ] **Step 3: Atualizar o runbook, se citar "aprovação manual"**

Run: `grep -n "aprova" "docs/runbooks/sincronizacao-desafios.md"`

Se houver ocorrência descrevendo o fluxo antigo de aprovar/reprovar, substituir por uma nota curta:

```markdown
## Revisão manual de submissões (pós-corte)

Desde 14/09/2026, toda submissão pós-corte conta automaticamente para pontos
(individuais do coach e percentual do clã). A única ação manual disponível é
**reprovar** uma submissão (ou desfazer uma reprovação) em "Desafios" — ver
`docs/superpowers/specs/2026-09-14-desafios-aprovacao-automatica-design.md`.
```

Se não houver ocorrência (o runbook fala só de sincronização da planilha, não de revisão), pular este step sem alterar o arquivo.

- [ ] **Step 4: Commit (só se o Step 3 alterou algo)**

```bash
git add docs/runbooks/sincronizacao-desafios.md
git commit -m "docs: atualiza runbook de desafios para o fluxo de aprovacao automatica

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FbnfCEAhHxsXZ6Q1kDE83e"
```

---

## Resumo de rollout (não é uma task de código — checklist manual pós-merge)

1. Fazer merge desta branch em `master`.
2. Rodar `cd backend && $PY -m admin.backfill_desafio_apuracao_automatica` (dry-run) contra produção e conferir a saída antes de decidir se roda `--apply` — hoje (14/09/2026) o resultado esperado é "Nenhum desafio apurado encontrado", mas o número pode ter mudado entre o levantamento e o merge.
3. Comunicar ao usuário que as ~123 submissões pós-corte hoje pendentes passam a contar automaticamente assim que o deploy for ao ar (decisão já validada — ver spec).
