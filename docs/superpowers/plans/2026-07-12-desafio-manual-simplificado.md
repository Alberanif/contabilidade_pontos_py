# Simplificação do Cadastro Manual de Desafios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o sistema de "Campos" customizados do cadastro manual de desafio por um formulário único com período (`data_inicio`/`data_fim`) e uma lista direta de Clã + Pontuação, salvos de uma só vez.

**Architecture:** Reaproveita as colunas `data_inicio`/`data_fim`/`origem` de `desafios` já especificadas pela importação de CSV (sem migration nova) e a tabela `desafio_registros` existente. Cada desafio `origem='manual'` passa a ter, gerenciado internamente pelo backend, um único `desafio_campo` implícito chamado `"Pontos"` — a UI nunca mostra "Campos" para o usuário. A lógica de diff (quais registros criar/atualizar/excluir e qual delta aplicar em cada clã ao editar) é extraída para uma função pura testável em `points_engine.py`, seguindo o padrão já usado por `calculate_desafio_pontos` e `desafio_import_engine.py`.

**Tech Stack:** Backend: Python/FastAPI + Supabase (pytest para lógica pura). Frontend: React 19 + TypeScript + Tailwind (sem testes automatizados no projeto — verificação via `npm run build`).

## Global Constraints

- Nenhuma migration nova — `data_inicio`, `data_fim`, `origem` já foram especificados em `docs/superpowers/specs/2026-07-12-desafio-import-csv-design.md` (ALTER TABLE pendente de execução manual no Supabase Dashboard, compartilhado com esta feature).
- Desafios `origem='csv_import'` nunca passam pelo formulário desta feature — são editados só pelo wizard de reimportação já implementado.
- `data` (coluna legada `NOT NULL`) sempre recebe o valor de `data_fim` ao criar/editar (mesma convenção da importação CSV).
- Endpoints granulares `POST/DELETE /api/desafios/{id}/registros` continuam existindo sem alteração — só deixam de ser chamados pela UI.
- Projeto não usa `field_validator` do Pydantic para validação de negócio — segue o padrão existente de `HTTPException(status_code=400, ...)` manual dentro do handler (ver `routers/contabilidade.py:1026-1036`).

---

### Task 1: Função pura de diff de registros (`points_engine.py`)

**Files:**
- Modify: `backend/points_engine.py` (adicionar função no final do arquivo)
- Test: `backend/tests/test_desafios_logic.py` (adicionar nova classe de teste)

**Interfaces:**
- Produces: `diff_desafio_registros(old_registros: list[dict], new_registros: list[dict], old_contabilizar: bool, new_contabilizar: bool) -> dict` com chaves `to_delete: list[int]`, `to_create: list[dict]` (`{clan, pontos}`), `to_update: list[dict]` (`{id, clan, pontos}`), `clan_deltas: dict[str, int]` (só entradas com delta != 0). `old_registros` tem itens `{id, clan, total_pontos}`; `new_registros` tem itens `{clan, pontos}`.

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao final de `backend/tests/test_desafios_logic.py`:

```python
from points_engine import diff_desafio_registros


class TestDiffDesafioRegistros:

    def test_clan_novo_com_contabilizar_soma_delta(self):
        resultado = diff_desafio_registros([], [{"clan": "Clã 1", "pontos": 50}], True, True)
        assert resultado["to_create"] == [{"clan": "Clã 1", "pontos": 50}]
        assert resultado["to_delete"] == []
        assert resultado["to_update"] == []
        assert resultado["clan_deltas"] == {"Clã 1": 50}

    def test_clan_novo_sem_contabilizar_nao_gera_delta(self):
        resultado = diff_desafio_registros([], [{"clan": "Clã 1", "pontos": 50}], True, False)
        assert resultado["to_create"] == [{"clan": "Clã 1", "pontos": 50}]
        assert resultado["clan_deltas"] == {}

    def test_clan_removido_com_contabilizar_desconta(self):
        old = [{"id": 1, "clan": "Clã 1", "total_pontos": 40}]
        resultado = diff_desafio_registros(old, [], True, True)
        assert resultado["to_delete"] == [1]
        assert resultado["clan_deltas"] == {"Clã 1": -40}

    def test_clan_removido_sem_contabilizar_nao_desconta(self):
        old = [{"id": 1, "clan": "Clã 1", "total_pontos": 40}]
        resultado = diff_desafio_registros(old, [], False, True)
        assert resultado["to_delete"] == [1]
        assert resultado["clan_deltas"] == {}

    def test_clan_atualizado_true_true_aplica_delta_liquido(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, True, True)
        assert resultado["to_update"] == [{"id": 2, "clan": "Clã 1", "pontos": 50}]
        assert resultado["clan_deltas"] == {"Clã 1": 20}

    def test_clan_atualizado_true_false_desconta_total_antigo(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, True, False)
        assert resultado["clan_deltas"] == {"Clã 1": -30}

    def test_clan_atualizado_false_true_soma_total_novo(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, False, True)
        assert resultado["clan_deltas"] == {"Clã 1": 50}

    def test_clan_atualizado_false_false_sem_delta(self):
        old = [{"id": 2, "clan": "Clã 1", "total_pontos": 30}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, False, False)
        assert resultado["clan_deltas"] == {}

    def test_clan_inalterado_aparece_em_to_update_sem_delta(self):
        old = [{"id": 3, "clan": "Clã 1", "total_pontos": 50}]
        new = [{"clan": "Clã 1", "pontos": 50}]
        resultado = diff_desafio_registros(old, new, True, True)
        assert resultado["to_update"] == [{"id": 3, "clan": "Clã 1", "pontos": 50}]
        assert resultado["clan_deltas"] == {}

    def test_multiplos_clans_combinados(self):
        old = [
            {"id": 1, "clan": "Clã 1", "total_pontos": 30},
            {"id": 2, "clan": "Clã 2", "total_pontos": 20},
        ]
        new = [
            {"clan": "Clã 1", "pontos": 30},
            {"clan": "Clã 3", "pontos": 10},
        ]
        resultado = diff_desafio_registros(old, new, True, True)
        assert resultado["to_delete"] == [2]
        assert resultado["to_create"] == [{"clan": "Clã 3", "pontos": 10}]
        assert resultado["to_update"] == [{"id": 1, "clan": "Clã 1", "pontos": 30}]
        assert resultado["clan_deltas"] == {"Clã 2": -20, "Clã 3": 10}
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

Run: `cd backend && ../venv/Scripts/python.exe -m pytest tests/test_desafios_logic.py -v`
Expected: FAIL com `ImportError: cannot import name 'diff_desafio_registros'`

- [ ] **Step 3: Implementar a função**

Adicionar ao final de `backend/points_engine.py`:

```python
def diff_desafio_registros(
    old_registros: list[dict],
    new_registros: list[dict],
    old_contabilizar: bool,
    new_contabilizar: bool,
) -> dict:
    """Calcula o diff entre os registros existentes de um desafio e a nova
    lista clã→pontos enviada na edição.

    old_registros: [{'id': int, 'clan': str, 'total_pontos': int}]
    new_registros: [{'clan': str, 'pontos': int}]

    Retorna to_delete (ids a excluir), to_create ({clan, pontos}),
    to_update ({id, clan, pontos} — inclui clãs sem mudança de pontuação,
    pois o valor ainda precisa ser regravado apontando pro campo atual) e
    clan_deltas (delta líquido por clã, só entradas != 0, para aplicar em
    add_delta_to_clan_total).
    """
    old_by_clan = {r["clan"]: r for r in old_registros}
    new_by_clan = {r["clan"]: r["pontos"] for r in new_registros}

    to_delete: list[int] = []
    to_create: list[dict] = []
    to_update: list[dict] = []
    clan_deltas: dict[str, int] = {}

    for clan, old_reg in old_by_clan.items():
        if clan not in new_by_clan:
            to_delete.append(old_reg["id"])
            if old_contabilizar and old_reg["total_pontos"] != 0:
                clan_deltas[clan] = clan_deltas.get(clan, 0) - old_reg["total_pontos"]

    for clan, pontos in new_by_clan.items():
        old_reg = old_by_clan.get(clan)
        if old_reg is None:
            to_create.append({"clan": clan, "pontos": pontos})
            if new_contabilizar and pontos != 0:
                clan_deltas[clan] = clan_deltas.get(clan, 0) + pontos
        else:
            to_update.append({"id": old_reg["id"], "clan": clan, "pontos": pontos})
            if old_contabilizar and new_contabilizar:
                delta = pontos - old_reg["total_pontos"]
            elif old_contabilizar and not new_contabilizar:
                delta = -old_reg["total_pontos"]
            elif not old_contabilizar and new_contabilizar:
                delta = pontos
            else:
                delta = 0
            if delta != 0:
                clan_deltas[clan] = clan_deltas.get(clan, 0) + delta

    return {
        "to_delete": to_delete,
        "to_create": to_create,
        "to_update": to_update,
        "clan_deltas": clan_deltas,
    }
```

- [ ] **Step 4: Rodar os testes e confirmar que passam**

Run: `cd backend && ../venv/Scripts/python.exe -m pytest tests/test_desafios_logic.py -v`
Expected: PASS (todos os testes, incluindo os pré-existentes de `TestCalculateDesafioPontos`)

- [ ] **Step 5: Commit**

```bash
git add backend/points_engine.py backend/tests/test_desafios_logic.py
git commit -m "feat: diff puro de registros de desafio por clã (create/update/delete/delta)"
```

---

### Task 2: Extender `update_desafio` para aceitar período (`supabase_client.py`)

**Files:**
- Modify: `backend/supabase_client.py:384-393`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `update_desafio(desafio_id: int, nome: str, contabilizar_pontos: bool, data: date, data_inicio: date | None = None, data_fim: date | None = None) -> dict` — assinatura retrocompatível (os dois novos parâmetros são opcionais e só entram no payload quando fornecidos), usada pela Task 3.

- [ ] **Step 1: Substituir a função existente**

Em `backend/supabase_client.py`, substituir (linhas 384-393):

```python
def update_desafio(desafio_id: int, nome: str, contabilizar_pontos: bool, data: date) -> dict:
    """Atualiza nome, modo de contabilização e data de um desafio."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIOS)
        .update({"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)})
        .eq("id", desafio_id)
        .execute()
    )
    return result.data[0]
```

por:

```python
def update_desafio(
    desafio_id: int,
    nome: str,
    contabilizar_pontos: bool,
    data: date,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict:
    """Atualiza nome, modo de contabilização, data e (opcionalmente) período de um desafio."""
    client = _get_client()
    payload = {"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)}
    if data_inicio is not None:
        payload["data_inicio"] = str(data_inicio)
    if data_fim is not None:
        payload["data_fim"] = str(data_fim)
    result = (
        client.table(TABLE_DESAFIOS)
        .update(payload)
        .eq("id", desafio_id)
        .execute()
    )
    return result.data[0]
```

- [ ] **Step 2: Verificar que não há outro chamador quebrado**

Run: `cd backend && grep -rn "update_desafio(" --include=*.py .`
Expected: só aparece a definição em `supabase_client.py` e um chamador em `routers/desafios.py` (será reescrito na Task 3) — sem chamadas em `routers/desafio_import.py` (esse usa `update_desafio_periodo_e_pontos`, uma função diferente e já existente).

- [ ] **Step 3: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat: update_desafio aceita data_inicio/data_fim opcionais"
```

---

### Task 3: Reescrever o router de desafios (`routers/desafios.py`)

**Files:**
- Modify: `backend/routers/desafios.py` (arquivo inteiro)

**Interfaces:**
- Consumes: `points_engine.diff_desafio_registros(...)` (Task 1), `supabase_client.update_desafio(..., data_inicio=, data_fim=)` (Task 2), `supabase_client.create_desafio(nome, contabilizar_pontos, data, data_inicio=, data_fim=, origem=)` (já existe), `supabase_client.delete_desafio_campos(desafio_id)`, `supabase_client.list_desafio_campos`, `supabase_client.insert_desafio_campos`, `supabase_client.create_desafio_registro`, `supabase_client.update_desafio_registro_pontos`, `supabase_client.delete_desafio_registro`, `supabase_client.add_delta_to_clan_total` (todas já existem em `supabase_client.py`).
- Produces: `POST /api/desafios` e `PUT /api/desafios/{id}` com o novo contrato `{nome, contabilizar_pontos, data_inicio, data_fim, registros: [{clan, pontos}]}`, consumido pela Task 5 (frontend).

- [ ] **Step 1: Substituir o conteúdo completo do arquivo**

Substituir todo o conteúdo de `backend/routers/desafios.py` por:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any
from datetime import date

import supabase_client
import points_engine

router = APIRouter()

NOME_CAMPO_PONTOS = "Pontos"


class RegistroClanInput(BaseModel):
    clan: str
    pontos: int = Field(ge=0)


class DesafioCreate(BaseModel):
    nome: str
    contabilizar_pontos: bool = True
    data_inicio: date
    data_fim: date
    registros: list[RegistroClanInput] = []


class DesafioUpdate(BaseModel):
    nome: str
    contabilizar_pontos: bool
    data_inicio: date
    data_fim: date
    registros: list[RegistroClanInput] = []


class RegistroCreate(BaseModel):
    clan: str
    valores: dict[str, Any]


def _validar_periodo_e_registros(
    data_inicio: date, data_fim: date, registros: list[RegistroClanInput]
) -> None:
    if data_fim < data_inicio:
        raise HTTPException(
            status_code=400, detail="data_fim deve ser maior ou igual a data_inicio"
        )
    clans = [r.clan for r in registros]
    if len(clans) != len(set(clans)):
        raise HTTPException(
            status_code=400,
            detail="Um mesmo clã não pode aparecer duas vezes na lista de registros",
        )


def _ensure_campo_pontos(desafio_id: int) -> dict:
    """Garante que o desafio tenha exatamente um campo implícito 'Pontos'
    (tipo pontuacao). Se os campos atuais forem diferentes (desafio legado
    com campos customizados), apaga todos e recria o campo implícito —
    essa é a conversão permanente para o novo formato."""
    campos = supabase_client.list_desafio_campos(desafio_id)
    if len(campos) == 1 and campos[0]["nome"] == NOME_CAMPO_PONTOS and campos[0]["tipo"] == "pontuacao":
        return campos[0]
    supabase_client.delete_desafio_campos(desafio_id)
    novos = supabase_client.insert_desafio_campos(
        [{"desafio_id": desafio_id, "nome": NOME_CAMPO_PONTOS, "tipo": "pontuacao", "ordem": 0}]
    )
    return novos[0]


@router.get("")
def listar_desafios():
    """Lista todos os desafios com seus campos e contagem de registros."""
    desafios = supabase_client.list_desafios()
    all_campos = supabase_client.list_all_desafio_campos()
    registro_counts = supabase_client.count_desafio_registros_by_desafio()

    campos_by_desafio: dict[int, list[dict]] = {}
    for c in all_campos:
        campos_by_desafio.setdefault(c["desafio_id"], []).append(c)

    return [
        {
            **d,
            "campos": campos_by_desafio.get(d["id"], []),
            "total_registros": registro_counts.get(d["id"], 0),
        }
        for d in desafios
    ]


@router.post("")
def criar_desafio(body: DesafioCreate):
    """Cria um novo desafio manual com período e registros de clã/pontuação."""
    _validar_periodo_e_registros(body.data_inicio, body.data_fim, body.registros)

    desafio = supabase_client.create_desafio(
        body.nome,
        body.contabilizar_pontos,
        body.data_fim,
        data_inicio=body.data_inicio,
        data_fim=body.data_fim,
        origem="manual",
    )
    campo_pontos = _ensure_campo_pontos(desafio["id"])

    for r in body.registros:
        supabase_client.create_desafio_registro(
            desafio["id"], r.clan, {str(campo_pontos["id"]): r.pontos}, r.pontos
        )
        if body.contabilizar_pontos and r.pontos > 0:
            supabase_client.add_delta_to_clan_total(r.clan, r.pontos)

    return {**desafio, "campos": [campo_pontos], "total_registros": len(body.registros)}


@router.put("/{desafio_id}")
def editar_desafio(desafio_id: int, body: DesafioUpdate):
    """Edita nome, período, modo de contabilização e registros de clã/pontuação.

    Desafios legados com campos customizados são convertidos para o campo
    implícito único 'Pontos' ao serem salvos por aqui (ver _ensure_campo_pontos).
    """
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    _validar_periodo_e_registros(body.data_inicio, body.data_fim, body.registros)

    old_contabilizar = desafio["contabilizar_pontos"]
    new_contabilizar = body.contabilizar_pontos

    old_registros = supabase_client.list_desafio_registros(desafio_id)
    diff = points_engine.diff_desafio_registros(
        [
            {"id": r["id"], "clan": r["clan"], "total_pontos": r["total_pontos"]}
            for r in old_registros
        ],
        [{"clan": r.clan, "pontos": r.pontos} for r in body.registros],
        old_contabilizar,
        new_contabilizar,
    )

    campo_pontos = _ensure_campo_pontos(desafio_id)

    for registro_id in diff["to_delete"]:
        supabase_client.delete_desafio_registro(registro_id)

    for item in diff["to_create"]:
        supabase_client.create_desafio_registro(
            desafio_id, item["clan"], {str(campo_pontos["id"]): item["pontos"]}, item["pontos"]
        )

    for item in diff["to_update"]:
        supabase_client.update_desafio_registro_pontos(
            item["id"], {str(campo_pontos["id"]): item["pontos"]}, item["pontos"]
        )

    for clan, delta in diff["clan_deltas"].items():
        supabase_client.add_delta_to_clan_total(clan, delta)

    updated = supabase_client.update_desafio(
        desafio_id,
        body.nome,
        new_contabilizar,
        body.data_fim,
        data_inicio=body.data_inicio,
        data_fim=body.data_fim,
    )
    return {**updated, "campos": [campo_pontos], "total_registros": len(body.registros)}


@router.delete("/{desafio_id}")
def excluir_desafio(desafio_id: int):
    """Remove o desafio. Se contabilizar_pontos=true, desconta pontos dos clãs."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    if desafio["contabilizar_pontos"]:
        registros = supabase_client.list_desafio_registros(desafio_id)
        for reg in registros:
            if reg["total_pontos"] > 0:
                supabase_client.add_delta_to_clan_total(reg["clan"], -reg["total_pontos"])

    supabase_client.delete_desafio(desafio_id)
    return {"mensagem": f"Desafio '{desafio['nome']}' excluído com sucesso."}


@router.get("/{desafio_id}/registros")
def listar_registros(desafio_id: int):
    """Lista os registros de clãs de um desafio."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return supabase_client.list_desafio_registros(desafio_id)


@router.post("/{desafio_id}/registros")
def criar_registro(desafio_id: int, body: RegistroCreate):
    """Registra pontos de um clã. Soma ao total geral se contabilizar_pontos=true."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    existing = supabase_client.get_desafio_registro_by_clan(desafio_id, body.clan)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Clã '{body.clan}' já possui registro neste desafio.",
        )

    campos = supabase_client.list_desafio_campos(desafio_id)
    total_pontos = points_engine.calculate_desafio_pontos(campos, body.valores)

    registro = supabase_client.create_desafio_registro(
        desafio_id, body.clan, body.valores, total_pontos
    )

    if desafio["contabilizar_pontos"] and total_pontos > 0:
        supabase_client.add_delta_to_clan_total(body.clan, total_pontos)

    return registro


@router.delete("/{desafio_id}/registros/{registro_id}")
def excluir_registro(desafio_id: int, registro_id: int):
    """Remove registro de um clã. Desconta pontos se contabilizar_pontos=true."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")

    registro = supabase_client.get_desafio_registro_by_id(registro_id)
    if not registro or registro["desafio_id"] != desafio_id:
        raise HTTPException(status_code=404, detail="Registro não encontrado")

    if desafio["contabilizar_pontos"] and registro["total_pontos"] > 0:
        supabase_client.add_delta_to_clan_total(registro["clan"], -registro["total_pontos"])

    supabase_client.delete_desafio_registro(registro_id)
    return {"mensagem": f"Registro do clã '{registro['clan']}' excluído."}
```

- [ ] **Step 2: Rodar a suíte completa de testes do backend**

Run: `cd backend && ../venv/Scripts/python.exe -m pytest -v`
Expected: PASS em todos os testes (os 32 de `desafio_import_engine`, os de `points_engine`/`desafios_logic` incluindo os novos da Task 1, e os demais já existentes) — este router não tem teste de I/O dedicado (segue o padrão do projeto: rotas com I/O real não são unit-testadas), então a verificação aqui é "nada quebrou" + revisão manual do diff.

- [ ] **Step 3: Verificar que o app inicia sem erro de import**

Run: `cd backend && ../venv/Scripts/python.exe -c "import main"`
Expected: sem exceções (confirma que `routers/desafios.py` está sintaticamente correto e importável).

- [ ] **Step 4: Commit**

```bash
git add backend/routers/desafios.py
git commit -m "feat: cadastro manual de desafio usa período + registros clã/pontuação direto"
```

---

### Task 4: Atualizar tipos e client HTTP do frontend (`client.ts`)

**Files:**
- Modify: `frontend/src/api/client.ts:234-276`

**Interfaces:**
- Produces: `Desafio` com `data_inicio?: string`, `data_fim?: string`, `origem?: string`; `createDesafio(data: {nome, contabilizar_pontos, data_inicio, data_fim, registros: {clan: string; pontos: number}[]})`; `updateDesafio(id, data: {mesmo shape})` — consumidos pela Task 5.

- [ ] **Step 1: Atualizar a interface `Desafio`**

Em `frontend/src/api/client.ts`, substituir (linhas 234-242):

```ts
export interface Desafio {
  id: number;
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  campos: DesafioCampo[];
  total_registros: number;
  created_at: string;
}
```

por:

```ts
export interface Desafio {
  id: number;
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  data_inicio?: string;
  data_fim?: string;
  origem?: string;
  campos: DesafioCampo[];
  total_registros: number;
  created_at: string;
}
```

- [ ] **Step 2: Atualizar `createDesafio` e `updateDesafio`**

Substituir (linhas 257-276):

```ts
export function createDesafio(data: {
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  campos: { nome: string; tipo: string; ordem: number }[];
}): Promise<Desafio> {
  return request('/api/desafios', { method: 'POST', body: JSON.stringify(data) });
}

export function updateDesafio(
  id: number,
  data: {
    nome: string;
    contabilizar_pontos: boolean;
    data: string;
    campos: { id?: number; nome: string; tipo: string; ordem: number }[];
  }
): Promise<Desafio> {
  return request(`/api/desafios/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
```

por:

```ts
export interface DesafioRegistroInput {
  clan: string;
  pontos: number;
}

export function createDesafio(data: {
  nome: string;
  contabilizar_pontos: boolean;
  data_inicio: string;
  data_fim: string;
  registros: DesafioRegistroInput[];
}): Promise<Desafio> {
  return request('/api/desafios', { method: 'POST', body: JSON.stringify(data) });
}

export function updateDesafio(
  id: number,
  data: {
    nome: string;
    contabilizar_pontos: boolean;
    data_inicio: string;
    data_fim: string;
    registros: DesafioRegistroInput[];
  }
): Promise<Desafio> {
  return request(`/api/desafios/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
```

- [ ] **Step 3: Verificar compilação isolada do módulo**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: FAIL nesse ponto (esperado) — `Desafios.tsx` ainda usa o formato antigo de `campos`/`data`; será corrigido na Task 5. Confirme que os únicos erros reportados estão em `Desafios.tsx`, não em `client.ts` nem em `ImportarDesafioWizard.tsx`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: client.ts usa data_inicio/data_fim/registros no lugar de campos"
```

---

### Task 5: Reescrever a página de Desafios (`Desafios.tsx`)

**Files:**
- Modify: `frontend/src/pages/Desafios.tsx` (arquivo inteiro)

**Interfaces:**
- Consumes: `createDesafio`, `updateDesafio`, `DesafioRegistroInput`, `Desafio` (todos da Task 4); `fetchDesafios`, `deleteDesafio`, `fetchDesafioRegistros`, `fetchRanking`, `atualizarPlanilha`, `type RankingEntry`, `type DesafioRegistro` (já existentes, sem mudança de assinatura); `ImportarDesafioWizard` (sem mudança).
- Produces: nenhuma outra task depende deste arquivo.

- [ ] **Step 1: Substituir o conteúdo completo do arquivo**

Substituir todo o conteúdo de `frontend/src/pages/Desafios.tsx` por:

```tsx
import { useEffect, useState } from "react";
import {
  fetchRanking,
  atualizarPlanilha,
  fetchDesafios,
  createDesafio,
  updateDesafio,
  deleteDesafio,
  fetchDesafioRegistros,
  type RankingEntry,
  type Desafio,
  type DesafioRegistro,
} from "../api/client";
import ImportarDesafioWizard from "../components/ImportarDesafioWizard";

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  const parts = dateStr.substring(0, 10).split("-");
  if (parts.length !== 3) return dateStr;
  const [year, month, day] = parts;
  return `${day}/${month}/${year}`;
}

function formatPeriodo(d: Desafio): string {
  if (d.data_inicio && d.data_fim) {
    return `${formatDate(d.data_inicio)} - ${formatDate(d.data_fim)}`;
  }
  return formatDate(d.data);
}

type Mode = "list" | "form" | "detail" | "import";

interface RegistroForm {
  clan: string;
  pontos: string;
}

export default function Desafios() {
  const [mode, setMode] = useState<Mode>("list");
  const [desafios, setDesafios] = useState<Desafio[]>([]);
  const [selectedDesafio, setSelectedDesafio] = useState<Desafio | null>(null);
  const [registros, setRegistros] = useState<DesafioRegistro[]>([]);
  const [ranking, setRanking] = useState<RankingEntry[]>([]);

  // Form state
  const [editingDesafio, setEditingDesafio] = useState<Desafio | null>(null);
  const [formNome, setFormNome] = useState("");
  const [formContabilizar, setFormContabilizar] = useState(true);
  const [formDataInicio, setFormDataInicio] = useState("");
  const [formDataFim, setFormDataFim] = useState("");
  const [formRegistros, setFormRegistros] = useState<RegistroForm[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [updatingSheet, setUpdatingSheet] = useState(false);
  const [sheetMessage, setSheetMessage] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadDesafios = async () => {
    try {
      setLoading(true);
      const data = await fetchDesafios();
      setDesafios(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar desafios");
    } finally {
      setLoading(false);
    }
  };

  const loadRanking = async () => {
    try {
      const data = await fetchRanking();
      setRanking(data);
    } catch {
      // ranking é opcional
    }
  };

  const loadRegistros = async (desafioId: number) => {
    try {
      const data = await fetchDesafioRegistros(desafioId);
      setRegistros(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar registros");
    }
  };

  useEffect(() => {
    loadDesafios();
    loadRanking();
  }, []);

  const handleAtualizarPlanilha = async () => {
    try {
      setUpdatingSheet(true);
      setSheetMessage("");
      setError("");
      const data = await atualizarPlanilha();
      setSheetMessage(data.mensagem);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao atualizar planilha");
    } finally {
      setUpdatingSheet(false);
    }
  };

  const openCreateForm = () => {
    setEditingDesafio(null);
    setFormNome("");
    setFormContabilizar(true);
    setFormDataInicio("");
    setFormDataFim("");
    setFormRegistros([]);
    setError("");
    setSuccess("");
    setMode("form");
  };

  const openEditForm = async (desafio: Desafio) => {
    setEditingDesafio(desafio);
    setFormNome(desafio.nome);
    setFormContabilizar(desafio.contabilizar_pontos);
    setFormDataInicio(desafio.data_inicio ?? desafio.data ?? "");
    setFormDataFim(desafio.data_fim ?? desafio.data ?? "");
    setError("");
    setSuccess("");
    try {
      const data = await fetchDesafioRegistros(desafio.id);
      setFormRegistros(data.map((r) => ({ clan: r.clan, pontos: String(r.total_pontos) })));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao carregar registros do desafio");
      setFormRegistros([]);
    }
    setMode("form");
  };

  const openDetail = async (desafio: Desafio) => {
    setSelectedDesafio(desafio);
    setError("");
    setSuccess("");
    await loadRegistros(desafio.id);
    setMode("detail");
  };

  const addRegistroRow = () => {
    setFormRegistros([...formRegistros, { clan: "", pontos: "0" }]);
  };

  const removeRegistroRow = (index: number) => {
    setFormRegistros(formRegistros.filter((_, i) => i !== index));
  };

  const updateRegistroRow = (
    index: number,
    field: keyof RegistroForm,
    value: string
  ) => {
    setFormRegistros(
      formRegistros.map((r, i) => (i === index ? { ...r, [field]: value } : r))
    );
  };

  const clanOptionsFor = (index: number) => {
    const chosenElsewhere = new Set(
      formRegistros.filter((_, i) => i !== index).map((r) => r.clan)
    );
    return ranking.filter((r) => !chosenElsewhere.has(r.clan));
  };

  const handleSaveDesafio = async () => {
    if (!formNome.trim()) {
      setError("O nome do desafio é obrigatório.");
      return;
    }
    if (!formDataInicio || !formDataFim) {
      setError("O período (data início e fim) é obrigatório.");
      return;
    }
    if (formDataFim < formDataInicio) {
      setError("A data fim deve ser maior ou igual à data início.");
      return;
    }
    if (formRegistros.some((r) => !r.clan || r.pontos.trim() === "")) {
      setError("Selecione o clã e informe a pontuação em todas as linhas.");
      return;
    }
    const clansInformados = formRegistros.map((r) => r.clan);
    if (new Set(clansInformados).size !== clansInformados.length) {
      setError("Um mesmo clã não pode aparecer duas vezes.");
      return;
    }
    try {
      setSubmitting(true);
      setError("");
      const registros = formRegistros.map((r) => ({
        clan: r.clan,
        pontos: Number(r.pontos),
      }));
      if (editingDesafio) {
        await updateDesafio(editingDesafio.id, {
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          data_inicio: formDataInicio,
          data_fim: formDataFim,
          registros,
        });
        setSuccess("Desafio atualizado com sucesso.");
      } else {
        await createDesafio({
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          data_inicio: formDataInicio,
          data_fim: formDataFim,
          registros,
        });
        setSuccess("Desafio criado com sucesso.");
      }
      await loadDesafios();
      setMode("list");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao salvar desafio");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteDesafio = async (desafio: Desafio) => {
    const msg = desafio.contabilizar_pontos
      ? `Excluir o desafio "${desafio.nome}"? Os pontos dos clãs serão descontados.`
      : `Excluir o desafio "${desafio.nome}"?`;
    if (!confirm(msg)) return;
    try {
      setError("");
      await deleteDesafio(desafio.id);
      setSuccess(`Desafio "${desafio.nome}" excluído.`);
      await loadDesafios();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erro ao excluir desafio");
    }
  };

  // --- Shared elements ---

  const sheetBtn = (
    <button
      onClick={handleAtualizarPlanilha}
      disabled={updatingSheet}
      className="bg-green-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
    >
      {updatingSheet ? "Atualizando..." : "Atualizar Planilha"}
    </button>
  );

  const alertError = error && (
    <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
      {error}
    </div>
  );

  const alertSuccess = success && (
    <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
      {success}
    </div>
  );

  const alertSheet = sheetMessage && (
    <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg">
      {sheetMessage}
    </div>
  );

  // --- List mode ---
  if (mode === "list") {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold text-gray-800">Desafios</h2>
          <div className="flex gap-3">
            {sheetBtn}
            <button
              onClick={() => {
                setError("");
                setSuccess("");
                setMode("import");
              }}
              className="bg-white text-indigo-600 border border-indigo-600 px-4 py-2 rounded-lg font-medium hover:bg-indigo-50 transition-colors"
            >
              Importar CSV
            </button>
            <button
              onClick={openCreateForm}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors"
            >
              Novo Desafio
            </button>
          </div>
        </div>

        {alertError}
        {alertSuccess}
        {alertSheet}

        {loading ? (
          <p className="text-gray-500">Carregando desafios...</p>
        ) : desafios.length === 0 ? (
          <p className="text-gray-500">
            Nenhum desafio cadastrado. Clique em "Novo Desafio" para começar.
          </p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Nome</th>
                  <th className="py-3 px-4 font-medium">Período</th>
                  <th className="py-3 px-4 font-medium text-center">Clãs registrados</th>
                  <th className="py-3 px-4 font-medium text-center">Pontuação</th>
                  <th className="py-3 px-4 font-medium text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {desafios.map((d) => (
                  <tr
                    key={d.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="py-3 px-4">
                      <button
                        onClick={() => openDetail(d)}
                        className="font-medium text-indigo-600 hover:underline text-left"
                      >
                        {d.nome}
                      </button>
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {formatPeriodo(d)}
                    </td>
                    <td className="py-3 px-4 text-center text-gray-600">
                      {d.total_registros}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          d.contabilizar_pontos
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {d.contabilizar_pontos ? "Registrar" : "Não Registrar"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right space-x-3">
                      {d.origem !== "csv_import" && (
                        <button
                          onClick={() => openEditForm(d)}
                          className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                        >
                          Editar
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteDesafio(d)}
                        className="text-red-600 hover:text-red-800 text-sm font-medium"
                      >
                        Excluir
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // --- Import mode (CSV wizard) ---
  if (mode === "import") {
    return (
      <ImportarDesafioWizard
        onCancel={() => setMode("list")}
        onImported={async () => {
          setSuccess("Desafio importado com sucesso.");
          await loadDesafios();
          setMode("list");
        }}
      />
    );
  }

  // --- Form mode (create / edit) ---
  if (mode === "form") {
    return (
      <div className="space-y-6 max-w-2xl">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMode("list")}
            className="text-gray-500 hover:text-gray-700 text-sm"
          >
            ← Desafios
          </button>
          <h2 className="text-2xl font-bold text-gray-800">
            {editingDesafio ? "Editar Desafio" : "Novo Desafio"}
          </h2>
        </div>

        {alertError}

        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nome do desafio
            </label>
            <input
              type="text"
              value={formNome}
              onChange={(e) => setFormNome(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="Ex: Semana de Treinos"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Data início
              </label>
              <input
                type="date"
                value={formDataInicio}
                onChange={(e) => setFormDataInicio(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Data fim
              </label>
              <input
                type="date"
                value={formDataFim}
                onChange={(e) => setFormDataFim(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Pontuação no ranking
            </label>
            <div className="flex rounded-lg border border-gray-300 overflow-hidden w-fit">
              <button
                type="button"
                onClick={() => setFormContabilizar(true)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  formContabilizar
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                Registrar Pontos
              </button>
              <button
                type="button"
                onClick={() => setFormContabilizar(false)}
                className={`px-4 py-2 text-sm font-medium border-l border-gray-300 transition-colors ${
                  !formContabilizar
                    ? "bg-indigo-600 text-white"
                    : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                Não Registrar Pontos
              </button>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              {formContabilizar
                ? "Os pontos deste desafio serão somados ao total geral dos clãs."
                : "Os pontos ficam apenas para controle interno, sem afetar o ranking."}
            </p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-700">
                Clãs e pontuação
              </label>
              <button
                type="button"
                onClick={addRegistroRow}
                className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
              >
                + Adicionar clã
              </button>
            </div>
            {formRegistros.length === 0 ? (
              <p className="text-sm text-gray-400 italic">
                Nenhum clã adicionado.
              </p>
            ) : (
              <div className="space-y-2">
                {formRegistros.map((registro, i) => (
                  <div key={i} className="flex gap-2 items-center">
                    <select
                      value={registro.clan}
                      onChange={(e) =>
                        updateRegistroRow(i, "clan", e.target.value)
                      }
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      <option value="">Selecione um clã</option>
                      {clanOptionsFor(i).map((r) => (
                        <option key={r.clan} value={r.clan}>
                          {r.clan}
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      min={0}
                      value={registro.pontos}
                      onChange={(e) =>
                        updateRegistroRow(i, "pontos", e.target.value)
                      }
                      className="w-32 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="0"
                    />
                    <button
                      type="button"
                      onClick={() => removeRegistroRow(i)}
                      className="text-red-500 hover:text-red-700 px-2 text-sm"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleSaveDesafio}
            disabled={submitting}
            className="bg-indigo-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Salvando..." : "Salvar Desafio"}
          </button>
          <button
            onClick={() => setMode("list")}
            className="bg-white text-gray-600 border border-gray-300 px-6 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors"
          >
            Cancelar
          </button>
        </div>
      </div>
    );
  }

  // --- Detail mode (somente leitura) ---
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setMode("list");
              setSelectedDesafio(null);
            }}
            className="text-gray-500 hover:text-gray-700 text-sm"
          >
            ← Desafios
          </button>
          <h2 className="text-2xl font-bold text-gray-800">
            {selectedDesafio?.nome}
          </h2>
          {selectedDesafio && (
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium ${
                selectedDesafio.contabilizar_pontos
                  ? "bg-green-100 text-green-700"
                  : "bg-gray-100 text-gray-600"
              }`}
            >
              {selectedDesafio.contabilizar_pontos
                ? "Registrar Pontos"
                : "Não Registrar Pontos"}
            </span>
          )}
          {selectedDesafio && (
            <span className="text-sm text-gray-500">
              {formatPeriodo(selectedDesafio)}
            </span>
          )}
        </div>
        <div className="flex gap-3">
          {sheetBtn}
          {selectedDesafio && selectedDesafio.origem !== "csv_import" && (
            <button
              onClick={() => openEditForm(selectedDesafio)}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-indigo-700 transition-colors"
            >
              Editar
            </button>
          )}
        </div>
      </div>

      {alertError}
      {alertSuccess}
      {alertSheet}

      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Clãs registrados ({registros.length})
        </h3>
        {registros.length === 0 ? (
          <p className="text-gray-500 text-sm">
            Nenhum clã registrado neste desafio ainda.
          </p>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left text-gray-500">
                  <th className="py-3 px-4 font-medium">Clã</th>
                  <th className="py-3 px-4 font-medium text-right">Pontos</th>
                </tr>
              </thead>
              <tbody>
                {registros.map((reg) => (
                  <tr
                    key={reg.id}
                    className="border-b border-gray-100 hover:bg-gray-50"
                  >
                    <td className="py-3 px-4 font-medium text-gray-700">
                      {reg.clan}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-indigo-600">
                      {reg.total_pontos.toLocaleString("pt-BR")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Rodar o type-check completo**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.app.json`
Expected: sem erros.

- [ ] **Step 3: Rodar o build de produção**

Run: `cd frontend && npm run build`
Expected: build concluído sem erros.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Desafios.tsx
git commit -m "feat: formulário único de desafio manual com período e clã/pontuação"
```

---

### Task 6: Verificação manual (bloqueada pela migration pendente)

**Files:** nenhum (só verificação).

- [ ] **Step 1: Confirmar se a migration de `desafios` já foi aplicada**

A coluna `origem`/`data_inicio`/`data_fim` em `desafios` depende do `ALTER TABLE` manual já descrito em `docs/superpowers/specs/2026-07-12-desafio-import-csv-design.md` (seção "Banco de dados"). Se ainda não foi rodado no Supabase Dashboard, rode-o agora — é o mesmo passo pendente das duas features, não precisa rodar de novo se já foi aplicado.

- [ ] **Step 2: Testar os cenários do design spec no navegador**

Com `data_inicio`/`data_fim`/`origem` aplicados no banco, seguir os 6 cenários de "Verificação end-to-end" de `docs/superpowers/specs/2026-07-12-desafio-manual-simplificado-design.md`:
1. Criar desafio novo com 2 clãs e conferir soma no Dashboard.
2. Editar esse desafio (remover um clã, mudar pontuação de outro, adicionar um terceiro) e conferir os deltas aplicados.
3. Alternar o toggle "Registrar Pontos" e conferir que os pontos só entram no ranking quando ligado.
4. Abrir um desafio legado (criado antes desta feature) para edição e confirmar a conversão para o campo único "Pontos" sem alterar o total dos clãs.
5. Confirmar que desafios com `origem="csv_import"` não mostram o botão "Editar" na listagem.
6. Excluir um desafio criado pelo novo formulário e confirmar que os pontos são descontados corretamente.

Sem acesso a credenciais reais do Supabase/Google Sheets nesta sessão, esta task fica pendente para execução manual pelo usuário.

---

## Self-Review

**Cobertura da spec:** regra 1 (campo implícito) → Task 3 `_ensure_campo_pontos`; regra 2 (criação em um passo) → Task 3 `criar_desafio`; regra 3 (diff por clã) → Task 1 + Task 3 `editar_desafio`; regra 4 (conversão de legado) → Task 3 `_ensure_campo_pontos` + Task 5 `openEditForm` (pré-preenche com `total_pontos`); regra 5 (csv_import não usa este formulário) → Task 5 (botão "Editar" oculto); regra 6 (`data` recebe `data_fim`) → Task 3 (`criar_desafio`/`editar_desafio` passam `body.data_fim` como `data`) e Task 2 (`update_desafio`); regra 7 (validação) → Task 3 `_validar_periodo_e_registros` + Task 5 `handleSaveDesafio`. Todos os 6 cenários end-to-end da spec estão listados na Task 6.

**Placeholders:** nenhum "TBD"/"implementar depois" — todo step tem código completo.

**Consistência de tipos:** `RegistroClanInput{clan, pontos}` (backend) ↔ `DesafioRegistroInput{clan, pontos}` (frontend) — mesmo shape serializado por `JSON.stringify`. `diff_desafio_registros` retorna `to_update` com itens `{id, clan, pontos}`, consumidos em `editar_desafio` via `item["id"]`/`item["clan"]`/`item["pontos"]` — nomes batem. `update_desafio` (Task 2) recebe `data_inicio`/`data_fim` como kwargs opcionais, chamado assim em `editar_desafio` (Task 3).
