# Identidade Canônica de Coach (Fusão de Aliases) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fundir a pontuação de coaches duplicados (mesma pessoa, grafias diferentes) num único nome canônico, agora e para sempre, via uma tabela de aliases editável pelo usuário no Supabase.

**Architecture:** Uma tabela nova `pontos_ultimate_coach_aliases` (alias → coach_canonico) resolvida por uma chave de comparação insensível a caixa/acento/espaço (`coach_identity.py`, funções puras). A normalização é aplicada na ingestão (mesmo padrão de `_normalize_clan`), então registros novos já nascem corretos. Um endpoint `POST /contabilidade/reprocessar-coaches` reaplica a tabela de aliases aos dados já existentes — usado tanto na migração inicial quanto sempre que o usuário adicionar um alias novo no futuro.

**Tech Stack:** Python 3.12, FastAPI, Supabase (postgrest via `supabase-py`), pytest + `unittest.mock`.

## Global Constraints

- Nomenclatura de tabela Supabase segue o padrão existente `pontos_ultimate_*` (ver `backend/supabase_client.py`).
- Migrações SQL vivem em `backend/migrations/NNN_*.sql`, numeração sequencial (próxima é `006`).
- Toda lógica pura de domínio fica em módulo próprio sem I/O (padrão já usado em `points_engine.py`); routers só orquestram chamadas a `supabase_client`.
- Testes seguem o padrão existente: `unittest.mock.patch` em funções de `supabase_client`/`google_sheets_client`, sem banco real. Rodar com `python -m pytest tests/ -q` a partir de `backend/` (venv em `../venv`, ativar com `source ../venv/Scripts/activate`).
- Nenhuma mudança de UI/frontend está no escopo (usuário decidiu editar a tabela de aliases direto pelo Supabase Table Editor).
- Este plano refina um ponto da spec aprovada (`docs/superpowers/specs/2026-07-13-coach-identity-aliases-design.md`): a spec descrevia a normalização de case/acento/espaço como "automática, sem precisar de linha na tabela". Na prática, a única forma de garantir que grupos de duplicata trivial colapsem no MESMO nome de exibição (e não apenas seriam "reconhecidos como iguais") é ter uma linha de alias por variante não-canônica — a comparação por chave normalizada é o que permite que uma variante nunca vista antes (ex: uma grafia com espaçamento diferente) ainda combine com um alias já cadastrado, sem precisar prever cada variação. Por isso a lista de seed cresce de 13 para 32 linhas (Task 9), cobrindo os 18 grupos triviais + os 4 grupos semânticos confirmados. O mecanismo (uma tabela, uma função de resolução) continua exatamente como aprovado — só a quantidade de linhas de seed muda.

---

## File Structure

- **Create** `backend/migrations/006_add_coach_aliases.sql` — schema da tabela de aliases.
- **Create** `backend/coach_identity.py` — funções puras: `normalize_key`, `resolve_coach`, `aggregate_by_canonical`, `detect_alias_chains`.
- **Create** `backend/tests/test_coach_identity.py` — testes unitários puros (sem mock) para `coach_identity.py`.
- **Modify** `backend/supabase_client.py` — tabela `TABLE_COACH_ALIASES` + CRUD (`get_coach_alias_map`, `insert_coach_alias`, `delete_coach_total`) + acesso bruto a registros (`list_all_registros`, `update_registros_coach`).
- **Modify** `backend/routers/contabilidade.py` — `_normalize_coach` (wrapper fino sobre `coach_identity`), normalização na ingestão (`_build_and_insert*`), em `aprovar_coach`, nas agregações `pontos_por_coach` (`executar_contabilidade`, `reprocessar_contabilidade`, `_process_pro_bono_records`, `importar_inicial`), e o novo endpoint `POST /contabilidade/reprocessar-coaches`.
- **Create** `backend/tests/test_coach_alias_normalization.py` — testes com mock para os pontos de integração acima (ingestão e `aprovar_coach`).
- **Create** `backend/tests/test_reprocessar_coaches.py` — testes com mock para o novo endpoint.
- **Create** `backend/seed_coach_aliases.py` — script único (roda uma vez) que popula o seed inicial e chama o endpoint de reprocessamento. Segue o padrão de scripts avulsos já existente (`backend/inspect_sheet.py`).

---

### Task 1: Tabela de aliases — migração e helpers de acesso

**Files:**
- Create: `backend/migrations/006_add_coach_aliases.sql`
- Modify: `backend/supabase_client.py`

**Interfaces:**
- Produces: `supabase_client.TABLE_COACH_ALIASES: str`, `supabase_client.get_coach_alias_map() -> dict[str, str]`, `supabase_client.insert_coach_alias(alias: str, coach_canonico: str) -> dict`, `supabase_client.delete_coach_total(coach: str) -> None`, `supabase_client.list_all_registros() -> list[dict]`, `supabase_client.update_registros_coach(old_coach: str, new_coach: str) -> int`

- [ ] **Step 1: Criar o arquivo de migração**

```sql
-- backend/migrations/006_add_coach_aliases.sql
CREATE TABLE IF NOT EXISTS pontos_ultimate_coach_aliases (
    id SERIAL PRIMARY KEY,
    alias VARCHAR NOT NULL UNIQUE,
    coach_canonico VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] **Step 2: Aplicar a migração no Supabase**

Esta tabela precisa existir antes de qualquer código que a use. Rode o SQL do Step 1 no SQL Editor do Supabase do projeto (mesma forma como as migrações `001`–`005` foram aplicadas — não há runner automatizado neste repositório). Confirme que a tabela foi criada antes de seguir para o Step 3.

- [ ] **Step 3: Adicionar a constante da tabela**

Em `backend/supabase_client.py`, localizar:

```python
TABLE_DESAFIO_IMPORTACAO_LINHAS = "desafio_importacao_linhas"
```

Substituir por:

```python
TABLE_DESAFIO_IMPORTACAO_LINHAS = "desafio_importacao_linhas"
TABLE_COACH_ALIASES = "pontos_ultimate_coach_aliases"
```

- [ ] **Step 4: Adicionar `list_all_registros` e `update_registros_coach`**

Em `backend/supabase_client.py`, localizar:

```python
def delete_all_registros() -> int:
    """Exclui todos os registros. Retorna a quantidade excluída."""
    client = _get_client()
    result = client.table(TABLE_REGISTROS).delete().neq("id", 0).execute()
    return len(result.data)
```

Substituir por (mantendo a função original e adicionando as duas novas logo depois):

```python
def delete_all_registros() -> int:
    """Exclui todos os registros. Retorna a quantidade excluída."""
    client = _get_client()
    result = client.table(TABLE_REGISTROS).delete().neq("id", 0).execute()
    return len(result.data)


def list_all_registros() -> list[dict]:
    """Retorna todos os registros contabilizados, sem paginação (usa range
    internamente para superar o limite padrão do PostgREST)."""
    client = _get_client()
    all_rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table(TABLE_REGISTROS)
            .select("*")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        if not result.data:
            break
        all_rows.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return all_rows


def update_registros_coach(old_coach: str, new_coach: str) -> int:
    """Reescreve o campo coach de old_coach para new_coach em todos os
    registros que casam. Retorna a quantidade de linhas atualizadas."""
    client = _get_client()
    result = (
        client.table(TABLE_REGISTROS)
        .update({"coach": new_coach})
        .eq("coach", old_coach)
        .execute()
    )
    return len(result.data)
```

- [ ] **Step 5: Adicionar `get_coach_alias_map`, `insert_coach_alias`, `delete_coach_total`**

Em `backend/supabase_client.py`, localizar:

```python
def get_coach_carry_over(coach: str) -> int:
    """Retorna o carry-over (pessoas_em_espera) atual do coach. Default 0."""
    client = _get_client()
    result = (
        client.table(TABLE_TOTAIS_COACH)
        .select("pessoas_em_espera")
        .eq("coach", coach)
        .execute()
    )
    return result.data[0]["pessoas_em_espera"] or 0 if result.data else 0
```

Substituir por:

```python
def get_coach_carry_over(coach: str) -> int:
    """Retorna o carry-over (pessoas_em_espera) atual do coach. Default 0."""
    client = _get_client()
    result = (
        client.table(TABLE_TOTAIS_COACH)
        .select("pessoas_em_espera")
        .eq("coach", coach)
        .execute()
    )
    return result.data[0]["pessoas_em_espera"] or 0 if result.data else 0


def delete_coach_total(coach: str) -> None:
    """Remove a linha de totais de um coach (usado ao fundir aliases)."""
    client = _get_client()
    client.table(TABLE_TOTAIS_COACH).delete().eq("coach", coach).execute()


def get_coach_alias_map() -> dict[str, str]:
    """Retorna {alias: coach_canonico} de todos os aliases cadastrados."""
    client = _get_client()
    result = client.table(TABLE_COACH_ALIASES).select("alias, coach_canonico").execute()
    return {row["alias"]: row["coach_canonico"] for row in result.data}


def insert_coach_alias(alias: str, coach_canonico: str) -> dict:
    """Cadastra (ou atualiza) um alias de coach."""
    client = _get_client()
    result = (
        client.table(TABLE_COACH_ALIASES)
        .upsert({"alias": alias, "coach_canonico": coach_canonico}, on_conflict="alias")
        .execute()
    )
    return result.data[0] if result.data else {}
```

- [ ] **Step 6: Verificar que o módulo importa sem erro**

Run: `cd backend && source ../venv/Scripts/activate && python -c "import supabase_client; print('ok')"`
Expected: `ok` (sem traceback)

- [ ] **Step 7: Commit**

```bash
git add backend/migrations/006_add_coach_aliases.sql backend/supabase_client.py
git commit -m "feat: adiciona tabela e helpers de aliases de coach"
```

---

### Task 2: `coach_identity.py` — funções puras de resolução

**Files:**
- Create: `backend/coach_identity.py`
- Test: `backend/tests/test_coach_identity.py`

**Interfaces:**
- Consumes: nada (módulo puro, sem dependência de `supabase_client`)
- Produces: `coach_identity.normalize_key(raw: str) -> str`, `coach_identity.resolve_coach(coach_raw: str, alias_map: dict[str, str]) -> str`, `coach_identity.aggregate_by_canonical(raw_points: dict[str, int], alias_map: dict[str, str]) -> dict[str, int]`, `coach_identity.detect_alias_chains(alias_map: dict[str, str]) -> list[str]`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_coach_identity.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coach_identity import (
    normalize_key,
    resolve_coach,
    aggregate_by_canonical,
    detect_alias_chains,
)


class TestNormalizeKey:

    def test_colapsa_case(self):
        assert normalize_key("Karlla Andrade") == normalize_key("KARLLA ANDRADE")

    def test_colapsa_acento(self):
        assert normalize_key("Cássia Fajardo") == normalize_key("Cassia Fajardo")

    def test_colapsa_espaco_duplo(self):
        assert normalize_key("Karlla  Andrade") == normalize_key("Karlla Andrade")

    def test_aparado_nas_pontas(self):
        assert normalize_key("  Karlla Andrade  ") == normalize_key("Karlla Andrade")


class TestResolveCoach:

    def test_sem_alias_retorna_proprio_nome_aparado(self):
        assert resolve_coach("  Vivian Gaspar  ", {}) == "Vivian Gaspar"

    def test_vazio_retorna_desconhecido(self):
        assert resolve_coach("", {}) == "DESCONHECIDO"
        assert resolve_coach(None, {}) == "DESCONHECIDO"

    def test_resolve_por_alias_exato(self):
        alias_map = {"Tati Pellicel": "Tatiane Pellicel"}
        assert resolve_coach("Tati Pellicel", alias_map) == "Tatiane Pellicel"

    def test_resolve_por_chave_normalizada_variante_nao_cadastrada(self):
        # Alias cadastrado com uma grafia; entrada chega com outra caixa/espaço.
        alias_map = {"KARLLA ANDADE": "Karlla Andrade"}
        assert resolve_coach("karlla   andade", alias_map) == "Karlla Andrade"

    def test_nome_igual_ao_canonico_nao_precisa_de_alias_proprio(self):
        alias_map = {"KARLLA ANDADE": "Karlla Andrade"}
        assert resolve_coach("Karlla Andrade", alias_map) == "Karlla Andrade"


class TestAggregateByCanonical:

    def test_soma_colisoes_apos_fundir(self):
        raw = {"Vini Marini": 30, "Vinicius Marini": 60}
        alias_map = {"Vini Marini": "Vinicius Marini"}
        assert aggregate_by_canonical(raw, alias_map) == {"Vinicius Marini": 90}

    def test_sem_colisao_mantem_entradas_separadas(self):
        raw = {"Coach A": 30, "Coach B": 60}
        assert aggregate_by_canonical(raw, {}) == {"Coach A": 30, "Coach B": 60}

    def test_dict_vazio_retorna_vazio(self):
        assert aggregate_by_canonical({}, {}) == {}


class TestDetectAliasChains:

    def test_sem_cadeia_retorna_vazio(self):
        alias_map = {"Tati Pellicel": "Tatiane Pellicel", "Vini Marini": "Vinicius Marini"}
        assert detect_alias_chains(alias_map) == []

    def test_detecta_cadeia_de_dois_saltos(self):
        alias_map = {"A": "B", "B": "C"}
        avisos = detect_alias_chains(alias_map)
        assert len(avisos) == 1
        assert "A" in avisos[0] and "B" in avisos[0] and "C" in avisos[0]
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_identity.py -v`
Expected: FAIL em todos os testes com `ModuleNotFoundError: No module named 'coach_identity'`

- [ ] **Step 3: Implementar `coach_identity.py`**

Criar `backend/coach_identity.py`:

```python
import re
import unicodedata


def normalize_key(raw: str) -> str:
    """Chave de comparação insensível a caixa, acento e espaçamento."""
    no_accents = "".join(
        c for c in unicodedata.normalize("NFD", raw.strip())
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", no_accents).upper()


def resolve_coach(coach_raw: str, alias_map: dict[str, str]) -> str:
    """Resolve o nome canônico de um coach a partir de um mapa {alias: canonico}.

    A comparação usa normalize_key nos dois lados, então uma grafia nunca
    vista antes (variação de caixa/acento/espaço de um alias já cadastrado)
    ainda resolve corretamente, sem precisar de uma linha própria na tabela.
    Sem alias correspondente, retorna o próprio nome (aparado).
    """
    coach_raw = (coach_raw or "").strip()
    if not coach_raw:
        return "DESCONHECIDO"
    key = normalize_key(coach_raw)
    by_key = {normalize_key(alias): canonico for alias, canonico in alias_map.items()}
    return by_key.get(key, coach_raw)


def aggregate_by_canonical(raw_points: dict[str, int], alias_map: dict[str, str]) -> dict[str, int]:
    """Reagrupa um dict {nome_bruto: valor} pelo nome canônico, somando colisões."""
    result: dict[str, int] = {}
    for raw_name, value in raw_points.items():
        canonical = resolve_coach(raw_name, alias_map)
        result[canonical] = result.get(canonical, 0) + value
    return result


def detect_alias_chains(alias_map: dict[str, str]) -> list[str]:
    """Detecta aliases cujo coach_canonico também é, ele mesmo, alias de outra
    linha (cadeia de 2+ saltos) — não resolvidos automaticamente, só reportados
    para o usuário corrigir a tabela apontando direto para o canônico final."""
    by_key = {normalize_key(alias): canonico for alias, canonico in alias_map.items()}
    warnings: list[str] = []
    for alias, canonico in alias_map.items():
        canonico_key = normalize_key(canonico)
        if canonico_key in by_key and by_key[canonico_key] != canonico:
            warnings.append(f"{alias} -> {canonico} -> {by_key[canonico_key]}")
    return warnings
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_identity.py -v`
Expected: PASS em todos os 12 testes

- [ ] **Step 5: Commit**

```bash
git add backend/coach_identity.py backend/tests/test_coach_identity.py
git commit -m "feat: adiciona coach_identity com resolucao pura de alias"
```

---

### Task 3: Normalizar coach na ingestão (`_build_and_insert*`)

**Files:**
- Modify: `backend/routers/contabilidade.py`
- Test: `backend/tests/test_coach_alias_normalization.py`

**Interfaces:**
- Consumes: `coach_identity.resolve_coach` (Task 2), `supabase_client.get_coach_alias_map` (Task 1)
- Produces: `_normalize_coach(coach_raw: str) -> str` em `routers/contabilidade.py`

Nota: `_process_group_records` (usado por `executar_contabilidade`/`reprocessar_contabilidade` para enfileirar pendentes de grupo) não precisa de edição própria — ele só insere via `_build_and_insert` (já corrigido aqui) e depois consulta `get_all_pending_coaches`/`get_pending_group_records_by_coach`, que já leem o valor `coach` gravado no banco (já normalizado). O mesmo vale para `aprovar_clan`/clã em geral, fora de escopo desta feature.

- [ ] **Step 1: Escrever o teste (falhando)**

Criar `backend/tests/test_coach_alias_normalization.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import _build_and_insert, _build_and_insert_pro_bono


def _row(coach="Tati Pellicel"):
    # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_DATE_PAYING=10, KEY_COLUMNS=[11]
    return ["1", coach, "", "", "", "Coaching Individual", "", "", "", "", "01/03/2026", "key1"]


class TestBuildAndInsertNormalizesCoach:

    def test_coach_e_normalizado_via_alias(self):
        row = _row("Tati Pellicel")
        header = [f"col_{i}" for i in range(len(row))]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Tati Pellicel": "Tatiane Pellicel"}), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _build_and_insert(
                "hash1", row, header, [row], pontos=30,
                extra_fields={"status": "contabilizado"},
                date_col=10,
            )

        assert inserted[0]["coach"] == "Tatiane Pellicel"

    def test_coach_sem_alias_mantem_nome_aparado(self):
        row = _row("Vivian Gaspar")
        header = [f"col_{i}" for i in range(len(row))]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _build_and_insert(
                "hash1", row, header, [row], pontos=30,
                extra_fields={"status": "contabilizado"},
                date_col=10,
            )

        assert inserted[0]["coach"] == "Vivian Gaspar"


def _pb_row(coach="Tati Pellicel"):
    # COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10
    return ["1", coach, "", "", "", "", "", "", "", "01/03/2026", "keypb1"]


class TestBuildAndInsertProBonoNormalizesCoach:

    def test_coach_e_normalizado_via_alias(self):
        row = _pb_row("Tati Pellicel")
        header = [f"col_{i}" for i in range(len(row))]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Tati Pellicel": "Tatiane Pellicel"}), \
             patch("supabase_client.insert_processed_record", side_effect=capture):
            _build_and_insert_pro_bono(
                "hash1", row, header, [row], pontos=10,
                extra_fields={"status": "contabilizado", "status_coach": "contabilizado"},
                date_col=9,
            )

        assert inserted[0]["coach"] == "Tatiane Pellicel"
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py -v`
Expected: FAIL — `assert 'Tati Pellicel' == 'Tatiane Pellicel'` (coach ainda não normalizado)

- [ ] **Step 3: Adicionar `_normalize_coach` e importar `coach_identity`**

Em `backend/routers/contabilidade.py`, localizar:

```python
import config
import google_sheets_client
import supabase_client
import points_engine

router = APIRouter()
```

Substituir por:

```python
import config
import google_sheets_client
import supabase_client
import points_engine
import coach_identity

router = APIRouter()
```

Em seguida, localizar:

```python
def _normalize_clan(clan_raw: str) -> str:
    try:
        return f"CLÃ {int(clan_raw.strip())}"
    except (ValueError, AttributeError):
        return clan_raw.strip()
```

Substituir por:

```python
def _normalize_clan(clan_raw: str) -> str:
    try:
        return f"CLÃ {int(clan_raw.strip())}"
    except (ValueError, AttributeError):
        return clan_raw.strip()


def _normalize_coach(coach_raw: str) -> str:
    """Resolve o nome canônico de um coach via pontos_ultimate_coach_aliases."""
    return coach_identity.resolve_coach(coach_raw, supabase_client.get_coach_alias_map())
```

- [ ] **Step 4: Normalizar coach em `_build_and_insert`**

Localizar:

```python
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)


def _build_and_insert_pro_bono(record_hash, row, header, data_rows, pontos, extra_fields=None, date_col=None):
```

Substituir por:

```python
    record_data["clan"] = _normalize_clan(record_data["clan"])
    record_data["coach"] = _normalize_coach(record_data["coach"])
    if extra_fields:
        record_data.update(extra_fields)
    supabase_client.insert_processed_record(record_data)


def _build_and_insert_pro_bono(record_hash, row, header, data_rows, pontos, extra_fields=None, date_col=None):
```

- [ ] **Step 5: Normalizar coach em `_build_and_insert_pro_bono`**

Localizar:

```python
    record_data["modalidade"] = "Pro-bono"
    record_data["clan"] = _normalize_clan(record_data["clan"])
    if extra_fields:
```

Substituir por:

```python
    record_data["modalidade"] = "Pro-bono"
    record_data["clan"] = _normalize_clan(record_data["clan"])
    record_data["coach"] = _normalize_coach(record_data["coach"])
    if extra_fields:
```

- [ ] **Step 6: Rodar os testes para confirmar que passam**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py -v`
Expected: PASS nos 3 testes

- [ ] **Step 7: Rodar a suíte completa (checar regressão)**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/ -q`
Expected: todos os testes passam (nenhuma regressão nos 116 já existentes)

- [ ] **Step 8: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_coach_alias_normalization.py
git commit -m "feat: normaliza coach na ingestao de registros"
```

---

### Task 4: `aprovar_coach` resolve alias antes de buscar a fila

**Files:**
- Modify: `backend/routers/contabilidade.py`
- Test: `backend/tests/test_coach_alias_normalization.py`

**Interfaces:**
- Consumes: `_normalize_coach` (Task 3)

- [ ] **Step 1: Escrever o teste (falhando)**

Adicionar ao final de `backend/tests/test_coach_alias_normalization.py`:

```python
from routers.contabilidade import aprovar_coach, AprovarCoachRequest


class TestAprovarCoachResolveAlias:

    def test_aprovar_com_alias_busca_fila_do_canonico(self):
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.get_pending_group_records_by_coach",
                   return_value=[]) as mock_pending, \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[]), \
             patch("supabase_client.upsert_coach_total", return_value={}):
            aprovar_coach(AprovarCoachRequest(coach="Vini Marini"))

        mock_pending.assert_called_once()
        args, _ = mock_pending.call_args
        assert args[0] == "Vinicius Marini"
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py::TestAprovarCoachResolveAlias -v`
Expected: FAIL — `assert 'Vini Marini' == 'Vinicius Marini'`

- [ ] **Step 3: Normalizar `body.coach` em `aprovar_coach`**

Em `backend/routers/contabilidade.py`, localizar:

```python
    try:
        coach = body.coach.strip()
        pending = supabase_client.get_pending_group_records_by_coach(coach, GROUP_MODALIDADES)
        carry_over = supabase_client.get_coach_carry_over(coach)
```

Substituir por:

```python
    try:
        coach = _normalize_coach(body.coach)
        pending = supabase_client.get_pending_group_records_by_coach(coach, GROUP_MODALIDADES)
        carry_over = supabase_client.get_coach_carry_over(coach)
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py -v`
Expected: PASS nos 4 testes do arquivo

- [ ] **Step 5: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_coach_alias_normalization.py
git commit -m "feat: aprovar-coach resolve alias antes de buscar fila"
```

---

### Task 5: Agregações `pontos_por_coach` somam por canônico

**Files:**
- Modify: `backend/routers/contabilidade.py`
- Test: `backend/tests/test_coach_alias_normalization.py`

**Interfaces:**
- Consumes: `coach_identity.aggregate_by_canonical` (Task 2)

Cobre os 3 pontos onde `points_engine.calculate_points_by_coach` produz um dict `{coach_bruto: pontos}` que hoje é usado direto — sem fundir por canônico, dois nomes que apontam pro mesmo alias ficariam como entradas separadas no dict, perdendo pontos na consolidação.

- [ ] **Step 1: Escrever o teste (falhando)**

Adicionar ao final de `backend/tests/test_coach_alias_normalization.py`:

```python
from routers.contabilidade import _process_pro_bono_records


class TestProcessProBonoMergesCoach:

    def test_dois_alias_do_mesmo_coach_somam(self):
        # COL_CLAN=0, COL_COACH=1, COL_DATE_PRO_BONO=9, COL_PRO_BONO_KEY=10
        row_a = ["1", "Vini Marini", "", "", "", "", "", "", "", "01/03/2026", "keyA"]
        row_b = ["1", "Vinicius Marini", "", "", "", "", "", "", "", "01/03/2026", "keyB"]

        with patch("google_sheets_client.fetch_records_pro_bono",
                   return_value=[[f"col_{i}" for i in range(11)], row_a, row_b]), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.insert_processed_record", side_effect=lambda r: r):
            _n_novos, _pontos_por_clan, pontos_por_coach = _process_pro_bono_records(set())

        assert pontos_por_coach == {"Vinicius Marini": 20}
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py::TestProcessProBonoMergesCoach -v`
Expected: FAIL — `{'Vini Marini': 10, 'Vinicius Marini': 10} == {'Vinicius Marini': 20}`

- [ ] **Step 3: Corrigir `_process_pro_bono_records`**

Em `backend/routers/contabilidade.py`, localizar:

```python
    pontos_por_clan = {_normalize_clan(k): v for k, v in raw_clan_pts.items()}
    pontos_por_coach = points_engine.calculate_points_by_coach(
        new_records, COL_COACH, config.POINTS_PER_PRO_BONO
    )
    return len(new_records), pontos_por_clan, pontos_por_coach
```

Substituir por:

```python
    pontos_por_clan = {_normalize_clan(k): v for k, v in raw_clan_pts.items()}
    raw_coach_pts = points_engine.calculate_points_by_coach(
        new_records, COL_COACH, config.POINTS_PER_PRO_BONO
    )
    pontos_por_coach = coach_identity.aggregate_by_canonical(
        raw_coach_pts, supabase_client.get_coach_alias_map()
    )
    return len(new_records), pontos_por_clan, pontos_por_coach
```

- [ ] **Step 4: Corrigir `executar_contabilidade`**

Localizar:

```python
        pontos_por_coach = points_engine.calculate_points_by_coach(
            new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        processed_hashes = supabase_client.get_processed_hashes()
        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan, pendentes_por_coach = _process_group_records(
```

Substituir por:

```python
        raw_coach_pts = points_engine.calculate_points_by_coach(
            new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_coach = coach_identity.aggregate_by_canonical(
            raw_coach_pts, supabase_client.get_coach_alias_map()
        )

        processed_hashes = supabase_client.get_processed_hashes()
        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan, pendentes_por_coach = _process_group_records(
```

- [ ] **Step 5: Corrigir `reprocessar_contabilidade`**

Localizar:

```python
        pontos_por_coach = points_engine.calculate_points_by_coach(
            new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan, pendentes_por_coach = _process_group_records(
            data_rows, header, processed_hashes=set()
        )
```

Substituir por:

```python
        raw_coach_pts = points_engine.calculate_points_by_coach(
            new_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_coach = coach_identity.aggregate_by_canonical(
            raw_coach_pts, supabase_client.get_coach_alias_map()
        )

        novos_pendentes, pontos_grupo_por_clan, pendentes_por_clan, pendentes_por_coach = _process_group_records(
            data_rows, header, processed_hashes=set()
        )
```

- [ ] **Step 6: Rodar os testes para confirmar que passam**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py -v`
Expected: PASS em todos os testes do arquivo (5 até aqui)

- [ ] **Step 7: Rodar a suíte completa**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/ -q`
Expected: todos passam, nenhuma regressão

- [ ] **Step 8: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_coach_alias_normalization.py
git commit -m "feat: agregacoes de pontos_por_coach somam por nome canonico"
```

---

### Task 6: `importar_inicial` normaliza coach nas Fases 4 e 7

**Files:**
- Modify: `backend/routers/contabilidade.py`
- Test: `backend/tests/test_coach_alias_normalization.py`

**Interfaces:**
- Consumes: `_normalize_coach` (Task 3), `coach_identity.aggregate_by_canonical` (Task 2)

- [ ] **Step 1: Escrever o teste (falhando)**

Adicionar ao final de `backend/tests/test_coach_alias_normalization.py`:

```python
from routers.contabilidade import importar_inicial


class TestImportarInicialMergeCoachBatch:

    def test_dois_alias_juntos_fecham_lote(self):
        # Cada linha tem 3 participantes; separados não fecham lote de 5,
        # juntos (6 pessoas) fecham 1 lote completo.
        # COL_CLAN=0, COL_COACH=1, COL_MODALIDADE=5, COL_PARTICIPANTES=8,
        # COL_DATE_PAYING=10, KEY_COLUMNS=[11]
        row_a = ["1", "Vini Marini", "", "", "", "Coaching em grupo", "", "", "3", "", "01/03/2026", "keyA"]
        row_b = ["1", "Vinicius Marini", "", "", "", "Coaching em grupo", "", "", "3", "", "01/03/2026", "keyB"]
        header = [f"col_{i}" for i in range(12)]
        pb_header = [f"col_{i}" for i in range(11)]
        inserted = []

        def capture(rec):
            inserted.append(rec)
            return rec

        with patch("supabase_client.delete_all_registros", return_value=0), \
             patch("supabase_client.reset_all_totals"), \
             patch("google_sheets_client.fetch_records", return_value=[header, row_a, row_b]), \
             patch("google_sheets_client.fetch_records_pro_bono", return_value=[pb_header]), \
             patch("google_sheets_client.fetch_ranking", return_value=[]), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.insert_processed_record", side_effect=capture), \
             patch("supabase_client.get_tipo_clan_totals", return_value={}), \
             patch("supabase_client.upsert_clan_total", return_value={}), \
             patch("supabase_client.upsert_coach_total", return_value={}), \
             patch("supabase_client.get_all_pending_clans", return_value=[]), \
             patch("supabase_client.get_all_pending_coaches", return_value=[]):
            importar_inicial()

        grupo = [r for r in inserted if r.get("modalidade") == "Coaching em grupo"]
        assert len(grupo) == 2
        assert all(r["status_coach"] == "contabilizado" for r in grupo)
        assert all(r["coach"] == "Vinicius Marini" for r in grupo)
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py::TestImportarInicialMergeCoachBatch -v`
Expected: FAIL — `status_coach` fica `pendente` (3 pessoas cada, nenhum dos dois nomes brutos sozinho fecha lote de 5)

- [ ] **Step 3: Normalizar coach na primeira agregação da Fase 4**

Em `backend/routers/contabilidade.py`, localizar:

```python
        for _, row in group_records:
            clan = _normalize_clan(row[COL_CLAN]) if COL_CLAN < len(row) else "DESCONHECIDO"
            coach = row[COL_COACH].strip() if COL_COACH < len(row) else ""
            if not coach:
                coach = "DESCONHECIDO"
            raw_part = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
```

Substituir por:

```python
        for _, row in group_records:
            clan = _normalize_clan(row[COL_CLAN]) if COL_CLAN < len(row) else "DESCONHECIDO"
            coach = _normalize_coach(row[COL_COACH]) if COL_COACH < len(row) else "DESCONHECIDO"
            raw_part = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
```

- [ ] **Step 4: Normalizar coach na segunda agregação (loop de inserção) da Fase 4**

Localizar:

```python
        for record_hash, row in group_records:
            clan = _normalize_clan(row[COL_CLAN]) if COL_CLAN < len(row) else "DESCONHECIDO"
            coach = row[COL_COACH].strip() if COL_COACH < len(row) else ""
            if not coach:
                coach = "DESCONHECIDO"
            raw_part = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
```

Substituir por:

```python
        for record_hash, row in group_records:
            clan = _normalize_clan(row[COL_CLAN]) if COL_CLAN < len(row) else "DESCONHECIDO"
            coach = _normalize_coach(row[COL_COACH]) if COL_COACH < len(row) else "DESCONHECIDO"
            raw_part = row[COL_PARTICIPANTES].strip() if COL_PARTICIPANTES < len(row) else ""
```

- [ ] **Step 5: Normalizar coach na Fase 7 (totais de coach)**

Localizar:

```python
        # Fase 7: Totais e carry-over por coach.
        pontos_por_coach = points_engine.calculate_points_by_coach(
            coaching_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )

        # Pontos Pro-bono para coaches (todas as datas, sem restrição)
        pb_data_for_coach = pb_rows_seed[1:] if pb_rows_seed else []
        pb_records_for_coach = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO), row)
            for row in pb_data_for_coach
        ]
        pro_bono_coach_pts_seed = points_engine.calculate_points_by_coach(
            pb_records_for_coach, COL_COACH, config.POINTS_PER_PRO_BONO
        )
```

Substituir por:

```python
        # Fase 7: Totais e carry-over por coach.
        coach_alias_map = supabase_client.get_coach_alias_map()
        raw_pontos_por_coach = points_engine.calculate_points_by_coach(
            coaching_records, COL_COACH, config.POINTS_PER_COACHING_INDIVIDUAL
        )
        pontos_por_coach = coach_identity.aggregate_by_canonical(raw_pontos_por_coach, coach_alias_map)

        # Pontos Pro-bono para coaches (todas as datas, sem restrição)
        pb_data_for_coach = pb_rows_seed[1:] if pb_rows_seed else []
        pb_records_for_coach = [
            (points_engine.compute_record_hash(row, KEY_COLUMNS_PRO_BONO, prefix=HASH_PREFIX_PRO_BONO), row)
            for row in pb_data_for_coach
        ]
        raw_pro_bono_coach_pts_seed = points_engine.calculate_points_by_coach(
            pb_records_for_coach, COL_COACH, config.POINTS_PER_PRO_BONO
        )
        pro_bono_coach_pts_seed = coach_identity.aggregate_by_canonical(
            raw_pro_bono_coach_pts_seed, coach_alias_map
        )
```

- [ ] **Step 6: Rodar o teste para confirmar que passa**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_coach_alias_normalization.py -v`
Expected: PASS em todos os testes do arquivo (6 até aqui)

- [ ] **Step 7: Rodar a suíte completa**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/ -q`
Expected: todos passam, nenhuma regressão

- [ ] **Step 8: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_coach_alias_normalization.py
git commit -m "feat: importar_inicial normaliza coach nas fases 4 e 7"
```

---

### Task 7: Endpoint `POST /contabilidade/reprocessar-coaches`

**Files:**
- Modify: `backend/routers/contabilidade.py`
- Test: `backend/tests/test_reprocessar_coaches.py`

**Interfaces:**
- Consumes: `supabase_client.get_coach_alias_map`, `supabase_client.list_all_registros`, `supabase_client.update_registros_coach`, `supabase_client.delete_coach_total`, `supabase_client.upsert_coach_total`, `coach_identity.resolve_coach`, `coach_identity.detect_alias_chains`, `aprovar_coach` (Task 4)
- Produces: `reprocessar_coaches() -> ReprocessarCoachesResponse`, rota `POST /contabilidade/reprocessar-coaches`

- [ ] **Step 1: Escrever os testes (falhando)**

Criar `backend/tests/test_reprocessar_coaches.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import reprocessar_coaches


def _registro(coach, modalidade, pontos_coach, status_coach="contabilizado", num_participantes=1):
    return {
        "coach": coach,
        "modalidade": modalidade,
        "pontos_coach": pontos_coach,
        "status_coach": status_coach,
        "num_participantes": num_participantes,
    }


class TestReprocessarCoachesMergeERecalcula:

    def test_funde_dois_alias_e_recalcula_totais(self):
        regs_antes = [
            _registro("Vini Marini", "Coaching Individual", 30),
            _registro("Vinicius Marini", "Pro-bono", 10),
        ]
        regs_depois = [
            _registro("Vinicius Marini", "Coaching Individual", 30),
            _registro("Vinicius Marini", "Pro-bono", 10),
        ]

        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.list_all_registros",
                   side_effect=[regs_antes, regs_depois]), \
             patch("supabase_client.update_registros_coach", return_value=1) as mock_update, \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert, \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[]):
            resultado = reprocessar_coaches()

        mock_update.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_delete.assert_called_once_with("Vini Marini")
        mock_upsert.assert_called_once_with(
            "Vinicius Marini", 40,
            pessoas_em_espera=0, total_pagante=30, total_pro_bono=10,
        )
        assert resultado.registros_atualizados == 1
        assert resultado.coaches_afetados == ["Vinicius Marini"]
        assert resultado.totais_recalculados == {"Vinicius Marini": 40}

    def test_sem_alias_correspondente_nao_altera_nada(self):
        regs = [_registro("Vivian Gaspar", "Coaching Individual", 30)]

        with patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.list_all_registros", return_value=regs), \
             patch("supabase_client.update_registros_coach") as mock_update, \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.upsert_coach_total") as mock_upsert:
            resultado = reprocessar_coaches()

        mock_update.assert_not_called()
        mock_delete.assert_not_called()
        mock_upsert.assert_not_called()
        assert resultado.registros_atualizados == 0
        assert resultado.coaches_afetados == []
        assert resultado.avisos == []

    def test_detecta_cadeia_de_alias_e_reporta_aviso(self):
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"A": "B", "B": "C"}), \
             patch("supabase_client.list_all_registros", return_value=[]), \
             patch("supabase_client.update_registros_coach"), \
             patch("supabase_client.delete_coach_total"), \
             patch("supabase_client.upsert_coach_total"):
            resultado = reprocessar_coaches()

        assert len(resultado.avisos) == 1
        assert "A" in resultado.avisos[0] and "B" in resultado.avisos[0] and "C" in resultado.avisos[0]
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_reprocessar_coaches.py -v`
Expected: FAIL — `ImportError: cannot import name 'reprocessar_coaches'`

- [ ] **Step 3: Implementar o endpoint**

Em `backend/routers/contabilidade.py`, localizar (final de `aprovar_coach`):

```python
            mensagem=(
                f"{n_complete} lote(s) aprovado(s) para {coach}. "
                f"+{pontos_adicionados} pontos. "
                f"Total agora: {novo_total} pts. "
                f"{novo_carry_over} pessoa(s) em espera."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executar", response_model=ExecutarResponse)
def executar_contabilidade():
```

Substituir por:

```python
            mensagem=(
                f"{n_complete} lote(s) aprovado(s) para {coach}. "
                f"+{pontos_adicionados} pontos. "
                f"Total agora: {novo_total} pts. "
                f"{novo_carry_over} pessoa(s) em espera."
            ),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ReprocessarCoachesResponse(BaseModel):
    registros_atualizados: int
    coaches_afetados: list[str]
    totais_recalculados: dict[str, int]
    avisos: list[str]
    mensagem: str


@router.post("/reprocessar-coaches", response_model=ReprocessarCoachesResponse)
def reprocessar_coaches():
    """Reaplica pontos_ultimate_coach_aliases: reescreve o coach dos registros
    já existentes para o nome canônico e recalcula do zero os totais afetados.
    Idempotente — sem mudança na tabela de aliases, não altera nada. Chamar
    sempre que uma linha nova for adicionada/editada em coach_aliases."""
    try:
        alias_map = supabase_client.get_coach_alias_map()
        avisos = coach_identity.detect_alias_chains(alias_map)

        all_regs = supabase_client.list_all_registros()
        raw_coaches = {r["coach"] for r in all_regs if r.get("coach")}

        registros_atualizados = 0
        coaches_afetados: set[str] = set()
        for raw_coach in raw_coaches:
            canonical = coach_identity.resolve_coach(raw_coach, alias_map)
            if canonical != raw_coach:
                registros_atualizados += supabase_client.update_registros_coach(raw_coach, canonical)
                coaches_afetados.add(canonical)
                supabase_client.delete_coach_total(raw_coach)

        totais_recalculados: dict[str, int] = {}
        if coaches_afetados:
            all_regs = supabase_client.list_all_registros()

        group_modalidades_upper = {m.upper() for m in GROUP_MODALIDADES}
        for canonical in coaches_afetados:
            regs_canonico = [r for r in all_regs if r.get("coach") == canonical]
            ci_pts = sum(
                r.get("pontos_coach") or 0
                for r in regs_canonico
                if (r.get("modalidade") or "").strip().upper() == "COACHING INDIVIDUAL"
                and r.get("status_coach") == "contabilizado"
            )
            pb_pts = sum(
                r.get("pontos_coach") or 0
                for r in regs_canonico
                if (r.get("modalidade") or "").strip().upper() == "PRO-BONO"
            )
            group_people = sum(
                r.get("num_participantes") or 1
                for r in regs_canonico
                if (r.get("modalidade") or "").strip().upper() in group_modalidades_upper
                and r.get("status_coach") == "contabilizado"
            )
            lotes = group_people // config.BATCH_SIZE_GROUP
            novo_carry = group_people % config.BATCH_SIZE_GROUP
            group_pts = lotes * config.POINTS_PER_BATCH_GROUP
            total_pagante = ci_pts + group_pts
            total_pontos = total_pagante + pb_pts
            supabase_client.upsert_coach_total(
                canonical, total_pontos,
                pessoas_em_espera=novo_carry,
                total_pagante=total_pagante,
                total_pro_bono=pb_pts,
            )
            totais_recalculados[canonical] = total_pontos

        for canonical in coaches_afetados:
            aprovar_coach(AprovarCoachRequest(coach=canonical))

        return ReprocessarCoachesResponse(
            registros_atualizados=registros_atualizados,
            coaches_afetados=sorted(coaches_afetados),
            totais_recalculados=totais_recalculados,
            avisos=avisos,
            mensagem=(
                f"{registros_atualizados} registro(s) atualizados. "
                f"{len(coaches_afetados)} coach(es) recalculados."
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/executar", response_model=ExecutarResponse)
def executar_contabilidade():
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/test_reprocessar_coaches.py -v`
Expected: PASS nos 3 testes

- [ ] **Step 5: Rodar a suíte completa**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/ -q`
Expected: todos passam, nenhuma regressão

- [ ] **Step 6: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_reprocessar_coaches.py
git commit -m "feat: adiciona endpoint POST /contabilidade/reprocessar-coaches"
```

---

### Task 8: Seed inicial — popular aliases e rodar o reprocessamento em produção

**Files:**
- Create: `backend/seed_coach_aliases.py`

**Interfaces:**
- Consumes: `supabase_client.insert_coach_alias` (Task 1), `routers.contabilidade.reprocessar_coaches` (Task 7)

Este é o script de migração única (dado real, não código de teste) que aplica o levantamento feito nesta conversa. Segue o padrão de scripts avulsos já existente em `backend/inspect_sheet.py` — roda uma vez, direto contra o Supabase de produção configurado em `.env`.

- [ ] **Step 1: Criar o script**

Criar `backend/seed_coach_aliases.py`:

```python
"""Script de migração única: popula pontos_ultimate_coach_aliases com o
levantamento de duplicatas feito em 2026-07-13 e roda o reprocessamento uma
vez. Ver docs/superpowers/specs/2026-07-13-coach-identity-aliases-design.md.

Uso: python seed_coach_aliases.py  (a partir de backend/, com venv ativo)
"""
import supabase_client
from routers.contabilidade import reprocessar_coaches

# (alias observado, nome canônico) — 22 grupos de duplicata confirmados:
# 18 triviais (case/acento/espaço) + 4 semânticos (Camilla, Vini/Vinicius,
# Tati/Tatiane, Solamita) confirmados nesta conversa. Backlog de ~17 pares
# adicionais (nome curto vs. completo) fica documentado na spec, para o
# usuário adicionar aqui quando confirmar cada um.
SEED = [
    ("ALEXSANDRE NAVES", "Alexsandre Naves"),
    ("Cassia Fajardo", "Cássia Fajardo"),
    ("clarissa Boeira", "Clarissa Boeira"),
    ("Claudete M Silva", "Claudete Maria da Silva"),
    ("Claudete m Silva", "Claudete Maria da Silva"),
    ("claudete m silva", "Claudete Maria da Silva"),
    ("Claudete M da Silva", "Claudete Maria da Silva"),
    ("DAMARIS ALFREDO SILVA DE OLIVEIRA", "Damaris Alfredo Silva de Oliveira"),
    ("FLAVIA GODOI", "Flavia Godoi"),
    ("Herverton Ferreira de Souza Sobrinho", "Hérverton Ferreira de Souza Sobrinho"),
    ("IVAN PEREIRA VIEIRA", "Ivan Pereira Vieira"),
    ("JOSE GEORGE C PEREIRA JUNIOR", "Jose George Canuto Pereira Junior"),
    ("Jose George C Pereira Junior", "Jose George Canuto Pereira Junior"),
    ("Jose George C. Pereira Junior", "Jose George Canuto Pereira Junior"),
    ("KARLLA  ANDRADE", "Karlla Andrade"),
    ("KARLLA ANDRADE", "Karlla Andrade"),
    ("KARLLA ANDADE", "Karlla Andrade"),
    ("KATIA APARECIDA DOS SANTOS", "Kátia Aparecida dos Santos"),
    ("KATIA APARECIDA DOS SANTOSQ", "Kátia Aparecida dos Santos"),
    ("MARIA BERNADETE LIMA DE OLIVEIRA", "Maria Bernadete Lima de Oliveira"),
    ("Patricia Pereira da Silva", "Patrícia Pereira da Silva"),
    ("pAULA pETROLI pIEROZZI", "Paula Petroli Pierozzi"),
    ("RAPHA FREITAS", "Rapha Freitas"),
    ("victor lucena", "Victor Lucena"),
    ("Vinicius Gonçalves Missiaggia", "Vinícius Gonçalves Missiaggia"),
    ("Wagner mendes faria", "Wagner Mendes Faria"),
    ("Camilla C Rentroia", "Camilla Crivelaro Rentroia"),
    ("Camilla Rentroia", "Camilla Crivelaro Rentroia"),
    ("Vini Marini", "Vinicius Marini"),
    ("Tati Pellicel", "Tatiane Pellicel"),
    ("solamita dos santos mariano", "Solamita dos Santos Mariano Rovarotto"),
    ("solamita dos santos mariano rovarotto", "Solamita dos Santos Mariano Rovarotto"),
]


def main():
    for alias, canonico in SEED:
        supabase_client.insert_coach_alias(alias, canonico)
    print(f"{len(SEED)} aliases inseridos.")

    resultado = reprocessar_coaches()
    print(f"registros_atualizados={resultado.registros_atualizados}")
    print(f"coaches_afetados={resultado.coaches_afetados}")
    print(f"totais_recalculados={resultado.totais_recalculados}")
    if resultado.avisos:
        print(f"AVISOS: {resultado.avisos}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rodar o script contra o Supabase real**

Run: `cd backend && source ../venv/Scripts/activate && python seed_coach_aliases.py`
Expected: `32 aliases inseridos.` seguido de `registros_atualizados=<N>` com N > 0, `coaches_afetados` listando os 22 nomes canônicos, sem `AVISOS`.

- [ ] **Step 3: Confirmar idempotência — rodar de novo**

Run: `cd backend && source ../venv/Scripts/activate && python -c "from routers.contabilidade import reprocessar_coaches; r = reprocessar_coaches(); print(r.registros_atualizados, r.coaches_afetados)"`
Expected: `0 []` (nenhuma mudança — todos os registros já estão sob o nome canônico)

- [ ] **Step 4: Commit**

```bash
git add backend/seed_coach_aliases.py
git commit -m "feat: script de seed inicial de aliases de coach + reprocessamento"
```

---

### Task 9: Verificação final

**Files:** nenhum (só validação)

- [ ] **Step 1: Rodar a suíte completa de testes**

Run: `cd backend && source ../venv/Scripts/activate && python -m pytest tests/ -q`
Expected: todos os testes passam (116 pré-existentes + os novos desta feature)

- [ ] **Step 2: Confirmar que o ranking de coaches não perdeu pontos na fusão**

Some por coach a soma de `total_pontos` de todos os coaches antes e depois do reprocessamento deve ser igual (a fusão só reagrupa, nunca cria/destrói pontos) — já coberto indiretamente pelos testes da Task 7, mas vale conferir no dado real:

Run:
```bash
cd backend && source ../venv/Scripts/activate && python -c "
import supabase_client as sc
totals = sc.list_coach_totals()
print('coaches distintos:', len(totals))
print('soma total_pontos:', sum(t['total_pontos'] for t in totals))
"
```
Expected: `coaches distintos` cai de 155 para ~133 (155 − 22 grupos fundidos, cada grupo remove `n_variantes - 1` linhas). A soma total de pontos deve ser igual à soma antes da migração (nenhum ponto perdido).

- [ ] **Step 3: Commit final (se houver ajustes pendentes)**

Se os Steps 1–2 passarem sem exigir mudança de código, não há o que commitar aqui — a feature já está com todos os commits das tasks anteriores.
