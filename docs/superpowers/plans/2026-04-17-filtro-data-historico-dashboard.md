# Filtro de Data Histórico no Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar campo "Ver ranking até [data]" no Dashboard que exibe rankings de clãs e coaches calculados a partir dos registros com data de planilha ≤ data escolhida, incluindo pontos de desafios.

**Architecture:** Adicionar coluna `data_registro DATE NULL` na tabela de registros e populá-la durante a inserção. Um endpoint de consulta agrega pontos filtrados por essa coluna. O frontend alterna entre totais pré-computados (estado atual) e totais recalculados on-demand (histórico).

**Tech Stack:** Python 3.11, FastAPI, Supabase Python client (supabase-py), React 18, TypeScript, Tailwind CSS

---

## File Map

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `backend/points_engine.py` | Modificar | Adicionar `date_col` em `build_record_data` |
| `backend/routers/contabilidade.py` | Modificar | Atualizar helpers e adicionar 2 novos endpoints |
| `backend/supabase_client.py` | Modificar | Adicionar 4 novas funções de consulta/update |
| `frontend/src/api/client.ts` | Modificar | Adicionar `fetchHistorico` |
| `frontend/src/pages/Dashboard.tsx` | Modificar | Adicionar date picker e lógica de histórico |
| `backend/tests/test_points_engine.py` | Modificar | Testes para `build_record_data` com `date_col` |

---

## Task 1: Migração do banco de dados (SQL manual no Supabase)

**Files:**
- Nenhum arquivo modificado — SQL executado diretamente no Supabase Dashboard

- [ ] **Step 1: Abrir o Supabase Dashboard**

Acessar o projeto no Supabase Dashboard → SQL Editor.

- [ ] **Step 2: Executar o SQL de migração**

```sql
ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN IF NOT EXISTS data_registro DATE NULL;
```

- [ ] **Step 3: Verificar que a coluna foi criada**

```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'pontos_ultimate_registros_contabilizados'
  AND column_name = 'data_registro';
```

Resultado esperado: uma linha com `column_name=data_registro`, `data_type=date`, `is_nullable=YES`.

---

## Task 2: Adicionar `date_col` em `build_record_data` (TDD)

**Files:**
- Modify: `backend/points_engine.py`
- Modify: `backend/tests/test_points_engine.py`

- [ ] **Step 1: Escrever os testes que irão falhar**

Abrir `backend/tests/test_points_engine.py` e adicionar ao final do arquivo:

```python
from points_engine import build_record_data


def _make_row_and_header():
    row = [
        "1",                       # col 0: clan
        "Coach A",                 # col 1: coach
        "", "", "",
        "Coaching Individual",     # col 5: modalidade
        "", "", "", "",
        "06/04/2026 13:58:38",     # col 10: data (col K)
        "HASH_KEY_123",            # col 11: chave
    ]
    header = [f"col_{i}" for i in range(len(row))]
    return row, header


def test_build_record_data_inclui_data_registro_quando_date_col_fornecido():
    row, header = _make_row_and_header()
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
        date_col=10,
    )
    assert result["data_registro"] == "2026-04-06"


def test_build_record_data_data_registro_none_quando_data_invalida():
    row, header = _make_row_and_header()
    row[10] = "data-invalida"
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
        date_col=10,
    )
    assert result["data_registro"] is None


def test_build_record_data_sem_data_registro_quando_date_col_none():
    row, header = _make_row_and_header()
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
    )
    assert "data_registro" not in result


def test_build_record_data_data_registro_none_quando_coluna_ausente():
    row = ["1", "Coach A", "", "", "", "Coaching Individual"]  # só 6 colunas
    header = [f"col_{i}" for i in range(len(row))]
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
        date_col=10,  # índice fora do range da row
    )
    assert result["data_registro"] is None
```

- [ ] **Step 2: Confirmar que os testes falham**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE
python -m pytest backend/tests/test_points_engine.py -k "build_record_data" -v
```

Resultado esperado: 4 testes falhando com `TypeError: build_record_data() got an unexpected keyword argument 'date_col'`.

- [ ] **Step 3: Implementar a mudança em `build_record_data`**

Em `backend/points_engine.py`, substituir a função `build_record_data` (linhas 125-157) por:

```python
def build_record_data(
    record_hash: str,
    row: list[str],
    header: list[str],
    modalidade_col: int,
    clan_col: int,
    coach_col: int,
    spreadsheet_id: str,
    sheet_name: str,
    row_number: int,
    pontos: int,
    date_col: int | None = None,
) -> dict:
    """Constrói o dicionário de dados para inserção no Supabase."""
    raw_data = {}
    for i, val in enumerate(row):
        col_name = header[i] if i < len(header) else f"col_{i}"
        raw_data[col_name] = val

    coach = row[coach_col].strip() if coach_col < len(row) else "DESCONHECIDO"
    if not coach:
        coach = "DESCONHECIDO"

    result = {
        "registro_hash": record_hash,
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name,
        "row_number": row_number,
        "modalidade": row[modalidade_col].strip() if modalidade_col < len(row) else "",
        "clan": row[clan_col].strip() if clan_col < len(row) else "",
        "coach": coach,
        "pontos": pontos,
        "raw_data": json.dumps(raw_data, ensure_ascii=False),
    }

    if date_col is not None:
        raw_date = row[date_col].strip() if date_col < len(row) else ""
        parsed = _parse_date(raw_date)
        result["data_registro"] = str(parsed) if parsed else None

    return result
```

- [ ] **Step 4: Confirmar que os testes passam**

```bash
python -m pytest backend/tests/test_points_engine.py -v
```

Resultado esperado: todos os testes passando (os anteriores + os 4 novos).

- [ ] **Step 5: Commit**

```bash
git add backend/points_engine.py backend/tests/test_points_engine.py
git commit -m "feat(points_engine): add date_col param to build_record_data"
```

---

## Task 3: Propagar `date_col` nos helpers e callers de `contabilidade.py`

**Files:**
- Modify: `backend/routers/contabilidade.py`

- [ ] **Step 1: Atualizar `_build_and_insert` para aceitar e repassar `date_col`**

Substituir a função `_build_and_insert` (linhas 31-48) por:

```python
def _build_and_insert(record_hash, row, header, data_rows, pontos, extra_fields=None, date_col=None):
    row_number = data_rows.index(row) + 2 if row in data_rows else 0
    record_data = points_engine.build_record_data(
        record_hash=record_hash,
        row=row,
        header=header,
        modalidade_col=COL_MODALIDADE,
        clan_col=COL_CLAN,
        coach_col=COL_COACH,
        spreadsheet_id=config.GSHEET_RECORDS_SPREADSHEET_ID,
        sheet_name=config.GSHEET_RECORDS_SHEET_NAME,
        row_number=row_number,
        pontos=pontos,
        date_col=date_col,
    )
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)
```

- [ ] **Step 2: Atualizar `_build_and_insert_pro_bono` para aceitar e repassar `date_col`**

Substituir a função `_build_and_insert_pro_bono` (linhas 51-69) por:

```python
def _build_and_insert_pro_bono(record_hash, row, header, data_rows, pontos, extra_fields=None, date_col=None):
    row_number = data_rows.index(row) + 2 if row in data_rows else 0
    record_data = points_engine.build_record_data(
        record_hash=record_hash,
        row=row,
        header=header,
        modalidade_col=COL_CLAN,  # dummy — será sobrescrito abaixo
        clan_col=COL_CLAN,
        coach_col=COL_COACH,
        spreadsheet_id=config.GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID,
        sheet_name=config.GSHEET_RECORDS_PRO_BONO_SHEET_NAME,
        row_number=row_number,
        pontos=pontos,
        date_col=date_col,
    )
    record_data["modalidade"] = "Pro-bono"
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)
```

- [ ] **Step 3: Atualizar `_process_group_records` para passar `date_col`**

Dentro de `_process_group_records` (linha ~134), localizar a chamada a `_build_and_insert` e adicionar `date_col=config.COL_DATE_PAYING`:

```python
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

- [ ] **Step 4: Atualizar `_process_pro_bono_records` para passar `date_col`**

Dentro de `_process_pro_bono_records` (linha ~91), localizar a chamada a `_build_and_insert_pro_bono`:

```python
        _build_and_insert_pro_bono(
            record_hash, row, header, data_rows,
            pontos=config.POINTS_PER_PRO_BONO,
            extra_fields={
                "status": "contabilizado",
                "status_coach": "contabilizado",
                "pontos_coach": config.POINTS_PER_PRO_BONO,
            },
            date_col=config.COL_DATE_PRO_BONO,
        )
```

- [ ] **Step 5: Atualizar `importar_registros` para passar `date_col`**

Dentro de `importar_registros` (linha ~261), atualizar:

```python
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=0,
                extra_fields={"status": "contabilizado", "status_coach": "contabilizado", "pontos_coach": 0},
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 6: Atualizar `executar_contabilidade` para passar `date_col`**

Dentro de `executar_contabilidade` (linha ~423), atualizar:

```python
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
                extra_fields={
                    "status_coach": "contabilizado",
                    "pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 7: Atualizar `reprocessar_contabilidade` para passar `date_col`**

Dentro de `reprocessar_contabilidade` (linha ~529), atualizar:

```python
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=config.POINTS_PER_COACHING_INDIVIDUAL,
                extra_fields={
                    "status_coach": "contabilizado",
                    "pontos_coach": config.POINTS_PER_COACHING_INDIVIDUAL
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 8: Atualizar `importar_inicial` — chamada de Coaching Individual**

Dentro de `importar_inicial` (linha ~636), atualizar:

```python
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=0,
                extra_fields={
                    "status": "contabilizado",
                    "status_coach": "contabilizado",
                    "pontos_coach": 0,
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 9: Atualizar `importar_inicial` — chamada de registros de grupo**

Dentro de `importar_inicial` (linha ~695), localizar o `_build_and_insert` que insere registros de grupo e atualizar:

```python
            _build_and_insert(
                record_hash, row, header, data_rows,
                pontos=0,
                extra_fields={
                    "status": status,
                    "status_coach": status_coach,
                    "num_participantes": num_participantes,
                    "pontos_coach": 0,
                },
                date_col=config.COL_DATE_PAYING,
            )
```

- [ ] **Step 10: Atualizar `importar_inicial` — chamada de Pro-bono**

Dentro de `importar_inicial` (linha ~755), atualizar:

```python
                _build_and_insert_pro_bono(
                    record_hash, row, pb_header, pb_data_rows,
                    pontos=0,
                    extra_fields={
                        "status": "contabilizado",
                        "status_coach": "contabilizado",
                        "pontos_coach": 0,
                    },
                    date_col=config.COL_DATE_PRO_BONO,
                )
```

- [ ] **Step 11: Verificar que os testes existentes ainda passam**

```bash
python -m pytest backend/tests/ -v
```

Resultado esperado: todos os testes passando.

- [ ] **Step 12: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat(contabilidade): propagate date_col to build_record_data calls"
```

---

## Task 4: Adicionar funções de consulta histórica e backfill em `supabase_client.py`

**Files:**
- Modify: `backend/supabase_client.py`

- [ ] **Step 1: Adicionar import de `date` no topo do arquivo (já existe)**

Verificar que a linha `from datetime import date` já está presente em `supabase_client.py` (linha 1). Se não estiver, adicionar.

- [ ] **Step 2: Adicionar função `update_data_registro` (usada pelo backfill)**

Ao final da seção `# --- Registros contabilizados ---`, adicionar:

```python
def update_data_registro(registro_hash: str, data_registro) -> bool:
    """Atualiza data_registro de um registro pelo hash. Retorna True se encontrou o registro."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .update({"data_registro": data_registro})
        .eq("registro_hash", registro_hash)
        .execute()
    )
    return len(result.data) > 0
```

- [ ] **Step 3: Adicionar as três funções de consulta histórica**

Ao final do arquivo `supabase_client.py`, adicionar:

```python
# --- Consultas históricas (filtradas por data_registro) ---


def get_historico_clan_totals(ate: date) -> dict[str, int]:
    """Soma pontos por clã para registros com data_registro <= ate e status=contabilizado."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .select("clan, pontos")
        .eq("status", "contabilizado")
        .lte("data_registro", str(ate))
        .execute()
    )
    totals: dict[str, int] = {}
    for row in result.data:
        clan = row.get("clan") or ""
        if clan:
            totals[clan] = totals.get(clan, 0) + (row.get("pontos") or 0)
    return totals


def get_historico_coach_totals(ate: date) -> dict[str, int]:
    """Soma pontos_coach por coach para registros com data_registro <= ate e status_coach=contabilizado."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .select("coach, pontos_coach")
        .eq("status_coach", "contabilizado")
        .lte("data_registro", str(ate))
        .execute()
    )
    totals: dict[str, int] = {}
    for row in result.data:
        coach = row.get("coach") or ""
        if coach and coach != "DESCONHECIDO":
            totals[coach] = totals.get(coach, 0) + (row.get("pontos_coach") or 0)
    return totals


def get_historico_desafio_totals(ate: date) -> dict[str, int]:
    """Soma total_pontos por clã para desafios com data <= ate e contabilizar_pontos=true."""
    client = _get_client()
    desafios_result = (
        client.table(TABLE_DESAFIOS)
        .select("id")
        .eq("contabilizar_pontos", True)
        .lte("data", str(ate))
        .execute()
    )
    desafio_ids = [row["id"] for row in desafios_result.data]
    if not desafio_ids:
        return {}
    registros_result = (
        client.table(TABLE_DESAFIO_REGISTROS)
        .select("clan, total_pontos")
        .in_("desafio_id", desafio_ids)
        .execute()
    )
    totals: dict[str, int] = {}
    for row in registros_result.data:
        clan = row.get("clan") or ""
        if clan:
            totals[clan] = totals.get(clan, 0) + (row.get("total_pontos") or 0)
    return totals
```

- [ ] **Step 4: Verificar que a importação Python não tem erros de sintaxe**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -c "import supabase_client; print('OK')"
```

Resultado esperado: `OK` (sem erros).

- [ ] **Step 5: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat(supabase): add historico query functions and update_data_registro"
```

---

## Task 5: Adicionar endpoint de backfill `POST /api/contabilidade/preencher-datas`

**Files:**
- Modify: `backend/routers/contabilidade.py`

- [ ] **Step 1: Adicionar o modelo Pydantic de resposta**

Após o bloco de modelos existentes (após `AtualizarPlanilhaResponse`), adicionar:

```python
class PreencherDatasResponse(BaseModel):
    registros_atualizados: int
    registros_sem_data: int
    mensagem: str
```

- [ ] **Step 2: Adicionar o endpoint**

Ao final do arquivo `backend/routers/contabilidade.py`, antes do último endpoint ou após `atualizar_planilha`, adicionar:

```python
@router.post("/preencher-datas", response_model=PreencherDatasResponse)
def preencher_datas():
    """Popula data_registro para registros existentes a partir das planilhas. Uso único (backfill)."""
    try:
        atualizados = 0
        sem_data = 0

        rows_pay = google_sheets_client.fetch_records()
        if rows_pay:
            data_rows = rows_pay[1:]
            for row in data_rows:
                record_hash = points_engine.compute_record_hash(row, KEY_COLUMNS)
                raw_date = row[config.COL_DATE_PAYING].strip() if config.COL_DATE_PAYING < len(row) else ""
                parsed = points_engine._parse_date(raw_date)
                val = str(parsed) if parsed else None
                encontrado = supabase_client.update_data_registro(record_hash, val)
                if encontrado:
                    if val:
                        atualizados += 1
                    else:
                        sem_data += 1

        rows_pb = google_sheets_client.fetch_records_pro_bono()
        if rows_pb:
            data_rows_pb = rows_pb[1:]
            for row in data_rows_pb:
                record_hash = points_engine.compute_record_hash(
                    row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO
                )
                raw_date = row[config.COL_DATE_PRO_BONO].strip() if config.COL_DATE_PRO_BONO < len(row) else ""
                parsed = points_engine._parse_date(raw_date)
                val = str(parsed) if parsed else None
                encontrado = supabase_client.update_data_registro(record_hash, val)
                if encontrado:
                    if val:
                        atualizados += 1
                    else:
                        sem_data += 1

        return PreencherDatasResponse(
            registros_atualizados=atualizados,
            registros_sem_data=sem_data,
            mensagem=f"Backfill concluído: {atualizados} registro(s) com data. {sem_data} sem data válida.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 3: Verificar importações e sintaxe**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -c "from routers import contabilidade; print('OK')"
```

Resultado esperado: `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat(contabilidade): add preencher-datas backfill endpoint"
```

---

## Task 6: Adicionar endpoint histórico `GET /api/contabilidade/historico`

**Files:**
- Modify: `backend/routers/contabilidade.py`

- [ ] **Step 1: Adicionar o modelo Pydantic de resposta**

Após `PreencherDatasResponse`, adicionar:

```python
class HistoricoResponse(BaseModel):
    clans: dict[str, int]
    coaches: dict[str, int]
```

- [ ] **Step 2: Adicionar o import de `date` e `Query` no topo de `contabilidade.py`**

Verificar se `from datetime import date` está importado. Se não, adicionar. Também adicionar `Query` ao import do FastAPI:

```python
from fastapi import APIRouter, HTTPException, Query
from datetime import date
```

- [ ] **Step 3: Adicionar o endpoint GET**

Ao final do arquivo, após `preencher_datas`, adicionar:

```python
@router.get("/historico", response_model=HistoricoResponse)
def get_historico(ate: str = Query(..., description="Data de corte no formato YYYY-MM-DD")):
    """Retorna totais de clãs e coaches acumulados até a data informada."""
    try:
        try:
            ate_date = date.fromisoformat(ate)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Parâmetro 'ate' inválido. Use o formato YYYY-MM-DD (ex: 2026-04-15).",
            )

        clan_totals = supabase_client.get_historico_clan_totals(ate_date)
        desafio_totals = supabase_client.get_historico_desafio_totals(ate_date)
        coach_totals = supabase_client.get_historico_coach_totals(ate_date)

        combined_clans: dict[str, int] = dict(clan_totals)
        for clan, pontos in desafio_totals.items():
            combined_clans[clan] = combined_clans.get(clan, 0) + pontos

        return HistoricoResponse(clans=combined_clans, coaches=coach_totals)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 4: Verificar que o servidor FastAPI sobe sem erros**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
python -c "from routers import contabilidade; print('OK')"
```

Resultado esperado: `OK`.

- [ ] **Step 5: Testar o endpoint manualmente (com servidor rodando)**

Com o servidor backend em execução (`uvicorn main:app --reload`), chamar:

```bash
curl "http://localhost:8000/api/contabilidade/historico?ate=2026-04-15"
```

Resultado esperado: JSON com `{"clans": {...}, "coaches": {...}}` (pode ser vazio antes do backfill, mas não deve dar erro 500).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/contabilidade.py
git commit -m "feat(contabilidade): add GET /historico endpoint for date-filtered rankings"
```

---

## Task 7: Executar migração e backfill

**Files:**
- Nenhum arquivo modificado — passos operacionais

- [ ] **Step 1: Confirmar que a migração SQL do Task 1 já foi executada**

```sql
SELECT COUNT(*) FROM pontos_ultimate_registros_contabilizados WHERE data_registro IS NOT NULL;
```

Resultado esperado antes do backfill: `0` (todos NULL ainda).

- [ ] **Step 2: Subir o servidor backend**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 3: Chamar o endpoint de backfill**

```bash
curl -X POST http://localhost:8000/api/contabilidade/preencher-datas
```

Resultado esperado: JSON como `{"registros_atualizados": N, "registros_sem_data": M, "mensagem": "Backfill concluído: N registro(s) com data. M sem data válida."}`. `N` deve ser > 0 se há registros no banco.

- [ ] **Step 4: Verificar resultado no banco**

```sql
SELECT
  COUNT(*) AS total,
  COUNT(data_registro) AS com_data,
  COUNT(*) - COUNT(data_registro) AS sem_data
FROM pontos_ultimate_registros_contabilizados;
```

Resultado esperado: `com_data` próximo de `total`; `sem_data` deve ser 0 ou muito baixo.

---

## Task 8: Adicionar `fetchHistorico` em `client.ts`

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Adicionar interface e função ao final da seção de Contabilidade**

Em `frontend/src/api/client.ts`, após `atualizarPlanilha`, adicionar:

```typescript
// --- Histórico ---

export interface HistoricoResponse {
  clans: Record<string, number>;
  coaches: Record<string, number>;
}

export function fetchHistorico(ate: string): Promise<HistoricoResponse> {
  return request(`/api/contabilidade/historico?ate=${encodeURIComponent(ate)}`);
}
```

- [ ] **Step 2: Verificar que o TypeScript compila sem erros**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/frontend
npm run build 2>&1 | tail -20
```

Resultado esperado: build bem-sucedido sem erros de TypeScript.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(client): add fetchHistorico for date-filtered rankings"
```

---

## Task 9: Adicionar filtro de data no `Dashboard.tsx`

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Adicionar o import de `fetchHistorico` e `HistoricoResponse`**

No topo de `Dashboard.tsx`, adicionar `fetchHistorico` e `HistoricoResponse` ao import existente:

```typescript
import {
  fetchClans,
  fetchRanking,
  fetchCoaches,
  fetchHistorico,
  executarContabilidade,
  atualizarPlanilha,
  type ClanTotal,
  type CoachTotal,
  type RankingEntry,
  type ExecutarResponse,
  type HistoricoResponse,
} from "../api/client";
```

- [ ] **Step 2: Adicionar estados para o filtro de data**

Após a linha `const [error, setError] = useState("");`, adicionar:

```typescript
  const [dataCorte, setDataCorte] = useState<string>("");
  const [historicoData, setHistoricoData] = useState<HistoricoResponse | null>(null);
  const [loadingHistorico, setLoadingHistorico] = useState(false);
```

- [ ] **Step 3: Adicionar função `loadHistorico`**

Após a função `loadRanking`, adicionar:

```typescript
  const loadHistorico = async (ate: string) => {
    try {
      setLoadingHistorico(true);
      setError("");
      const data = await fetchHistorico(ate);
      setHistoricoData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar histórico");
      setHistoricoData(null);
    } finally {
      setLoadingHistorico(false);
    }
  };
```

- [ ] **Step 4: Adicionar handler para mudança de data**

Após `loadHistorico`, adicionar:

```typescript
  const handleDataCorteChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setDataCorte(val);
    if (val) {
      loadHistorico(val);
    } else {
      setHistoricoData(null);
    }
  };
```

- [ ] **Step 5: Adicionar o seletor de data e banner no JSX**

Após o bloco de mensagem de erro (`{error && ...}`) e antes do bloco `{sheetMessage && ...}`, adicionar:

```tsx
      <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
        <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
          Ver ranking até:
        </label>
        <input
          type="date"
          value={dataCorte}
          onChange={handleDataCorteChange}
          className="border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        {dataCorte && (
          <button
            onClick={() => {
              setDataCorte("");
              setHistoricoData(null);
            }}
            className="text-sm text-gray-500 hover:text-gray-700 underline"
          >
            Limpar filtro
          </button>
        )}
      </div>

      {dataCorte && historicoData && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 px-4 py-2 rounded-lg text-sm">
          Visualizando histórico até{" "}
          <strong>
            {new Date(dataCorte + "T00:00:00").toLocaleDateString("pt-BR")}
          </strong>
          . Os valores abaixo refletem o estado acumulado até essa data.
        </div>
      )}

      {loadingHistorico && (
        <p className="text-gray-500 text-sm">Carregando histórico...</p>
      )}
```

- [ ] **Step 6: Criar dados derivados para os rankings (clãs)**

Dentro do bloco `{activeTab === "clans" && (`, substituir a derivação de `sorted` por lógica condicional. Localizar o trecho que começa em `const nomeMap` dentro do callback `(() => {` e substituir por:

```tsx
              const nomeMap: Record<string, string> = {};
              for (const entry of ranking) {
                nomeMap[entry.clan] = entry.nome_completo;
              }

              const clanSource: { clan: string; total_pontos: number }[] =
                dataCorte && historicoData
                  ? Object.entries(historicoData.clans).map(([clan, total_pontos]) => ({
                      clan,
                      total_pontos,
                    }))
                  : clans.map((c) => ({ clan: c.clan, total_pontos: c.total_pontos }));

              const sorted = [...clanSource]
                .sort((a, b) => b.total_pontos - a.total_pontos)
                .map((c, idx) => ({
                  posicao: idx + 1,
                  clan: c.clan,
                  nome_completo: nomeMap[c.clan] ?? "",
                  total_pontos: c.total_pontos,
                }));
```

- [ ] **Step 7: Atualizar os ClanCards para respeitar o filtro**

Localizar o bloco de ClanCards:

```tsx
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {clans.map((c) => (
                  <ClanCard key={c.id} clan={c.clan} totalPontos={c.total_pontos} />
                ))}
              </div>
```

Substituir por:

```tsx
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {(dataCorte && historicoData
                  ? Object.entries(historicoData.clans).map(([clan, total_pontos], idx) => ({
                      id: idx,
                      clan,
                      total_pontos,
                    }))
                  : clans
                ).map((c) => (
                  <ClanCard key={c.clan} clan={c.clan} totalPontos={c.total_pontos} />
                ))}
              </div>
```

- [ ] **Step 8: Atualizar o ranking de coaches para respeitar o filtro**

Dentro do bloco `{activeTab === "coaches" && (`, localizar a derivação de `sorted` dentro do callback `(() => {`:

```tsx
            const sorted = [...coaches]
              .sort((a, b) => b.total_pontos - a.total_pontos)
              .map((c, idx) => ({
                posicao: idx + 1,
                coach: c.coach,
                total_pontos: c.total_pontos,
              }));
```

Substituir por:

```tsx
            const coachSource: { coach: string; total_pontos: number }[] =
              dataCorte && historicoData
                ? Object.entries(historicoData.coaches).map(([coach, total_pontos]) => ({
                    coach,
                    total_pontos,
                  }))
                : coaches.map((c) => ({ coach: c.coach, total_pontos: c.total_pontos }));

            const sorted = [...coachSource]
              .sort((a, b) => b.total_pontos - a.total_pontos)
              .map((c, idx) => ({
                posicao: idx + 1,
                coach: c.coach,
                total_pontos: c.total_pontos,
              }));
```

- [ ] **Step 9: Atualizar a condição de exibição do ranking de coaches**

Localizar a condição `coaches.length === 0` no bloco de coaches e atualizar para:

```tsx
          ) : (dataCorte && historicoData
                ? Object.keys(historicoData.coaches).length === 0
                : coaches.length === 0) ? (
            <p className="text-gray-500">Nenhum dado disponível.</p>
```

Se a condição estiver em uma estrutura ternária, ajustar de:

```tsx
          ) : coaches.length === 0 ? (
```

Para:

```tsx
          ) : (dataCorte && historicoData ? Object.keys(historicoData.coaches).length === 0 : coaches.length === 0) ? (
```

- [ ] **Step 10: Verificar que o TypeScript compila sem erros**

```bash
cd /home/alberani/Documentos/IGT/CALCULA_PONTOS_ULTIMATE/frontend
npm run build 2>&1 | tail -30
```

Resultado esperado: build bem-sucedido sem erros de TypeScript.

- [ ] **Step 11: Testar manualmente no navegador**

Subir o servidor de desenvolvimento:

```bash
npm run dev
```

Verificar:
1. O campo "Ver ranking até:" aparece acima dos rankings
2. Sem data selecionada → rankings mostram dados atuais normalmente
3. Selecionar uma data → banner amarelo aparece, rankings atualizam com dados históricos
4. Clicar "Limpar filtro" → volta ao estado atual

- [ ] **Step 12: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): add date filter for historical ranking view"
```

---

## Checklist de verificação final

- [ ] Coluna `data_registro` existe no banco (Task 1)
- [ ] Novos registros inseridos via `executar` têm `data_registro` preenchido automaticamente
- [ ] Backfill executado com sucesso (Task 7)
- [ ] `GET /api/contabilidade/historico?ate=2026-04-15` retorna JSON correto
- [ ] `GET /api/contabilidade/historico?ate=data-invalida` retorna HTTP 400
- [ ] Dashboard mostra campo de data
- [ ] Com data selecionada, rankings refletem totais históricos
- [ ] "Limpar filtro" restaura a view atual
- [ ] Sem filtro, comportamento atual não foi alterado
