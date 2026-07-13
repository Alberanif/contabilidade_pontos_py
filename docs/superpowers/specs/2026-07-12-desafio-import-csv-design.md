# Importação de Desafios via CSV — Design Spec

**Data:** 2026-07-12
**Status:** Aprovado (via sessão de grilling)

---

## Contexto

Hoje, cadastrar um desafio e registrar a participação de cada clã é 100% manual (`frontend/src/pages/Desafios.tsx` + `POST /api/desafios`, `POST /api/desafios/{id}/registros`). Os desafios pontuais reais (ex: "Desafio G", "Desafio H") são coletados via formulário externo (Circle/Typeform) e exportados como CSV, com uma linha por submissão individual de coach — não por clã. Hoje alguém precisa ler esse CSV manualmente e lançar os pontos de cada clã à mão.

Esta feature permite subir esse CSV diretamente: o usuário mapeia as colunas do arquivo para os campos que o sistema entende (clã, nome, validação, data, token), informa o nome do desafio, o período e quantos pontos vale cada participação validada, vê uma prévia do resultado calculado, e confirma — o sistema cria (ou atualiza) o desafio e registra os pontos de cada clã automaticamente.

## Achados do CSV real analisado

Arquivo de exemplo (`Desafios Pontuais - PROD - IGT ULTIMATE_ Desafios _ Pontuais.csv`, ~77 linhas) revelou padrões que moldam as regras abaixo:
- Um clã tem várias pessoas diferentes submetendo (ex: Clã 1 com 9 pessoas).
- O arquivo mistura dois desafios diferentes (G e H), distinguíveis só pela data de submissão — o texto da pergunta do formulário não muda.
- A mesma pessoa pode reenviar o formulário para "editar" a resposta dentro do mesmo desafio (ex: Luciana Batista, linhas 34 e 47).
- Nomes têm variação de capitalização entre submissões da mesma pessoa (ex: "Carolina dorte gadbem" vs "carolina dorte gadbem").
- A coluna de validação normalmente é "Sim", mas o formulário permite "Não" (e teoricamente vazio/outro texto).

---

## Regras de negócio

1. **Pontuação cumulativa por pessoa.** O total de pontos de um clã num desafio importado é `nº de participações validadas únicas × pontos por participação` (valor informado no wizard).
2. **Cálculo já multiplicado.** O importador calcula o total por clã e grava esse valor pronto num campo `pontuacao` do desafio (reaproveitando `desafio_campos`/`desafio_registros`/`calculate_desafio_pontos` sem mudança de schema nessas duas tabelas). Um segundo campo `texto` guarda a contagem bruta de participações só para exibição.
3. **Validação estrita.** Só conta como participação validada um valor cuja versão normalizada (trim + lowercase) seja exatamente `"sim"`. Qualquer outra coisa (vazio, "não", "talvez", erro de digitação) é tratada como não-validada.
4. **Auditoria completa.** Toda linha do CSV com clã reconhecido é gravada em `desafio_importacao_linhas` (nome, clã, validado, se contou para a pontuação, data de submissão, token original) — mesmo as não-validadas. Linhas com clã não reconhecido **não** são persistidas, só aparecem como aviso na prévia.
5. **Dedup em duas camadas:**
   - **Entre importações** (reimportação incremental): por `token_original`, único por desafio. Uma linha com token já visto é ignorada silenciosamente (não reprocessada, não gera aviso — é o comportamento esperado de reimportar um export incremental).
   - **Dentro da mesma importação**: por `(clã, nome normalizado)`. Se a mesma pessoa aparecer mais de uma vez (reenvio/edição), só a submissão mais recente (`submitted_at`) conta para a pontuação; as demais são gravadas na auditoria com `contabilizado = false`.
6. **Clã desconhecido não bloqueia a importação.** Linhas cujo número de clã não corresponde a nenhum clã do ranking atual (`GET /api/clans/ranking`) são ignoradas e listadas como aviso; o restante da importação prossegue.
7. **Filtro por período.** Só entram no cálculo linhas cujo `submitted_at` está dentro de `[data_inicio, data_fim]` (inclusive). Linhas com data ilegível são excluídas e contam como aviso (fail-closed — diferente do `points_engine.filter_by_date_range` existente, que é fail-open; aqui o risco de inflar pontos por engano pesa mais que perder uma linha ambígua).
8. **Prévia obrigatória.** `POST /api/desafios/importar/preview` calcula tudo (pontos por clã, participações, avisos) sem gravar nada. Só `POST /api/desafios/importar/confirmar` persiste.
9. **Criar novo ou atualizar existente.** O usuário escolhe explicitamente no wizard. Só desafios com `origem = 'csv_import'` aparecem como alvo de atualização (evita corromper a estrutura de campos de um desafio criado manualmente). Ao atualizar, período e pontos-por-participação são herdados do desafio existente (editáveis), os dois campos (`pontuacao`/`texto`) são reaproveitados (mesmos IDs), e o total por clã é recalculado com **delta** aplicado ao ranking geral — mesmo padrão já usado em `editar_desafio` (`backend/routers/desafios.py:104-126`).
10. **Mapeamento de colunas genérico.** O usuário sobe o CSV, o sistema lê o cabeçalho, e o usuário mapeia visualmente cada coluna necessária (Clã, Nome, Validação, Data de submissão, Token) — sem hardcode de nomes de coluna.

---

## Banco de dados

### Alterações em `desafios` (SQL manual via Supabase Dashboard — mesmo padrão do campo `data`, sem arquivo de migration)

```sql
ALTER TABLE desafios ADD COLUMN data_inicio date;
ALTER TABLE desafios ADD COLUMN data_fim date;
ALTER TABLE desafios ADD COLUMN origem varchar NOT NULL DEFAULT 'manual';
ALTER TABLE desafios ADD COLUMN pontos_por_participacao integer;
```

`data` (coluna existente, `NOT NULL`) recebe `data_fim` na criação via importação — mantém compatibilidade com o fluxo manual sem exigir mudança de schema nessa coluna.

### Nova tabela (migration `backend/migrations/005_add_desafio_importacao_linhas.sql`)

```sql
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

`validado` reflete o que o CSV disse; `contabilizado` indica se essa linha especificamente contribuiu para o total de pontos do clã (falso para não-validadas e para duplicatas-de-pessoa perdedoras).

---

## Lógica pura (`backend/desafio_import_engine.py`, zero I/O)

Módulo novo, no mesmo espírito de `points_engine.py`. Funções principais (ver seams no plano de implementação):

```
normalizar_validado(raw: str) -> bool
normalizar_nome(raw: str) -> str
normalizar_clan(raw: str) -> str
parse_submitted_at(raw: str) -> datetime | None
parse_row(raw_row: dict, mapping: dict) -> ImportRow
filtrar_por_periodo(rows, data_inicio, data_fim) -> (dentro, fora)
filtrar_clans_validos(rows, clans_validos) -> (validos, invalidos)
filtrar_tokens_novos(rows, tokens_ja_importados) -> (novos, ja_importados)
deduplicar_por_pessoa(rows) -> rows_com_flag_contabilizado
processar_importacao(raw_rows, mapping, clans_validos, tokens_ja_importados,
                      data_inicio, data_fim, pontos_por_participacao) -> ImportResult
```

`ImportResult`: `pontos_por_clan: dict[str,int]`, `participacoes_por_clan: dict[str,int]`, `linhas_auditoria: list[dict]`, `avisos: list[str]`.

---

## Backend

**Novos arquivos:** `backend/desafio_import_engine.py`, `backend/routers/desafio_import.py`
**Alterações:** `backend/supabase_client.py` (funções novas), `backend/main.py` (registrar router), `backend/google_sheets_client.py` (nenhuma mudança — só consumido via `fetch_ranking()`)

### Endpoints

```
POST /api/desafios/importar/preview
  multipart/form-data: file (CSV), mapping (JSON), config (JSON)
  config: { nome, desafio_id?: int, data_inicio, data_fim, pontos_por_participacao }
  → calcula tudo, NÃO grava. Retorna:
    { pontos_por_clan, participacoes_por_clan, avisos, total_linhas, total_contabilizadas }

POST /api/desafios/importar/confirmar
  mesmo input do preview
  → cria/atualiza desafio (origem='csv_import'), grava desafio_importacao_linhas,
    atualiza/cria desafio_registros, aplica delta no total do clã (add_delta_to_clan_total)
  → retorna o desafio atualizado (mesmo shape de GET /api/desafios/{id})

GET /api/desafios?origem=csv_import
  → reutiliza GET /api/desafios existente com filtro opcional de origem,
    usado para popular o dropdown "atualizar desafio existente" no wizard
```

---

## Frontend

Novo modo `"importar"` dentro de `frontend/src/pages/Desafios.tsx` (ou componente dedicado `ImportarDesafioWizard.tsx` importado por ela), com 3 passos:

```
Passo 1 — Upload e mapeamento
  Input de arquivo CSV → sistema lê cabeçalho → dropdowns:
  Clã, Nome, Validação (Sim/Não), Data de submissão, Token

Passo 2 — Configuração
  ( ) Criar novo desafio        Nome: [_______]
  (•) Atualizar existente:      [Desafio G ▾] (só origem=csv_import)
  Período: [data_inicio] a [data_fim]
  Pontos por participação: [___]
  (período/pontos pré-preenchidos e editáveis se "atualizar existente")

Passo 3 — Prévia e confirmação
  Tabela: Clã | Participações | Pontos
  ⚠ Avisos (clã inválido, linhas fora do período, etc.)
  [Cancelar]  [Confirmar importação]
```

---

## Verificação end-to-end

1. **Importação nova:** subir o CSV de exemplo, mapear colunas, nome "Desafio G", período 11/05–30/06, 10 pontos/participação → prévia mostra Clã 1 com 9 participações/90 pontos → confirmar → desafio aparece em `/desafios`, total do Clã 1 sobe 90 pontos no Dashboard.
2. **Dedup de pessoa:** Luciana Batista (Clã 1) aparece 2x no período → prévia conta 1 participação para ela, não 2.
3. **Não-validado:** linha com "Não" não soma ponto, mas aparece na auditoria.
4. **Clã inválido:** linha com clã "9" (inexistente) → aviso na prévia, resto importa normalmente.
5. **Reimportação incremental:** subir um CSV com 2 linhas novas (tokens inéditos) + todas as antigas → prévia soma só as 2 novas; confirmar → total do clã sobe só o delta das 2 novas, tokens antigos não duplicam.
6. **Fora do período:** linha de "Desafio H" (data em julho) não conta ao importar "Desafio G" (período até 30/06).
7. **Cancelar prévia:** gerar prévia, clicar "Cancelar" → nada é gravado no banco (nem desafio, nem auditoria, nem pontos).
