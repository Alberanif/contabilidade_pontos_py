# Importação de Desafios via CSV — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development (or the project's `tdd` skill) task-by-task, red before green, one seam per cycle. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir subir um CSV de submissões de desafio, mapear colunas, ver uma prévia calculada e confirmar — criando ou atualizando um desafio e contabilizando pontos por clã automaticamente, sem cadastro manual.

**Architecture:** Lógica de negócio 100% pura em `backend/desafio_import_engine.py` (zero I/O, testável sem mocks), seguindo o padrão já estabelecido por `points_engine.py`. I/O (Supabase) fica em `supabase_client.py`. Orquestração num novo router `backend/routers/desafio_import.py`. Frontend: wizard de 3 passos integrado a `Desafios.tsx`.

**Tech Stack:** Python/FastAPI + Supabase (PostgreSQL), `csv` da stdlib para parsing, React 19 + TypeScript + Tailwind CSS.

**Spec de referência:** `docs/superpowers/specs/2026-07-12-desafio-import-csv-design.md`

---

## Seams (confirmar antes de escrever qualquer teste)

Esta é a lista de fronteiras públicas que serão testadas. Nenhum teste deve ser escrito fora dessas fronteiras (nada de testar função privada, nem inspecionar estado interno do Supabase diretamente).

| # | Seam | Onde | Como é testado |
|---|---|---|---|
| 1 | `normalizar_validado(raw) -> bool` | `desafio_import_engine.py` | Unitário puro |
| 2 | `normalizar_nome(raw) -> str` | `desafio_import_engine.py` | Unitário puro |
| 3 | `normalizar_clan(raw) -> str` | `desafio_import_engine.py` | Unitário puro |
| 4 | `parse_submitted_at(raw) -> datetime \| None` | `desafio_import_engine.py` | Unitário puro |
| 5 | `parse_row(raw_row, mapping) -> ImportRow` | `desafio_import_engine.py` | Unitário puro |
| 6 | `filtrar_por_periodo(rows, inicio, fim) -> (dentro, fora)` | `desafio_import_engine.py` | Unitário puro |
| 7 | `filtrar_clans_validos(rows, validos) -> (ok, invalidos)` | `desafio_import_engine.py` | Unitário puro |
| 8 | `filtrar_tokens_novos(rows, tokens_vistos) -> (novos, repetidos)` | `desafio_import_engine.py` | Unitário puro |
| 9 | `deduplicar_por_pessoa(rows) -> list[ImportRow]` | `desafio_import_engine.py` | Unitário puro |
| 10 | `processar_importacao(...) -> ImportResult` | `desafio_import_engine.py` | Unitário puro (orquestrador, cenário composto) |
| 11 | `POST /api/desafios/importar/preview` | `routers/desafio_import.py` | Manual (curl/Swagger) — depende de Supabase real, sem teste automatizado, mesmo padrão de `routers/desafios.py` |
| 12 | `POST /api/desafios/importar/confirmar` | `routers/desafio_import.py` | Manual (curl/Swagger) |

Seams 1–10 são o foco do ciclo red→green. Seams 11–12 são finos o bastante (repassam para funções já testadas) para não precisarem de teste automatizado — mesmo padrão que `routers/desafios.py` já usa hoje (ver Task 4 de `docs/superpowers/plans/2026-04-15-desafios.md`, onde o router não ganhou testes próprios).

---

## File Map

| Arquivo | Operação | Responsabilidade |
|---|---|---|
| `backend/desafio_import_engine.py` | Criar | Lógica pura: parsing, normalização, filtros, dedup, cálculo |
| `backend/tests/test_desafio_import_engine.py` | Criar | Testes unitários dos seams 1–10 |
| `backend/migrations/005_add_desafio_importacao_linhas.sql` | Criar | Tabela de auditoria |
| `backend/supabase_client.py` | Modificar | Colunas novas em `desafios`, funções de `desafio_importacao_linhas` |
| `backend/routers/desafio_import.py` | Criar | Endpoints preview/confirmar |
| `backend/main.py` | Modificar | Registrar o novo router |
| `frontend/src/api/client.ts` | Modificar | Tipos e funções de importação |
| `frontend/src/components/ImportarDesafioWizard.tsx` | Criar | Wizard de 3 passos |
| `frontend/src/pages/Desafios.tsx` | Modificar | Botão "Importar CSV" abrindo o wizard |

---

## Task 1: Migração do banco

**Files:**
- Create: `backend/migrations/005_add_desafio_importacao_linhas.sql`

- [ ] **Step 1: Alterar `desafios` manualmente no Supabase Dashboard** (mesmo padrão da migration `2026-04-16-desafios-campo-data` — sem arquivo versionado para `ALTER TABLE`)

```sql
ALTER TABLE desafios ADD COLUMN data_inicio date;
ALTER TABLE desafios ADD COLUMN data_fim date;
ALTER TABLE desafios ADD COLUMN origem varchar NOT NULL DEFAULT 'manual';
ALTER TABLE desafios ADD COLUMN pontos_por_participacao integer;
```

Verifique: `SELECT id, nome, data, data_inicio, data_fim, origem FROM desafios LIMIT 5;` — desafios existentes devem aparecer com `origem = 'manual'`, `data_inicio`/`data_fim`/`pontos_por_participacao` nulos.

- [ ] **Step 2: Criar a migration da tabela de auditoria**

```sql
-- backend/migrations/005_add_desafio_importacao_linhas.sql
CREATE TABLE desafio_importacao_linhas (
  id                 SERIAL PRIMARY KEY,
  desafio_id         INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  clan               VARCHAR NOT NULL,
  nome_participante  VARCHAR NOT NULL,
  validado           BOOLEAN NOT NULL,
  contabilizado      BOOLEAN NOT NULL DEFAULT FALSE,
  submitted_at       TIMESTAMP,
  token_original     VARCHAR NOT NULL,
  created_at         TIMESTAMP DEFAULT NOW(),
  UNIQUE(desafio_id, token_original)
);
```

- [ ] **Step 3: Aplicar no Supabase Dashboard → SQL Editor**, confirmar que a tabela aparece em Table Editor.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/005_add_desafio_importacao_linhas.sql
git commit -m "chore: add migration for desafio_importacao_linhas table"
```

---

## Task 2: Lógica pura — `normalizar_validado`

**Files:**
- Create: `backend/desafio_import_engine.py`
- Create: `backend/tests/test_desafio_import_engine.py`

- [ ] **Step 1: Teste falhando**

```python
# backend/tests/test_desafio_import_engine.py
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desafio_import_engine import normalizar_validado


class TestNormalizarValidado:

    def test_sim_exato(self):
        assert normalizar_validado("Sim") is True

    def test_sim_minusculo(self):
        assert normalizar_validado("sim") is True

    def test_sim_com_espacos(self):
        assert normalizar_validado("  Sim  ") is True

    def test_nao_e_falso(self):
        assert normalizar_validado("Não") is False

    def test_vazio_e_falso(self):
        assert normalizar_validado("") is False

    def test_valor_ambiguo_e_falso(self):
        assert normalizar_validado("Talvez") is False
```

- [ ] **Step 2: Rodar e confirmar falha**

```bash
cd backend && python -m pytest tests/test_desafio_import_engine.py -v
```

Esperado: `ImportError: cannot import name 'normalizar_validado'`

- [ ] **Step 3: Implementar**

```python
# backend/desafio_import_engine.py
"""Lógica pura de importação de desafios via CSV. Zero I/O — sem chamadas a Supabase/rede."""

from dataclasses import dataclass, field
from datetime import date, datetime


def normalizar_validado(raw: str) -> bool:
    """Só conta como validado um valor cuja forma normalizada seja exatamente 'sim'."""
    return raw.strip().lower() == "sim"
```

- [ ] **Step 4: Rodar e confirmar passe**

```bash
cd backend && python -m pytest tests/test_desafio_import_engine.py -v
```

Esperado: 6 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add normalizar_validado to desafio_import_engine"
```

---

## Task 3: Lógica pura — `normalizar_nome`

- [ ] **Step 1: Teste falhando** (adicionar a `test_desafio_import_engine.py`)

```python
from desafio_import_engine import normalizar_nome


class TestNormalizarNome:

    def test_trim_e_lowercase(self):
        assert normalizar_nome("  Ana Albertim  ") == "ana albertim"

    def test_mesma_pessoa_capitalizacao_diferente(self):
        # Caso real do CSV: "Carolina dorte gadbem" vs "carolina dorte gadbem"
        assert normalizar_nome("Carolina dorte gadbem") == normalizar_nome("carolina dorte gadbem")

    def test_espacos_internos_multiplos_preservados(self):
        assert normalizar_nome("Ana  Paula") == "ana  paula"
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
def normalizar_nome(raw: str) -> str:
    """Normaliza nome para comparação de dedup: trim + lowercase."""
    return raw.strip().lower()
```

- [ ] **Step 4: Rodar e confirmar passe (9 testes no total). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add normalizar_nome to desafio_import_engine"
```

---

## Task 4: Lógica pura — `normalizar_clan`

- [ ] **Step 1: Teste falhando**

```python
from desafio_import_engine import normalizar_clan


class TestNormalizarClan:

    def test_numero_simples(self):
        assert normalizar_clan("2") == "CLÃ 2"

    def test_numero_com_espacos(self):
        assert normalizar_clan(" 8 ") == "CLÃ 8"

    def test_nao_numerico_mantido_como_esta(self):
        # Mesmo fallback de _normalize_clan em routers/contabilidade.py
        assert normalizar_clan("abc") == "abc"
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar** (mesma lógica de `_normalize_clan` em `routers/contabilidade.py:25-29`, duplicada aqui deliberadamente — é um helper de 3 linhas e evita acoplar o módulo puro novo a um router existente)

```python
def normalizar_clan(raw: str) -> str:
    """Converte '2' em 'CLÃ 2'. Valores não numéricos são mantidos como estão (trim)."""
    try:
        return f"CLÃ {int(raw.strip())}"
    except (ValueError, AttributeError):
        return raw.strip()
```

- [ ] **Step 4: Rodar e confirmar passe (12 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add normalizar_clan to desafio_import_engine"
```

---

## Task 5: Lógica pura — `parse_submitted_at`

- [ ] **Step 1: Teste falhando** (valores reais extraídos do CSV analisado)

```python
from desafio_import_engine import parse_submitted_at


class TestParseSubmittedAt:

    def test_formato_completo_com_hora(self):
        assert parse_submitted_at("11/05/2026 14:34:00") == datetime(2026, 5, 11, 14, 34, 0)

    def test_data_invalida_retorna_none(self):
        # Junho só tem 30 dias
        assert parse_submitted_at("31/06/2026 10:00:00") is None

    def test_texto_nao_reconhecido_retorna_none(self):
        assert parse_submitted_at("não é uma data") is None

    def test_vazio_retorna_none(self):
        assert parse_submitted_at("") is None
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
def parse_submitted_at(raw: str) -> datetime | None:
    """Faz parse de 'dd/mm/yyyy HH:MM:SS'. Retorna None se ilegível ou vazio."""
    if not raw or not raw.strip():
        return None
    try:
        return datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None
```

- [ ] **Step 4: Rodar e confirmar passe (16 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add parse_submitted_at to desafio_import_engine"
```

---

## Task 6: Lógica pura — `parse_row`

- [ ] **Step 1: Teste falhando** (composição das funções anteriores; usa uma linha real do CSV — linha 2 do arquivo analisado)

```python
from desafio_import_engine import parse_row, ImportRow

MAPPING = {
    "clan": "Selecionar o Clã em que você está (1 a 8):",
    "nome": "Coloque aqui o seu Nome:",
    "validado": "Você cumpriu o Desafio Pontual G?",
    "submitted_at": "Submitted At",
    "token": "Token",
}


class TestParseRow:

    def test_linha_real_do_csv(self):
        raw_row = {
            "Selecionar o Clã em que você está (1 a 8):": "2",
            "Coloque aqui o seu Nome:": "Vinicius Alves",
            "Você cumpriu o Desafio Pontual G?": "Sim",
            "Submitted At": "11/05/2026 14:34:00",
            "Token": "gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        }
        row = parse_row(raw_row, MAPPING)
        assert row == ImportRow(
            clan="CLÃ 2",
            nome="Vinicius Alves",
            nome_normalizado="vinicius alves",
            validado=True,
            submitted_at=datetime(2026, 5, 11, 14, 34, 0),
            token="gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        )

    def test_linha_com_data_ilegivel(self):
        raw_row = {**{k: "" for k in MAPPING.values()}, MAPPING["submitted_at"]: "lixo"}
        row = parse_row(raw_row, MAPPING)
        assert row.submitted_at is None
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
@dataclass(frozen=True)
class ImportRow:
    clan: str
    nome: str
    nome_normalizado: str
    validado: bool
    submitted_at: datetime | None
    token: str


def parse_row(raw_row: dict, mapping: dict) -> ImportRow:
    """Extrai e normaliza uma linha do CSV usando o mapeamento de colunas escolhido no wizard."""
    nome = raw_row.get(mapping["nome"], "").strip()
    return ImportRow(
        clan=normalizar_clan(raw_row.get(mapping["clan"], "")),
        nome=nome,
        nome_normalizado=normalizar_nome(nome),
        validado=normalizar_validado(raw_row.get(mapping["validado"], "")),
        submitted_at=parse_submitted_at(raw_row.get(mapping["submitted_at"], "")),
        token=raw_row.get(mapping["token"], "").strip(),
    )
```

- [ ] **Step 4: Rodar e confirmar passe (18 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add parse_row to desafio_import_engine"
```

---

## Task 7: Lógica pura — `filtrar_por_periodo`

- [ ] **Step 1: Teste falhando**

```python
from desafio_import_engine import filtrar_por_periodo

def _row(submitted_at):
    return ImportRow(
        clan="CLÃ 1", nome="X", nome_normalizado="x",
        validado=True, submitted_at=submitted_at, token="t1",
    )


class TestFiltrarPorPeriodo:

    def test_dentro_do_periodo(self):
        row = _row(datetime(2026, 5, 20, 10, 0, 0))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [row] and fora == []

    def test_limites_inclusivos(self):
        inicio = _row(datetime(2026, 5, 11, 0, 0, 0))
        fim = _row(datetime(2026, 6, 30, 23, 59, 59))
        dentro, fora = filtrar_por_periodo([inicio, fim], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [inicio, fim]

    def test_antes_do_periodo_excluido(self):
        row = _row(datetime(2026, 5, 1, 10, 0, 0))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]

    def test_depois_do_periodo_excluido(self):
        # Caso real: submissão de "Desafio H" em julho não deve contar pro "Desafio G"
        row = _row(datetime(2026, 7, 5, 0, 10, 21))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]

    def test_data_ausente_e_fail_closed(self):
        row = _row(None)
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
def filtrar_por_periodo(
    rows: list[ImportRow], data_inicio: date, data_fim: date
) -> tuple[list[ImportRow], list[ImportRow]]:
    """Separa linhas dentro de [data_inicio, data_fim] (inclusive) das demais.

    Fail-closed: linha sem data parseável é tratada como fora do período
    (diferente do fail-open de points_engine.filter_by_date_range — aqui o
    risco de inflar pontos por engano pesa mais que perder uma linha ambígua).
    """
    dentro, fora = [], []
    for row in rows:
        if row.submitted_at is not None and data_inicio <= row.submitted_at.date() <= data_fim:
            dentro.append(row)
        else:
            fora.append(row)
    return dentro, fora
```

- [ ] **Step 4: Rodar e confirmar passe (23 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add filtrar_por_periodo to desafio_import_engine"
```

---

## Task 8: Lógica pura — `filtrar_clans_validos`

- [ ] **Step 1: Teste falhando**

```python
from desafio_import_engine import filtrar_clans_validos

CLANS_1_A_8 = {f"CLÃ {n}" for n in range(1, 9)}


class TestFiltrarClansValidos:

    def test_clan_valido_mantido(self):
        row = _row_com_clan("CLÃ 1")
        ok, invalidos = filtrar_clans_validos([row], CLANS_1_A_8)
        assert ok == [row] and invalidos == []

    def test_clan_fora_do_ranking_e_invalido(self):
        row = _row_com_clan("CLÃ 9")
        ok, invalidos = filtrar_clans_validos([row], CLANS_1_A_8)
        assert ok == [] and invalidos == [row]
```

(helper `_row_com_clan` no topo do arquivo de teste, análogo a `_row`)

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
def filtrar_clans_validos(
    rows: list[ImportRow], clans_validos: set[str]
) -> tuple[list[ImportRow], list[ImportRow]]:
    """Separa linhas com clã reconhecido (presente no ranking atual) das demais."""
    ok = [r for r in rows if r.clan in clans_validos]
    invalidos = [r for r in rows if r.clan not in clans_validos]
    return ok, invalidos
```

- [ ] **Step 4: Rodar e confirmar passe (25 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add filtrar_clans_validos to desafio_import_engine"
```

---

## Task 9: Lógica pura — `filtrar_tokens_novos`

- [ ] **Step 1: Teste falhando**

```python
from desafio_import_engine import filtrar_tokens_novos


class TestFiltrarTokensNovos:

    def test_token_novo_mantido(self):
        row = _row_com_token("abc")
        novos, repetidos = filtrar_tokens_novos([row], {"outro_token"})
        assert novos == [row] and repetidos == []

    def test_token_ja_importado_e_pulado(self):
        # Reimportação incremental: mesma linha não deve ser reprocessada
        row = _row_com_token("ja_visto")
        novos, repetidos = filtrar_tokens_novos([row], {"ja_visto"})
        assert novos == [] and repetidos == [row]
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
def filtrar_tokens_novos(
    rows: list[ImportRow], tokens_ja_importados: set[str]
) -> tuple[list[ImportRow], list[ImportRow]]:
    """Separa linhas com token inédito das que já foram importadas em execução anterior."""
    novos = [r for r in rows if r.token not in tokens_ja_importados]
    repetidos = [r for r in rows if r.token in tokens_ja_importados]
    return novos, repetidos
```

- [ ] **Step 4: Rodar e confirmar passe (27 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add filtrar_tokens_novos to desafio_import_engine"
```

---

## Task 10: Lógica pura — `deduplicar_por_pessoa`

- [ ] **Step 1: Teste falhando** (caso real: Luciana Batista reenviando o formulário)

```python
from desafio_import_engine import deduplicar_por_pessoa, ContabilizacaoRow


class TestDeduplicarPorPessoa:

    def test_pessoa_unica_conta(self):
        row = _row(datetime(2026, 5, 25, 16, 3, 30))
        result = deduplicar_por_pessoa([row])
        assert result == [ContabilizacaoRow(row=row, contabilizado=True)]

    def test_duas_submissoes_mesma_pessoa_so_a_mais_recente_conta(self):
        antiga = ImportRow(
            clan="CLÃ 1", nome="Luciana Batista", nome_normalizado="luciana batista",
            validado=True, submitted_at=datetime(2026, 6, 26, 17, 59, 7), token="1tih",
        )
        recente = ImportRow(
            clan="CLÃ 1", nome="Luciana Batista", nome_normalizado="luciana batista",
            validado=True, submitted_at=datetime(2026, 6, 30, 1, 14, 36), token="9w3r",
        )
        result = deduplicar_por_pessoa([antiga, recente])
        assert set(result) == {
            ContabilizacaoRow(row=antiga, contabilizado=False),
            ContabilizacaoRow(row=recente, contabilizado=True),
        }

    def test_pessoas_diferentes_mesmo_clan_ambas_contam(self):
        ana = _row_pessoa("CLÃ 1", "Ana Albertim", datetime(2026, 5, 25, 16, 3, 30))
        gustavo = _row_pessoa("CLÃ 1", "Gustavo Imhof", datetime(2026, 5, 31, 5, 2, 47))
        result = deduplicar_por_pessoa([ana, gustavo])
        assert all(r.contabilizado for r in result)
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
@dataclass(frozen=True)
class ContabilizacaoRow:
    row: ImportRow
    contabilizado: bool


def deduplicar_por_pessoa(rows: list[ImportRow]) -> list[ContabilizacaoRow]:
    """Agrupa por (clã, nome normalizado); só a submissão mais recente de cada
    pessoa conta para a pontuação. As demais são marcadas contabilizado=False
    (permanecem na auditoria, mas não somam pontos)."""
    mais_recente_por_pessoa: dict[tuple[str, str], ImportRow] = {}
    for row in rows:
        chave = (row.clan, row.nome_normalizado)
        atual = mais_recente_por_pessoa.get(chave)
        if atual is None or (row.submitted_at or datetime.min) > (atual.submitted_at or datetime.min):
            mais_recente_por_pessoa[chave] = row

    vencedores = set(mais_recente_por_pessoa.values())
    return [ContabilizacaoRow(row=row, contabilizado=row in vencedores) for row in rows]
```

- [ ] **Step 4: Rodar e confirmar passe (30 testes). Commit.**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add deduplicar_por_pessoa to desafio_import_engine"
```

---

## Task 11: Lógica pura — `processar_importacao` (orquestrador)

Este é o seam mais importante — compõe todos os anteriores num pipeline único, na ordem definida na spec: **período → clã válido → token novo → dedup de pessoa**.

- [ ] **Step 1: Teste falhando** (cenário composto, cobrindo todas as regras de uma vez — valores derivados do CSV real analisado)

```python
from desafio_import_engine import processar_importacao

MAPPING_TESTE = {
    "clan": "clan", "nome": "nome", "validado": "validado",
    "submitted_at": "data", "token": "token",
}


def _raw(clan, nome, validado, data, token):
    return {"clan": clan, "nome": nome, "validado": validado, "data": data, "token": token}


class TestProcessarImportacao:

    def test_cenario_completo(self):
        raw_rows = [
            _raw("1", "Ana Albertim", "Sim", "25/05/2026 16:03:30", "AAA"),
            _raw("1", "Luciana Batista", "Sim", "26/06/2026 17:59:07", "BBB1"),
            _raw("1", "Luciana Batista", "Sim", "30/06/2026 01:14:36", "BBB2"),  # reenvio, mais recente
            _raw("8", "Paula Petroli Pierozzi", "Sim", "21/06/2026 23:18:42", "CCC"),
            _raw("9", "Alguem", "Sim", "01/06/2026 00:00:00", "DDD"),            # clã inexistente
            _raw("1", "Outra Pessoa", "Não", "01/06/2026 00:00:00", "EEE"),      # não validado
            _raw("1", "Mais Alguem", "Sim", "05/07/2026 00:10:21", "FFF"),       # fora do período
        ]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={f"CLÃ {n}" for n in range(1, 9)},
            tokens_ja_importados=set(),
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
        )

        assert result.pontos_por_clan == {"CLÃ 1": 20, "CLÃ 8": 10}
        assert result.participacoes_por_clan == {"CLÃ 1": 2, "CLÃ 8": 1}
        assert len(result.avisos) >= 2  # clã 9 inválido + linha fora do período

        auditoria_por_token = {a["token_original"]: a for a in result.linhas_auditoria}
        assert set(auditoria_por_token) == {"AAA", "BBB1", "BBB2", "CCC", "EEE"}
        assert auditoria_por_token["BBB1"]["contabilizado"] is False
        assert auditoria_por_token["BBB2"]["contabilizado"] is True
        assert auditoria_por_token["EEE"]["validado"] is False
        assert auditoria_por_token["EEE"]["contabilizado"] is False

    def test_token_ja_importado_e_ignorado_silenciosamente(self):
        raw_rows = [_raw("1", "Ana Albertim", "Sim", "25/05/2026 16:03:30", "AAA")]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={"CLÃ 1"},
            tokens_ja_importados={"AAA"},
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
        )
        assert result.pontos_por_clan == {}
        assert result.linhas_auditoria == []
```

- [ ] **Step 2: Rodar e confirmar falha.**

- [ ] **Step 3: Implementar**

```python
@dataclass
class ImportResult:
    pontos_por_clan: dict[str, int] = field(default_factory=dict)
    participacoes_por_clan: dict[str, int] = field(default_factory=dict)
    linhas_auditoria: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def processar_importacao(
    raw_rows: list[dict],
    mapping: dict,
    clans_validos: set[str],
    tokens_ja_importados: set[str],
    data_inicio: date,
    data_fim: date,
    pontos_por_participacao: int,
) -> ImportResult:
    """Pipeline completo: parse → período → clã válido → token novo → dedup de pessoa → agregação.

    Ordem deliberada: período primeiro (é o filtro mais barato/fundamental — decide
    se a linha pertence a este desafio), depois clã (senão avisos de clã inválido
    incluiriam linhas de outros desafios), depois dedup entre importações (token),
    e por último dedup dentro do lote (pessoa), que só faz sentido sobre o conjunto final.
    """
    parsed = [parse_row(r, mapping) for r in raw_rows]

    dentro_periodo, fora_periodo = filtrar_por_periodo(parsed, data_inicio, data_fim)
    validos, invalidos = filtrar_clans_validos(dentro_periodo, clans_validos)
    novos, repetidos = filtrar_tokens_novos(validos, tokens_ja_importados)
    contabilizacao = deduplicar_por_pessoa(novos)

    result = ImportResult()

    for item in contabilizacao:
        row = item.row
        result.linhas_auditoria.append({
            "clan": row.clan,
            "nome_participante": row.nome,
            "validado": row.validado,
            "contabilizado": row.validado and item.contabilizado,
            "submitted_at": row.submitted_at,
            "token_original": row.token,
        })
        if row.validado and item.contabilizado:
            result.participacoes_por_clan[row.clan] = result.participacoes_por_clan.get(row.clan, 0) + 1
            result.pontos_por_clan[row.clan] = result.participacoes_por_clan[row.clan] * pontos_por_participacao

    if invalidos:
        clans_desconhecidos = sorted({r.clan for r in invalidos})
        result.avisos.append(
            f"{len(invalidos)} linha(s) ignorada(s) por clã não reconhecido: {', '.join(clans_desconhecidos)}"
        )
    if fora_periodo:
        result.avisos.append(f"{len(fora_periodo)} linha(s) fora do período informado foram ignoradas")

    return result
```

- [ ] **Step 4: Rodar e confirmar passe (32 testes). Rodar a suíte inteira do backend para checar que nada quebrou.**

```bash
cd backend && python -m pytest tests/ -v
```

Esperado: todos `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: add processar_importacao orchestrator to desafio_import_engine"
```

---

## Task 12: Supabase client — funções de I/O

Sem testes automatizados nesta task — segue o padrão já estabelecido no projeto (I/O contra Supabase real não é coberto por testes unitários; a lógica que importa já está 100% coberta na Task 2–11).

**Files:**
- Modify: `backend/supabase_client.py`

- [ ] **Step 1: Adicionar constante de tabela**

```python
TABLE_DESAFIO_IMPORTACAO_LINHAS = "desafio_importacao_linhas"
```

- [ ] **Step 2: Estender `create_desafio` e `update_desafio` com os campos novos (mantendo compatibilidade com o fluxo manual existente)**

```python
def create_desafio(
    nome: str,
    contabilizar_pontos: bool,
    data: date,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    origem: str = "manual",
    pontos_por_participacao: int | None = None,
) -> dict:
    """Cria um novo desafio. `data_inicio`/`data_fim`/`pontos_por_participacao` só
    são usados por desafios criados via importação de CSV (origem='csv_import')."""
    client = _get_client()
    payload = {
        "nome": nome,
        "contabilizar_pontos": contabilizar_pontos,
        "data": str(data),
        "origem": origem,
    }
    if data_inicio is not None:
        payload["data_inicio"] = str(data_inicio)
    if data_fim is not None:
        payload["data_fim"] = str(data_fim)
    if pontos_por_participacao is not None:
        payload["pontos_por_participacao"] = pontos_por_participacao
    result = client.table(TABLE_DESAFIOS).insert(payload).execute()
    return result.data[0]


def update_desafio_periodo_e_pontos(
    desafio_id: int, data_inicio: date, data_fim: date, pontos_por_participacao: int
) -> dict:
    """Atualiza período e pontos-por-participação de um desafio importado (reimportação)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIOS)
        .update({
            "data_inicio": str(data_inicio),
            "data_fim": str(data_fim),
            "data": str(data_fim),
            "pontos_por_participacao": pontos_por_participacao,
        })
        .eq("id", desafio_id)
        .execute()
    )
    return result.data[0]


def list_desafios(origem: str | None = None) -> list[dict]:
    """Lista desafios, opcionalmente filtrando por origem ('manual' | 'csv_import')."""
    client = _get_client()
    query = client.table(TABLE_DESAFIOS).select("*").order("created_at", desc=False)
    if origem is not None:
        query = query.eq("origem", origem)
    return query.execute().data
```

(A assinatura de `list_desafios` muda de `list_desafios()` para `list_desafios(origem=None)` — chamada existente em `routers/desafios.py:41` continua funcionando sem alteração, já que o parâmetro é opcional.)

- [ ] **Step 3: Funções para `desafio_importacao_linhas`**

```python
# --- Desafio Importação Linhas ---


def get_tokens_importados(desafio_id: int) -> set[str]:
    """Retorna o set de tokens já importados para um desafio (usado no dedup entre importações)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_IMPORTACAO_LINHAS)
        .select("token_original")
        .eq("desafio_id", desafio_id)
        .execute()
    )
    return {row["token_original"] for row in result.data}


def insert_desafio_importacao_linhas(desafio_id: int, linhas: list[dict]) -> list[dict]:
    """Insere as linhas de auditoria de uma importação. Cada dict já vem no formato
    de ImportResult.linhas_auditoria (clan, nome_participante, validado, contabilizado,
    submitted_at, token_original)."""
    if not linhas:
        return []
    client = _get_client()
    payload = [{**linha, "desafio_id": desafio_id, "submitted_at": str(linha["submitted_at"])} for linha in linhas]
    result = client.table(TABLE_DESAFIO_IMPORTACAO_LINHAS).insert(payload).execute()
    return result.data
```

- [ ] **Step 4: Confirmar que os testes existentes continuam passando**

```bash
cd backend && python -m pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat: add supabase client functions for desafio CSV import"
```

---

## Task 13: Backend router — `desafio_import.py`

**Files:**
- Create: `backend/routers/desafio_import.py`

- [ ] **Step 1: Criar o router**

```python
# backend/routers/desafio_import.py
import csv
import io
import json
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import desafio_import_engine
import google_sheets_client
import points_engine
import supabase_client

router = APIRouter()

NOME_CAMPO_PARTICIPACOES = "Participações Validadas"
NOME_CAMPO_PONTUACAO = "Pontuação"


class ImportConfig(BaseModel):
    nome: str
    desafio_id: int | None = None
    data_inicio: date
    data_fim: date
    pontos_por_participacao: int


def _ler_csv(file_bytes: bytes) -> list[dict]:
    texto = file_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto)))


def _clans_validos() -> set[str]:
    ranking = google_sheets_client.fetch_ranking()
    return {entry["clan"] for entry in ranking}


def _tokens_ja_importados(desafio_id: int | None) -> set[str]:
    if desafio_id is None:
        return set()
    return supabase_client.get_tokens_importados(desafio_id)


def _processar(file: UploadFile, mapping_json: str, config_json: str) -> tuple[desafio_import_engine.ImportResult, ImportConfig]:
    mapping = json.loads(mapping_json)
    config = ImportConfig(**json.loads(config_json))
    raw_rows = _ler_csv(file.file.read())

    result = desafio_import_engine.processar_importacao(
        raw_rows=raw_rows,
        mapping=mapping,
        clans_validos=_clans_validos(),
        tokens_ja_importados=_tokens_ja_importados(config.desafio_id),
        data_inicio=config.data_inicio,
        data_fim=config.data_fim,
        pontos_por_participacao=config.pontos_por_participacao,
    )
    return result, config


@router.post("/preview")
def preview(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    config: str = Form(...),
):
    """Calcula o resultado da importação SEM gravar nada."""
    result, _ = _processar(file, mapping, config)
    return {
        "pontos_por_clan": result.pontos_por_clan,
        "participacoes_por_clan": result.participacoes_por_clan,
        "avisos": result.avisos,
        "total_linhas_contabilizadas": sum(result.participacoes_por_clan.values()),
    }


@router.post("/confirmar")
def confirmar(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    config: str = Form(...),
):
    """Efetiva a importação: cria ou atualiza o desafio e aplica os pontos."""
    result, config_obj = _processar(file, mapping, config)

    if config_obj.desafio_id is not None:
        desafio = supabase_client.get_desafio(config_obj.desafio_id)
        if not desafio or desafio.get("origem") != "csv_import":
            raise HTTPException(
                status_code=404,
                detail="Desafio importável não encontrado (só desafios criados via importação podem ser atualizados).",
            )
        supabase_client.update_desafio_periodo_e_pontos(
            config_obj.desafio_id, config_obj.data_inicio, config_obj.data_fim,
            config_obj.pontos_por_participacao,
        )
        campos = supabase_client.list_desafio_campos(config_obj.desafio_id)
    else:
        desafio = supabase_client.create_desafio(
            nome=config_obj.nome,
            contabilizar_pontos=True,
            data=config_obj.data_fim,
            data_inicio=config_obj.data_inicio,
            data_fim=config_obj.data_fim,
            origem="csv_import",
            pontos_por_participacao=config_obj.pontos_por_participacao,
        )
        campos = supabase_client.insert_desafio_campos([
            {"desafio_id": desafio["id"], "nome": NOME_CAMPO_PARTICIPACOES, "tipo": "texto", "ordem": 0},
            {"desafio_id": desafio["id"], "nome": NOME_CAMPO_PONTUACAO, "tipo": "pontuacao", "ordem": 1},
        ])

    campo_participacoes = next(c for c in campos if c["nome"] == NOME_CAMPO_PARTICIPACOES)
    campo_pontuacao = next(c for c in campos if c["nome"] == NOME_CAMPO_PONTUACAO)

    if result.linhas_auditoria:
        supabase_client.insert_desafio_importacao_linhas(desafio["id"], result.linhas_auditoria)

    for clan, participacoes in result.participacoes_por_clan.items():
        pontos = result.pontos_por_clan[clan]
        valores = {str(campo_participacoes["id"]): str(participacoes), str(campo_pontuacao["id"]): pontos}

        existente = supabase_client.get_desafio_registro_by_clan(desafio["id"], clan)
        if existente:
            novo_total = points_engine.calculate_desafio_pontos(campos, valores)
            delta = novo_total - existente["total_pontos"]
            supabase_client.update_desafio_registro_pontos(existente["id"], valores, novo_total)
            if delta != 0:
                supabase_client.add_delta_to_clan_total(clan, delta)
        else:
            supabase_client.create_desafio_registro(desafio["id"], clan, valores, pontos)
            supabase_client.add_delta_to_clan_total(clan, pontos)

    campos_atualizados = supabase_client.list_desafio_campos(desafio["id"])
    registros = supabase_client.list_desafio_registros(desafio["id"])
    return {**supabase_client.get_desafio(desafio["id"]), "campos": campos_atualizados, "total_registros": len(registros)}
```

- [ ] **Step 2: Confirmar que os testes existentes continuam passando** (este router não ganha teste automatizado, mesmo padrão de `routers/desafios.py` — depende de Supabase e Google Sheets reais)

```bash
cd backend && python -m pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/desafio_import.py
git commit -m "feat: add desafio_import router with preview and confirmar endpoints"
```

---

## Task 14: Registrar o router em `main.py`

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Adicionar import e `include_router`**

```python
from routers import contabilidade, registros, clans, coaches, desafios, desafio_import
...
app.include_router(desafio_import.router, prefix="/api/desafios/importar", tags=["Desafios"])
```

- [ ] **Step 2: Verificar que o backend sobe sem erros**

```bash
cd backend && python main.py &
sleep 2
curl http://localhost:8000/api/health
kill %1
```

Esperado: `{"status":"ok"}`

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: register desafio_import router in main.py"
```

---

## Task 15: Frontend — API client

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Adicionar tipos e funções**

```typescript
// --- Importação de Desafios via CSV ---

export interface ImportPreviewResult {
  pontos_por_clan: Record<string, number>;
  participacoes_por_clan: Record<string, number>;
  avisos: string[];
  total_linhas_contabilizadas: number;
}

export interface ImportConfig {
  nome: string;
  desafio_id?: number;
  data_inicio: string;
  data_fim: string;
  pontos_por_participacao: number;
}

export type ColumnMapping = {
  clan: string;
  nome: string;
  validado: string;
  submitted_at: string;
  token: string;
};

function buildImportFormData(file: File, mapping: ColumnMapping, config: ImportConfig): FormData {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('mapping', JSON.stringify(mapping));
  formData.append('config', JSON.stringify(config));
  return formData;
}

export async function previewImportacaoDesafio(
  file: File,
  mapping: ColumnMapping,
  config: ImportConfig
): Promise<ImportPreviewResult> {
  const response = await fetch(`${API_BASE}/api/desafios/importar/preview`, {
    method: 'POST',
    body: buildImportFormData(file, mapping, config),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function confirmarImportacaoDesafio(
  file: File,
  mapping: ColumnMapping,
  config: ImportConfig
): Promise<Desafio> {
  const response = await fetch(`${API_BASE}/api/desafios/importar/confirmar`, {
    method: 'POST',
    body: buildImportFormData(file, mapping, config),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export function fetchDesafiosImportaveis(): Promise<Desafio[]> {
  return request('/api/desafios?origem=csv_import');
}
```

Ajuste `API_BASE`/`request` conforme o que já existe no topo de `client.ts` (confirmar nome exato antes de aplicar — o arquivo já define a base URL usada por `fetchDesafios` etc).

- [ ] **Step 2: Verificar que o TypeScript compila**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add CSV import API functions to client.ts"
```

---

## Task 16: Frontend — wizard de importação

**Files:**
- Create: `frontend/src/components/ImportarDesafioWizard.tsx`

- [ ] **Step 1: Criar o componente** com 3 passos internos (`upload` → `config` → `preview`), reaproveitando os tipos de `client.ts`:

  - **Passo upload:** `<input type="file" accept=".csv">`; ao selecionar, ler as primeiras linhas no browser (`FileReader` + split da primeira linha por vírgula) só para popular os `<select>` de mapeamento — não faz parsing completo no frontend, isso é responsabilidade do backend.
  - **Passo config:** toggle "Criar novo" / "Atualizar existente" (dropdown populado via `fetchDesafiosImportaveis`), inputs de nome (se novo), período, pontos por participação.
  - **Passo preview:** chama `previewImportacaoDesafio`, renderiza tabela clã → participações → pontos, lista `avisos`, botões Cancelar/Confirmar. Confirmar chama `confirmarImportacaoDesafio` e fecha o wizard com callback `onImported`.

  Seguir o mesmo estilo visual de `Desafios.tsx` (Tailwind, `bg-white rounded-xl border border-gray-200 p-6`, botões `bg-indigo-600 text-white ... hover:bg-indigo-700`).

- [ ] **Step 2: Verificar que o TypeScript compila**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ImportarDesafioWizard.tsx
git commit -m "feat: add ImportarDesafioWizard component"
```

---

## Task 17: Frontend — integrar o wizard em `Desafios.tsx`

**Files:**
- Modify: `frontend/src/pages/Desafios.tsx`

- [ ] **Step 1: Adicionar botão "Importar CSV" ao lado de "Novo Desafio"** no modo lista, abrindo `<ImportarDesafioWizard />` num modo novo (`mode === "import"`) ou modal. Ao concluir (`onImported`), chamar `loadDesafios()` e voltar para `mode === "list"`.

- [ ] **Step 2: Testar manualmente no navegador**

```bash
cd frontend && npm run dev
```

1. `/desafios` → botão "Importar CSV" visível
2. Subir o CSV de exemplo → mapear as 5 colunas → preencher nome/período/pontos → prévia mostra números batendo com a análise manual (Clã 1 com 9 participações no período de Maio–Junho)
3. Confirmar → desafio aparece na lista com badge "csv_import" (se exibido) → total do clã sobe no Dashboard
4. Reimportar o mesmo CSV escolhendo "Atualizar existente" → prévia mostra 0 novas participações (todos os tokens já vistos) → confirmar não duplica pontos

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Desafios.tsx
git commit -m "feat: integrate CSV import wizard into Desafios page"
```

---

## Verificação final

```bash
# Backend — suíte completa (32+ testes novos de desafio_import_engine + 74 existentes)
cd backend && python -m pytest tests/ -v

# Frontend — build limpo
cd frontend && npm run build
```

Checar os 7 cenários da spec (`docs/superpowers/specs/2026-07-12-desafio-import-csv-design.md`, seção "Verificação end-to-end"):
1. Importação nova com CSV de exemplo → prévia e totais corretos
2. Dedup de pessoa (Luciana Batista) → conta 1x, não 2x
3. Linha "Não" → não pontua, aparece na auditoria
4. Clã inválido → aviso, resto importa
5. Reimportação incremental → soma só o delta de tokens novos
6. Linha fora do período → ignorada com aviso
7. Cancelar prévia → nada gravado no banco
