# Pontos de Grupo por Número de Pessoas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mudar o cálculo de pontos de coaching em grupo/empresa para contar pessoas atendidas (coluna I da planilha) em vez de registros, com carry-over por clã entre aprovações.

**Architecture:** Duas novas colunas no Supabase (`num_participantes` em registros, `pessoas_em_espera` em totais), nova função em `points_engine.py`, e ajustes em `supabase_client.py` e `contabilidade.py`. Nenhuma mudança na planilha ou no frontend é necessária.

**Tech Stack:** Python 3.11+, FastAPI, Supabase (postgrest-py), pytest

---

## Mapa de Arquivos

| Arquivo | Ação |
|---|---|
| `backend/config.py` | Modificar — nova constante `COL_PARTICIPANTES_GROUP` |
| `backend/points_engine.py` | Modificar — nova função `compute_batch_promotions_by_people` |
| `backend/supabase_client.py` | Modificar — `upsert_clan_total` + nova `get_clan_carry_over` |
| `backend/routers/contabilidade.py` | Modificar — `_process_group_records`, `/aprovar-clan`, `AprovarClanResponse` |
| `backend/tests/test_points_engine.py` | Criar — testes unitários para `compute_batch_promotions_by_people` |
| `backend/tests/test_contabilidade_integration.py` | Criar — testes de integração para o fluxo de aprovação |
| Supabase (SQL manual) | Migração — 2 novas colunas |

---

## Task 1: Migração do banco de dados

**Files:**
- Create: `backend/migrations/001_add_participantes_and_carry_over.sql`

- [ ] **Step 1: Criar arquivo de migração SQL**

```sql
-- Adiciona num_participantes em registros (default 1 para compatibilidade)
ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN IF NOT EXISTS num_participantes INTEGER NOT NULL DEFAULT 1;

-- Adiciona carry-over por clã em totais
ALTER TABLE pontos_ultimate_totais_por_clan
ADD COLUMN IF NOT EXISTS pessoas_em_espera INTEGER NOT NULL DEFAULT 0;
```

Salvar em `backend/migrations/001_add_participantes_and_carry_over.sql`.

- [ ] **Step 2: Executar a migração no Supabase**

Acesse o SQL Editor do Supabase e execute o conteúdo do arquivo acima.
Verifique que as colunas aparecem nas tabelas antes de continuar.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/001_add_participantes_and_carry_over.sql
git commit -m "chore: add migration for num_participantes and pessoas_em_espera"
```

---

## Task 2: Adicionar constante em `config.py`

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Adicionar constante após `GROUP_MODALIDADES`**

Abrir `backend/config.py` e adicionar após a linha `GROUP_MODALIDADES = [...]`:

```python
# Coluna I: "Número de pessoas atendidas por você nesse contrato"
COL_PARTICIPANTES_GROUP = 8
```

- [ ] **Step 2: Verificar que o servidor ainda inicia**

```bash
cd backend && python -c "import config; print(config.COL_PARTICIPANTES_GROUP)"
```

Saída esperada: `8`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "chore: add COL_PARTICIPANTES_GROUP constant"
```

---

## Task 3: Nova função em `points_engine.py` (TDD)

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_points_engine.py`
- Modify: `backend/points_engine.py`

- [ ] **Step 1: Instalar pytest se necessário**

```bash
cd backend && pip install pytest
```

- [ ] **Step 2: Criar `backend/tests/__init__.py`**

Arquivo vazio:
```python
```

- [ ] **Step 3: Escrever os testes**

Criar `backend/tests/test_points_engine.py`:

```python
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from points_engine import compute_batch_promotions_by_people


def make_records(counts: list[int]) -> list[dict]:
    """Cria lista de registros com num_participantes para uso nos testes."""
    return [{"id": i + 1, "num_participantes": n} for i, n in enumerate(counts)]


class TestComputeBatchPromotionsByPeople:

    def test_sem_registros_sem_carry_over(self):
        ids, lotes, carry = compute_batch_promotions_by_people([], 0, 5)
        assert ids == []
        assert lotes == 0
        assert carry == 0

    def test_exatamente_um_lote(self):
        records = make_records([5])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 0

    def test_registro_com_mais_de_um_lote(self):
        records = make_records([10])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1]
        assert lotes == 2
        assert carry == 0

    def test_registro_com_sobra(self):
        # 6 pessoas → 1 lote + 1 em espera
        records = make_records([6])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 1

    def test_carry_over_completa_lote(self):
        # carry_over=1, novo registro com 4 → total 5 → 1 lote
        records = make_records([4])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 1, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 0

    def test_multiplos_registros_sem_lote_completo(self):
        # 2 + 2 = 4 pessoas → 0 lotes, todos ficam pendentes
        records = make_records([2, 2])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1, 2]
        assert lotes == 0
        assert carry == 4

    def test_multiplos_registros_dois_lotes(self):
        # 3 + 4 + 3 = 10 → 2 lotes, carry=0
        records = make_records([3, 4, 3])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert sorted(ids) == [1, 2, 3]
        assert lotes == 2
        assert carry == 0

    def test_carry_over_sem_registros_novos(self):
        # Apenas carry-over acumulado, sem registros pendentes
        ids, lotes, carry = compute_batch_promotions_by_people([], 5, 5)
        assert ids == []
        assert lotes == 1
        assert carry == 0

    def test_fallback_num_participantes_ausente(self):
        # Registro sem chave num_participantes usa default 1
        records = [{"id": 1}]
        ids, lotes, carry = compute_batch_promotions_by_people(records, 4, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 0

    def test_sem_lote_completo_retorna_carry_acumulado(self):
        # carry=3 + 1 pessoa = 4 → 0 lotes, carry=4
        records = make_records([1])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 3, 5)
        assert ids == [1]
        assert lotes == 0
        assert carry == 4
```

- [ ] **Step 4: Rodar os testes e confirmar que falham**

```bash
cd backend && python -m pytest tests/test_points_engine.py -v
```

Saída esperada: erros de `ImportError` ou `AttributeError` para `compute_batch_promotions_by_people`.

- [ ] **Step 5: Implementar a função em `points_engine.py`**

Adicionar ao final de `backend/points_engine.py`:

```python
def compute_batch_promotions_by_people(
    pending_records: list[dict],
    pessoas_em_espera: int,
    batch_size: int,
) -> tuple[list[int], int, int]:
    """Calcula lotes baseados em número de pessoas (não registros).

    Soma os participantes de todos os registros pendentes com o carry-over
    existente. Todos os registros pendentes são promovidos de uma vez.

    Retorna (ids_para_promover, n_lotes_completos, novo_carry_over).
    """
    total_pessoas = pessoas_em_espera + sum(
        r.get("num_participantes", 1) for r in pending_records
    )
    n_lotes = total_pessoas // batch_size
    novo_carry_over = total_pessoas % batch_size
    ids_to_promote = [r["id"] for r in pending_records]
    return ids_to_promote, n_lotes, novo_carry_over
```

- [ ] **Step 6: Rodar os testes e confirmar que passam**

```bash
cd backend && python -m pytest tests/test_points_engine.py -v
```

Saída esperada: todos os testes `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add backend/points_engine.py backend/tests/__init__.py backend/tests/test_points_engine.py
git commit -m "feat: add compute_batch_promotions_by_people with tests"
```

---

## Task 4: Atualizar `supabase_client.py`

**Files:**
- Modify: `backend/supabase_client.py`

- [ ] **Step 1: Atualizar `upsert_clan_total` para aceitar `pessoas_em_espera`**

Substituir a função `upsert_clan_total` em `backend/supabase_client.py`:

```python
def upsert_clan_total(clan: str, total: int, pessoas_em_espera: int | None = None) -> dict:
    """Atualiza ou insere o total de pontos de um clã.

    Se pessoas_em_espera for informado, também atualiza o carry-over.
    """
    client = _get_client()
    payload: dict = {"clan": clan, "total_pontos": total}
    if pessoas_em_espera is not None:
        payload["pessoas_em_espera"] = pessoas_em_espera
    result = client.table(TABLE_TOTAIS).upsert(
        payload,
        on_conflict="clan",
    ).execute()
    return result.data[0] if result.data else {}
```

- [ ] **Step 2: Adicionar `get_clan_carry_over` após `upsert_clan_total`**

```python
def get_clan_carry_over(clan: str) -> int:
    """Retorna o carry-over (pessoas_em_espera) atual do clã. Default 0."""
    client = _get_client()
    result = (
        client.table(TABLE_TOTAIS)
        .select("pessoas_em_espera")
        .eq("clan", clan)
        .execute()
    )
    return result.data[0]["pessoas_em_espera"] if result.data else 0
```

- [ ] **Step 3: Verificar que o módulo importa sem erros**

```bash
cd backend && python -c "import supabase_client; print('OK')"
```

Saída esperada: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat: update upsert_clan_total and add get_clan_carry_over"
```

---

## Task 5: Atualizar `contabilidade.py` — inserção de pendentes

**Files:**
- Modify: `backend/routers/contabilidade.py`

- [ ] **Step 1: Adicionar constante `COL_PARTICIPANTES` e atualizar `_process_group_records`**

Logo após a linha `GROUP_MODALIDADES = config.GROUP_MODALIDADES` em `backend/routers/contabilidade.py`, adicionar:

```python
COL_PARTICIPANTES = config.COL_PARTICIPANTES_GROUP
```

- [ ] **Step 2: Substituir o loop de inserção dentro de `_process_group_records`**

Localizar o bloco:
```python
    # 3. Inserir novos como status='pendente', pontos=0
    for record_hash, row in new_records:
        _build_and_insert(
            record_hash, row, header, data_rows,
            pontos=0,
            extra_fields={"status": "pendente"},
        )
```

Substituir por:
```python
    # 3. Inserir novos como status='pendente', pontos=0
    for record_hash, row in new_records:
        raw_participantes = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
        try:
            num_participantes = max(1, int(raw_participantes))
        except (ValueError, AttributeError):
            num_participantes = 1
        _build_and_insert(
            record_hash, row, header, data_rows,
            pontos=0,
            extra_fields={"status": "pendente", "num_participantes": num_participantes},
        )
```

- [ ] **Step 3: Verificar que o servidor inicia sem erros**

```bash
cd backend && python -c "from routers.contabilidade import router; print('OK')"
```

Saída esperada: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: read num_participantes from column I when inserting group pending records"
```

---

## Task 6: Atualizar `contabilidade.py` — endpoint `/aprovar-clan`

**Files:**
- Modify: `backend/routers/contabilidade.py`

- [ ] **Step 1: Atualizar `AprovarClanResponse` com novos campos**

Substituir a classe `AprovarClanResponse`:

```python
class AprovarClanResponse(BaseModel):
    clan: str
    lotes_aprovados: int
    registros_promovidos: int
    pessoas_contabilizadas: int
    pessoas_em_espera: int
    pontos_adicionados: int
    novo_total: int
    pendentes_restantes: int
    mensagem: str
```

- [ ] **Step 2: Substituir a lógica do endpoint `/aprovar-clan`**

Substituir o corpo completo da função `aprovar_clan`:

```python
@router.post("/aprovar-clan", response_model=AprovarClanResponse)
def aprovar_clan(body: AprovarClanRequest):
    """Aprova os lotes completos de grupo/empresa de um clã e contabiliza os pontos."""
    try:
        clan = _normalize_clan(body.clan)
        pending = supabase_client.get_pending_group_records_by_clan(clan, GROUP_MODALIDADES)
        carry_over = supabase_client.get_clan_carry_over(clan)

        ids_to_promote, n_complete, novo_carry_over = points_engine.compute_batch_promotions_by_people(
            pending, carry_over, config.BATCH_SIZE_GROUP
        )

        if n_complete == 0:
            return AprovarClanResponse(
                clan=clan,
                lotes_aprovados=0,
                registros_promovidos=0,
                pessoas_contabilizadas=0,
                pessoas_em_espera=carry_over + sum(r.get("num_participantes", 1) for r in pending),
                pontos_adicionados=0,
                novo_total=supabase_client.get_clan_totals().get(clan, 0),
                pendentes_restantes=len(pending),
                mensagem=f"Nenhum lote completo disponível. {len(pending)} registro(s) ainda aguardando.",
            )

        pessoas_contabilizadas = carry_over + sum(r.get("num_participantes", 1) for r in pending)

        supabase_client.promote_pending_to_contabilizado(
            ids_to_promote, config.POINTS_PER_RECORD_IN_BATCH
        )
        pontos_adicionados = n_complete * config.POINTS_PER_BATCH_GROUP
        current_totals = supabase_client.get_clan_totals()
        novo_total = current_totals.get(clan, 0) + pontos_adicionados
        supabase_client.upsert_clan_total(clan, novo_total, pessoas_em_espera=novo_carry_over)

        google_sheets_client.update_clan_totals({clan: pontos_adicionados})

        pendentes_restantes = len(pending) - len(ids_to_promote)

        return AprovarClanResponse(
            clan=clan,
            lotes_aprovados=n_complete,
            registros_promovidos=len(ids_to_promote),
            pessoas_contabilizadas=pessoas_contabilizadas,
            pessoas_em_espera=novo_carry_over,
            pontos_adicionados=pontos_adicionados,
            novo_total=novo_total,
            pendentes_restantes=pendentes_restantes,
            mensagem=(
                f"{n_complete} lote(s) aprovado(s) para {clan}. "
                f"+{pontos_adicionados} pontos. "
                f"Total agora: {novo_total} pts. "
                f"{novo_carry_over} pessoa(s) em espera."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 3: Verificar que o servidor inicia sem erros**

```bash
cd backend && python -c "from routers.contabilidade import router; print('OK')"
```

Saída esperada: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: update aprovar-clan to use people-based batch logic with carry-over"
```

---

## Task 7: Teste de integração do fluxo completo

**Files:**
- Create: `backend/tests/test_contabilidade_integration.py`

> Estes testes usam mocks para isolar a lógica sem chamar Supabase ou Google Sheets.

- [ ] **Step 1: Criar `backend/tests/test_contabilidade_integration.py`**

```python
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import points_engine


class TestFluxoAprovacaoCompleto:
    """Testa a composição de compute_batch_promotions_by_people com cenários reais."""

    def test_cenario_usuario_6_pessoas(self):
        """CLÃ 5 tem 1 registro com 6 pessoas. Deve ganhar 30 pts, 1 em espera."""
        pending = [{"id": 1, "num_participantes": 6}]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 0, 5)
        assert lotes == 1
        assert carry == 1
        assert ids == [1]

    def test_cenario_usuario_6_mais_4_pessoas(self):
        """Depois do cenário anterior (carry=1), novo registro com 4 pessoas.
        Total: 1 + 4 = 5. Deve ganhar mais 30 pts, carry=0."""
        pending = [{"id": 2, "num_participantes": 4}]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 1, 5)
        assert lotes == 1
        assert carry == 0
        assert ids == [2]

    def test_cenario_multiplos_registros_acumulados(self):
        """3 registros: 2 + 2 + 3 pessoas = 7. Carry inicial 0.
        Resultado: 1 lote (5 pts), carry=2."""
        pending = [
            {"id": 1, "num_participantes": 2},
            {"id": 2, "num_participantes": 2},
            {"id": 3, "num_participantes": 3},
        ]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 0, 5)
        assert lotes == 1
        assert carry == 2
        assert sorted(ids) == [1, 2, 3]

    def test_cenario_sem_lote_completo_nao_promove(self):
        """4 pessoas no total. Nenhum lote completo. IDs ainda são retornados
        (chamador decide não promover quando n_lotes == 0)."""
        pending = [{"id": 1, "num_participantes": 4}]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 0, 5)
        assert lotes == 0
        assert carry == 4
        assert ids == [1]  # IDs retornados mas não devem ser promovidos (n_lotes == 0)

    def test_cenario_carry_over_acumulado_varios_ciclos(self):
        """Simula 3 ciclos: carry cresce até completar lote."""
        # Ciclo 1: 3 pessoas, carry=0 → carry=3
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(
            [{"id": 1, "num_participantes": 3}], 0, 5
        )
        assert lotes == 0
        assert carry == 3

        # Ciclo 2: 1 pessoa, carry=3 → carry=4
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(
            [{"id": 2, "num_participantes": 1}], carry, 5
        )
        assert lotes == 0
        assert carry == 4

        # Ciclo 3: 3 pessoas, carry=4 → total=7 → 1 lote, carry=2
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(
            [{"id": 3, "num_participantes": 3}], carry, 5
        )
        assert lotes == 1
        assert carry == 2
```

- [ ] **Step 2: Rodar todos os testes**

```bash
cd backend && python -m pytest tests/ -v
```

Saída esperada: todos os testes `PASSED` (incluindo `test_points_engine.py` e `test_contabilidade_integration.py`).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_contabilidade_integration.py
git commit -m "test: add integration tests for people-based batch approval flow"
```

---

## Task 8: Smoke test manual do servidor

- [ ] **Step 1: Iniciar o servidor**

```bash
cd backend && uvicorn main:app --reload
```

- [ ] **Step 2: Verificar que os endpoints respondem**

```bash
curl -s http://localhost:8000/docs | grep -o "openapi" | head -1
```

Saída esperada: `openapi`

- [ ] **Step 3: Executar contabilidade e verificar que registros de grupo são inseridos com `num_participantes`**

```bash
curl -s -X POST http://localhost:8000/contabilidade/executar | python -m json.tool
```

Verificar no Supabase que os novos registros pendentes possuem `num_participantes > 0`.

- [ ] **Step 4: Testar aprovação de um clã**

```bash
curl -s -X POST http://localhost:8000/contabilidade/aprovar-clan \
  -H "Content-Type: application/json" \
  -d '{"clan": "CLÃ 1"}' | python -m json.tool
```

Verificar que a resposta contém `pessoas_contabilizadas` e `pessoas_em_espera`.

- [ ] **Step 5: Commit final**

```bash
git add -A
git commit -m "feat: complete group points by people — carry-over logic with DB migration"
```
