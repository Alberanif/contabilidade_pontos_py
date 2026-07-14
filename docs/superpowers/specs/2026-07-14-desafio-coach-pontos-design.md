# Pontos de desafio CSV por coach — Design Spec

**Data:** 2026-07-14
**Status:** Aprovado

---

## Contexto

A importação de desafios via CSV (`docs/superpowers/specs/2026-07-12-desafio-import-csv-design.md`) já contabiliza pontos por clã a partir de linhas do CSV — uma linha por submissão individual de coach. Hoje esses pontos não são atribuídos a nenhum coach: o Dashboard mostra explicitamente "Desafios não registram pontos por coach" na aba Coaches (`frontend/src/pages/Dashboard.tsx:423`), e `get_tipo_coach_totals("desafios")` retorna `{}` (`backend/supabase_client.py:856-857`).

O CSV real (`Desafios Pontuais - PROD - IGT ULTIMATE| Desafios | Pontuais.csv`) tem uma única coluna de nome ("Coloque aqui o seu Nome:") — quem preenche o formulário é o próprio coach cumprindo o desafio individual. Não existe (nem é necessário) um campo de coach separado do campo "Nome" já mapeado no wizard.

Esta feature faz o importador atribuir, além do total por clã, o total individual de pontos a cada coach que participou — usando o mesmo sistema de identidade canônica (`coach_identity.py` + `pontos_ultimate_coach_aliases`) já validado para Coaching Individual/Grupo/Pro-bono. Aplica-se **somente** a desafios com `origem='csv_import'`; desafios manuais não têm dado de coach no CSV e continuam sem essa contabilização.

---

## Regras de negócio

1. **Mesma fórmula do clã, agrupada por coach.** Pontos de um coach num desafio importado = nº de participações validadas únicas dele × pontos por participação (o mesmo valor configurado no wizard, mesmo cálculo de `processar_importacao`). Reaproveita a dedup por pessoa já existente (`deduplicar_por_pessoa`): a submissão vencedora de cada pessoa (por `(clã, nome_normalizado)`) é a que conta tanto para o clã quanto para o coach.
2. **Coach = coluna "Nome" já mapeada.** Sem novo campo de mapeamento no wizard. O nome bruto da linha (`nome_participante`) é normalizado para o nome canônico do coach da mesma forma que o restante do sistema (camada A automática de `coach_identity.normalize_key` + camada B via tabela `pontos_ultimate_coach_aliases`).
3. **Canônico persistido na importação.** O nome canônico do coach é resolvido e gravado no momento da importação (`desafio_importacao_linhas.coach`, `desafio_registros_coach.coach`) — não recalculado a cada leitura. Alinhado com o padrão já usado para o campo `coach` em `pontos_ultimate_registros_contabilizados`: correções de alias exigem reprocessamento explícito, não afetam automaticamente dados já gravados.
4. **Soma direto no total geral do coach.** Pontos de desafio importado somam em `pontos_ultimate_totais_por_coach.total_pontos` no momento da confirmação — igual ao que já acontece para o clã via `add_delta_to_clan_total`. O ranking geral de coaches (aba "todos" do Dashboard, sem filtro de tipo/período) passa a incluir esses pontos.
5. **Só `csv_import` contabiliza coach.** Desafios manuais (`origem='manual'`) nunca têm registro em `desafio_registros_coach` — o CSV é a única fonte de atribuição individual por coach.
6. **Exclusão reverte.** Excluir um desafio desconta os pontos de `desafio_registros_coach` do total geral de cada coach afetado, no mesmo passo em que já desconta os pontos de clã (`excluir_desafio`).
7. **Fusão de alias propaga para desafios.** `POST /contabilidade/reprocessar-coaches` (fusão de nomes duplicados) passa a também reescrever o `coach` em `desafio_importacao_linhas`/`desafio_registros_coach` e recalcular os totais afetados — senão uma fusão de alias corrige os pontos de coaching mas deixa os pontos de desafio fragmentados sob a grafia antiga.

---

## Banco de dados

### Migration `backend/migrations/007_add_desafio_registros_coach.sql`

```sql
ALTER TABLE desafio_importacao_linhas ADD COLUMN coach varchar;

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

`desafio_importacao_linhas.coach` guarda o nome canônico calculado na importação; `nome_participante` continua guardando o nome bruto do CSV (auditoria). `desafio_registros_coach` espelha `desafio_registros` — mesma estrutura (`valores`/`total_pontos`), só troca a chave de agrupamento de `clan` para `coach`.

---

## Lógica pura (`backend/desafio_import_engine.py`)

- `ImportRow` ganha campo `coach: str` (nome canônico).
- `parse_row` ganha parâmetro `coach_alias_map: dict[str, str]` e resolve `coach = coach_identity.resolve_coach(nome, coach_alias_map)`. Import de `coach_identity` no módulo (ainda zero I/O — `resolve_coach` só faz lookup num dict já carregado, mesmo padrão de `clans_validos`/`tokens_ja_importados` injetados pelo router).
- `ImportResult` ganha `pontos_por_coach: dict[str, int]` e `participacoes_por_coach: dict[str, int]`.
- `linhas_auditoria` ganha chave `"coach"`.
- `processar_importacao` ganha parâmetro `coach_alias_map: dict[str, str]`, repassado para `parse_row`. No loop de agregação (onde hoje só popula `pontos_por_clan`/`participacoes_por_clan` para linhas `validado and contabilizado`), popula também `pontos_por_coach`/`participacoes_por_coach` usando `row.coach`.

---

## Backend

### `backend/routers/desafio_import.py`

`_processar` busca `coach_alias_map = supabase_client.get_coach_alias_map()` e repassa para `processar_importacao` (mesmo lugar onde já busca `clans_validos`/`tokens_ja_importados`).

`preview` retorna adicionalmente `pontos_por_coach` e `participacoes_por_coach`.

`confirmar`: depois do loop que grava `desafio_registros` por clã, loop análogo para `desafio_registros_coach` por coach — busca registro existente (`get_desafio_registro_coach_by_coach`), se existir recalcula e aplica delta (`add_delta_to_coach_total`), senão cria e soma o total inteiro. Grava `linha["coach"]` junto com o resto da auditoria em `insert_desafio_importacao_linhas` (já genérico, só precisa a chave estar no dict).

### `backend/supabase_client.py`

Novas funções, espelhando as equivalentes de clã:

```
create_desafio_registro_coach(desafio_id, coach, valores, total_pontos) -> dict
list_desafio_registros_coach(desafio_id) -> list[dict]
get_desafio_registro_coach_by_coach(desafio_id, coach) -> dict | None
update_desafio_registro_coach_pontos(registro_id, valores, total_pontos) -> dict
add_delta_to_coach_total(coach, delta) -> dict   # espelha add_delta_to_clan_total
get_period_desafio_coach_totals(inicio, fim) -> dict[str, int]   # espelha get_period_desafio_totals
```

`get_tipo_coach_totals("desafios")` deixa de retornar `{}` — passa a ler `desafio_registros_coach` igual `get_tipo_clan_totals("desafios")` lê `desafio_registros` (com e sem filtro de período).

### `backend/routers/contabilidade.py`

`historico()`: hoje `coach_totals = supabase_client.get_period_coach_totals(...)` sem mesclar desafio. Passa a mesclar com `get_period_desafio_coach_totals(inicio, fim)`, igual ao merge já existente pra clã (`merged_clans`).

`reprocessar_coaches()`: depois do loop que reescreve `coach` em `pontos_ultimate_registros_contabilizados` e recalcula `pontos_ultimate_totais_por_coach`, novo passo — para cada `raw_coach` com canônico diferente, reescreve `coach` em `desafio_importacao_linhas` e em `desafio_registros_coach` (merge de linhas: se o canônico já tem uma linha em `desafio_registros_coach` para o mesmo `desafio_id`, soma `total_pontos` e remove a duplicata; senão só renomeia). Recalcula o delta correspondente no total geral do coach.

### `backend/routers/desafios.py`

`excluir_desafio`: antes de `delete_desafio`, além do loop existente que desconta `desafio_registros` de clã, novo loop que desconta `desafio_registros_coach` de cada coach afetado via `add_delta_to_coach_total(reg["coach"], -reg["total_pontos"])`. Roda sempre (não só quando `contabilizar_pontos=true`) já que `desafio_registros_coach` só existe pra `csv_import` — mas por consistência segue a mesma guarda de `contabilizar_pontos` do loop de clã.

---

## Frontend

`frontend/src/pages/Dashboard.tsx:422-423`: remove o bloqueio condicional `tipoFiltro === "desafios"` que mostra "Desafios não registram pontos por coach". A tabela genérica de ranking de coaches (já usada pelos outros filtros) passa a renderizar `activeData.coaches` normalmente também para `tipoFiltro === "desafios"` — nenhuma outra mudança de UI necessária, o código já é agnóstico à fonte dos dados.

---

## Verificação end-to-end

1. **Importação nova:** subir CSV de exemplo, mapear colunas, "Desafio G", 11/05–30/06, 10 pontos/participação → confirmar → cada coach com participação validada única aparece em `desafio_registros_coach` com pontos corretos; total geral do coach (`GET /coaches`) sobe o mesmo valor.
2. **Dedup de pessoa:** Luciana Batista aparece 2x no período → só 1 participação conta pros pontos dela (mesma lógica que já vale pro clã).
3. **Alias de coach:** nome do CSV bate com um `alias` cadastrado em `pontos_ultimate_coach_aliases` → `desafio_registros_coach.coach` grava o `coach_canonico`, não a grafia bruta.
4. **Reimportação incremental:** delta aplicado só sobre participações novas, coach existente tem `total_pontos` atualizado (não duplicado).
5. **Exclusão:** excluir um desafio `csv_import` com pontos de coach → total geral de cada coach afetado desce o valor correspondente.
6. **Reprocessar-coaches:** cadastrar um novo alias que afeta um coach com pontos de desafio → chamar `POST /contabilidade/reprocessar-coaches` → pontos de desafio das duas grafias se fundem sob o canônico, total geral não muda (só reagrupa).
7. **Dashboard:** aba Coaches, filtro Desafios → mostra ranking real (não mais a mensagem placeholder); aba Coaches, filtro "todos" → totais já incluem pontos de desafio.
8. **Desafio manual:** desafio `origem='manual'` nunca gera linha em `desafio_registros_coach` mesmo com `contabilizar_pontos=true`.
