# Pontos de desafio CSV por coach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Also follow superpowers:test-driven-development for every task with a red/green cycle — write the failing test, watch it fail for the stated reason, write minimal code, watch it pass, commit.

**Goal:** Make CSV-imported desafios (`origem='csv_import'`) attribute individual points to each coach, not just to clãs — same formula, same coach-identity normalization already used elsewhere.

**Architecture:** Mirror the existing per-clã bookkeeping (`desafio_registros`, `add_delta_to_clan_total`, `get_tipo_clan_totals("desafios")`) with a parallel per-coach path (`desafio_registros_coach`, `add_delta_to_coach_total`, `get_tipo_coach_totals("desafios")`). The pure engine (`desafio_import_engine.py`) gains a `coach` field resolved via the existing `coach_identity` alias system, injected by the router exactly like `clans_validos`/`tokens_ja_importados` already are.

**Tech Stack:** Python 3 / FastAPI / Supabase (postgrest-py) backend, pytest, React/TypeScript frontend (no test harness — verify via `tsc`/manual).

## Global Constraints

- Coach identity for desafio CSV rows = the same "Nome" column already mapped in the wizard (no new mapping field) — approved in spec.
- Applies **only** to `origem='csv_import'` desafios. Manual desafios never get coach records.
- Coach points sum directly into `pontos_ultimate_totais_por_coach.total_pontos` at confirm time (ranking geral "todos" includes them) — approved in spec.
- Coach canonical name is resolved and persisted at import time (not recomputed on read); alias corrections require `POST /contabilidade/reprocessar-coaches`, which must also fix desafio data — approved in spec.
- Spec: `docs/superpowers/specs/2026-07-14-desafio-coach-pontos-design.md`.

---

### Task 1: Migration — `desafio_registros_coach` table + `coach` column

**Files:**
- Create: `backend/migrations/007_add_desafio_registros_coach.sql`

**Interfaces:**
- Produces: table `desafio_registros_coach(id, desafio_id, coach, valores, total_pontos, created_at)` with `UNIQUE(desafio_id, coach)`; column `desafio_importacao_linhas.coach` (nullable varchar).

No automated test — this repo applies migrations manually via the Supabase Dashboard (see `backend/migrations/005_add_desafio_importacao_linhas.sql` / `006_add_coach_aliases.sql`, no migration runner in the codebase). Verification is manual (Task 1 Step 2).

- [ ] **Step 1: Write the migration file**

```sql
-- backend/migrations/007_add_desafio_registros_coach.sql
ALTER TABLE desafio_importacao_linhas ADD COLUMN coach VARCHAR;

CREATE TABLE desafio_registros_coach (
  id           SERIAL PRIMARY KEY,
  desafio_id   INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  coach        VARCHAR NOT NULL,
  valores      JSONB NOT NULL,
  total_pontos INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(desafio_id, coach)
);
```

- [ ] **Step 2: Note for the user**

This SQL must be run once against the Supabase project (Dashboard → SQL Editor) before the feature works end-to-end. Flag this at the end of the plan — do not attempt to run it programmatically.

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/007_add_desafio_registros_coach.sql
git commit -m "feat: migration para desafio_registros_coach e coach em desafio_importacao_linhas"
```

---

### Task 2: Pure engine — coach identity threaded through `desafio_import_engine.py`

**Files:**
- Modify: `backend/desafio_import_engine.py`
- Modify: `backend/tests/test_desafio_import_engine.py`

**Interfaces:**
- Consumes: `coach_identity.resolve_coach(coach_raw: str, alias_map: dict[str, str]) -> str` (existing, `backend/coach_identity.py`).
- Produces: `ImportRow.coach: str`; `parse_row(raw_row, mapping, coach_alias_map) -> ImportRow`; `processar_importacao(..., coach_alias_map: dict[str, str]) -> ImportResult`; `ImportResult.pontos_por_coach: dict[str, int]`, `ImportResult.participacoes_por_coach: dict[str, int]`; `linhas_auditoria` entries gain key `"coach"`.

- [ ] **Step 1: Update the test file to the new interface and add coach assertions**

Replace `backend/tests/test_desafio_import_engine.py` entirely with:

```python
import sys
import os
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desafio_import_engine import (
    normalizar_validado,
    normalizar_nome,
    normalizar_clan,
    parse_submitted_at,
    parse_row,
    ImportRow,
    filtrar_por_periodo,
    filtrar_clans_validos,
    filtrar_tokens_novos,
    deduplicar_por_pessoa,
    ContabilizacaoRow,
    processar_importacao,
)

MAPPING_TESTE = {
    "clan": "clan", "nome": "nome", "validado": "validado",
    "submitted_at": "data", "token": "token",
}


def _raw(clan, nome, validado, data, token):
    return {"clan": clan, "nome": nome, "validado": validado, "data": data, "token": token}

MAPPING = {
    "clan": "Selecionar o Clã em que você está (1 a 8):",
    "nome": "Coloque aqui o seu Nome:",
    "validado": "Você cumpriu o Desafio Pontual G?",
    "submitted_at": "Submitted At",
    "token": "Token",
}


def _row(submitted_at):
    return ImportRow(
        clan="CLÃ 1", nome="X", nome_normalizado="x", coach="X",
        validado=True, submitted_at=submitted_at, token="t1",
    )


def _row_com_clan(clan):
    return ImportRow(
        clan=clan, nome="X", nome_normalizado="x", coach="X",
        validado=True, submitted_at=datetime(2026, 5, 20, 10, 0, 0), token="t1",
    )


def _row_com_token(token):
    return ImportRow(
        clan="CLÃ 1", nome="X", nome_normalizado="x", coach="X",
        validado=True, submitted_at=datetime(2026, 5, 20, 10, 0, 0), token=token,
    )


def _row_pessoa(clan, nome, submitted_at):
    return ImportRow(
        clan=clan, nome=nome, nome_normalizado=normalizar_nome(nome), coach=nome,
        validado=True, submitted_at=submitted_at, token=f"{clan}-{nome}",
    )


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


class TestNormalizarNome:

    def test_trim_e_lowercase(self):
        assert normalizar_nome("  Ana Albertim  ") == "ana albertim"

    def test_mesma_pessoa_capitalizacao_diferente(self):
        assert normalizar_nome("Carolina dorte gadbem") == normalizar_nome("carolina dorte gadbem")

    def test_espacos_internos_multiplos_preservados(self):
        assert normalizar_nome("Ana  Paula") == "ana  paula"


class TestNormalizarClan:

    def test_numero_simples(self):
        assert normalizar_clan("2") == "CLÃ 2"

    def test_numero_com_espacos(self):
        assert normalizar_clan(" 8 ") == "CLÃ 8"

    def test_nao_numerico_mantido_como_esta(self):
        assert normalizar_clan("abc") == "abc"


class TestParseSubmittedAt:

    def test_formato_completo_com_hora(self):
        assert parse_submitted_at("11/05/2026 14:34:00") == datetime(2026, 5, 11, 14, 34, 0)

    def test_data_invalida_retorna_none(self):
        assert parse_submitted_at("31/06/2026 10:00:00") is None

    def test_texto_nao_reconhecido_retorna_none(self):
        assert parse_submitted_at("não é uma data") is None

    def test_vazio_retorna_none(self):
        assert parse_submitted_at("") is None


class TestParseRow:

    def test_linha_real_do_csv(self):
        raw_row = {
            "Selecionar o Clã em que você está (1 a 8):": "2",
            "Coloque aqui o seu Nome:": "Vinicius Alves",
            "Você cumpriu o Desafio Pontual G?": "Sim",
            "Submitted At": "11/05/2026 14:34:00",
            "Token": "gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        }
        row = parse_row(raw_row, MAPPING, {})
        assert row == ImportRow(
            clan="CLÃ 2",
            nome="Vinicius Alves",
            nome_normalizado="vinicius alves",
            coach="Vinicius Alves",
            validado=True,
            submitted_at=datetime(2026, 5, 11, 14, 34, 0),
            token="gqf0oqvq3c1s7e76nj1gqf0oqk9mpyn0",
        )

    def test_linha_com_data_ilegivel(self):
        raw_row = {**{k: "" for k in MAPPING.values()}, MAPPING["submitted_at"]: "lixo"}
        row = parse_row(raw_row, MAPPING, {})
        assert row.submitted_at is None

    def test_coach_resolvido_via_alias_map(self):
        raw_row = {
            "Selecionar o Clã em que você está (1 a 8):": "1",
            "Coloque aqui o seu Nome:": "Vini Marini",
            "Você cumpriu o Desafio Pontual G?": "Sim",
            "Submitted At": "11/05/2026 14:34:00",
            "Token": "tok1",
        }
        row = parse_row(raw_row, MAPPING, {"Vini Marini": "Vinicius Marini"})
        assert row.coach == "Vinicius Marini"


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
        row = _row(datetime(2026, 7, 5, 0, 10, 21))
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]

    def test_data_ausente_e_fail_closed(self):
        row = _row(None)
        dentro, fora = filtrar_por_periodo([row], date(2026, 5, 11), date(2026, 6, 30))
        assert dentro == [] and fora == [row]


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


class TestFiltrarTokensNovos:

    def test_token_novo_mantido(self):
        row = _row_com_token("abc")
        novos, repetidos = filtrar_tokens_novos([row], {"outro_token"})
        assert novos == [row] and repetidos == []

    def test_token_ja_importado_e_pulado(self):
        row = _row_com_token("ja_visto")
        novos, repetidos = filtrar_tokens_novos([row], {"ja_visto"})
        assert novos == [] and repetidos == [row]


class TestDeduplicarPorPessoa:

    def test_pessoa_unica_conta(self):
        row = _row(datetime(2026, 5, 25, 16, 3, 30))
        result = deduplicar_por_pessoa([row])
        assert result == [ContabilizacaoRow(row=row, contabilizado=True)]

    def test_duas_submissoes_mesma_pessoa_so_a_mais_recente_conta(self):
        antiga = ImportRow(
            clan="CLÃ 1", nome="Luciana Batista", nome_normalizado="luciana batista",
            coach="Luciana Batista",
            validado=True, submitted_at=datetime(2026, 6, 26, 17, 59, 7), token="1tih",
        )
        recente = ImportRow(
            clan="CLÃ 1", nome="Luciana Batista", nome_normalizado="luciana batista",
            coach="Luciana Batista",
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


class TestProcessarImportacao:

    def test_cenario_completo(self):
        raw_rows = [
            _raw("1", "Ana Albertim", "Sim", "25/05/2026 16:03:30", "AAA"),
            _raw("1", "Luciana Batista", "Sim", "26/06/2026 17:59:07", "BBB1"),
            _raw("1", "Luciana Batista", "Sim", "30/06/2026 01:14:36", "BBB2"),
            _raw("8", "Paula Petroli Pierozzi", "Sim", "21/06/2026 23:18:42", "CCC"),
            _raw("9", "Alguem", "Sim", "01/06/2026 00:00:00", "DDD"),
            _raw("1", "Outra Pessoa", "Não", "01/06/2026 00:00:00", "EEE"),
            _raw("1", "Mais Alguem", "Sim", "05/07/2026 00:10:21", "FFF"),
        ]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={f"CLÃ {n}" for n in range(1, 9)},
            tokens_ja_importados=set(),
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
            coach_alias_map={},
        )

        assert result.pontos_por_clan == {"CLÃ 1": 20, "CLÃ 8": 10}
        assert result.participacoes_por_clan == {"CLÃ 1": 2, "CLÃ 8": 1}
        assert result.pontos_por_coach == {
            "Ana Albertim": 10, "Luciana Batista": 10, "Paula Petroli Pierozzi": 10,
        }
        assert result.participacoes_por_coach == {
            "Ana Albertim": 1, "Luciana Batista": 1, "Paula Petroli Pierozzi": 1,
        }
        assert len(result.avisos) >= 2

        auditoria_por_token = {a["token_original"]: a for a in result.linhas_auditoria}
        assert set(auditoria_por_token) == {"AAA", "BBB1", "BBB2", "CCC", "EEE"}
        assert auditoria_por_token["BBB1"]["contabilizado"] is False
        assert auditoria_por_token["BBB2"]["contabilizado"] is True
        assert auditoria_por_token["BBB2"]["coach"] == "Luciana Batista"
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
            coach_alias_map={},
        )
        assert result.pontos_por_clan == {}
        assert result.pontos_por_coach == {}
        assert result.linhas_auditoria == []

    def test_coach_com_alias_agrega_sob_canonico(self):
        raw_rows = [
            _raw("1", "Vini Marini", "Sim", "20/05/2026 10:00:00", "T1"),
            _raw("1", "Ana Albertim", "Sim", "21/05/2026 10:00:00", "T2"),
        ]
        result = processar_importacao(
            raw_rows=raw_rows,
            mapping=MAPPING_TESTE,
            clans_validos={"CLÃ 1"},
            tokens_ja_importados=set(),
            data_inicio=date(2026, 5, 11),
            data_fim=date(2026, 6, 30),
            pontos_por_participacao=10,
            coach_alias_map={"Vini Marini": "Vinicius Marini"},
        )
        assert result.pontos_por_coach == {"Vinicius Marini": 10, "Ana Albertim": 10}
        assert result.participacoes_por_coach == {"Vinicius Marini": 1, "Ana Albertim": 1}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && python -m pytest tests/test_desafio_import_engine.py -v`
Expected: FAIL — `ImportRow.__init__() missing 1 required positional argument: 'coach'` (or `TypeError: parse_row() takes 2 positional arguments but 3 were given` for the parse_row calls, and `unexpected keyword argument 'coach_alias_map'` for `processar_importacao`).

- [ ] **Step 3: Implement — add `coach` to `ImportRow`, thread `coach_alias_map` through `parse_row`/`processar_importacao`, populate `pontos_por_coach`/`participacoes_por_coach`**

In `backend/desafio_import_engine.py`:

Add the import at the top of the file (after the existing `from datetime import date, datetime`):

```python
import coach_identity
```

Replace the `ImportRow` dataclass:

```python
@dataclass(frozen=True)
class ImportRow:
    clan: str
    nome: str
    nome_normalizado: str
    coach: str
    validado: bool
    submitted_at: datetime | None
    token: str
```

Replace `parse_row`:

```python
def parse_row(raw_row: dict, mapping: dict, coach_alias_map: dict[str, str]) -> ImportRow:
    """Extrai e normaliza uma linha do CSV usando o mapeamento de colunas escolhido no wizard.

    coach = mesma coluna 'Nome' já mapeada, resolvida para o nome canônico via
    coach_identity (quem preenche o formulário é o próprio coach)."""
    nome = raw_row.get(mapping["nome"], "").strip()
    return ImportRow(
        clan=normalizar_clan(raw_row.get(mapping["clan"], "")),
        nome=nome,
        nome_normalizado=normalizar_nome(nome),
        coach=coach_identity.resolve_coach(nome, coach_alias_map),
        validado=normalizar_validado(raw_row.get(mapping["validado"], "")),
        submitted_at=parse_submitted_at(raw_row.get(mapping["submitted_at"], "")),
        token=raw_row.get(mapping["token"], "").strip(),
    )
```

Replace the `ImportResult` dataclass:

```python
@dataclass
class ImportResult:
    pontos_por_clan: dict[str, int] = field(default_factory=dict)
    participacoes_por_clan: dict[str, int] = field(default_factory=dict)
    pontos_por_coach: dict[str, int] = field(default_factory=dict)
    participacoes_por_coach: dict[str, int] = field(default_factory=dict)
    linhas_auditoria: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
```

Replace `processar_importacao`:

```python
def processar_importacao(
    raw_rows: list[dict],
    mapping: dict,
    clans_validos: set[str],
    tokens_ja_importados: set[str],
    data_inicio: date,
    data_fim: date,
    pontos_por_participacao: int,
    coach_alias_map: dict[str, str],
) -> ImportResult:
    """Pipeline completo: parse → período → clã válido → token novo → dedup de pessoa → agregação.

    Ordem deliberada: período primeiro (é o filtro mais barato/fundamental — decide
    se a linha pertence a este desafio), depois clã (senão avisos de clã inválido
    incluiriam linhas de outros desafios), depois dedup entre importações (token),
    e por último dedup dentro do lote (pessoa), que só faz sentido sobre o conjunto final.

    Pontos de coach usam a mesma submissão vencedora (contabilizado=True) que já
    decide os pontos de clã — coach = a mesma coluna 'Nome', resolvida ao canônico.
    """
    parsed = [parse_row(r, mapping, coach_alias_map) for r in raw_rows]

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
            "coach": row.coach,
            "validado": row.validado,
            "contabilizado": row.validado and item.contabilizado,
            "submitted_at": row.submitted_at,
            "token_original": row.token,
        })
        if row.validado and item.contabilizado:
            result.participacoes_por_clan[row.clan] = result.participacoes_por_clan.get(row.clan, 0) + 1
            result.pontos_por_clan[row.clan] = result.participacoes_por_clan[row.clan] * pontos_por_participacao

            result.participacoes_por_coach[row.coach] = result.participacoes_por_coach.get(row.coach, 0) + 1
            result.pontos_por_coach[row.coach] = result.participacoes_por_coach[row.coach] * pontos_por_participacao

    if invalidos:
        clans_desconhecidos = sorted({r.clan for r in invalidos})
        result.avisos.append(
            f"{len(invalidos)} linha(s) ignorada(s) por clã não reconhecido: {', '.join(clans_desconhecidos)}"
        )
    if fora_periodo:
        result.avisos.append(f"{len(fora_periodo)} linha(s) fora do período informado foram ignoradas")

    return result
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && python -m pytest tests/test_desafio_import_engine.py -v`
Expected: PASS (all tests green)

- [ ] **Step 5: Commit**

```bash
git add backend/desafio_import_engine.py backend/tests/test_desafio_import_engine.py
git commit -m "feat: motor de importação de desafios calcula pontos por coach"
```

---

### Task 3: `supabase_client.py` — CRUD de `desafio_registros_coach` + `add_delta_to_coach_total`

**Files:**
- Modify: `backend/supabase_client.py`
- Create: `backend/tests/test_desafio_registros_coach.py`

**Interfaces:**
- Consumes: `TABLE_DESAFIOS`, `_get_client()`, `get_coach_totals()`, `upsert_coach_total()` (existing).
- Produces: `TABLE_DESAFIO_REGISTROS_COACH = "desafio_registros_coach"`; `create_desafio_registro_coach(desafio_id, coach, valores, total_pontos) -> dict`; `list_desafio_registros_coach(desafio_id) -> list[dict]`; `get_desafio_registro_coach_by_coach(desafio_id, coach) -> dict | None`; `update_desafio_registro_coach_pontos(registro_id, valores, total_pontos) -> dict`; `add_delta_to_coach_total(coach, delta) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_desafio_registros_coach.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
import supabase_client


def _mock_client(returned_rows):
    result = MagicMock()
    result.data = returned_rows
    chain = MagicMock()
    chain.execute.return_value = result
    for m in ("table", "select", "insert", "update", "eq", "order"):
        getattr(chain, m).return_value = chain
    client = MagicMock()
    client.table.return_value = chain
    return client


class TestCreateDesafioRegistroCoach:

    def test_insere_e_retorna_primeira_linha(self):
        row = {"id": 1, "desafio_id": 5, "coach": "Ana Albertim", "valores": {}, "total_pontos": 10}
        with patch("supabase_client._get_client", return_value=_mock_client([row])):
            result = supabase_client.create_desafio_registro_coach(5, "Ana Albertim", {}, 10)
        assert result == row


class TestGetDesafioRegistroCoachByCoach:

    def test_encontrado_retorna_linha(self):
        row = {"id": 1, "desafio_id": 5, "coach": "Ana Albertim", "total_pontos": 10}
        with patch("supabase_client._get_client", return_value=_mock_client([row])):
            result = supabase_client.get_desafio_registro_coach_by_coach(5, "Ana Albertim")
        assert result == row

    def test_nao_encontrado_retorna_none(self):
        with patch("supabase_client._get_client", return_value=_mock_client([])):
            result = supabase_client.get_desafio_registro_coach_by_coach(5, "Ninguem")
        assert result is None


class TestUpdateDesafioRegistroCoachPontos:

    def test_atualiza_e_retorna_linha(self):
        row = {"id": 1, "valores": {"9": "2"}, "total_pontos": 20}
        with patch("supabase_client._get_client", return_value=_mock_client([row])):
            result = supabase_client.update_desafio_registro_coach_pontos(1, {"9": "2"}, 20)
        assert result == row


class TestListDesafioRegistrosCoach:

    def test_lista_registros_do_desafio(self):
        rows = [{"id": 1, "coach": "Ana Albertim"}, {"id": 2, "coach": "Gustavo Imhof"}]
        with patch("supabase_client._get_client", return_value=_mock_client(rows)):
            result = supabase_client.list_desafio_registros_coach(5)
        assert result == rows


class TestAddDeltaToCoachTotal:

    def test_soma_delta_positivo_ao_total_existente(self):
        with patch("supabase_client.get_coach_totals", return_value={"Ana Albertim": 30}), \
             patch("supabase_client.upsert_coach_total",
                   return_value={"coach": "Ana Albertim", "total_pontos": 40}) as mock_upsert:
            result = supabase_client.add_delta_to_coach_total("Ana Albertim", 10)
        mock_upsert.assert_called_once_with("Ana Albertim", 40)
        assert result == {"coach": "Ana Albertim", "total_pontos": 40}

    def test_coach_sem_total_existente_parte_de_zero(self):
        with patch("supabase_client.get_coach_totals", return_value={}), \
             patch("supabase_client.upsert_coach_total",
                   return_value={"coach": "Novo Coach", "total_pontos": 10}) as mock_upsert:
            supabase_client.add_delta_to_coach_total("Novo Coach", 10)
        mock_upsert.assert_called_once_with("Novo Coach", 10)

    def test_delta_negativo_nao_passa_de_zero(self):
        with patch("supabase_client.get_coach_totals", return_value={"Ana Albertim": 10}), \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert:
            supabase_client.add_delta_to_coach_total("Ana Albertim", -50)
        mock_upsert.assert_called_once_with("Ana Albertim", 0)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && python -m pytest tests/test_desafio_registros_coach.py -v`
Expected: FAIL — `AttributeError: module 'supabase_client' has no attribute 'create_desafio_registro_coach'` (and similarly for the other new functions).

- [ ] **Step 3: Implement**

In `backend/supabase_client.py`, add the table constant next to the other `TABLE_*` constants (after `TABLE_DESAFIO_REGISTROS = "desafio_registros"`):

```python
TABLE_DESAFIO_REGISTROS_COACH = "desafio_registros_coach"
```

Add a new section right after `update_desafio_registro_pontos` (which ends the existing `# --- Desafio Registros ---` section) and before `# --- Desafio Importação Linhas ---`:

```python
# --- Desafio Registros Coach ---


def create_desafio_registro_coach(
    desafio_id: int, coach: str, valores: dict, total_pontos: int
) -> dict:
    """Cria um registro de coach em um desafio."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_REGISTROS_COACH).insert(
        {
            "desafio_id": desafio_id,
            "coach": coach,
            "valores": valores,
            "total_pontos": total_pontos,
        }
    ).execute()
    return result.data[0]


def list_desafio_registros_coach(desafio_id: int) -> list[dict]:
    """Lista registros de coach de um desafio ordenados por data de criação."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .select("*")
        .eq("desafio_id", desafio_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


def get_desafio_registro_coach_by_coach(desafio_id: int, coach: str) -> dict | None:
    """Busca o registro de um coach específico em um desafio."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .select("*")
        .eq("desafio_id", desafio_id)
        .eq("coach", coach)
        .execute()
    )
    return result.data[0] if result.data else None


def update_desafio_registro_coach_pontos(
    registro_id: int, valores: dict, total_pontos: int
) -> dict:
    """Atualiza os valores e total_pontos de um registro de coach (usado no recálculo)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .update({"valores": valores, "total_pontos": total_pontos})
        .eq("id", registro_id)
        .execute()
    )
    return result.data[0]


def add_delta_to_coach_total(coach: str, delta: int) -> dict:
    """Soma delta (positivo ou negativo) ao total_pontos do coach. Mínimo 0."""
    current_totals = get_coach_totals()
    current = current_totals.get(coach, 0)
    new_total = max(0, current + delta)
    return upsert_coach_total(coach, new_total)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && python -m pytest tests/test_desafio_registros_coach.py -v`
Expected: PASS (all tests green)

- [ ] **Step 5: Commit**

```bash
git add backend/supabase_client.py backend/tests/test_desafio_registros_coach.py
git commit -m "feat: CRUD de desafio_registros_coach e add_delta_to_coach_total"
```

---

### Task 4: `supabase_client.py` — `get_tipo_coach_totals("desafios")` real + `get_period_desafio_coach_totals`

**Files:**
- Modify: `backend/supabase_client.py`
- Modify: `backend/tests/test_tipo_filter_breakdown.py`
- Modify: `backend/tests/test_period_totals_floor.py`

**Interfaces:**
- Consumes: `TABLE_DESAFIOS`, `TABLE_DESAFIO_REGISTROS_COACH` (Task 3), `_get_client()`.
- Produces: `get_period_desafio_coach_totals(inicio: date, fim: date) -> dict[str, int]`; `get_tipo_coach_totals("desafios", inicio=None, fim=None)` now returns real data instead of `{}`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_tipo_filter_breakdown.py` (new class at the end of the file):

```python
class TestGetTipoCoachTotalsDesafiosNoDate:
    """Sem datas: lê desafio_registros_coach dos desafios com contabilizar_pontos=true."""

    def test_soma_pontos_de_coach_dos_desafios_contabilizados(self):
        client = MagicMock()

        result_desafios = MagicMock()
        result_desafios.data = [{"id": 1}, {"id": 2}]
        chain_desafios = MagicMock()
        chain_desafios.execute.return_value = result_desafios
        for m in ("table", "select", "eq"):
            getattr(chain_desafios, m).return_value = chain_desafios

        result_registros = MagicMock()
        result_registros.data = [
            {"coach": "Ana Albertim", "total_pontos": 20},
            {"coach": "Ana Albertim", "total_pontos": 10},
        ]
        chain_registros = MagicMock()
        chain_registros.execute.return_value = result_registros
        for m in ("table", "select", "in_"):
            getattr(chain_registros, m).return_value = chain_registros

        client.table.side_effect = [chain_desafios, chain_registros]

        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.get_tipo_coach_totals("desafios")
        assert result == {"Ana Albertim": 30}

    def test_sem_desafio_contabilizavel_retorna_vazio(self):
        client = MagicMock()
        result_desafios = MagicMock()
        result_desafios.data = []
        chain_desafios = MagicMock()
        chain_desafios.execute.return_value = result_desafios
        for m in ("table", "select", "eq"):
            getattr(chain_desafios, m).return_value = chain_desafios
        client.table.return_value = chain_desafios

        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.get_tipo_coach_totals("desafios")
        assert result == {}


class TestGetTipoCoachTotalsDesafiosComData:

    def test_delega_para_get_period_desafio_coach_totals(self):
        from datetime import date
        inicio, fim = date(2026, 5, 1), date(2026, 6, 30)
        with patch("supabase_client.get_period_desafio_coach_totals",
                   return_value={"Ana Albertim": 30}) as mock_period:
            result = supabase_client.get_tipo_coach_totals("desafios", inicio, fim)
        mock_period.assert_called_once_with(inicio, fim)
        assert result == {"Ana Albertim": 30}
```

Append to `backend/tests/test_period_totals_floor.py` (new class at the end of the file):

```python
def _mock_sequential_client(desafios_rows, registros_rows):
    result_desafios = MagicMock()
    result_desafios.data = desafios_rows
    chain_desafios = MagicMock()
    chain_desafios.execute.return_value = result_desafios
    for m in ("table", "select", "gte", "lte", "eq"):
        getattr(chain_desafios, m).return_value = chain_desafios

    result_registros = MagicMock()
    result_registros.data = registros_rows
    chain_registros = MagicMock()
    chain_registros.execute.return_value = result_registros
    for m in ("table", "select", "in_"):
        getattr(chain_registros, m).return_value = chain_registros

    client = MagicMock()
    client.table.side_effect = [chain_desafios, chain_registros]
    return client


class TestGetPeriodDesafioCoachTotals:

    def test_soma_pontos_de_coach_dos_desafios_no_periodo(self):
        desafios_rows = [{"id": 1}]
        registros_rows = [
            {"coach": "Ana Albertim", "total_pontos": 20},
            {"coach": "Ana Albertim", "total_pontos": 10},
            {"coach": "Gustavo Imhof", "total_pontos": 10},
        ]
        with patch("supabase_client._get_client",
                   return_value=_mock_sequential_client(desafios_rows, registros_rows)):
            result = supabase_client.get_period_desafio_coach_totals(INICIO, FIM)
        assert result == {"Ana Albertim": 30, "Gustavo Imhof": 10}

    def test_sem_desafio_no_periodo_retorna_vazio(self):
        with patch("supabase_client._get_client",
                   return_value=_mock_sequential_client([], [])):
            result = supabase_client.get_period_desafio_coach_totals(INICIO, FIM)
        assert result == {}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && python -m pytest tests/test_tipo_filter_breakdown.py tests/test_period_totals_floor.py -v`
Expected: FAIL — `get_tipo_coach_totals("desafios")` currently returns `{}` unconditionally (assertion mismatch), and `AttributeError: module 'supabase_client' has no attribute 'get_period_desafio_coach_totals'`.

- [ ] **Step 3: Implement**

In `backend/supabase_client.py`, add `get_period_desafio_coach_totals` right after `get_period_desafio_totals`:

```python
def get_period_desafio_coach_totals(inicio: date, fim: date) -> dict[str, int]:
    """
    Sum desafio points per coach for desafios within the period [inicio, fim].
    Only includes desafios with contabilizar_pontos=true.
    Returns dict[coach_name, total_pontos].
    """
    client = _get_client()

    desafios_query = (
        client.table(TABLE_DESAFIOS)
        .select("id")
        .gte("data", inicio.isoformat())
        .lte("data", fim.isoformat())
        .eq("contabilizar_pontos", True)
    )
    desafios = desafios_query.execute().data
    desafio_ids = [d["id"] for d in desafios]

    if not desafio_ids:
        return {}

    registros_query = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .select("coach, total_pontos")
        .in_("desafio_id", desafio_ids)
    )
    registros = registros_query.execute().data

    totals = {}
    for registro in registros:
        coach = registro["coach"]
        totals[coach] = totals.get(coach, 0) + registro["total_pontos"]

    return totals
```

Replace the entire `get_tipo_coach_totals` function (currently the `if tipo == "desafios": return {}` short-circuit at the top, followed by the `pagante`/`pro_bono` branches) with:

```python
def get_tipo_coach_totals(
    tipo: str,
    inicio: "date | None" = None,
    fim: "date | None" = None,
) -> dict[str, int]:
    if tipo == "desafios":
        if inicio and fim:
            return get_period_desafio_coach_totals(inicio, fim)
        client = _get_client()
        desafios = (
            client.table(TABLE_DESAFIOS)
            .select("id")
            .eq("contabilizar_pontos", True)
            .execute()
            .data
        )
        desafio_ids = [d["id"] for d in desafios]
        if not desafio_ids:
            return {}
        registros = (
            client.table(TABLE_DESAFIO_REGISTROS_COACH)
            .select("coach, total_pontos")
            .in_("desafio_id", desafio_ids)
            .execute()
            .data
        )
        totals: dict[str, int] = {}
        for r in registros:
            totals[r["coach"]] = totals.get(r["coach"], 0) + r["total_pontos"]
        return totals

    client = _get_client()

    # Without date filter: read breakdown columns from TABLE_TOTAIS_COACH
    if not (inicio and fim):
        if tipo == "pagante":
            col = "total_pagante"
        elif tipo == "pro_bono":
            col = "total_pro_bono"
        else:
            raise ValueError(f"tipo inválido para totais por tipo: {tipo!r}")
        rows = (
            client.table(TABLE_TOTAIS_COACH)
            .select(f"coach, {col}")
            .execute()
            .data
        )
        return {r["coach"]: r[col] for r in rows if (r.get(col) or 0) > 0}

    # With date filter: sum from TABLE_REGISTROS (period-based, existing behavior)
    query = (
        client.table(TABLE_REGISTROS)
        .select("coach, pontos_coach, modalidade")
        .eq("status_coach", "contabilizado")
        .gte("data_registro", inicio.isoformat())
        .lte("data_registro", fim.isoformat())
    )
    records = query.execute().data

    is_pro_bono = tipo == "pro_bono"
    group_raw: dict[str, int] = {}
    totals: dict[str, int] = {}
    for rec in records:
        rec_is_pro_bono = rec.get("modalidade", "") == "Pro-bono"
        if is_pro_bono != rec_is_pro_bono:
            continue
        coach = rec.get("coach")
        if not coach:
            continue
        p = rec["pontos_coach"]
        if p == config.POINTS_PER_RECORD_IN_BATCH:
            group_raw[coach] = group_raw.get(coach, 0) + p
        else:
            totals[coach] = totals.get(coach, 0) + p

    for coach, g in group_raw.items():
        complete = (g // config.POINTS_PER_BATCH_GROUP) * config.POINTS_PER_BATCH_GROUP
        if complete:
            totals[coach] = totals.get(coach, 0) + complete
    return totals
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && python -m pytest tests/test_tipo_filter_breakdown.py tests/test_period_totals_floor.py -v`
Expected: PASS (all tests green, including the pre-existing ones in both files)

- [ ] **Step 5: Run the full backend suite to catch regressions**

Run: `cd backend && python -m pytest -v`
Expected: PASS (all tests, including Task 2/3 additions)

- [ ] **Step 6: Commit**

```bash
git add backend/supabase_client.py backend/tests/test_tipo_filter_breakdown.py backend/tests/test_period_totals_floor.py
git commit -m "feat: get_tipo_coach_totals(desafios) e get_period_desafio_coach_totals lêem dados reais"
```

---

### Task 5: `routers/desafio_import.py` — persistir pontos de coach no preview/confirmar

**Files:**
- Modify: `backend/routers/desafio_import.py`
- Create: `backend/tests/test_desafio_import_router.py`

**Interfaces:**
- Consumes: `desafio_import_engine.processar_importacao(..., coach_alias_map)` (Task 2); `supabase_client.get_coach_alias_map()` (existing), `create_desafio_registro_coach`/`get_desafio_registro_coach_by_coach`/`update_desafio_registro_coach_pontos`/`add_delta_to_coach_total` (Task 3).
- Produces: `preview()` response gains `pontos_por_coach`/`participacoes_por_coach`; `confirmar()` persists `desafio_registros_coach` rows and coach deltas.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_desafio_import_router.py`:

```python
import sys, os, io, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.desafio_import import preview, confirmar

MAPPING = {
    "clan": "clã",
    "nome": "nome",
    "validado": "validado",
    "submitted_at": "data",
    "token": "token",
}

CSV_CONTENT = (
    "clã,nome,validado,data,token\n"
    "1,Ana Albertim,Sim,20/05/2026 10:00:00,T1\n"
    "1,Vini Marini,Sim,21/05/2026 10:00:00,T2\n"
).encode("utf-8")

CSV_CONTENT_SINGLE = (
    "clã,nome,validado,data,token\n"
    "1,Ana Albertim,Sim,20/05/2026 10:00:00,T1\n"
).encode("utf-8")


class _FakeUploadFile:
    def __init__(self, content: bytes):
        self.file = io.BytesIO(content)


def _config(desafio_id=None):
    return json.dumps({
        "nome": "Desafio Teste",
        "desafio_id": desafio_id,
        "data_inicio": "2026-05-11",
        "data_fim": "2026-06-30",
        "pontos_por_participacao": 10,
    })


class TestPreviewIncluiCoach:

    def test_preview_retorna_pontos_e_participacoes_por_coach(self):
        with patch("google_sheets_client.fetch_ranking", return_value=[{"clan": "CLÃ 1"}]), \
             patch("supabase_client.get_tokens_importados", return_value=set()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}):
            result = preview(
                file=_FakeUploadFile(CSV_CONTENT),
                mapping=json.dumps(MAPPING),
                config=_config(),
            )
        assert result["pontos_por_coach"] == {"Ana Albertim": 10, "Vinicius Marini": 10}
        assert result["participacoes_por_coach"] == {"Ana Albertim": 1, "Vinicius Marini": 1}


class TestConfirmarPersisteRegistrosDeCoach:

    def test_cria_registro_de_coach_novo_e_soma_delta(self):
        desafio_criado = {"id": 42, "nome": "Desafio Teste", "origem": "csv_import"}
        campos = [
            {"id": 1, "nome": "Participações Validadas", "tipo": "texto", "ordem": 0},
            {"id": 2, "nome": "Pontuação", "tipo": "pontuacao", "ordem": 1},
        ]
        with patch("google_sheets_client.fetch_ranking", return_value=[{"clan": "CLÃ 1"}]), \
             patch("supabase_client.get_tokens_importados", return_value=set()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.create_desafio", return_value=desafio_criado), \
             patch("supabase_client.insert_desafio_campos", return_value=campos), \
             patch("supabase_client.insert_desafio_importacao_linhas", return_value=[]), \
             patch("supabase_client.get_desafio_registro_by_clan", return_value=None), \
             patch("supabase_client.create_desafio_registro", return_value={}), \
             patch("supabase_client.add_delta_to_clan_total", return_value={}), \
             patch("supabase_client.get_desafio_registro_coach_by_coach", return_value=None), \
             patch("supabase_client.create_desafio_registro_coach", return_value={}) as mock_create_coach, \
             patch("supabase_client.add_delta_to_coach_total", return_value={}) as mock_delta_coach, \
             patch("supabase_client.list_desafio_campos", return_value=campos), \
             patch("supabase_client.list_desafio_registros", return_value=[]), \
             patch("supabase_client.get_desafio", return_value=desafio_criado):
            confirmar(
                file=_FakeUploadFile(CSV_CONTENT),
                mapping=json.dumps(MAPPING),
                config=_config(),
            )

        mock_create_coach.assert_any_call(42, "Ana Albertim", {"1": "1", "2": 10}, 10)
        mock_create_coach.assert_any_call(42, "Vinicius Marini", {"1": "1", "2": 10}, 10)
        mock_delta_coach.assert_any_call("Ana Albertim", 10)
        mock_delta_coach.assert_any_call("Vinicius Marini", 10)

    def test_atualiza_registro_de_coach_existente_e_aplica_delta(self):
        desafio_existente = {"id": 42, "nome": "Desafio Teste", "origem": "csv_import"}
        campos = [
            {"id": 1, "nome": "Participações Validadas", "tipo": "texto", "ordem": 0},
            {"id": 2, "nome": "Pontuação", "tipo": "pontuacao", "ordem": 1},
        ]
        existente_coach = {"id": 7, "coach": "Ana Albertim", "valores": {"1": "0", "2": 0}, "total_pontos": 0}
        with patch("google_sheets_client.fetch_ranking", return_value=[{"clan": "CLÃ 1"}]), \
             patch("supabase_client.get_tokens_importados", return_value=set()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_desafio", return_value=desafio_existente), \
             patch("supabase_client.update_desafio_periodo_e_pontos", return_value=None), \
             patch("supabase_client.list_desafio_campos", return_value=campos), \
             patch("supabase_client.insert_desafio_importacao_linhas", return_value=[]), \
             patch("supabase_client.get_desafio_registro_by_clan", return_value=None), \
             patch("supabase_client.create_desafio_registro", return_value={}), \
             patch("supabase_client.add_delta_to_clan_total", return_value={}), \
             patch("supabase_client.get_desafio_registro_coach_by_coach", return_value=existente_coach), \
             patch("supabase_client.update_desafio_registro_coach_pontos", return_value={}) as mock_update_coach, \
             patch("supabase_client.add_delta_to_coach_total", return_value={}) as mock_delta_coach, \
             patch("supabase_client.list_desafio_registros", return_value=[]):
            confirmar(
                file=_FakeUploadFile(CSV_CONTENT_SINGLE),
                mapping=json.dumps(MAPPING),
                config=_config(desafio_id=42),
            )

        mock_update_coach.assert_any_call(7, {"1": "1", "2": 10}, 10)
        mock_delta_coach.assert_any_call("Ana Albertim", 10)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && python -m pytest tests/test_desafio_import_router.py -v`
Expected: FAIL — `preview()`/`confirmar()` calls `desafio_import_engine.processar_importacao` without `coach_alias_map`, raising `TypeError: processar_importacao() missing 1 required positional argument: 'coach_alias_map'`.

- [ ] **Step 3: Implement**

In `backend/routers/desafio_import.py`, replace `_processar`:

```python
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
        coach_alias_map=supabase_client.get_coach_alias_map(),
    )
    return result, config
```

Replace `preview`:

```python
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
        "pontos_por_coach": result.pontos_por_coach,
        "participacoes_por_coach": result.participacoes_por_coach,
        "avisos": result.avisos,
        "total_linhas_contabilizadas": sum(result.participacoes_por_clan.values()),
    }
```

In `confirmar`, insert this block right after the existing clan loop (`for clan, participacoes in result.participacoes_por_clan.items(): ...`) and before `campos_atualizados = supabase_client.list_desafio_campos(desafio["id"])`:

```python
    for coach, participacoes in result.participacoes_por_coach.items():
        pontos = result.pontos_por_coach[coach]
        valores = {str(campo_participacoes["id"]): str(participacoes), str(campo_pontuacao["id"]): pontos}

        existente_coach = supabase_client.get_desafio_registro_coach_by_coach(desafio["id"], coach)
        if existente_coach:
            novo_total = points_engine.calculate_desafio_pontos(campos, valores)
            delta = novo_total - existente_coach["total_pontos"]
            supabase_client.update_desafio_registro_coach_pontos(existente_coach["id"], valores, novo_total)
            if delta != 0:
                supabase_client.add_delta_to_coach_total(coach, delta)
        else:
            supabase_client.create_desafio_registro_coach(desafio["id"], coach, valores, pontos)
            supabase_client.add_delta_to_coach_total(coach, pontos)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && python -m pytest tests/test_desafio_import_router.py -v`
Expected: PASS (all tests green)

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/desafio_import.py backend/tests/test_desafio_import_router.py
git commit -m "feat: preview/confirmar de importação de desafio persistem pontos por coach"
```

---

### Task 6: `routers/contabilidade.py` — `historico()` mescla pontos de desafio no coach

**Files:**
- Modify: `backend/routers/contabilidade.py`
- Create: `backend/tests/test_historico_merge_coach_desafio.py`

**Interfaces:**
- Consumes: `supabase_client.get_period_desafio_coach_totals` (Task 4).
- Produces: `historico()` response `coaches` field now includes desafio points for the period, mirroring `clans`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_historico_merge_coach_desafio.py`:

```python
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.contabilidade import historico


class TestHistoricoMergeCoachDesafio:

    def test_merge_pontos_desafio_no_total_do_coach(self):
        with patch("supabase_client.get_period_clan_totals", return_value={"CLÃ 1": 100}), \
             patch("supabase_client.get_period_desafio_totals", return_value={"CLÃ 1": 20}), \
             patch("supabase_client.get_period_coach_totals", return_value={"Ana Albertim": 50}), \
             patch("supabase_client.get_period_desafio_coach_totals",
                   return_value={"Ana Albertim": 10, "Gustavo Imhof": 5}):
            resultado = asyncio.run(historico(inicio="2026-05-01", fim="2026-06-30"))

        assert resultado.clans == {"CLÃ 1": 120}
        assert resultado.coaches == {"Ana Albertim": 60, "Gustavo Imhof": 5}
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd backend && python -m pytest tests/test_historico_merge_coach_desafio.py -v`
Expected: FAIL — `AttributeError` on `supabase_client.get_period_desafio_coach_totals` not being consumed (mock never called is fine, but the actual assertion `resultado.coaches == {"Ana Albertim": 60, "Gustavo Imhof": 5}` fails because current code returns `{"Ana Albertim": 50}` — the unmerged raw value).

- [ ] **Step 3: Implement**

In `backend/routers/contabilidade.py`, inside `historico()`, replace:

```python
        # Get period totals
        clan_totals = supabase_client.get_period_clan_totals(inicio_date, fim_date)
        desafio_totals = supabase_client.get_period_desafio_totals(inicio_date, fim_date)
        coach_totals = supabase_client.get_period_coach_totals(inicio_date, fim_date)

        # Merge clan points + desafio points
        all_clans = set(clan_totals.keys()) | set(desafio_totals.keys())
        merged_clans = {}
        for clan in all_clans:
            merged_clans[clan] = clan_totals.get(clan, 0) + desafio_totals.get(clan, 0)

        return HistoricoResponse(clans=merged_clans, coaches=coach_totals)
```

with:

```python
        # Get period totals
        clan_totals = supabase_client.get_period_clan_totals(inicio_date, fim_date)
        desafio_totals = supabase_client.get_period_desafio_totals(inicio_date, fim_date)
        coach_totals = supabase_client.get_period_coach_totals(inicio_date, fim_date)
        desafio_coach_totals = supabase_client.get_period_desafio_coach_totals(inicio_date, fim_date)

        # Merge clan points + desafio points
        all_clans = set(clan_totals.keys()) | set(desafio_totals.keys())
        merged_clans = {}
        for clan in all_clans:
            merged_clans[clan] = clan_totals.get(clan, 0) + desafio_totals.get(clan, 0)

        # Merge coach points + desafio points
        all_coaches = set(coach_totals.keys()) | set(desafio_coach_totals.keys())
        merged_coaches = {}
        for coach in all_coaches:
            merged_coaches[coach] = coach_totals.get(coach, 0) + desafio_coach_totals.get(coach, 0)

        return HistoricoResponse(clans=merged_clans, coaches=merged_coaches)
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd backend && python -m pytest tests/test_historico_merge_coach_desafio.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/contabilidade.py backend/tests/test_historico_merge_coach_desafio.py
git commit -m "feat: historico mescla pontos de desafio no total por coach"
```

---

### Task 7: `routers/contabilidade.py` — fusão de alias propaga para dados de desafio

**Files:**
- Modify: `backend/supabase_client.py`
- Modify: `backend/routers/contabilidade.py`
- Modify: `backend/tests/test_reprocessar_coaches.py`

**Interfaces:**
- Produces: `supabase_client.get_all_desafio_coach_names() -> set[str]`; `supabase_client.update_desafio_importacao_linhas_coach(old_coach, new_coach) -> int`; `supabase_client.merge_desafio_registros_coach(raw_coach, canonical) -> int`; `supabase_client.get_desafio_coach_total(coach) -> int`. `reprocessar_coaches()` now also fixes `desafio_importacao_linhas`/`desafio_registros_coach` and includes desafio points in `totais_recalculados`.

This is the trickiest task: `desafio_registros_coach` has `UNIQUE(desafio_id, coach)`. Renaming a raw coach to a canonical that **already** has a row for the same `desafio_id` would violate that constraint — so the merge must sum the colliding rows instead of blindly renaming.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_desafio_registros_coach.py` (new classes at the end of the file):

```python
class TestGetAllDesafioCoachNames:

    def test_retorna_nomes_distintos_ignorando_nulos(self):
        rows = [{"coach": "Ana Albertim"}, {"coach": "Ana Albertim"}, {"coach": None}]
        with patch("supabase_client._get_client", return_value=_mock_client(rows)):
            result = supabase_client.get_all_desafio_coach_names()
        assert result == {"Ana Albertim"}


class TestUpdateDesafioImportacaoLinhasCoach:

    def test_reescreve_coach_e_retorna_quantidade(self):
        with patch("supabase_client._get_client", return_value=_mock_client([{"id": 1}, {"id": 2}])):
            result = supabase_client.update_desafio_importacao_linhas_coach("Vini Marini", "Vinicius Marini")
        assert result == 2


class TestGetDesafioCoachTotal:

    def test_soma_total_pontos_de_todos_os_desafios_do_coach(self):
        rows = [{"total_pontos": 10}, {"total_pontos": 15}]
        with patch("supabase_client._get_client", return_value=_mock_client(rows)):
            result = supabase_client.get_desafio_coach_total("Vinicius Marini")
        assert result == 25

    def test_sem_registros_retorna_zero(self):
        with patch("supabase_client._get_client", return_value=_mock_client([])):
            result = supabase_client.get_desafio_coach_total("Ninguem")
        assert result == 0


class TestMergeDesafioRegistrosCoach:

    def _mock_merge_client(self, raw_rows, canonical_rows):
        result_raw = MagicMock()
        result_raw.data = raw_rows
        chain_raw = MagicMock()
        chain_raw.execute.return_value = result_raw
        for m in ("table", "select", "eq"):
            getattr(chain_raw, m).return_value = chain_raw

        result_canonical = MagicMock()
        result_canonical.data = canonical_rows
        chain_canonical = MagicMock()
        chain_canonical.execute.return_value = result_canonical
        for m in ("table", "select", "eq"):
            getattr(chain_canonical, m).return_value = chain_canonical

        write_chain = MagicMock()
        write_result = MagicMock()
        write_result.data = []
        write_chain.execute.return_value = write_result
        for m in ("table", "update", "delete", "eq"):
            getattr(write_chain, m).return_value = write_chain

        client = MagicMock()
        client.table.side_effect = [chain_raw, chain_canonical] + [write_chain] * 10
        return client, write_chain

    def test_sem_linhas_do_raw_coach_nao_faz_nada(self):
        client, _ = self._mock_merge_client([], [])
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.merge_desafio_registros_coach("Vini Marini", "Vinicius Marini")
        assert result == 0

    def test_desafio_sem_conflito_so_renomeia(self):
        raw_rows = [{"id": 1, "desafio_id": 100, "coach": "Vini Marini",
                     "valores": {"1": "1", "2": 10}, "total_pontos": 10}]
        client, write_chain = self._mock_merge_client(raw_rows, [])
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.merge_desafio_registros_coach("Vini Marini", "Vinicius Marini")
        assert result == 1
        write_chain.update.assert_any_call({"coach": "Vinicius Marini"})

    def test_desafio_com_conflito_soma_e_apaga_linha_antiga(self):
        raw_rows = [{"id": 1, "desafio_id": 100, "coach": "Vini Marini",
                     "valores": {"1": "1", "2": 10}, "total_pontos": 10}]
        canonical_rows = [{"id": 2, "desafio_id": 100, "coach": "Vinicius Marini",
                            "valores": {"1": "2", "2": 20}, "total_pontos": 20}]
        client, write_chain = self._mock_merge_client(raw_rows, canonical_rows)
        with patch("supabase_client._get_client", return_value=client):
            result = supabase_client.merge_desafio_registros_coach("Vini Marini", "Vinicius Marini")
        assert result == 1
        write_chain.update.assert_any_call({"valores": {"1": "3", "2": 30}, "total_pontos": 30})
        write_chain.delete.assert_called_once()
```

Replace `backend/tests/test_reprocessar_coaches.py` entirely with:

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
             patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
             patch("supabase_client.update_registros_coach", return_value=1) as mock_update, \
             patch("supabase_client.update_desafio_importacao_linhas_coach", return_value=0), \
             patch("supabase_client.merge_desafio_registros_coach", return_value=0), \
             patch("supabase_client.get_desafio_coach_total", return_value=0), \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert, \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[
                 {"coach": "Vinicius Marini", "total_pontos": 40,
                  "total_pagante": 30, "total_pro_bono": 10, "pessoas_em_espera": 0},
             ]):
            resultado = reprocessar_coaches()

        mock_update.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_delete.assert_called_once_with("Vini Marini")
        mock_upsert.assert_any_call(
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
             patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
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
             patch("supabase_client.get_all_desafio_coach_names", return_value=set()), \
             patch("supabase_client.update_registros_coach"), \
             patch("supabase_client.delete_coach_total"), \
             patch("supabase_client.upsert_coach_total"):
            resultado = reprocessar_coaches()

        assert len(resultado.avisos) == 1
        assert "A" in resultado.avisos[0] and "B" in resultado.avisos[0] and "C" in resultado.avisos[0]

    def test_funde_alias_de_coach_que_so_existe_em_desafio(self):
        """Coach que nunca apareceu em pontos_ultimate_registros_contabilizados
        (só tem pontos de desafio CSV) ainda deve ser fundido pela reprocessagem."""
        with patch("supabase_client.get_coach_alias_map",
                    return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.list_all_registros", return_value=[]), \
             patch("supabase_client.get_all_desafio_coach_names", return_value={"Vini Marini"}), \
             patch("supabase_client.update_registros_coach", return_value=0), \
             patch("supabase_client.delete_coach_total") as mock_delete, \
             patch("supabase_client.update_desafio_importacao_linhas_coach", return_value=2) as mock_update_linhas, \
             patch("supabase_client.merge_desafio_registros_coach", return_value=1) as mock_merge, \
             patch("supabase_client.get_desafio_coach_total", return_value=25) as mock_desafio_total, \
             patch("supabase_client.get_pending_group_records_by_coach", return_value=[]), \
             patch("supabase_client.get_coach_carry_over", return_value=0), \
             patch("supabase_client.list_coach_totals", return_value=[
                 {"coach": "Vinicius Marini", "total_pontos": 25,
                  "total_pagante": 0, "total_pro_bono": 0, "pessoas_em_espera": 0},
             ]), \
             patch("supabase_client.upsert_coach_total", return_value={}) as mock_upsert:
            resultado = reprocessar_coaches()

        mock_update_linhas.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_merge.assert_called_once_with("Vini Marini", "Vinicius Marini")
        mock_desafio_total.assert_called_once_with("Vinicius Marini")
        mock_delete.assert_called_once_with("Vini Marini")
        mock_upsert.assert_any_call(
            "Vinicius Marini", 25,
            pessoas_em_espera=0, total_pagante=0, total_pro_bono=0,
        )
        assert resultado.coaches_afetados == ["Vinicius Marini"]
        assert resultado.totais_recalculados == {"Vinicius Marini": 25}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && python -m pytest tests/test_desafio_registros_coach.py tests/test_reprocessar_coaches.py -v`
Expected: FAIL — `AttributeError: module 'supabase_client' has no attribute 'get_all_desafio_coach_names'` (and similarly for the other three new functions); the reprocessar_coaches tests fail the same way since the router will call them once implemented, or fail on `totais_recalculados` mismatch once mocks are in place but the router doesn't yet call them.

- [ ] **Step 3: Implement — new `supabase_client.py` functions**

Add these four functions at the end of the `# --- Desafio Registros Coach ---` section added in Task 3 (after `add_delta_to_coach_total`):

```python
def get_all_desafio_coach_names() -> set[str]:
    """Retorna o conjunto de nomes distintos de coach em desafio_registros_coach."""
    client = _get_client()
    result = client.table(TABLE_DESAFIO_REGISTROS_COACH).select("coach").execute()
    return {row["coach"] for row in result.data if row.get("coach")}


def update_desafio_importacao_linhas_coach(old_coach: str, new_coach: str) -> int:
    """Reescreve o campo coach de old_coach para new_coach em desafio_importacao_linhas.
    Retorna a quantidade de linhas atualizadas."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_IMPORTACAO_LINHAS)
        .update({"coach": new_coach})
        .eq("coach", old_coach)
        .execute()
    )
    return len(result.data)


def get_desafio_coach_total(coach: str) -> int:
    """Soma total_pontos de todos os registros de desafio de um coach (todos os desafios)."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH)
        .select("total_pontos")
        .eq("coach", coach)
        .execute()
    )
    return sum(r["total_pontos"] for r in result.data)


def _soma_valor_desafio(existente_valor, raw_valor):
    total = int(existente_valor) + int(raw_valor)
    return str(total) if isinstance(existente_valor, str) else total


def merge_desafio_registros_coach(raw_coach: str, canonical: str) -> int:
    """Funde os registros de desafio de raw_coach no canônico. Se o canônico já
    tiver um registro no mesmo desafio (colisão de UNIQUE(desafio_id, coach)),
    soma valores/total_pontos e apaga a linha antiga; senão, só renomeia o
    coach da linha. Retorna a quantidade de linhas de raw_coach processadas."""
    client = _get_client()
    raw_rows = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH).select("*").eq("coach", raw_coach).execute().data
    )
    if not raw_rows:
        return 0

    canonical_rows = (
        client.table(TABLE_DESAFIO_REGISTROS_COACH).select("*").eq("coach", canonical).execute().data
    )
    canonical_by_desafio = {r["desafio_id"]: r for r in canonical_rows}

    for raw_row in raw_rows:
        existente = canonical_by_desafio.get(raw_row["desafio_id"])
        if existente:
            valores_merged = {
                campo_id: _soma_valor_desafio(valor, raw_row["valores"].get(campo_id, 0))
                for campo_id, valor in existente["valores"].items()
            }
            novo_total = existente["total_pontos"] + raw_row["total_pontos"]
            client.table(TABLE_DESAFIO_REGISTROS_COACH).update(
                {"valores": valores_merged, "total_pontos": novo_total}
            ).eq("id", existente["id"]).execute()
            client.table(TABLE_DESAFIO_REGISTROS_COACH).delete().eq("id", raw_row["id"]).execute()
        else:
            client.table(TABLE_DESAFIO_REGISTROS_COACH).update(
                {"coach": canonical}
            ).eq("id", raw_row["id"]).execute()

    return len(raw_rows)
```

- [ ] **Step 4: Implement — wire propagation into `reprocessar_coaches()`**

In `backend/routers/contabilidade.py`, inside `reprocessar_coaches()`, replace:

```python
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
```

with:

```python
        all_regs = supabase_client.list_all_registros()
        raw_coaches = {r["coach"] for r in all_regs if r.get("coach")}
        raw_coaches |= supabase_client.get_all_desafio_coach_names()

        registros_atualizados = 0
        coaches_afetados: set[str] = set()
        for raw_coach in raw_coaches:
            canonical = coach_identity.resolve_coach(raw_coach, alias_map)
            if canonical != raw_coach:
                registros_atualizados += supabase_client.update_registros_coach(raw_coach, canonical)
                supabase_client.update_desafio_importacao_linhas_coach(raw_coach, canonical)
                supabase_client.merge_desafio_registros_coach(raw_coach, canonical)
                coaches_afetados.add(canonical)
                supabase_client.delete_coach_total(raw_coach)
```

Then, inside the `for canonical in coaches_afetados:` recompute loop, replace:

```python
            total_pagante = ci_pts + group_pts
            total_pontos = total_pagante + pb_pts
```

with:

```python
            desafio_pts = supabase_client.get_desafio_coach_total(canonical)
            total_pagante = ci_pts + group_pts
            total_pontos = total_pagante + pb_pts + desafio_pts
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd backend && python -m pytest tests/test_desafio_registros_coach.py tests/test_reprocessar_coaches.py -v`
Expected: PASS (all tests green)

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/supabase_client.py backend/routers/contabilidade.py backend/tests/test_desafio_registros_coach.py backend/tests/test_reprocessar_coaches.py
git commit -m "feat: fusão de alias de coach propaga para desafio_importacao_linhas e desafio_registros_coach"
```

---

### Task 8: `routers/desafios.py` — `excluir_desafio` desconta pontos de coach

**Files:**
- Modify: `backend/routers/desafios.py`
- Create: `backend/tests/test_excluir_desafio_coach.py`

**Interfaces:**
- Consumes: `supabase_client.list_desafio_registros_coach`, `add_delta_to_coach_total` (Task 3).
- Produces: `excluir_desafio(desafio_id)` now also reverts coach totals for any `desafio_registros_coach` rows before deleting the desafio.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_excluir_desafio_coach.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.desafios import excluir_desafio


class TestExcluirDesafioDescontaCoach:

    def test_desconta_pontos_de_coach_ao_excluir(self):
        desafio = {"id": 42, "nome": "Desafio G", "contabilizar_pontos": True, "origem": "csv_import"}
        registros_clan = [{"clan": "CLÃ 1", "total_pontos": 20}]
        registros_coach = [
            {"coach": "Ana Albertim", "total_pontos": 10},
            {"coach": "Gustavo Imhof", "total_pontos": 10},
        ]
        with patch("supabase_client.get_desafio", return_value=desafio), \
             patch("supabase_client.list_desafio_registros", return_value=registros_clan), \
             patch("supabase_client.add_delta_to_clan_total") as mock_delta_clan, \
             patch("supabase_client.list_desafio_registros_coach", return_value=registros_coach), \
             patch("supabase_client.add_delta_to_coach_total") as mock_delta_coach, \
             patch("supabase_client.delete_desafio", return_value=desafio) as mock_delete:
            resultado = excluir_desafio(42)

        mock_delta_clan.assert_called_once_with("CLÃ 1", -20)
        mock_delta_coach.assert_any_call("Ana Albertim", -10)
        mock_delta_coach.assert_any_call("Gustavo Imhof", -10)
        mock_delete.assert_called_once_with(42)
        assert resultado == {"mensagem": "Desafio 'Desafio G' excluído com sucesso."}

    def test_contabilizar_pontos_false_nao_desconta_nada(self):
        desafio = {"id": 42, "nome": "Desafio Manual", "contabilizar_pontos": False, "origem": "manual"}
        with patch("supabase_client.get_desafio", return_value=desafio), \
             patch("supabase_client.list_desafio_registros") as mock_list_clan, \
             patch("supabase_client.list_desafio_registros_coach") as mock_list_coach, \
             patch("supabase_client.add_delta_to_clan_total") as mock_delta_clan, \
             patch("supabase_client.add_delta_to_coach_total") as mock_delta_coach, \
             patch("supabase_client.delete_desafio", return_value=desafio):
            excluir_desafio(42)

        mock_list_clan.assert_not_called()
        mock_list_coach.assert_not_called()
        mock_delta_clan.assert_not_called()
        mock_delta_coach.assert_not_called()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd backend && python -m pytest tests/test_excluir_desafio_coach.py -v`
Expected: FAIL — `mock_delta_coach.assert_any_call(...)` fails (`add_delta_to_coach_total` never called) since the router doesn't touch coach totals yet.

- [ ] **Step 3: Implement**

In `backend/routers/desafios.py`, replace `excluir_desafio`:

```python
@router.delete("/{desafio_id}")
def excluir_desafio(desafio_id: int):
    """Remove o desafio. Se contabilizar_pontos=true, desconta pontos dos clãs e coaches."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    if desafio["contabilizar_pontos"]:
        registros = supabase_client.list_desafio_registros(desafio_id)
        for reg in registros:
            if reg["total_pontos"] > 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], -reg["total_pontos"])

        registros_coach = supabase_client.list_desafio_registros_coach(desafio_id)
        for reg in registros_coach:
            if reg["total_pontos"] > 0:
                supabase_client.add_delta_to_coach_total(reg["coach"], -reg["total_pontos"])

    supabase_client.delete_desafio(desafio_id)
    return {"mensagem": f"Desafio '{desafio['nome']}' excluído com sucesso."}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && python -m pytest tests/test_excluir_desafio_coach.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS (all backend tests green)

- [ ] **Step 6: Commit**

```bash
git add backend/routers/desafios.py backend/tests/test_excluir_desafio_coach.py
git commit -m "feat: excluir_desafio desconta pontos de coach de desafios csv_import"
```

---

### Task 9: Frontend — remover placeholder "Desafios não registram pontos por coach"

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx:419-470`

**Interfaces:**
- Consumes: `HistoricoResponse`/`fetchTotaisPorTipo` (existing, unchanged types — backend now returns real data for `tipoFiltro === "desafios"` on the `coaches` field).

No frontend test harness exists in this repo (no test runner configured) — verification is `tsc` typecheck + manual read.

- [ ] **Step 1: Remove the placeholder branch**

In `frontend/src/pages/Dashboard.tsx`, replace:

```tsx
          {tipoFiltro === "desafios" ? (
            <p className="text-gray-500 text-sm italic">Desafios não registram pontos por coach.</p>
          ) : loading ? (
```

with:

```tsx
          {loading ? (
```

(No other lines in that ternary chain change — `Nenhum dado disponível.` and the ranking table branches stay exactly as they are.)

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: aba Coaches/Desafios do Dashboard mostra ranking real em vez de placeholder"
```

---

## After implementation

- Run the full backend suite once more: `cd backend && python -m pytest -v` — all green.
- **Manual step required from the user:** run `backend/migrations/007_add_desafio_registros_coach.sql` against the Supabase project (Dashboard → SQL Editor) before using the feature — nothing in this plan runs it automatically.
- Suggest a manual smoke test via the `/run` skill or `npm run dev`: import the real CSV (`Desafios Pontuais - PROD - IGT ULTIMATE| Desafios | Pontuais.csv`), confirm, and check the Dashboard's Coaches tab (both "todos" and "Desafios" filters) shows real per-coach totals.
