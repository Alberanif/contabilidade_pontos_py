# Fix Filtro de Data — Registros Importados

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir `importar_inicial()` para atribuir valores de `pontos` corretos a cada tipo de registro, fazendo o filtro de data no Dashboard subtrair corretamente os registros importados.

**Architecture:** Mudança cirúrgica em `importar_inicial()` — trocar `pontos=0` por constantes corretas por tipo (CI coaching, grupo contabilizado, pro-bono). A abordagem de subtração do filtro já funciona; o problema era que todos os registros importados tinham `pontos=0`, tornando a subtração inoperante. O filtro de data faz `total_atual - SUM(pontos WHERE data_registro > ate)`, e a correção restaura o invariante `SUM(pontos dos registros) ≈ total de coaching atual`.

**Tech Stack:** Python/FastAPI, pytest, `points_engine.filter_records_by_date_from()`

---

## Arquivos

- **Modificar:** `backend/routers/contabilidade.py` — Fases 3, 4 e 8 de `importar_inicial()`
- **Modificar:** `backend/supabase_client.py` — remover comentário desatualizado (~linha 502)
- **Criar:** `backend/tests/test_importar_inicial_pontos.py` — testes dos valores de pontos inseridos

---

### Task 1: Testes para os valores de pontos esperados por tipo de registro

**Files:**
- Create: `backend/tests/test_importar_inicial_pontos.py`

- [ ] **Step 1: Criar o arquivo de teste com os 5 cenários**

```python
# backend/tests/test_importar_inicial_pontos.py
"""Verifica que importar_inicial() grava pontos corretos por tipo de registro.

Todos os mocks são aplicados antes de qualquer import do módulo router,
pois config.py chama _validate() no import e exige env vars.
"""
import os
import sys

# Env vars mínimas antes de qualquer import que carregue config.py
_FAKE_ENV = {
    "GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
    "GSHEET_RECORDS_SPREADSHEET_ID": "fake-id",
    "GSHEET_RECORDS_SHEET_NAME": "Sheet1",
    "GSHEET_TOTALS_SPREADSHEET_ID": "fake-totals-id",
    "GSHEET_TOTALS_SHEET_NAME": "Totals",
    "SUPABASE_URL": "https://fake.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "fake-key",
}
for k, v in _FAKE_ENV.items():
    os.environ.setdefault(k, v)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
import config


# ── Helpers para construir linhas de planilha ──────────────────────────────

def _ci_row(date_str: str) -> list[str]:
    row = [""] * 12
    row[0] = "1"                       # clan (col 0)
    row[1] = "Coach X"                 # coach (COL_COACH = 1)
    row[5] = "Coaching Individual"     # modalidade (COL_MODALIDADE = 5)
    row[10] = date_str                 # data (COL_DATE_PAYING = 10)
    row[11] = f"CI-{date_str}"         # chave hash (KEY_COLUMNS = [11])
    return row


def _group_row(date_str: str, n: int = 6) -> list[str]:
    row = [""] * 12
    row[0] = "1"
    row[1] = "Coach X"
    row[5] = "Coaching em grupo"       # modalidade
    row[8] = str(n)                    # participantes (COL_PARTICIPANTES_GROUP = 8)
    row[10] = date_str
    row[11] = f"GRP-{date_str}-{n}"
    return row


def _pb_row(date_str: str) -> list[str]:
    row = [""] * 12
    row[0] = "1"
    row[1] = "Coach X"
    row[9] = date_str                  # data pro-bono (COL_DATE_PRO_BONO = 9)
    row[10] = f"PB-{date_str}"         # chave (COL_PRO_BONO_KEY = 10)
    return row


HEADER = ["clan", "coach", "", "", "", "modalidade", "", "", "participantes", "", "data", "key"]
PB_HEADER = ["clan", "coach", "", "", "", "", "", "", "", "data_pb", "key_pb", ""]


# ── Helper para executar o import com mocks ────────────────────────────────

def _run_import(ci_rows=None, group_rows=None, pb_rows=None, ranking=None):
    """Executa importar_inicial() com deps externas mockadas.

    Retorna a lista de dicts passados a insert_processed_record.
    """
    ci_rows = ci_rows or []
    group_rows = group_rows or []
    pb_rows = pb_rows or []
    ranking = ranking or []

    inserted: list[dict] = []

    def capture_insert(record_data: dict):
        inserted.append(dict(record_data))

    with patch("routers.contabilidade.supabase_client") as mock_supa, \
         patch("routers.contabilidade.google_sheets_client") as mock_gsc:

        mock_supa.delete_all_registros.return_value = 0
        mock_supa.reset_all_totals.return_value = None
        mock_supa.upsert_clan_total.return_value = None
        mock_supa.upsert_coach_total.return_value = None
        mock_supa.insert_processed_record.side_effect = capture_insert

        mock_gsc.fetch_records.return_value = [HEADER] + ci_rows + group_rows
        mock_gsc.fetch_records_pro_bono.return_value = [PB_HEADER] + pb_rows
        mock_gsc.fetch_ranking.return_value = ranking

        from routers.contabilidade import importar_inicial
        importar_inicial()

    return inserted


# ── Testes ─────────────────────────────────────────────────────────────────

class TestImportarInicialPontos:

    def test_ci_elegivel_pontos_e_pontos_coach_corretos(self):
        """CI coaching com data >= COACH_RANKING_START_DATE:
        pontos = POINTS_PER_COACHING_INDIVIDUAL, pontos_coach = POINTS_PER_COACHING_INDIVIDUAL."""
        records = _run_import(
            ci_rows=[_ci_row("06/04/2026")],
            ranking=[{"clan": "CLÃ 1", "total_pontos": 30}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_COACHING_INDIVIDUAL
        assert records[0]["pontos_coach"] == config.POINTS_PER_COACHING_INDIVIDUAL

    def test_ci_inelegivel_pontos_coach_zero(self):
        """CI coaching com data < COACH_RANKING_START_DATE (antes de 01/04/2026):
        pontos = POINTS_PER_COACHING_INDIVIDUAL, pontos_coach = 0."""
        records = _run_import(
            ci_rows=[_ci_row("15/03/2026")],
            ranking=[{"clan": "CLÃ 1", "total_pontos": 30}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_COACHING_INDIVIDUAL
        assert records[0]["pontos_coach"] == 0

    def test_grupo_contabilizado_pontos_per_record_in_batch(self):
        """Grupo com pessoas >= BATCH_SIZE_GROUP (clã tem lote completo):
        pontos = POINTS_PER_RECORD_IN_BATCH."""
        records = _run_import(
            group_rows=[_group_row("06/04/2026", n=6)],  # 6 >= BATCH_SIZE_GROUP (5)
            ranking=[{"clan": "CLÃ 1", "total_pontos": 6}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_RECORD_IN_BATCH

    def test_grupo_pendente_pontos_zero(self):
        """Grupo com pessoas < BATCH_SIZE_GROUP (sem lote completo): pontos = 0."""
        records = _run_import(
            group_rows=[_group_row("06/04/2026", n=2)],  # 2 < BATCH_SIZE_GROUP (5)
            ranking=[{"clan": "CLÃ 1", "total_pontos": 0}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == 0

    def test_pro_bono_pontos_per_pro_bono(self):
        """Pro-bono contabilizado: pontos = POINTS_PER_PRO_BONO."""
        records = _run_import(
            pb_rows=[_pb_row("06/04/2026")],
            ranking=[{"clan": "CLÃ 1", "total_pontos": 10}],
        )
        assert len(records) == 1
        assert records[0]["pontos"] == config.POINTS_PER_PRO_BONO
```

- [ ] **Step 2: Executar os testes para confirmar que FALHAM**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_pontos.py -v 2>&1 | head -60
```

Esperado: 5 testes FAILING — os 3 primeiros falham porque `pontos` e `pontos_coach` esperados diferem de `0`; os outros 2 (grupo pendente e pro-bono) também falham com `pontos = 0` recebido vs esperado.

---

### Task 2: Corrigir Fase 3 — CI Coaching

**Files:**
- Modify: `backend/routers/contabilidade.py:647-665`

- [ ] **Step 1: Substituir o bloco de inserção dos CI records na Fase 3**

Localizar o bloco que começa em `# Fase 3: Importar Coaching Individual como contabilizado` (~linha 647).

Substituir o trecho existente pelo abaixo (a diferença está na adição de `coach_eligible_set` e nos valores de `pontos`/`pontos_coach`):

```python
        # Fase 3: Importar Coaching Individual como contabilizado
        coaching_rows = points_engine.filter_by_modalidade(
            data_rows, COL_MODALIDADE, "Coaching Individual"
        )
        coaching_records = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS), row)
            for row in coaching_rows
        ]
        coach_eligible_set = {
            h for h, _ in points_engine.filter_records_by_date_from(
                coaching_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
            )
        }
        for record_hash, row in coaching_records:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
                extra_fields={
                    "status": "contabilizado",
                    "status_coach": "contabilizado",
                    "pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL if record_hash in coach_eligible_set else 0,
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 2: Executar testes de CI**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_ci_elegivel_pontos_e_pontos_coach_corretos tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_ci_inelegivel_pontos_coach_zero -v
```

Esperado: 2 PASSED.

---

### Task 3: Corrigir Fase 4 — Group Coaching

**Files:**
- Modify: `backend/routers/contabilidade.py:715-724`

- [ ] **Step 1: Substituir a chamada `_build_and_insert` para registros de grupo**

Localizar dentro do loop `for record_hash, row in group_records:` (~linha 701) e substituir apenas a chamada a `_build_and_insert` (o restante do loop permanece igual):

```python
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_RECORD_IN_BATCH if status == "contabilizado" else 0,
                extra_fields={
                    "status": status,
                    "status_coach": status_coach,
                    "num_participantes": num_participantes,
                    "pontos_coach": 0,
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 2: Executar testes de grupo**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_grupo_contabilizado_pontos_per_record_in_batch tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_grupo_pendente_pontos_zero -v
```

Esperado: 2 PASSED.

---

### Task 4: Corrigir Fase 8 — Pro-bono

**Files:**
- Modify: `backend/routers/contabilidade.py:776-786`

- [ ] **Step 1: Substituir a chamada `_build_and_insert_pro_bono` na Fase 8**

Localizar dentro de `# Fase 8: Importar registros Pro-bono` (~linha 769) e substituir:

```python
            for record_hash, row in pb_records:
                _build_and_insert_pro_bono(
                    record_hash, row, pb_header, pb_data_rows,
                    pontos=config.POINTS_PER_PRO_BONO,
                    extra_fields={
                        "status": "contabilizado",
                        "status_coach": "contabilizado",
                        "pontos_coach": 0,
                    },
                    date_col=config.COL_DATE_PRO_BONO,
                )
```

Nota: `pontos_coach = 0` é intencional — o total de coaches é semeado apenas de CI (Fase 7). Pro-bono coach points para registros NOVOS (via `executar()`) são tratados corretamente lá.

- [ ] **Step 2: Executar teste de pro-bono**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_pro_bono_pontos_per_pro_bono -v
```

Esperado: PASSED.

---

### Task 5: Atualizar comentário desatualizado no supabase_client

**Files:**
- Modify: `backend/supabase_client.py:499-502`

- [ ] **Step 1: Localizar e corrigir a docstring de `get_historico_clan_totals`**

Em `backend/supabase_client.py`, a função `get_historico_clan_totals` tem atualmente a docstring:

```python
def get_historico_clan_totals(ate: date) -> dict[str, int]:
    """Calcula totais por clã até `ate` subtraindo do total atual os pontos de registros
    com data_registro > ate. Correto porque TABLE_TOTAIS já contém o total acumulado completo
    e apenas registros do executar_contabilidade têm pontos > 0."""
```

Substituir por:

```python
def get_historico_clan_totals(ate: date) -> dict[str, int]:
    """Calcula totais por clã até `ate` subtraindo do total atual os pontos de registros
    com data_registro > ate."""
```

---

### Task 6: Rodar suite completa e commitar

- [ ] **Step 1: Rodar todos os testes**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/ -v
```

Esperado: Todos os testes existentes PASSAM + os 5 novos PASSAM. Output de exemplo:

```
tests/test_contabilidade_integration.py::TestFluxoAprovacaoCompleto::... PASSED
tests/test_points_engine.py::... PASSED
tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_ci_elegivel_pontos_e_pontos_coach_corretos PASSED
tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_ci_inelegivel_pontos_coach_zero PASSED
tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_grupo_contabilizado_pontos_per_record_in_batch PASSED
tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_grupo_pendente_pontos_zero PASSED
tests/test_importar_inicial_pontos.py::TestImportarInicialPontos::test_pro_bono_pontos_per_pro_bono PASSED
```

- [ ] **Step 2: Verificar status do git**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE
git diff --stat
```

Esperado: 3 arquivos modificados (`contabilidade.py`, `supabase_client.py`, novo `test_importar_inicial_pontos.py`).

- [ ] **Step 3: Commitar**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE
git add backend/routers/contabilidade.py backend/supabase_client.py backend/tests/test_importar_inicial_pontos.py
git commit -m "fix(import): set correct pontos per record type in importar_inicial

Imported records previously had pontos=0, making the date filter
unable to subtract their contribution. Now:
- CI coaching: POINTS_PER_COACHING_INDIVIDUAL (pontos_coach set for eligible dates only)
- Group contabilizado: POINTS_PER_RECORD_IN_BATCH
- Group pendente: 0 (not yet counted)
- Pro-bono: POINTS_PER_PRO_BONO"
```

---

### Task 7: Verificação E2E no Dashboard

- [ ] **Step 1: Executar importação**

Com o backend rodando, acessar a página Contabilidade e clicar em "Importar Dados Existentes". Confirmar o diálogo.

- [ ] **Step 2: Verificar no Supabase que pontos foram gravados**

Executar no Supabase SQL Editor:

```sql
SELECT
  modalidade,
  status,
  pontos,
  pontos_coach,
  data_registro
FROM pontos_ultimate_registros_contabilizados
ORDER BY data_registro DESC
LIMIT 20;
```

Esperado:
- Registros CI: `pontos = 30`
- Registros grupo contabilizados: `pontos = 6`
- Registros pro-bono: `pontos = 10`

- [ ] **Step 3: Testar filtro de data — deve diminuir totais**

No Dashboard, definir data de corte para 5-7 dias atrás (ex: `2026-04-10`). Verificar que os totais dos clãs DIMINUEM em relação ao display sem filtro.

- [ ] **Step 4: Confirmar "hoje" = total sem filtro**

Definir a data de corte para hoje (`2026-04-17`). Os totais devem ser idênticos ao display sem filtro (subtração = 0).

- [ ] **Step 5: Verificar filtro de coaches**

Definir data de corte para `2026-03-31` (antes do `COACH_RANKING_START_DATE = 2026-04-01`). O ranking de coaches deve mostrar todos os totais zerados (nenhum CI é elegível antes de abril).
