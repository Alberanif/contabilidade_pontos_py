# Remove COACH_RANKING_START_DATE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover a constante `COACH_RANKING_START_DATE` de todos os 7 locais no código, fazendo todos os registros de coaches contarem pontos independentemente da data.

**Architecture:** Cada local de uso é corrigido individualmente, do mais simples ao mais complexo. A constante só é removida do `config.py` no final, após todas as referências no código terem sido eliminadas. Testes focados validam as três mudanças comportamentais principais.

**Tech Stack:** Python 3.11, FastAPI, pytest, unittest.mock

---

## File Map

| Arquivo | Ação | O que muda |
|---|---|---|
| `backend/tests/test_importar_inicial_coach_points.py` | Criar | Testes TDD para comportamento sem restrição de data |
| `backend/routers/contabilidade.py` | Modificar | 7 locais: `_process_pro_bono_records`, `_process_group_records`, `executar_contabilidade`, `reprocessar_contabilidade`, `importar_inicial` Fase 3, Fase 7+8, `debug_date_sample` |
| `backend/config.py` | Modificar | Remover constante `COACH_RANKING_START_DATE` (feito por último) |

---

### Task 1: Escrever os testes que devem falhar

**Arquivos:**
- Criar: `backend/tests/test_importar_inicial_coach_points.py`

- [ ] **Step 1: Criar o arquivo de testes**

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import (
    _process_group_records,
    _process_pro_bono_records,
    importar_inicial,
)


def _group_row(date_str: str, key: str = "key_grp") -> list[str]:
    # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_PARTICIPANTES=8,
    # COL_DATE_PAYING=10, KEY_COLUMNS=[11]
    return ["1", "Coach A", "", "", "", "Coaching em grupo", "", "", "3", "", date_str, key]


def _pb_row(date_str: str, key: str = "key_pb") -> list[str]:
    # COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10
    return ["1", "Coach A", "", "", "", "", "", "", "", date_str, key]


def _ci_row(date_str: str, key: str = "key_ci") -> list[str]:
    # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_DATE_PAYING=10, KEY_COLUMNS=[11]
    return ["1", "Coach A", "", "", "", "Coaching Individual", "", "", "", "", date_str, key]


class TestGroupRecordAlwaysPendente:
    """Registros de grupo via executar devem sempre ter status_coach='pendente'."""

    def _run(self, date_str: str) -> list[dict]:
        row = _group_row(date_str)
        header = [f"col_{i}" for i in range(len(row))]
        inserted: list[dict] = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.insert_processed_record", side_effect=capture), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_pending_group_records_by_clan", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]), \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]):
            _process_group_records([row], header, processed_hashes=set())

        return inserted

    def test_pre_april_group_gets_status_coach_pendente(self):
        inserted = self._run("15/03/2026")
        assert len(inserted) == 1
        assert inserted[0]["status_coach"] == "pendente"

    def test_post_april_group_gets_status_coach_pendente(self):
        inserted = self._run("15/04/2026")
        assert len(inserted) == 1
        assert inserted[0]["status_coach"] == "pendente"


class TestProBonoAlways10Pts:
    """Registros Pro Bono devem sempre ter pontos_coach=10."""

    def _run(self, date_str: str) -> list[dict]:
        pb_row = _pb_row(date_str)
        header = [f"col_{i}" for i in range(len(pb_row))]
        inserted: list[dict] = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("google_sheets_client.fetch_records_pro_bono", return_value=[header, pb_row]), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _process_pro_bono_records(processed_hashes=set())

        return inserted

    def test_pre_april_pro_bono_gets_pontos_coach_10(self):
        inserted = self._run("15/03/2026")
        assert len(inserted) == 1
        assert inserted[0]["pontos_coach"] == 10

    def test_post_april_pro_bono_gets_pontos_coach_10(self):
        inserted = self._run("15/04/2026")
        assert len(inserted) == 1
        assert inserted[0]["pontos_coach"] == 10


class TestIndividualCoachingAlways30Pts:
    """Coaching Individual em importar_inicial deve sempre ter pontos_coach=30."""

    def _run(self, date_str: str) -> list[dict]:
        header = [f"col_{i}" for i in range(12)]
        row = _ci_row(date_str)
        pb_header = [f"col_{i}" for i in range(11)]
        inserted: list[dict] = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=[header, row]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=[pb_header]), \
             patch("google_sheets_client.fetch_ranking",
                   return_value=[{"clan": "CLÃ 1", "total_pontos": 30}]), \
             patch("supabase_client.insert_processed_record", side_effect=capture), \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.upsert_clan_total", return_value={}), \
             patch("supabase_client.upsert_coach_total", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]):
            importar_inicial()

        return [r for r in inserted if r.get("modalidade") == "Coaching Individual"]

    def test_pre_april_individual_coaching_gets_pontos_coach_30(self):
        ci = self._run("15/03/2026")
        assert len(ci) == 1
        assert ci[0]["pontos_coach"] == 30

    def test_post_april_individual_coaching_gets_pontos_coach_30(self):
        ci = self._run("15/04/2026")
        assert len(ci) == 1
        assert ci[0]["pontos_coach"] == 30
```

- [ ] **Step 2: Confirmar que os testes pré-Abril falham**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_coach_points.py -v
```

Esperado: `test_pre_april_group_gets_status_coach_pendente` FAIL, `test_pre_april_pro_bono_gets_pontos_coach_10` FAIL, `test_pre_april_individual_coaching_gets_pontos_coach_30` FAIL. Os três testes pós-Abril podem já passar.

---

### Task 2: Corrigir `_process_pro_bono_records`

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

- [ ] **Step 1: Remover o filtro de data**

Localizar este bloco (dentro de `_process_pro_bono_records`, após o cálculo de `pontos_por_clan`):

```python
    coach_eligible_pb = points_engine.filter_records_by_date_from(
        new_records, config.COL_DATE_PRO_BONO, config.COACH_RANKING_START_DATE
    )
    pontos_por_coach = points_engine.calculate_points_by_coach(
        coach_eligible_pb, COL_COACH, config.POINTS_PER_PRO_BONO
    )
```

Substituir por:

```python
    pontos_por_coach = points_engine.calculate_points_by_coach(
        new_records, COL_COACH, config.POINTS_PER_PRO_BONO
    )
```

- [ ] **Step 2: Rodar os testes de Pro Bono**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_coach_points.py::TestProBonoAlways10Pts -v
```

Esperado: ambos PASS.

- [ ] **Step 3: Rodar todos os testes**

```bash
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: pro bono coach points count for all dates in executar"
```

---

### Task 3: Corrigir `_process_group_records`

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

- [ ] **Step 1: Remover o check de data e simplificar o insert**

Localizar este bloco (dentro de `_process_group_records`, no loop `for record_hash, row in new_records`):

```python
        record_date = points_engine.parse_date(
            row[config.COL_DATE_PAYING].strip() if config.COL_DATE_PAYING < len(row) else ""
        )
        coach_elegivel = record_date is not None and record_date >= config.COACH_RANKING_START_DATE
        _build_and_insert(
            record_hash, row, header, data_rows,
            pontos=0,
            extra_fields={
                "status": "pendente",
                "num_participantes": num_participantes,
                "status_coach": "pendente" if coach_elegivel else "contabilizado",
                "pontos_coach": 0
            },
            date_col=config.COL_DATE_PAYING,
        )
```

Substituir por:

```python
        _build_and_insert(
            record_hash, row, header, data_rows,
            pontos=0,
            extra_fields={
                "status": "pendente",
                "num_participantes": num_participantes,
                "status_coach": "pendente",
                "pontos_coach": 0
            },
            date_col=config.COL_DATE_PAYING,
        )
```

- [ ] **Step 2: Rodar os testes de grupo**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_coach_points.py::TestGroupRecordAlwaysPendente -v
```

Esperado: ambos PASS.

- [ ] **Step 3: Rodar todos os testes**

```bash
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: group coaching records always enter coach approval queue"
```

---

### Task 4: Corrigir `executar_contabilidade`

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

- [ ] **Step 1: Remover o filtro de data do cálculo de pontos do coach**

Localizar este bloco (dentro de `executar_contabilidade`, após o cálculo de `pontos_por_clan`):

```python
        coach_eligible_ci = points_engine.filter_records_by_date_from(
            new_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
        )
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coach_eligible_ci, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
```

Substituir por:

```python
        pontos_por_coach = points_engine.calculate_points_by_coach(
            new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
```

- [ ] **Step 2: Rodar todos os testes**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: individual coaching coach points count for all dates in executar"
```

---

### Task 5: Corrigir `reprocessar_contabilidade`

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

- [ ] **Step 1: Remover o filtro de data do cálculo de totais do coach**

Localizar este bloco (dentro de `reprocessar_contabilidade`, após o cálculo de `pontos_por_clan`):

```python
        coach_eligible_ci = points_engine.filter_records_by_date_from(
            new_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
        )
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coach_eligible_ci, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
```

Substituir por:

```python
        pontos_por_coach = points_engine.calculate_points_by_coach(
            new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
```

> Nota: `reprocessar_contabilidade` já insere os registros individuais com `pontos_coach = 30` (sem check de data). Esta mudança afeta apenas o acúmulo do total por coach no loop de upsert subsequente.

- [ ] **Step 2: Rodar todos os testes**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: individual coaching coach points count for all dates in reprocessar"
```

---

### Task 6: Corrigir `importar_inicial` Fase 3

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

- [ ] **Step 1: Remover `coach_eligible_set` e simplificar o insert**

Localizar este bloco (dentro de `importar_inicial`, seção "Fase 3"):

```python
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

Substituir por:

```python
        for record_hash, row in coaching_records:
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
                extra_fields={
                    "status": "contabilizado",
                    "status_coach": "contabilizado",
                    "pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL,
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 2: Rodar os testes de Coaching Individual**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/test_importar_inicial_coach_points.py::TestIndividualCoachingAlways30Pts -v
```

Esperado: ambos PASS.

- [ ] **Step 3: Rodar todos os testes**

```bash
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: individual coaching always gets pontos_coach=30 in importar_inicial"
```

---

### Task 7: Corrigir `importar_inicial` Fases 7 e 8 (juntas)

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

> As Fases 7 e 8 são corrigidas juntas porque a Fase 8 usa `coach_eligible_pb_hashes` definido na Fase 7.

- [ ] **Step 1: Substituir o bloco da Fase 7**

Localizar este bloco (dentro de `importar_inicial`, seção "Fase 7"):

```python
        # Fase 7: Totais e carry-over por coach.
        # Apenas registros >= COACH_RANKING_START_DATE contam para pontuação de coaches.
        coach_eligible_seed = points_engine.filter_records_by_date_from(
            coaching_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
        )
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coach_eligible_seed, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        # Pontos Pro-bono elegíveis para coaches (data >= COACH_RANKING_START_DATE)
        pb_data_for_coach = pb_rows_seed[1:] if pb_rows_seed else []
        pb_records_for_coach = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO), row)
            for row in pb_data_for_coach
        ]
        coach_eligible_pb_seed = points_engine.filter_records_by_date_from(
            pb_records_for_coach, config.COL_DATE_PRO_BONO, config.COACH_RANKING_START_DATE
        )
        pro_bono_coach_pts_seed = points_engine.calculate_points_by_coach(
            coach_eligible_pb_seed, COL_COACH, config.POINTS_PER_PRO_BONO
        )
        coach_eligible_pb_hashes = {h for h, _ in coach_eligible_pb_seed}
```

Substituir por:

```python
        # Fase 7: Totais e carry-over por coach.
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coaching_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        pb_data_for_coach = pb_rows_seed[1:] if pb_rows_seed else []
        pb_records_for_coach = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO), row)
            for row in pb_data_for_coach
        ]
        pro_bono_coach_pts_seed = points_engine.calculate_points_by_coach(
            pb_records_for_coach, COL_COACH, config.POINTS_PER_PRO_BONO
        )
```

- [ ] **Step 2: Corrigir a Fase 8 (mesma edição)**

Localizar este trecho (dentro de `importar_inicial`, seção "Fase 8", dentro do loop `for record_hash, row in pb_records`):

```python
                    "pontos_coach": config.POINTS_PER_PRO_BONO if record_hash in coach_eligible_pb_hashes else 0,
```

Substituir por:

```python
                    "pontos_coach": config.POINTS_PER_PRO_BONO,
```

- [ ] **Step 3: Rodar todos os testes**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat: pro bono coach points and totals count for all dates in importar_inicial"
```

---

### Task 8: Simplificar `debug_date_sample`

**Arquivos:**
- Modificar: `backend/routers/contabilidade.py`

- [ ] **Step 1: Substituir o corpo inteiro da função**

Localizar o endpoint `@router.get("/debug/date-sample")` e substituir o corpo completo da função por:

```python
@router.get("/debug/date-sample")
def debug_date_sample():
    """Diagnóstico: resumo por modalidade e amostra dos primeiros registros."""
    rows_pay = google_sheets_client.fetch_records()
    rows_pb  = google_sheets_client.fetch_records_pro_bono()

    ci_total = 0
    group_total = 0
    ci_sample = []

    for i, row in enumerate(rows_pay[1:], start=2):
        modalidade = row[COL_MODALIDADE].strip() if COL_MODALIDADE < len(row) else ""
        coach = row[config.COL_COACH].strip() if config.COL_COACH < len(row) else ""
        raw_date = row[config.COL_DATE_PAYING] if config.COL_DATE_PAYING < len(row) else ""
        parsed = points_engine.parse_date(raw_date)
        if modalidade.upper() == "COACHING INDIVIDUAL":
            ci_total += 1
            if len(ci_sample) < 10:
                ci_sample.append({
                    "linha": i, "coach": coach,
                    "col_k_raw": raw_date, "data_parsed": str(parsed) if parsed else None,
                })
        elif any(m.upper() in modalidade.upper() for m in ["GRUPO", "EMPRESA"]):
            group_total += 1

    pb_total = 0
    pb_sample = []
    for i, row in enumerate(rows_pb[1:], start=2):
        coach = row[config.COL_COACH].strip() if config.COL_COACH < len(row) else ""
        raw_date = row[config.COL_DATE_PRO_BONO] if config.COL_DATE_PRO_BONO < len(row) else ""
        parsed = points_engine.parse_date(raw_date)
        pb_total += 1
        if len(pb_sample) < 10:
            pb_sample.append({
                "linha": i, "coach": coach,
                "col_j_raw": raw_date, "data_parsed": str(parsed) if parsed else None,
            })

    return {
        "resumo": {
            "ci_total": ci_total,
            "group_total": group_total,
            "pro_bono_total": pb_total,
        },
        "ci_amostra": ci_sample,
        "pro_bono_amostra": pb_sample,
        "config": {
            "col_date_paying": config.COL_DATE_PAYING,
            "col_date_pro_bono": config.COL_DATE_PRO_BONO,
        },
    }
```

- [ ] **Step 2: Rodar todos os testes**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/ -v
```

Esperado: todos passam.

- [ ] **Step 3: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "refactor: simplify debug endpoint after removing COACH_RANKING_START_DATE references"
```

---

### Task 9: Remover `COACH_RANKING_START_DATE` de `config.py`

**Arquivos:**
- Modificar: `backend/config.py`

> Este é o último passo — a constante só é removida após todas as referências terem sido eliminadas do código.

- [ ] **Step 1: Confirmar que não há mais referências no código**

```bash
grep -r "COACH_RANKING_START_DATE" /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend/routers/
```

Esperado: saída vazia (zero matches).

- [ ] **Step 2: Remover a constante de config.py**

Localizar e remover estas duas linhas no final de `backend/config.py`:

```python
from datetime import date as _date
COACH_RANKING_START_DATE = _date(2026, 4, 1)
```

- [ ] **Step 3: Verificar se `_date` é usado em outro lugar em config.py**

```bash
grep "_date" /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend/config.py
```

Se a saída for vazia, o import foi removido corretamente. Se houver outra referência a `_date`, mantenha o import.

- [ ] **Step 4: Verificar que config carrega sem erros**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -c "import config; print('OK')"
```

Esperado: `OK`

- [ ] **Step 5: Rodar todos os testes**

```bash
python -m pytest tests/ -v
```

Esperado: todos passam, incluindo os novos testes em `test_importar_inicial_coach_points.py`.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py
git commit -m "refactor: remove COACH_RANKING_START_DATE constant"
```

---

### Task 10: Verificação final

**Arquivos:**
- Nenhum (verificação apenas)

- [ ] **Step 1: Confirmar zero referências restantes**

```bash
grep -r "COACH_RANKING_START_DATE" /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend/
```

Esperado: saída vazia.

- [ ] **Step 2: Rodar a suite completa de testes**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -m pytest tests/ -v
```

Esperado: todos os testes passam (incluindo os 6 novos em `test_importar_inicial_coach_points.py`).

- [ ] **Step 3: Lembrete operacional**

Após deploy do código:
1. Reiniciar o servidor FastAPI (aplica o fix `modalidade` e estas mudanças)
2. Clicar "Importar Dados Existentes" na UI — os upserts atualizam `pontos_coach` nos registros existentes (0→30 para CI, 0→10 para Pro Bono pré-Abril)
3. Verificar filtro "Pro Bono" com qualquer período → coaches com 10 pts aparecem
4. Verificar filtro "Pagantes" com qualquer período → somente pontos de CI e grupo, sem 10 pts
