# Runbook — Sincronização contínua de desafios (Google Sheets)

Este documento cobre a **operação em regime** do pipeline planilha → banco
(`desafio_sync_service.sync_desafios`, disparado a cada `Executar
Contabilidade`): variáveis de ambiente, como ler os logs estruturados, o que
fazer quando uma remoção em massa pede confirmação, como investigar
submissões `invalid`/`conflicted`, recuperação de falhas e consultas de
observabilidade.

**Não é** o runbook da migração administrativa única que corta a produção
para este pipeline pela primeira vez — esse é
[`docs/runbooks/migracao-desafios-google-sheets.md`](./migracao-desafios-google-sheets.md).
Se `desafio_submissions_current` ainda está vazio e os desafios legados
(`origem IN ('manual', 'csv_import')`) ainda pontuam, você quer aquele
documento, não este. Este runbook assume a migração já concluída.

---

## 1. Variáveis de ambiente e permissão da service account

| Variável | Uso | Obrigatória para o sync de desafios |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | credencial da service account (JSON completo, uma linha) | sim |
| `GSHEET_DESAFIOS_SPREADSHEET_ID` | ID da planilha oficial de desafios | sim |
| `GSHEET_DESAFIOS_SHEET_NAME` | nome da aba dentro da planilha | sim |
| `POINTS_PER_DESAFIO_SUBMISSION` | pontos por submissão elegível (padrão `10`) | não (tem default) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | acesso ao RPC `apply_desafio_reconciliation` e às tabelas de leitura | sim (compartilhada com o resto do backend) |
| `LOG_LEVEL` | nível do logging estruturado (`backend/logging_config.py`), padrão `INFO` | não |

Diferente da planilha de Registros (`fetch_records`, escopo
`spreadsheets` de leitura/escrita compartilhado com outras rotinas), a leitura
de desafios usa um escopo dedicado
(`google_sheets_client.READONLY_SCOPES = spreadsheets.readonly`) — a service
account só **precisa** de acesso de leitura à planilha de desafios. Não
conceda edição: o pipeline nunca escreve na planilha, e um acesso de escrita
desnecessário amplia o raio de um vazamento de credencial sem nenhum
benefício operacional.

`config.py` só valida a *presença* de `GOOGLE_SERVICE_ACCOUNT_JSON`,
`GSHEET_RECORDS_*` e `GSHEET_TOTALS_*` na importação (`REQUIRED_VARS`);
`GSHEET_DESAFIOS_*` é lido sob demanda e sua ausência não derruba o backend —
ela aparece como uma falha de fase `leitura` (`error_category:
"configuracao"`) só quando `sync_desafios` roda de fato. Isso é intencional
(RF-*: a etapa de desafios não pode interromper as demais fontes de pontos),
mas significa que um ambiente mal configurado só se revela no primeiro
`Executar Contabilidade`, não no boot do processo — monitore o log, não só o
health check.

---

## 2. Como ler os logs estruturados

`backend/desafio_sync_service.py` (logger `"desafio_sync"`) emite um evento
por fase de cada chamada a `sync_desafios`, com o payload completo sob a
chave `desafio_sync` do `LogRecord` (visível em `record.desafio_sync` em
testes/`caplog`; em produção, `backend/logging_config.py` configura um
`StreamHandler` cujo formatter anexa esse payload como JSON no fim da linha —
`... desafio_sync: fase_concluida {"correlation_id": "...", "phase": "leitura", ...}`).

### 2.1 Correlação entre fases — leia isto antes de procurar um `run_id`

`desafio_sync_runs.id` (`run_id`) só nasce **dentro** do RPC
`apply_desafio_reconciliation` (migração `009`), no `INSERT` que abre a
execução — ou seja, só existe a partir da fase de aplicação, a última das
cinco. As fases anteriores (leitura, parse, snapshot, reconciliação) rodam
inteiramente em memória, antes de qualquer linha em `desafio_sync_runs`
existir, e por isso **não têm `run_id` para carregar**.

Por causa disso, toda chamada a `sync_desafios` gera, logo no início, um
`correlation_id` (um `uuid4` hex, só em memória — não é persistido em nenhuma
tabela) que **todo** evento daquela chamada carrega, da fase `leitura` até o
evento final. É esse campo — não `run_id` — que você usa para juntar os logs
de uma execução inteira:

```
grep '"correlation_id": "8f2a1c..."' backend.log
```

A partir da fase `snapshot` (quando `build_desafio_snapshot` calcula o hash),
os eventos passam a carregar também `snapshot_hash` — o mesmo valor que, se a
execução chegar até a fase de aplicação, acaba persistido em
`desafio_sync_runs.snapshot_hash`. Isso dá um segundo eixo de junção: mesmo
sem ter guardado o `correlation_id` de uma execução específica, dá para ligar
os logs das fases 1-5 à linha que elas produziram no banco (ou constatar que
nenhuma foi produzida, se a execução falhou antes da fase de aplicação) por
`snapshot_hash`. O evento final da fase de aplicação carrega os três:
`correlation_id`, `snapshot_hash` e `run_id` (quando existe) — é o elo
completo entre "o que os logs registraram" e "o que o banco persistiu".

Resumo de quando cada chave existe:

| Fase | `correlation_id` | `snapshot_hash` | `run_id` |
|---|---|---|---|
| `leitura` | sempre | nunca | nunca |
| `parse` | sempre | nunca | nunca |
| `snapshot` | sempre | sempre | nunca |
| `reconciliacao` | sempre | sempre | nunca |
| `aplicacao` (sucesso) | sempre | sempre | sempre |
| `aplicacao` (`already_running`) | sempre | sempre | nunca (o RPC nem chega a inserir a linha — ver seção 6.4) |
| `aplicacao` (`awaiting_confirmation`) | sempre | sempre | nunca (nada foi escrito) |

### 2.2 Campos de cada evento

| Campo | Presente em | Significado |
|---|---|---|
| `phase` | todos | `leitura` \| `parse` \| `snapshot` \| `reconciliacao` \| `aplicacao` |
| `status` | todos | `ok` \| `failed` \| `awaiting_confirmation` \| `already_running` \| `success` |
| `duration_seconds` | todos | duração da fase (fases 1-4) ou da execução inteira (evento final da fase 5) |
| `sheet_row_count` / `parsed_row_count` / `token_count` | leitura/parse/snapshot | contagens brutas de cada etapa |
| `state_counts` | reconciliação, aplicação (sucesso) | contagem de tokens por `change_reason`/estado (`new`, `unchanged`, `missing`, ...) |
| `clan_deltas` | reconciliação, aplicação (sucesso) | delta de pontos por clã que o plano produziria/produziu |
| `mass_removal_required` / `mass_removal_ratio` / `mass_removal_count` | reconciliação, `awaiting_confirmation` | guarda de 20% (RF-17) — seção 3 |
| `error_type` / `error_category` / `error_message` | eventos `failed` | ver tabela da seção 5 |
| `challenges_created` / `_archived` / `_reactivated` / `tokens_versioned` | evento final de sucesso | efeito líquido gravado pelo RPC |

Nenhum evento carrega `GOOGLE_SERVICE_ACCOUNT_JSON` nem qualquer token
OAuth/de acesso derivado dele — isso é coberto por teste
(`backend/tests/test_desafio_sync_observability.py::TestAusenciaDeSegredosNosLogs`).
O `token` de negócio (coluna I da planilha, identificador de uma submissão) **não**
é segredo — já é público via `GET /api/desafios/submissoes/{token}` — então
contagens que o referenciam indiretamente (`state_counts`, `tokens_versioned`)
não são vazamento; nenhum evento loga a lista de tokens em si, só contagens
agregadas.

---

## 3. Confirmação de remoção em massa (>20% dos tokens ativos)

Sintomas: `sync_desafios()` volta com `status == "awaiting_confirmation"`; no
log, um evento com `status: "awaiting_confirmation"` na fase `aplicacao`
carregando `mass_removal_count` e `mass_removal_ratio`. **Nada foi escrito no
banco** — é uma guarda antes de qualquer chamada ao RPC (RF-17).

Passo a passo:

1. **Não confirme por reflexo.** Investigue por que mais de 20% dos tokens
   ativos sumiriam — planilha compartilhada editada por engano, filtro
   aplicado sem querer, aba errada, linhas apagadas em massa. Compare
   `mass_removal_count` (quantos tokens sumiriam) com `active_tokens_before`
   (quantos estavam ativos antes) no evento de log ou na resposta da chamada.
2. Se a mudança é legítima (ex.: limpeza deliberada de submissões antigas),
   reenvie a mesma chamada com `confirm_mass_removal=True` **e**
   `confirm_snapshot_hash=<snapshot_hash da prévia>`. O hash é uma
   pré-condição de frescor: se a planilha mudou entre a prévia e a
   confirmação, `apply_reconciliation` recusa (`SnapshotConfirmationMismatchError`,
   `error_category: "confirmacao_divergente"`) em vez de aplicar um plano que
   já não corresponde ao estado atual — refaça a prévia.
3. `confirm_mass_removal=True` sozinho, sem o hash certo, nunca basta —
   `confirmed_snapshot_hash` e `confirm_mass_removal` são dois consentimentos
   independentes por desenho (ver docstring de
   `desafio_reconciliation_store.apply_reconciliation`).

---

## 4. Investigando submissões `invalid` ou `conflicted`

`desafio_submissions_current.status` tem seis valores possíveis (constraint
da migração `009`). Os primeiros quatro são efetivamente produzidos pelo
pipeline hoje; `blocked_by_guardrail` está reservado no schema para uma guarda
futura e não é emitido pelo parser/reconciliação atuais:

| Status | O que significa | Onde a causa aparece |
|---|---|---|
| `active_counted` | linha estruturalmente válida, coluna C ("Validado") = "Sim" | pontua |
| `active_not_counted` | linha estruturalmente válida, mas coluna C ≠ "Sim" | não pontua, mas é rastreada |
| `invalid` | falha estrutural (coluna obrigatória vazia/malformada) | `invalid_reasons` |
| `conflicted` | o mesmo token (coluna I) aparece em ≥2 linhas com conteúdo divergente | `invalid_reasons = ["duplicate_token_conflict"]` |
| `inactive_missing` | token existia e saiu da planilha | (sem `invalid_reasons` — não é erro de dado) |
| `blocked_by_guardrail` | reservado, não emitido pelo pipeline atual | — |

Valores possíveis de `invalid_reasons` (`backend/desafio_sheet_parser.py`):
`missing_columns`, `missing_clan`, `invalid_clan_legacy`, `invalid_clan_current`,
`conflicting_clans`, `missing_name`, `missing_challenge`,
`invalid_submitted_at`, `missing_token`.

### 4.1 Via API (um token ou um desafio de cada vez)

```
GET /api/desafios/submissoes/{token}                # estado atual do token
GET /api/desafios/submissoes/{token}/versoes         # histórico imutável de versões
GET /api/desafios                                    # lista desafios (para achar o id)
GET /api/desafios/{desafio_id}/submissoes?status=invalid
GET /api/desafios/{desafio_id}/submissoes?status=conflicted
```

Note que o filtro `status` da última rota só existe **por desafio** — não há
endpoint que liste todos os `invalid`/`conflicted` do sistema de uma vez. Para
uma varredura geral, use a consulta SQL abaixo.

### 4.2 Via SQL (varredura geral)

```sql
SELECT token, status, invalid_reasons, raw_challenge, raw_token,
       raw_clan_legacy, raw_clan_current, row_numbers, last_seen_run_id
  FROM desafio_submissions_current
 WHERE status IN ('invalid', 'conflicted')
 ORDER BY updated_at DESC;
```

Para `conflicted`, os `row_numbers` mostram todas as linhas da planilha que
compartilham o token — vá até essas linhas na planilha para ver a divergência
com os próprios olhos (o parser não decide qual das duas está "certa"; ambas
ficam de fora até alguém corrigir a planilha).

Correção sempre acontece **na planilha**, nunca no banco: a próxima
sincronização bem-sucedida reprocessa a linha corrigida e o token normalmente
transiciona para `active_counted`/`active_not_counted` (`change_reason` no
histórico de versões refletirá a transição).

---

## 5. Recuperação de falhas

Toda falha das fases 1-4 (leitura, parse, snapshot, reconciliação) **não
escreve nada** — elas rodam inteiramente em memória, antes de qualquer
chamada ao RPC. Uma falha na fase 5 (aplicação) também não escreve nada
*visível*: o RPC roda em uma única transação Postgres, e uma falha nela
aborta a transação inteira — inclusive o `INSERT` que abriria a linha em
`desafio_sync_runs`. Ou seja: **não existe uma linha `status = 'failed'`
persistida em `desafio_sync_runs`** — a coluna `error` dessa tabela existe no
schema (migração `009`) mas nenhum caminho do RPC ou do Python a preenche
hoje; o único registro de uma falha é o log estruturado. Se você precisar de
histórico de falhas para auditoria/alerta, ele vem dos logs, não do banco.

Isso também significa que uma sincronização com falha nunca deixa o banco em
estado parcial — o próximo `Executar Contabilidade` tenta de novo do zero, e
por ser idempotente (delta contra o estado persistido), uma reexecução
imediata é sempre segura.

| `error_category` (log) | Fase típica | Causa | O que fazer |
|---|---|---|---|
| `configuracao` | leitura | `GSHEET_DESAFIOS_SPREADSHEET_ID`/`_SHEET_NAME` ausente ou `GOOGLE_SERVICE_ACCOUNT_JSON` inválido | conferir variáveis de ambiente (seção 1); não é um problema transitório, vai falhar toda vez até corrigir |
| `rede` | leitura | `ConnectionError`/`TimeoutError`/`OSError` ao contatar a API do Google Sheets | geralmente transitório; a próxima execução automática resolve. Persistindo, checar quota da API/acesso da service account |
| `dados` | parse | `ValueError` no parser | planilha com formato inesperado fora do que os `invalid_reasons` já toleram; investigar a linha citada na mensagem |
| `planilha_vazia` | aplicação | planilha veio vazia havendo tokens ativos (RF-18) | **não é bug** — é a guarda que impede estornar tudo por um erro de leitura acidental da planilha. Confirme se a planilha foi mesmo esvaziada de propósito; se não, corrija a planilha e rode de novo |
| `total_negativo` | aplicação | o delta deixaria um total de clã negativo (RF-19) | sinal de divergência contábil fora do pipeline de desafios (alguém mexeu direto no banco, ou os totais já estavam inconsistentes). Investigar antes de qualquer nova tentativa — a transação abortou, nada mudou |
| `plano_obsoleto` | aplicação | o estado mudou entre a leitura e a aplicação (concorrência otimista) | rode de novo; se acontecer com frequência, algo está sincronizando desafios em paralelo fora do fluxo normal |
| `confirmacao_divergente` | aplicação | `confirm_snapshot_hash` não bate com o snapshot atual | a planilha mudou entre a prévia e a confirmação; refaça a prévia (seção 3) |
| `confirmacao_pendente` | — | (não deveria aparecer como `failed` — é tratado como `awaiting_confirmation`, seção 3) | se aparecer aqui, é uma regressão no tratamento de exceções da fachada |
| `aplicacao` | aplicação | outro `DesafioReconciliationError` não coberto acima (ex.: resposta inesperada do RPC) | ler `error_message` completo no log; provavelmente incompatibilidade entre o payload enviado e o RPC instalado — conferir se a migração `009` em produção bate com a versão do código |
| `desconhecido` | qualquer | exceção não classificada | ler `error_type`/`error_message`; considerar adicionar uma categoria nova em `desafio_sync_service._error_category` se for um caso recorrente |

---

## 6. Métricas — consultas SQL

Não há exportador de métricas no projeto (sem Prometheus/OpenTelemetry/statsd
em `backend/requirements.txt`) — greenfield, mesma situação do logging antes
desta Task. As métricas abaixo são consultas diretas contra
`desafio_sync_runs` (e, para tentativas concorrentes, contra o log
estruturado — seção 6.6, a única fonte que existe para isso).

### 6.1 Taxa de sucesso (últimos 7 dias)

```sql
SELECT status, COUNT(*),
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
  FROM desafio_sync_runs
 WHERE started_at >= NOW() - INTERVAL '7 days'
 GROUP BY status
 ORDER BY COUNT(*) DESC;
```

Lembre-se: como a seção 5 explica, uma execução que falhou **não aparece
aqui** — só `succeeded` e, mais raramente, `awaiting_confirmation`/`cancelled`
se algum dia forem usados. `status` nesta tabela nunca vale `'failed'` na
prática hoje (nenhum caminho do RPC faz `UPDATE ... SET status = 'failed'`
antes de um `RAISE EXCEPTION`, que aborta a própria linha). Para taxa de
sucesso "de verdade" (contando falhas), combine esta consulta com a contagem
de eventos `status: "failed"` nos logs do mesmo período.

### 6.2 Duração

```sql
SELECT id, started_at,
       EXTRACT(EPOCH FROM (finished_at - started_at)) AS duracao_segundos
  FROM desafio_sync_runs
 WHERE status = 'succeeded'
 ORDER BY started_at DESC
 LIMIT 50;

-- Percentis dos últimos 30 dias
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at))) AS p50,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (finished_at - started_at))) AS p95,
       MAX(EXTRACT(EPOCH FROM (finished_at - started_at))) AS max
  FROM desafio_sync_runs
 WHERE status = 'succeeded' AND started_at >= NOW() - INTERVAL '30 days';
```

### 6.3 Tokens por estado (última execução)

```sql
SELECT id, started_at, state_counts
  FROM desafio_sync_runs
 WHERE status = 'succeeded'
 ORDER BY started_at DESC
 LIMIT 1;

-- Estado atual agregado (não depende de uma execução específica)
SELECT status, COUNT(*) FROM desafio_submissions_current GROUP BY status;
```

### 6.4 Deltas de clã (histórico)

```sql
SELECT id, started_at, clan_deltas
  FROM desafio_sync_runs
 WHERE status = 'succeeded' AND clan_deltas <> '{}'::JSONB
 ORDER BY started_at DESC
 LIMIT 50;
```

### 6.5 Guarda de 20% acionada (contagem)

`awaiting_confirmation` nunca chega a ser persistido — a guarda dispara
**antes** da chamada ao RPC (`desafio_reconciliation_store.apply_reconciliation`
levanta `MassRemovalConfirmationRequiredError` em memória, sem tocar o banco;
ver seção 3). Não há coluna que conte "quantas vezes a guarda disparou".
A única fonte é o log estruturado:

```
grep '"status": "awaiting_confirmation"' backend.log | wc -l
```

Se um dia isso precisar de agregação em SQL, seria necessário persistir
esses eventos em algum lugar (não existe hoje) — considerar essa lacuna se a
guarda começar a disparar com frequência inesperada.

### 6.6 Tentativas concorrentes (`already_running`)

Mesma lacuna e mesmo motivo que a 6.5, mas confirmado diretamente na migração
`009`: quando `pg_try_advisory_xact_lock` falha, a função `RETURN`s
imediatamente com `status = 'already_running'` **sem nenhum `INSERT` em
`desafio_sync_runs`** (veja o primeiro `IF` da função, antes de qualquer
`INSERT`). Não existe consulta SQL possível para "quantas tentativas
concorrentes houve" — nenhuma linha é gravada para elas. A única fonte é,
de novo, o log estruturado:

```
grep '"status": "already_running"' backend.log | wc -l
```

Isso é normalmente raríssimo: só acontece se `Executar Contabilidade` for
disparado duas vezes ao mesmo tempo (ou concorrente com uma migração
administrativa, que usa a mesma chave de lock `7345901220834561`). Um volume
alto desse evento indica algo dispara o sync em paralelo fora do fluxo normal
(ex.: um cron duplicado) — vale investigar o chamador, não o pipeline.

### 6.7 Idade da última sincronização bem-sucedida

```sql
SELECT started_at,
       NOW() - started_at AS idade
  FROM desafio_sync_runs
 WHERE status = 'succeeded'
 ORDER BY started_at DESC
 LIMIT 1;
```

Uma idade grande (maior que o intervalo esperado entre execuções de
`Executar Contabilidade`) é o sinal mais simples de que o pipeline parou de
rodar com sucesso — combine com a seção 6.1 para saber se está falhando ou
simplesmente não está sendo disparado.

---

## 7. Retenção do backup/auditoria — indefinida, por desenho

Nenhuma das estruturas de auditoria deste pipeline tem rotina de expurgo:

- `desafio_submission_versions` (versões imutáveis por token, migração `009`)
  — trigger `desafio_submission_versions_immutable` bloqueia `UPDATE`/`DELETE`;
  `desafio_submission_versions_no_truncate` bloqueia `TRUNCATE`.
- `desafio_sync_runs` — sem trigger de imutabilidade dedicado, mas sem
  nenhuma rotina de limpeza no código; tratar como append-only na prática.
- `desafio_legacy_migracao_backup` (backup da migração administrativa,
  runbook de migração, seção 8) — também protegido por trigger contra
  `UPDATE`/`DELETE`/`TRUNCATE`, com retenção indeterminada por decisão do PRD
  (seção 19).

Isso é intencional: a auditoria de desafios (issue #18) existe justamente
para reconstruir "o que a planilha dizia quando" indefinidamente, sem
depender de backups externos ao Postgres. Não crie uma rotina de expurgo para
essas tabelas sem revisitar essa decisão explicitamente — e, se um dia isso
mudar, atualizar tanto este runbook quanto o de migração.

---

## 8. Referências

- Código: `backend/desafio_sync_service.py` (orquestração + logging
  estruturado), `backend/logging_config.py` (configuração mínima de
  logging), `backend/desafio_reconciliation_store.py` (porta de escrita),
  `backend/routers/desafio_auditoria.py` (API somente-leitura).
- Migrations: `backend/migrations/008`, `009`.
- Testes: `backend/tests/test_desafio_sync_observability.py` (correlação de
  fases e ausência de segredos nos logs), `backend/tests/test_desafio_sync_service.py`
  (comportamento funcional da fachada).
- Runbook irmão (migração administrativa, evento único):
  [`docs/runbooks/migracao-desafios-google-sheets.md`](./migracao-desafios-google-sheets.md).
- PRD: `docs/superpowers/specs/2026-08-19-contabilidade-desafios-google-sheets-prd.md`
  (RF-17 remoção em massa, RF-18 planilha vazia, RF-19 total negativo, seção
  19 retenção).

## Fase 2 — pontos de desafio para coaches

A partir da Fase 2, cada token `active_counted` também pontua para o **coach**
(coluna B da planilha, resolvida ao nome canônico via
`pontos_ultimate_coach_aliases`). Não há schema novo nem migração de banco.

### Após o deploy da Fase 2

1. Garanta que a Fase 1 já foi migrada e que houve ao menos uma sincronização
   bem-sucedida (`POST /api/contabilidade/executar`) — senão o backfill vem zerado.
2. Rode **uma vez** `POST /api/contabilidade/reprocessar`. Ele reconstrói todos
   os totais do zero e passa a somar `get_tipo_coach_totals("desafios")` no total
   de cada coach. `reprocessar-coaches` sozinho **não** serve de backfill (só
   cobre coaches afetados por mudança de alias).
3. Validação: para cada desafio, a soma de `pontos_por_coach` (em
   `GET /api/desafios/{id}`) deve ser igual a
   `points_per_submission × (nº de tokens active_counted com coluna B não vazia)`.

### Manutenção contínua

- `POST /api/contabilidade/executar` e `POST /api/contabilidade/confirmar-desafios`
  recompõem automaticamente a fatia de desafio no total dos coaches ao fim do sync
  (`_refresh_desafio_coach_totals`).
- A aba "Desafios" do ranking de Coaches (Dashboard) e `GET /api/contabilidade/totais-por-tipo?tipo=desafios`
  leem os tokens ao vivo — sempre exatos, mesmo antes de um `/reprocessar`.
- Um nome de coach com grafia nova na coluna B pontua sob o nome bruto até ser
  resolvido; ele aparece em `POST /api/contabilidade/sugerir-aliases-llm` e na fila
  de aliases pendentes.
