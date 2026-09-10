# Contabilidade de Pontos de Desafios via Google Sheets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir lançamento manual e importação CSV de pontos de desafios por uma sincronização token-centric a partir de uma Google Sheet dedicada, integrada à ação **Executar Contabilidade**.

**Architecture:** Pipeline puro (leitor Sheets → parser posicional → snapshot/reconciliação → aplicador transacional) orquestrado por uma fachada de serviço chamada a partir do router de contabilidade; consultas somente leitura expostas em endpoints dedicados; migração administrativa separada para reconstruir dados existentes.

**Tech Stack:** Python/FastAPI, Supabase/Postgres (RPC transacional), Google Sheets API, React/TypeScript no frontend.

**Fonte:** PRD completo em `docs/superpowers/specs/2026-08-19-contabilidade-desafios-google-sheets-prd.md` (issue GitHub #11). Cada task abaixo corresponde 1:1 a uma sub-issue já registrada (`[Desafios/N]`, issues #12–#24) — os números entre colchetes no título de cada task são os números da issue.

## Global Constraints

- Fonte única: a Google Sheet é a única autoridade para existência/estado contábil de uma submissão de desafio (PRD §4).
- Token é identidade global, opaco, case-sensitive, trim apenas nas extremidades (PRD §9.1).
- Contrato posicional fixo A–I (não usar cabeçalho para mapear campo): A=clã legado, B=nome, C=validação, D=link, E=observação, F=desafio, G=clã atual, H=Submitted At, I=token (PRD §8.3).
- Apenas `Sim` (case-insensitive, trim) pontua; qualquer outro valor não pontua mas fica auditável (PRD §9.3).
- Clã normalizado para `CLÃ 1`–`CLÃ 8`; A e G preenchidos e divergentes = conflito, não pontua (PRD §9.2).
- Valor por submissão: variável `POINTS_PER_DESAFIO_SUBMISSION`, padrão `10`; mudança recalcula retroativamente todos os tokens ativos na próxima sincronização (PRD §8.1, §10).
- Datas (`Submitted At`) interpretadas em `America/Sao_Paulo`, formato `dd/mm/aaaa HH:MM:SS`; usadas para atribuir período histórico de cada contribuição (PRD §9.6).
- Nenhum ponto individual de coach é criado a partir de desafios nesta fase; nome bruto é preservado apenas para auditoria (PRD §4, princípio 8).
- Reconciliação integral a cada execução: novo, inalterado, alterado (com/sem efeito contábil), ausente (inativar+estornar), reaparecido (reativar) (PRD §12).
- Guardas obrigatórias: planilha vazia com tokens ativos bloqueia; remoção >20% dos tokens ativos exige confirmação explícita vinculada a `run_id`/`snapshot_hash`; total de clã nunca pode ficar negativo (aborta) (PRD §14.4, §14.5, RF-17 a RF-19).
- Atomicidade: toda a etapa de desafios aplica em uma única transação; falha não afeta outras fontes de contabilidade (PRD RNF-01, RNF-04).
- Concorrência: apenas uma sincronização de desafios ativa por vez; segunda tentativa recebe `already_running` (PRD RNF-03).
- Auditoria permanente: toda execução e toda mudança de token tem timestamp, snapshot, valores antes/depois e deltas, retidos indefinidamente (PRD RNF-05, RNF-06).
- Endpoints de escrita legados (criar/editar/excluir desafio, registro manual, upload CSV) devem responder erro de domínio, preferencialmente HTTP 410, explicando que a Google Sheet é a fonte oficial (PRD RF-15, §20.4).
- Migração administrativa é comando de backend/deploy protegido, nunca endpoint público (PRD §20.5, RNF-07).

---

### Task 1: Criar schema token-centric e trilha de auditoria [issue #12]

**Status:** Já implementado no worktree (não commitado) antes desta execução formal do plano — esta task documenta e fecha o trabalho existente; não reimplementar do zero.

**Files:**
- Create: `backend/migrations/008_add_desafio_google_sync.sql`
- Modify: `backend/supabase_client.py`
- Create: `backend/tests/test_desafio_sync_schema.py`
- Create: `backend/tests/test_desafio_sync_schema_postgres.py`
- Create: `backend/requirements-dev.txt`

**Interfaces:**
- Produces: tabelas `desafio_sync_runs`, `desafio_submissions_current`, `desafio_submission_versions`; colunas novas em `desafios` (`origem`, `nome_normalizado`, `status`, `arquivado_at`, `reativado_at`, `updated_at`); constantes `TABLE_DESAFIO_SYNC_RUNS`, `TABLE_DESAFIO_SUBMISSIONS_CURRENT`, `TABLE_DESAFIO_SUBMISSION_VERSIONS` e helpers somente leitura `list_desafio_sync_runs`, `list_desafio_submissions_current`, `get_desafio_submission_current`, `list_desafio_submission_versions` em `backend/supabase_client.py`.

- [x] **Step 1: Verificar que a migration e os testes de contrato de schema já existem e cobrem PK global do token, FK de versões/execuções, checks de status/origem e índices obrigatórios.**
- [x] **Step 2: Rodar `pytest backend/tests/test_desafio_sync_schema.py backend/tests/test_desafio_sync_schema_postgres.py -v` e confirmar que passam.**
- [x] **Step 3: Rodar a suíte backend completa (`pytest -q`, ignorando módulos que exigem `.env` real) e confirmar ausência de regressão.**
- [ ] **Step 4: Commitar isoladamente (migration + supabase_client.py + testes de schema + requirements-dev.txt) com mensagem `feat: schema token-centric e auditoria de sincronização de desafios`.**

---

### Task 2: Integrar Google Sheets e implementar parser posicional A–I [issue #13]

**Status:** Já implementado no worktree (não commitado) antes desta execução formal do plano — esta task documenta e fecha o trabalho existente; não reimplementar do zero.

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/google_sheets_client.py`
- Create: `backend/desafio_sheet_parser.py`
- Create: `backend/tests/test_desafio_sheet_parser.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: nenhuma interface de tasks anteriores (paralelo à Task 1).
- Produces: `config.GSHEET_DESAFIOS_SPREADSHEET_ID`, `config.GSHEET_DESAFIOS_SHEET_NAME`, `config.POINTS_PER_DESAFIO_SUBMISSION` (default `10`); `google_sheets_client.fetch_desafio_records() -> list[list[str]]` (lança `DesafioSheetConfigurationError` se config ausente); `desafio_sheet_parser.parse_desafio_row(row_number: int, cells: list[str]) -> ParsedDesafioRow`; `desafio_sheet_parser.build_parsed_rows(rows: list[list[str]]) -> list[ParsedDesafioRow]`; `desafio_sheet_parser.normalize_clan(raw: str) -> str | None`; `desafio_sheet_parser.normalize_challenge(raw: str) -> tuple[str, str]`. `ParsedDesafioRow` expõe brutos, normalizados, `status` (`active_counted`/`active_not_counted`/`invalid`/`conflicted`), `structurally_valid`, `eligible`, `reasons: tuple[str, ...]`, `submitted_at: datetime | None` (timezone-aware America/Sao_Paulo).

- [x] **Step 1: Verificar que os testes parametrizados de posição, padding, normalização, conflito A/G, validação, token, nome, desafio e data já existem em `backend/tests/test_desafio_sheet_parser.py`.**
- [x] **Step 2: Rodar `pytest backend/tests/test_desafio_sheet_parser.py -v` e confirmar que passam.**
- [x] **Step 3: Rodar a suíte backend completa e confirmar ausência de regressão.**
- [ ] **Step 4: Commitar isoladamente (config.py + google_sheets_client.py + desafio_sheet_parser.py + teste do parser + .env.example) com mensagem `feat: parser posicional A-I e leitura da planilha oficial de desafios`.**

---

### Task 3: Implementar motor puro de snapshot e reconciliação [issue #14]

**Files:**
- Create: `backend/desafio_reconciliation.py`
- Create: `backend/tests/test_desafio_reconciliation.py`
- Modify: `backend/desafio_sheet_parser.py` (somente se o contrato tipado precisar de ajuste)

**Interfaces:**
- Consumes: `desafio_sheet_parser.ParsedDesafioRow` (Task 2).
- Produces:
  ```python
  build_desafio_snapshot(rows: list[ParsedDesafioRow], points_per_submission: int) -> DesafioSnapshot
  reconcile_desafios(snapshot: DesafioSnapshot, current: dict[str, CurrentSubmission]) -> ReconciliationPlan
  ```
  `ReconciliationPlan` contém: mudanças por token (novo/inalterado/alterado/ausente/reaparecido), versões a criar, deltas por clã, transições de desafios (criar/arquivar/reativar), contagens por estado, guardas acionadas (`is_empty_snapshot`, `mass_removal_ratio`), e hash determinístico do snapshot (`snapshot_hash: str`). `CurrentSubmission` é o shape de leitura equivalente à linha de `desafio_submissions_current` (Task 1).

- [ ] **Step 1: Escrever `backend/tests/test_desafio_reconciliation.py` cobrindo CA-01 a CA-14, CA-16, CA-17 e CA-22 do PRD (§27): token válido, múltiplas submissões, idempotência, duplicata idêntica/conflitante, correção de clã/validação/data, remoção, duas colunas de clã, linha incompleta, criação/arquivamento/reativação automática de desafio, snapshot vazio, remoção >20%, mudança do valor configurado.**
- [ ] **Step 2: Rodar os testes e confirmar falha (funções ainda não existem).**
- [ ] **Step 3: Implementar `build_desafio_snapshot`: consolidar duplicatas idênticas preservando posições, marcar duplicatas conflitantes como não pontuáveis, calcular hash determinístico.**
- [ ] **Step 4: Implementar a máquina de estados e o diff contra `current` (novo/inalterado/alterado sem efeito/alterado com efeito/ausente/reaparecido).**
- [ ] **Step 5: Implementar cálculo de delta por clã (estorno da contribuição anterior + nova contribuição) e transições de desafio (criar apenas com token elegível; arquivar quando sem tokens pontuáveis; reativar quando token elegível reaparece).**
- [ ] **Step 6: Implementar guardas: snapshot vazio com tokens ativos existentes, e redução >20% dos tokens ativos — expor nos resultados sem aplicar automaticamente (aplicação é responsabilidade da Task 4/5).**
- [ ] **Step 7: Adicionar teste de propriedade: reconciliar duas vezes o mesmo snapshot contra o resultado da primeira reconciliação produz delta zero para todos os clãs.**
- [ ] **Step 8: Rodar `pytest backend/tests/test_desafio_reconciliation.py -v` e a suíte backend completa; confirmar que o módulo não importa `google_sheets_client` nem `supabase_client`.**
- [ ] **Step 9: Rodar `git diff --check` e commitar com mensagem `feat: motor puro de snapshot e reconciliação de desafios`.**

**Dependências:** Task 2 (issue #13).

---

### Task 4: Aplicar reconciliação em transação com lock e auditoria [issue #15]

**Files:**
- Create: `backend/migrations/009_apply_desafio_reconciliation.sql`
- Modify: `backend/supabase_client.py`
- Create: `backend/desafio_reconciliation_store.py`
- Create: `backend/tests/test_desafio_reconciliation_store.py`
- Create ou atualizar: teste de integração SQL/RPC conforme infraestrutura disponível (seguir o padrão de `test_desafio_sync_schema_postgres.py` da Task 1)

**Interfaces:**
- Consumes: `ReconciliationPlan`, `DesafioSnapshot` (Task 3); tabelas da Task 1.
- Produces:
  ```python
  apply_reconciliation(plan: ReconciliationPlan, *, confirmed_snapshot_hash: str | None = None) -> AppliedSyncResult
  get_current_desafio_submissions() -> dict[str, CurrentSubmission]
  ```
  `AppliedSyncResult` retorna execução (id, status), contagens, transições e deltas efetivamente aplicados.

- [ ] **Step 1: Escrever testes de atomicidade (falha no meio não deixa estado parcial), lock exclusivo (segunda tentativa concorrente recebe already_running), totais negativos (aborta), versões imutáveis e transições de desafio.**
- [ ] **Step 2: Rodar os testes e confirmar falha.**
- [ ] **Step 3: Implementar a migration `009_apply_desafio_reconciliation.sql` com RPC transacional (lock exclusivo, upsert de estado atual, insert de versão imutável, upsert de execução, aplicação de delta líquido ao total do clã, rejeição de total negativo).**
- [ ] **Step 4: Implementar `desafio_reconciliation_store.py` como wrapper único que chama o RPC (uma única operação transacional de domínio; sem múltiplas gravações não-transacionais soltas no futuro router).**
- [ ] **Step 5: Testar falha intencional no meio da operação (ex.: violação de constraint) e confirmar rollback integral via `pytest`.**
- [ ] **Step 6: Testar duas tentativas concorrentes (ou simular via lock) e confirmar que somente uma aplica; a outra recebe status `already_running`.**
- [ ] **Step 7: Testar execução repetida do mesmo snapshot já aplicado e confirmar delta zero.**
- [ ] **Step 8: Rodar os testes específicos e a suíte backend completa; rodar `git diff --check`; commitar com mensagem `feat: aplicação transacional da reconciliação de desafios com lock e auditoria`.**

**Dependências:** Task 1 (issue #12), Task 3 (issue #14).

---

### Task 5: Integrar sincronização ao Executar Contabilidade e guardas [issue #16]

**Files:**
- Create: `backend/desafio_sync_service.py`
- Modify: `backend/routers/contabilidade.py`
- Modify: `backend/main.py` (somente se um router dedicado for necessário)
- Create: `backend/tests/test_desafio_sync_service.py`
- Modify: `backend/tests/test_contabilidade_integration.py`

**Interfaces:**
- Consumes: `google_sheets_client.fetch_desafio_records` (Task 2), `desafio_sheet_parser.build_parsed_rows` (Task 2), `desafio_reconciliation.build_desafio_snapshot`/`reconcile_desafios` (Task 3), `desafio_reconciliation_store.apply_reconciliation`/`get_current_desafio_submissions` (Task 4).
- Produces:
  ```python
  sync_desafios(*, confirm_snapshot_hash: str | None = None) -> DesafioSyncResult
  ```
  `DesafioSyncResult` cobre status (`success`/`failed`/`awaiting_confirmation`/`already_running`), contagens, deltas por clã, duração, e (quando `awaiting_confirmation`) hash e impacto por clã. `ExecutarResponse` (schema existente do router de contabilidade) ganha campo `desafios: DesafioSyncResult` independente das demais fontes.

- [ ] **Step 1: Escrever testes para: sucesso, delta zero, configuração ausente (`DesafioSheetConfigurationError`), Google Sheets indisponível, planilha vazia com tokens ativos, redução >20%, confirmação válida vinculada a hash, e snapshot alterado entre prévia e confirmação.**
- [ ] **Step 2: Rodar os testes e confirmar falha.**
- [ ] **Step 3: Implementar `desafio_sync_service.sync_desafios` como fachada fina que apenas orquestra leitura → parse → snapshot → reconciliação → (aplicação ou retorno `awaiting_confirmation`) — sem duplicar regras já implementadas nas Tasks 2–4.**
- [ ] **Step 4: Integrar a fachada em `executar_contabilidade`: captura de exceção isolada para a fonte `desafios` (falha não impede outras fontes; falha de outra fonte não duplica desafios).**
- [ ] **Step 5: Implementar endpoint/operação de confirmação que recebe `run_id`/`snapshot_hash`, revalida contra o snapshot atual (se mudou, exige nova prévia) e delega para `apply_reconciliation`.**
- [ ] **Step 6: Rodar os testes específicos, `test_contabilidade_integration.py` e a suíte backend completa; rodar `git diff --check`; commitar com mensagem `feat: integra sincronização de desafios ao Executar Contabilidade`.**

**Dependências:** Task 2 (issue #13), Task 4 (issue #15).

---

### Task 6: Bloquear fluxos legados e remover pontos de coach [issue #17]

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/desafios.py`
- Modify ou remover registro: `backend/routers/desafio_import.py`
- Modify: `backend/routers/contabilidade.py`
- Modify: `backend/supabase_client.py`
- Modify/remover: `backend/tests/test_desafio_import_router.py`, `backend/tests/test_desafio_registros_coach.py`, `backend/tests/test_excluir_desafio_coach.py`, `backend/tests/test_historico_merge_coach_desafio.py`, `backend/tests/test_reprocessar_inclui_desafio.py`
- Create: `backend/tests/test_desafio_legacy_writes_blocked.py`

**Interfaces:**
- Consumes: nenhuma nova; modifica comportamento de endpoints existentes em `backend/routers/desafios.py` (`criar_desafio`, `editar_desafio`, `excluir_desafio`, `criar_registro`, `excluir_registro`) e `backend/routers/desafio_import.py`.
- Produces: mesmos endpoints agora retornam HTTP 410 com mensagem apontando a Google Sheet como fonte oficial, exceto os de leitura que permanecem ativos até serem substituídos pela Task 7.

- [ ] **Step 1: Escrever testes que provem HTTP 410 (com mensagem de domínio) para: criar desafio, editar desafio, excluir desafio, criar registro manual, excluir registro, preview CSV, confirmar CSV.**
- [ ] **Step 2: Escrever testes que provem que qualquer submissão sincronizada por Google Sheets produz delta zero no total individual de coach, e que reprocessar coaches não toca nas novas submissões de desafios.**
- [ ] **Step 3: Rodar os testes e confirmar falha.**
- [ ] **Step 4: Bloquear os handlers mutáveis de `backend/routers/desafios.py` e `backend/routers/desafio_import.py` (ou remover o registro do router em `backend/main.py`), retornando 410 com mensagem clara.**
- [ ] **Step 5: Remover a criação/atualização de `desafio_registros_coach` do fluxo de sincronização (ela não deve existir nesse caminho) e remover desafios da fusão de aliases/reprocessamento de coaches em `backend/supabase_client.py`/`backend/routers/contabilidade.py`.**
- [ ] **Step 6: Atualizar os testes legados que assumiam pontuação de coach ou importação CSV ativa — ajustar expectativas para 410/comportamento bloqueado sem apagar cobertura que ainda faz sentido (ex.: `test_desafio_registros_coach.py` pode virar teste de que a tabela não recebe mais escrita).**
- [ ] **Step 7: Rodar a suíte backend completa e buscar (`grep`) referências remanescentes de escrita em desafios fora da migração administrativa (Task 11).**
- [ ] **Step 8: Rodar `git diff --check`; commitar com mensagem `feat: bloqueia escrita legada de desafios e remove pontuação de coach do fluxo`.**

**Dependências:** Task 1 (issue #12). Deve ser concluída antes da migração administrativa (Task 11) e do rollout (Task 13).

---

### Task 7: Criar APIs somente leitura de desafios e auditoria [issue #18]

**Files:**
- Create: `backend/routers/desafio_auditoria.py` (ou dividir o router existente mantendo responsabilidade clara)
- Modify: `backend/main.py`
- Modify: `backend/supabase_client.py`
- Create: `backend/tests/test_desafio_auditoria_router.py`

**Interfaces:**
- Consumes: `supabase_client.list_desafio_sync_runs`, `list_desafio_submissions_current`, `get_desafio_submission_current`, `list_desafio_submission_versions` (Task 1); tabela `desafios` evoluída (Task 1).
- Produces contratos mínimos:
  - `GET /api/desafios?status=active|archived|all`
  - `GET /api/desafios/{id}`
  - `GET /api/desafios/{id}/submissoes`
  - `GET /api/desafios/submissoes/{token}`
  - `GET /api/desafios/submissoes/{token}/versoes`
  - `GET /api/desafios/sincronizacoes`
  - `GET /api/desafios/sincronizacoes/{run_id}`

- [ ] **Step 1: Escrever testes de contrato, filtros combinados, paginação/ordenação determinística, 404 para desafio/token/execução inexistente, e serialização de datas timezone-aware.**
- [ ] **Step 2: Rodar os testes e confirmar falha.**
- [ ] **Step 3: Implementar as queries necessárias em `backend/supabase_client.py` que ainda não existem (ex.: listar desafios com filtro de status, detalhar desafio com totais por clã).**
- [ ] **Step 4: Implementar schemas Pydantic e as rotas somente leitura em `backend/routers/desafio_auditoria.py`, cuidando da ordem das rotas para não colidir `{id}` com segmentos estáticos como `submissoes` e `sincronizacoes`.**
- [ ] **Step 5: Testar explicitamente que nenhum endpoint deste router realiza escrita (ex.: só métodos GET registrados).**
- [ ] **Step 6: Rodar a suíte backend completa; rodar `git diff --check`; commitar com mensagem `feat: APIs somente leitura de auditoria de desafios`.**

**Dependências:** Task 1 (issue #12), Task 4 (issue #15).

---

### Task 8: Recalcular totais e histórico por Submitted At de cada token [issue #19]

**Files:**
- Modify: `backend/supabase_client.py`
- Modify: `backend/routers/contabilidade.py`
- Modify: `backend/routers/clans.py` (se o ranking agregado passar por esse router)
- Create: `backend/tests/test_desafio_token_totals.py`
- Modify: `backend/tests/test_tipo_filter_breakdown.py`
- Modify: `backend/tests/test_period_totals_floor.py`
- Modify: `backend/tests/test_historico_merge_coach_desafio.py`

**Interfaces:**
- Consumes: `desafio_submissions_current` (Task 1), resultado aplicado da Task 4.
- Produces: `get_period_desafio_totals(...)` e `get_tipo_clan_totals('desafios')` (nomes existentes no código atual, ajustar assinatura se necessário) agora derivados de tokens ativos filtrados por `submitted_at` em América/São_Paulo, em vez do período do desafio.

- [ ] **Step 1: Escrever testes de período usando tokens na virada do dia e do mês em São Paulo (ex.: submitted_at 23:59 vs 00:01 local).**
- [ ] **Step 2: Escrever testes de correção retroativa (mudança de data/clã/validação move ou remove a contribuição do relatório histórico) e de ausência total de contribuição de coach nesses relatórios.**
- [ ] **Step 3: Rodar os testes e confirmar falha.**
- [ ] **Step 4: Implementar as queries derivadas dos tokens ativos (`status = 'active_counted'`) agrupadas por clã e por período de `submitted_at`.**
- [ ] **Step 5: Validar que o total por tipo `desafios` e o total geral do clã reconciliam (soma de `desafio_submissions_current.points` ativos = delta acumulado).**
- [ ] **Step 6: Rodar os testes específicos e a suíte backend completa; rodar `git diff --check`; commitar com mensagem `feat: totais e histórico de desafios derivados de submitted_at por token`.**

**Dependências:** Task 4 (issue #15), Task 7 (issue #18).

---

### Task 9: Exibir resultado da sincronização e confirmar remoções em massa [issue #20]

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Contabilidade.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/src/components/ExecutionResult.tsx`
- Create testes de componente/transformação (adicionar Vitest + Testing Library nesta task se o frontend ainda não tiver harness de teste)

**Interfaces:**
- Consumes: `DesafioSyncResult` retornado por `POST /contabilidade/executar` e endpoint de confirmação (Task 5).
- Produces: componente `ExecutionResult` reutilizável entre Dashboard e Contabilidade; tipos TypeScript equivalentes a `DesafioSyncResult`.

- [ ] **Step 1: Verificar se existe harness de teste frontend (`ls frontend/package.json`, procurar por vitest/jest); se não existir, instalar e configurar Vitest + Testing Library como parte desta task.**
- [ ] **Step 2: Escrever testes para: sucesso, falha isolada de desafios (outras fontes continuam visíveis como sucesso), delta zero, fluxo de confirmação com impacto por clã, e snapshot alterado (deve pedir nova execução).**
- [ ] **Step 3: Rodar os testes e confirmar falha.**
- [ ] **Step 4: Estender os tipos em `frontend/src/api/client.ts` para o resultado de desafios e a chamada de confirmação.**
- [ ] **Step 5: Implementar `ExecutionResult.tsx` mostrando status, linhas, tokens (novos/alterados/inativados/inválidos/conflitos), transições de desafio, deltas por clã e duração; erros de desafios não devem esconder o sucesso das outras fontes.**
- [ ] **Step 6: Implementar o fluxo `requires_confirmation`: exibir impacto, enviar confirmação vinculada a `run_id`+`snapshot_hash`, desabilitar o botão durante a chamada (evitar duplo clique) e tratar `already_running` de forma não destrutiva.**
- [ ] **Step 7: Integrar o componente nas duas telas que executam contabilidade (Contabilidade e Dashboard).**
- [ ] **Step 8: Rodar os testes do frontend, `npm run lint` e `npm run build`; rodar `git diff --check`; commitar com mensagem `feat: exibe resultado de sincronização de desafios e confirmação de remoção em massa`.**

**Dependências:** Task 5 (issue #16).

---

### Task 10: Transformar tela de Desafios em consulta e auditoria [issue #21]

**Files:**
- Reescrever: `frontend/src/pages/Desafios.tsx`
- Remover: `frontend/src/components/ImportarDesafioWizard.tsx`
- Modify: `frontend/src/api/client.ts`
- Create (se necessário): `frontend/src/components/DesafioFilters.tsx`, `frontend/src/components/SubmissionDetail.tsx`, `frontend/src/components/SyncRunDetail.tsx`
- Create testes de componentes e transformações

**Interfaces:**
- Consumes: endpoints somente leitura da Task 7 (`GET /api/desafios`, `/api/desafios/{id}`, `/api/desafios/{id}/submissoes`, `/api/desafios/submissoes/{token}`, `/api/desafios/submissoes/{token}/versoes`, `/api/desafios/sincronizacoes[/{run_id}]`).
- Produces: tela `Desafios.tsx` inteiramente somente leitura.

- [ ] **Step 1: Escrever testes que provem ausência de botões/ações de criar, editar, excluir, registrar manualmente ou importar CSV, e presença dos filtros (desafio, clã, status, token, período) e dos estados (ativo/arquivado).**
- [ ] **Step 2: Escrever testes do detalhe de token (A–I, motivos, link, observação, estado atual) e do histórico de versões/deltas.**
- [ ] **Step 3: Rodar os testes e confirmar falha.**
- [ ] **Step 4: Remover do cliente (`client.ts`) todas as chamadas mutáveis de desafios (criar/editar/excluir desafio ou registro, upload/preview/confirmar CSV).**
- [ ] **Step 5: Implementar lista de desafios (ativos por padrão, toggle para arquivados), totais de submissões/pontos por clã, e os filtros combináveis.**
- [ ] **Step 6: Implementar detalhe de desafio/token com histórico de versões, e navegação de uma execução de sincronização para os tokens que ela afetou.**
- [ ] **Step 7: Remover `ImportarDesafioWizard.tsx` e qualquer referência a ele; tratar estados de carregamento, vazio e erro.**
- [ ] **Step 8: Rodar os testes, `npm run lint`, `npm run build`; rodar `git diff --check`; confirmar (`grep`) que nenhuma chamada mutável de desafios permanece no bundle; commitar com mensagem `feat: transforma tela de Desafios em consulta e auditoria somente leitura`.**

**Dependências:** Task 7 (issue #18), Task 9 (issue #20).

---

### Task 11: Criar migração administrativa com backup, rebuild e rollback [issue #22]

**Files:**
- Create: `backend/admin/__init__.py`
- Create: `backend/admin/migrate_desafios_google_sheet.py`
- Create: `backend/tests/test_migrate_desafios_google_sheet.py`
- Create: `docs/runbooks/migracao-desafios-google-sheets.md`
- Modify: helpers administrativos em `backend/supabase_client.py` somente quando indispensável

**Interfaces:**
- Consumes: pipeline completo das Tasks 2–6 (leitura, parser, snapshot, reconciliação, aplicação, bloqueio de escrita legada).
- Produces: comando CLI `python -m admin.migrate_desafios_google_sheet [--apply] [--confirm-hash HASH]`, dry-run por padrão.

- [ ] **Step 1: Escrever testes de: dry-run não escreve nada, falta de pré-condição bloqueia (config ausente, planilha vazia, coluna F não preenchida), backup é criado e restaurável, aplicação remove pontos antigos de clã e coach, rollback em falha, e reexecução pós-migração com delta zero.**
- [ ] **Step 2: Rodar os testes e confirmar falha.**
- [ ] **Step 3: Implementar o modo dry-run com relatório de totais antigos vs. novos por clã (e por coach, para mostrar o que será removido).**
- [ ] **Step 4: Implementar backup verificável das tabelas afetadas (desafios, desafio_registros, desafio_registros_coach, desafio_importacao_linhas e totais de clã/coach envolvidos) antes de qualquer escrita.**
- [ ] **Step 5: Implementar a aplicação protegida por `--apply` + hash de confirmação do snapshot, dentro de uma transação: obter lock administrativo, remover contribuição antiga de desafios de clãs e coaches, desativar estruturas manuais/CSV antigas sem apagar o backup, aplicar o snapshot inicial usando `apply_reconciliation` (Task 4).**
- [ ] **Step 6: Implementar validações pós-migração (soma de pontos de desafio por clã = tokens ativos elegíveis × valor configurado; nenhum ponto de coach; reexecução imediata com delta zero) e o procedimento de rollback documentado.**
- [ ] **Step 7: Ensaiar contra um ambiente de teste/cópia saneada (não usar dados reais); registrar evidência no runbook.**
- [ ] **Step 8: Escrever `docs/runbooks/migracao-desafios-google-sheets.md` com pré-condições, passos, validações e rollback.**
- [ ] **Step 9: Rodar a suíte backend completa; rodar `git diff --check`; commitar com mensagem `feat: migração administrativa de desafios para Google Sheets com backup e rollback`.**

**Dependências:** Tasks 1, 2, 3, 4, 5, 6, 8 (issues #12, #13, #14, #15, #16, #17, #19).

---

### Task 12: Adicionar observabilidade, segurança operacional e runbook [issue #23]

**Files:**
- Modify: `backend/desafio_sync_service.py`
- Modify: configuração/logging existente do backend
- Create: `backend/tests/test_desafio_sync_observability.py`
- Create: `docs/runbooks/sincronizacao-desafios.md`
- Modify: documentação de deploy/ambiente existente

**Interfaces:**
- Consumes: `desafio_sync_service.sync_desafios` (Task 5).
- Produces: eventos de log estruturado por fase da sincronização, correlacionados por `sync_run_id`.

- [ ] **Step 1: Escrever testes com captura de logs verificando correlação por `sync_run_id` entre fases e ausência total de segredos (service account JSON, tokens de acesso) nos registros.**
- [ ] **Step 2: Rodar os testes e confirmar falha.**
- [ ] **Step 3: Implementar eventos estruturados em cada fase (leitura, parse, snapshot, reconciliação, aplicação) com duração, contagens, status e categoria de erro.**
- [ ] **Step 4: Implementar métricas usando o mecanismo já disponível no projeto; se não houver exportador, persistir no registro de execução (`desafio_sync_runs`) e documentar as consultas SQL para: taxa de sucesso, duração, tokens por estado, deltas, contagem de guardas de 20% acionadas, tentativas concorrentes e idade da última sincronização bem-sucedida.**
- [ ] **Step 5: Escrever `docs/runbooks/sincronizacao-desafios.md` com: variáveis de ambiente e permissão de leitura da service account, operação normal, confirmação acima de 20%, investigação de inválidos/conflitos, recuperação de falhas, e retenção indefinida do backup/auditoria.**
- [ ] **Step 6: Rodar os testes específicos e a suíte backend completa; rodar `git diff --check`; commitar com mensagem `feat: observabilidade e runbook operacional da sincronização de desafios`.**

**Dependências:** Task 5 (issue #16), Task 11 (issue #22).

---

### Task 13: Executar validação E2E e checklist de rollout [issue #24]

**Files:**
- Create: `backend/tests/fixtures/desafios_sheet_sanitized.csv` (ou fixture programática equivalente — sem nomes, links, observações ou tokens reais)
- Create: `backend/tests/test_desafio_e2e.py`
- Create/ajustar: testes E2E do frontend
- Create: `docs/runbooks/release-desafios-google-sheets.md`
- Modify: CI, se necessário, para executar as novas suítes

**Interfaces:**
- Consumes: todo o pipeline das Tasks 1–12.
- Produces: relatório de cobertura dos CA-01 a CA-22 do PRD e checklist de rollout.

- [ ] **Step 1: Criar a fixture sintética com o layout A–I, incluindo casos com duas colunas de clã preenchidas (conflito), linhas incompletas, duplicatas idênticas e conflitantes — sem dados pessoais reais.**
- [ ] **Step 2: Mapear cada CA-01 a CA-22 do PRD (§27) para um teste automatizado ou evidência operacional explícita em `test_desafio_e2e.py`, cobrindo: token válido, múltiplos tokens, duplicatas, conflitos, correções, remoções, datas, arquivamento/reativação, falha isolada, guardas (vazio e 20%), concorrência, atomicidade e ausência de pontos de coach.**
- [ ] **Step 3: Rodar `pytest backend/tests -v` e cada teste novo isoladamente.**
- [ ] **Step 4: Rodar os testes do frontend, `npm run lint`, `npm run build`.**
- [ ] **Step 5: Ensaiar dry-run, migração (`--apply`), rollback e rebuild da Task 11 em ambiente de teste; executar a sincronização duas vezes seguidas e confirmar delta zero.**
- [ ] **Step 6: Confirmar que fluxos manuais/CSV estão inacessíveis (410) e que nenhum ponto de coach é gerado, ponta a ponta.**
- [ ] **Step 7: Escrever `docs/runbooks/release-desafios-google-sheets.md` com o checklist de rollout: `GSHEET_DESAFIOS_SPREADSHEET_ID`, `GSHEET_DESAFIOS_SHEET_NAME`, confirmação de acesso da service account, confirmação de que as 85 linhas históricas têm a coluna F preenchida, e janela operacional da migração.**
- [ ] **Step 8: Rodar `git diff --check`; commitar com mensagem `test: valida E2E os critérios de aceitação e prepara checklist de rollout`.**

**Dependências:** Tasks 9, 10, 12 (issues #20, #21, #23) e todas as anteriores.
