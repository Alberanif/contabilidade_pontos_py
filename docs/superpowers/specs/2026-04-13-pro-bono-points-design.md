# Design: Contabilidade de Pontos Pro-bono

**Data:** 2026-04-13  
**Status:** Aprovado  
**Autor:** Claude Code (Brainstorming)

---

## Contexto

O sistema já contabiliza pontos para registros de coaching pagantes (Coaching Individual e Coaching em Grupo/Empresa). Existe uma segunda planilha Google Sheets configurada no `.env` para registros Pro-bono (`GSHEET_RECORDS_PRO_BONO_*`) que não estava sendo processada.

A nova lógica: **cada registro Pro-bono gera 10 pontos imediatos** para o clã e 10 pontos para o coach — sem fila, sem batches. Isso deve funcionar tanto no processamento incremental (`executar`) quanto na importação inicial (`importar-inicial`).

---

## Estrutura da Planilha Pro-bono

| Coluna | Índice | Conteúdo |
|--------|--------|----------|
| A | 0 | Número do Clã (normalizado para "CLÃ N") |
| B | 1 | Nome do Coach |
| J | 9 | Data do registro |
| K | 10 | ID único (chave de deduplicação) |

Não há coluna de Modalidade — todos os registros nessa planilha são Pro-bono por definição.

---

## Regras de Negócio

- **10 pontos por registro** para o clã do registro.
- **10 pontos por registro** para o coach do registro.
- Processamento imediato: sem fila, sem batch, sem carry-over.
- `status = "contabilizado"` e `status_coach = "contabilizado"` na inserção.
- `modalidade = "Pro-bono"` armazenado para identificação.
- Deduplicação via `registro_hash = SHA256("pro_bono:" + row[10])`.

---

## Arquitetura

### Sem migração de banco de dados

Os registros Pro-bono são armazenados na mesma tabela `pontos_ultimate_registros_contabilizados`. O campo `spreadsheet_id` (já existente) os diferencia dos registros pagantes. Não é necessária nenhuma coluna nova.

### Fluxo de dados

```
Planilha Pro-bono (GSHEET_RECORDS_PRO_BONO_*)
        │
        ▼
fetch_records_pro_bono()   [google_sheets_client.py — NOVO]
        │
        ▼
_process_pro_bono_records() [contabilidade.py — NOVO helper]
        │
        ├─ find_new_records(rows, KEY_COLUMNS=[10], hashes, prefix="pro_bono:")
        ├─ Para cada novo: _build_and_insert_pro_bono(..., pontos=10)
        ├─ calculate_points_by_clan(..., 10)
        └─ calculate_points_by_coach(..., 10)
        │
        ▼
pontos_ultimate_registros_contabilizados
pontos_ultimate_totais_por_clan   (total_pontos += 10 por registro)
pontos_ultimate_totais_por_coach  (total_pontos += 10 por registro)
```

---

## Arquivos Modificados

### 1. `backend/points_engine.py`
**Mudança:** Adicionar parâmetro `prefix=""` em `compute_record_hash()` e `find_new_records()`.

```python
def compute_record_hash(row, key_columns, prefix="") -> str:
    key_values = [row[c].strip() if c < len(row) else "" for c in key_columns]
    raw = prefix + "|".join(key_values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def find_new_records(rows, key_columns, processed_hashes, hash_prefix=""):
    new_records = []
    for row in rows:
        record_hash = compute_record_hash(row, key_columns, prefix=hash_prefix)
        if record_hash not in processed_hashes:
            new_records.append((record_hash, row))
    return new_records
```

**Motivo:** `find_new_records` chama `compute_record_hash` internamente, então o prefix precisa ser passado por ambas. Registros Pro-bono usarão `hash_prefix="pro_bono:"`. Chamadas existentes sem prefix continuam funcionando (default `""` é backward-compatible).

### 2. `backend/config.py`
**Mudança:** Adicionar vars Pro-bono (opcionais — sem quebrar startup se ausentes) e constante de pontos.

```python
GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID = os.getenv("GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID")
GSHEET_RECORDS_PRO_BONO_SHEET_NAME = os.getenv("GSHEET_RECORDS_PRO_BONO_SHEET_NAME")
POINTS_PER_PRO_BONO = int(os.getenv("POINTS_PER_PRO_BONO", "10"))
COL_PRO_BONO_KEY = 10   # Coluna K
```

### 3. `backend/google_sheets_client.py`
**Mudança:** Adicionar `fetch_records_pro_bono()`.

```python
def fetch_records_pro_bono() -> list[list[str]]:
    """Busca todos os registros da planilha Pro-bono. Retorna [] se não configurada."""
    if not config.GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID:
        return []
    service = _get_service()
    sheet_name = f"'{config.GSHEET_RECORDS_PRO_BONO_SHEET_NAME}'"
    result = (
        service.spreadsheets().values()
        .get(spreadsheetId=config.GSHEET_RECORDS_PRO_BONO_SPREADSHEET_ID, range=sheet_name)
        .execute()
    )
    return result.get("values", [])
```

### 4. `backend/routers/contabilidade.py`
**Mudança:** Adicionar helpers e estender 3 endpoints.

**Novas constantes:**
```python
KEY_COLUMNS_PRO_BONO = [config.COL_PRO_BONO_KEY]   # [10]
HASH_PREFIX_PRO_BONO = "pro_bono:"
POINTS_PER_PRO_BONO = config.POINTS_PER_PRO_BONO    # 10
```

**Novo helper `_build_and_insert_pro_bono()`:** idêntico a `_build_and_insert()` mas com `spreadsheet_id=PRO_BONO_ID`, `sheet_name=PRO_BONO_NAME`, `modalidade="Pro-bono"`, e `key_columns=KEY_COLUMNS_PRO_BONO`.

**Novo helper `_process_pro_bono_records()`:**
- Busca `fetch_records_pro_bono()`
- Encontra novos registros via `find_new_records(..., KEY_COLUMNS_PRO_BONO, hashes, prefix=HASH_PREFIX_PRO_BONO)`
- Insere cada um com `pontos=10`, `pontos_coach=10`, `status="contabilizado"`, `status_coach="contabilizado"`
- Retorna `(n_novos, pontos_por_clan, pontos_por_coach)`

**Endpoints estendidos:**

| Endpoint | Adição |
|----------|--------|
| `POST /executar` | Após processar pagantes, chama `_process_pro_bono_records()` e soma pontos nos totais de clã/coach |
| `POST /reprocessar` | Idem (já faz clean + reprocessa tudo) |
| `POST /importar-inicial` | Após importar Coaching Individual e Grupo, importa Pro-bono como `contabilizado` com 10 pts |

**`ImportarInicialResponse`** recebe campo adicional `pro_bono_importados: int`. O `ExecutarResponse` e `ReprocessarResponse` recebem `pro_bono_registros: int` e `pro_bono_pontos_por_clan: dict[str, int]`.

**5. `frontend/src/api/client.ts`**
- Adicionar `pro_bono_importados: number` à interface `ImportarInicialResponse`.
- Adicionar `pro_bono_registros: number` e `pro_bono_pontos_por_clan: Record<string, number>` às interfaces `ExecutarResponse` e `ReprocessarResponse`.

---

## Verificação

1. **Testar `executar`:**
   - Garantir que a planilha Pro-bono tem pelo menos 1 registro.
   - `POST /api/contabilidade/executar` → verificar `novos_registros` inclui Pro-bono.
   - `GET /api/registros` com filtro `modalidade=Pro-bono` → deve retornar os registros.
   - `GET /api/clans` → total_pontos do clã envolvido deve ter subido 10 pts por registro.
   - `GET /api/coaches` → idem para o coach.

2. **Testar `importar-inicial`:**
   - Limpar o banco manualmente ou deixar o botão fazer isso.
   - Clicar "Importar Dados Existentes" no frontend.
   - Response deve incluir `pro_bono_importados > 0`.
   - Verificar que registros Pro-bono aparecem no banco com `status="contabilizado"` e `pontos=10`.

3. **Testar deduplicação:**
   - Rodar `executar` duas vezes — Pro-bono não deve ser contabilizado duas vezes.
   - `GET /api/registros?modalidade=Pro-bono` deve retornar o mesmo número nas duas chamadas.

---

## Fora do Escopo

- Frontend: nenhuma mudança de UI necessária (os mesmos botões já disparam os endpoints estendidos).
- Novo endpoint dedicado para Pro-bono: YAGNI.
- Migração de banco de dados: não necessária.
- Sincronização de totais Pro-bono de volta à planilha: os totais já são sincronizados junto com os outros via `atualizar-planilha`.
