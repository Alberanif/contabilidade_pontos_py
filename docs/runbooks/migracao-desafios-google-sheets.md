# Runbook — Migração administrativa de desafios para a Google Sheet

Migração **única e irreversível na prática**: remove dos totais reais de clã e
de coach a contribuição dos desafios manuais e importados por CSV, arquiva as
estruturas antigas e reconstrói a pontuação de desafios exclusivamente a partir
da planilha oficial (PRD RF-20, seção 21).

Rodada com `--apply`, ela **altera pontuação de produção**. Leia este documento
inteiro antes de executar.

---

## 1. O que a migração faz — e o que ela não faz

Comando:

```
cd backend
python -m admin.migrate_desafios_google_sheet [--apply] [--confirm-hash HASH]
                                              [--confirm-mass-removal]
```

Sem `--apply`, é **dry-run**: lê a planilha, lê o estado atual e imprime o
relatório de antes/depois. Nada é escrito.

Com `--apply`, executa **duas fases atômicas sequenciais**:

| Fase | Onde | O que faz | Transação |
|---|---|---|---|
| 1 | RPC `migrate_desafio_legacy_contribution` (migração `010`) | advisory lock, backup verificável, subtração explícita da contribuição legada em clãs e coaches, arquivamento dos desafios manuais/CSV | uma transação do Postgres |
| 2 | `desafio_sync_service.sync_desafios` → RPC `apply_desafio_reconciliation` (migração `009`) | aplica o primeiro snapshot da planilha oficial | outra transação do Postgres |

> **Isto não é uma transação única cobrindo as duas fases.** O cliente REST do
> Supabase não mantém uma transação aberta entre chamadas, e replicar o pipeline
> de leitura/parse/snapshot/reconciliação dentro de uma função SQL gigante
> duplicaria uma fronteira de atomicidade já revisada (migração `009`). Cada
> fase é atômica isoladamente; o desfecho "Fase 1 commitada, Fase 2 falhou" é
> possível e está coberto na seção 7 deste runbook — é justamente para ele que o
> backup da Fase 1 existe.

As duas fases usam **a mesma chave de advisory lock** (`7345901220834561`), de
modo que a migração e uma sincronização normal nunca se intercalam.

Garantias da Fase 1:

- **Nada é apagado.** Os desafios legados passam a `status = 'arquivado'` e
  `contabilizar_pontos = FALSE`; `desafio_registros`,
  `desafio_registros_coach` e `desafio_importacao_linhas` continuam intactos
  (o marcador fica no `desafios`, que é o pai por FK de todos eles e o portão
  por onde todas as leituras de pontos passam).
- **Nenhum total é truncado para zero.** A subtração é explícita
  (`total_atual - contribuição_legada`); se algum total ficaria negativo, a
  transação inteira aborta (PRD RF-19).
- **Só pode ser aplicada uma vez** (índice único no banco + verificação
  explícita): uma segunda execução subtrairia os mesmos pontos de novo.

---

## 2. Ensaio obrigatório em ambiente de teste — **ainda não realizado**

> **Esta seção descreve trabalho que NÃO foi executado durante a implementação.**
> O ambiente onde a Task 11 foi desenvolvida não tem PostgreSQL nem Docker
> disponíveis, então o ensaio contra uma cópia saneada **precisa ser feito pelo
> operador** antes de qualquer `--apply` em produção. Os testes de integração
> `backend/tests/test_migrate_desafios_legacy_postgres.py` existem e cobrem o
> comportamento SQL, mas **pulam** sem `TEST_POSTGRES_DSN` — foi o que aconteceu
> no ambiente de desenvolvimento.

Antes de liberar a janela de produção, execute o checklist abaixo contra uma
**cópia saneada** do banco (nunca dados reais expostos) e registre a evidência
aqui mesmo, neste arquivo, no commit correspondente.

| # | Verificação | Como | Evidência | Data / responsável |
|---|---|---|---|---|
| 1 | Suíte de integração SQL passa | `TEST_POSTGRES_DSN=... pytest backend/tests/test_migrate_desafios_legacy_postgres.py -v` | saída do pytest | |
| 2 | Suíte de integração da sincronização passa | `TEST_POSTGRES_DSN=... pytest backend/tests/test_desafio_reconciliation_apply_postgres.py -v` | saída do pytest | |
| 3 | Migrations `008`, `009` e `010` aplicam na cópia | psql | log | |
| 4 | Dry-run na cópia bate com os números conferidos manualmente | `python -m admin.migrate_desafios_google_sheet` | relatório colado | |
| 5 | `--apply` na cópia termina com as três validações `[OK]` | `... --apply --confirm-hash <hash>` | relatório colado | |
| 6 | Reexecução imediata na cópia produz delta zero | rodar `--apply` de novo (deve pular a Fase 1 e não mover nada) | relatório colado | |
| 7 | Restauração na cópia devolve os totais originais | `SELECT restore_desafio_legacy_migracao(<id>);` | totais antes/depois | |
| 8 | Backup da cópia tem checksum recomputável | consulta da seção 8 | checksum | |
| 9 | Restauração é recusada depois de uma sincronização bem-sucedida, inclusive com `p_force` | `SELECT restore_desafio_legacy_migracao(<id>, TRUE);` **deve falhar** | mensagem de erro | |
| 10 | Roteiro manual da seção 7.4 ensaiado na cópia | seção 7.4, do `BEGIN` ao `COMMIT` | saída do passo 8 | |
| 11 | Roteiro da 7.4 ensaiado **com uma sincronização anterior à Fase 1** | na cópia, rodar um sync bem-sucedido, depois `--apply`, depois a 7.4 | passo 8 vazio e totais iguais a `clan_before − planilha_antes_da_fase_1` | |

Enquanto qualquer linha desta tabela estiver vazia, **não execute `--apply` em
produção**.

---

## 3. Pré-condições (PRD 21.1)

- [ ] `GOOGLE_SERVICE_ACCOUNT_JSON`, `GSHEET_DESAFIOS_SPREADSHEET_ID` e
      `GSHEET_DESAFIOS_SHEET_NAME` configurados no ambiente de produção.
- [ ] Service account com acesso **de leitura** à planilha oficial.
- [ ] `POINTS_PER_DESAFIO_SUBMISSION` com o valor acordado (padrão `10`).
- [ ] **Coluna F (Desafio) preenchida em todas as linhas com token.** A CLI
      bloqueia e lista as linhas faltantes — inclusive as ~85 linhas históricas
      citadas no PRD.
- [ ] Backup do banco (snapshot do Supabase) habilitado e testado.
- [ ] Migrations `008`, `009` e `010` aplicadas em produção.
- [ ] Nenhuma contabilidade em andamento e ninguém editando a planilha durante a
      janela.
- [ ] Ensaio da seção 2 concluído e registrado.
- [ ] Aprovação explícita do responsável pelas regras de pontuação.

A CLI verifica sozinha o que consegue verificar (configuração ausente, planilha
vazia, coluna F em branco, totais que ficariam negativos) e **aborta sem
escrever nada** nesses casos.

---

## 4. Passo a passo

### 4.1 Aplicar as migrations

```
psql "$DATABASE_URL" -f backend/migrations/008_add_desafio_google_sync.sql
psql "$DATABASE_URL" -f backend/migrations/009_apply_desafio_reconciliation.sql
psql "$DATABASE_URL" -f backend/migrations/010_migrate_legacy_desafio_contribution.sql
```

`010` é aditiva: cria `desafio_legacy_migracoes`,
`desafio_legacy_migracao_backup` e as três funções
(`desafio_legacy_migration_report`, `migrate_desafio_legacy_contribution`,
`restore_desafio_legacy_migracao`). Aplicá-la não altera nenhum dado.

### 4.2 Dry-run

```
cd backend
python -m admin.migrate_desafios_google_sheet
```

O relatório mostra, por clã: total atual → contribuição legada removida → total
após a Fase 1 → pontos vindos da planilha → total após a Fase 2. E, por coach:
total atual → contribuição legada removida → total após a Fase 1 (desafios
deixam de pontuar o ranking individual, definitivamente).

**Confira os números com o responsável pelas regras de pontuação antes de
prosseguir.** Guarde o relatório: ele é o registro de quem aprovou o quê.

No fim, o dry-run imprime o `snapshot_hash` e o comando exato do próximo passo.

### 4.3 Aplicar

```
python -m admin.migrate_desafios_google_sheet --apply --confirm-hash <hash do dry-run>
```

O `--confirm-hash` é uma pré-condição de frescor: se a planilha mudou entre o
dry-run e o `--apply`, o hash não bate e a CLI recusa — refaça o dry-run e
reveja os números.

`--confirm-mass-removal` só é necessário se o plano tirar mais de 20% dos tokens
ativos de pontuação (RF-17). **Em uma migração inicial isso não deve acontecer**
(não há tokens ativos ainda). Se acontecer, é sinal de que o estado não é o que
se pensava: pare e investigue antes de usar a flag.

Guarde a saída completa: ela contém o `migracao_id`, o número de linhas do
backup e o `backup_checksum`.

---

## 5. Validações pós-migração (PRD 21.3)

A CLI executa as três primeiras automaticamente e falha (código `6`) se alguma
não passar:

- [x] soma dos pontos de desafio por clã = tokens ativos elegíveis × valor
      configurado;
- [x] nenhum ponto de desafio no ranking individual de coach;
- [x] reexecução imediata da sincronização com delta zero.

Confira manualmente as demais:

- [ ] Dashboard geral e filtro **Desafios** mostram os mesmos agregados do banco.
- [ ] Relatórios por período usam a data individual dos tokens (um token movido
      de data muda de período na execução seguinte).
- [ ] A tela de Desafios está somente leitura e a auditoria lista a execução da
      Fase 2.
- [ ] O backup continua acessível e fora das consultas normais (seção 8).

---

## 6. Códigos de saída

| Código | Significado | Estado do banco |
|---|---|---|
| `0` | migração concluída e validada | Fase 1 e Fase 2 aplicadas |
| `2` | pré-condição não satisfeita (config, planilha vazia, coluna F, total ficaria negativo) | **intacto** |
| `3` | falta confirmação, hash divergente ou remoção em massa não confirmada | **intacto** |
| `4` | Fase 1 falhou | **intacto** (transação abortada) |
| `5` | Fase 1 commitada, **Fase 2 falhou** | ver seção 7 |
| `6` | as duas fases aplicaram, mas uma validação falhou | ver seção 7 |

---

## 7. Rollback

### 7.1 Falha na Fase 1 (código `4`)

Nada a fazer. A Fase 1 é uma transação única do Postgres: o aborto desfaz o
registro da migração, o backup, as subtrações e o arquivamento. A mensagem de
erro identifica a causa:

| Marcador na mensagem | Causa | O que fazer |
|---|---|---|
| `desafio_legacy_migration_negative_clan_total` | um clã ficaria com total negativo | investigar a divergência contábil; a migração nunca trunca para zero |
| `desafio_legacy_migration_negative_coach_total` | idem, para um coach | idem |
| `desafio_legacy_migration_missing_clan_total` / `..._coach_total` | há contribuição legada sem linha de total correspondente | corrigir os dados de origem |
| `desafio_legacy_migration_already_applied` | a Fase 1 já rodou antes | reexecutar a CLI: ela pula a Fase 1 e refaz só a Fase 2 |
| `desafio_legacy_migration_locked` | uma sincronização ou outra migração está em andamento | esperar e repetir |

### 7.2 Fase 1 commitada e Fase 2 falhou (código `5`)

**Como reconhecer:** a CLI imprime `Fase 2 FALHOU (...)` seguido de `ATENÇÃO: a
Fase 1 (migração #N) JÁ FOI COMMITADA`. Confirme no banco:

```sql
SELECT id, status, started_at, finished_at, backup_rows, backup_checksum
  FROM desafio_legacy_migracoes ORDER BY id DESC;
-- status = 'applied' e nenhuma linha 'succeeded' em desafio_sync_runs
SELECT id, status, started_at FROM desafio_sync_runs ORDER BY id DESC LIMIT 5;
```

Nesse estado os pontos legados **já saíram** dos totais e os pontos da planilha
**ainda não entraram** — o ranking está temporariamente subestimado. Há dois
caminhos:

**(a) Concluir — preferido.** Corrija a causa da falha (acesso à planilha,
indisponibilidade, etc.) e reexecute a CLI normalmente:

```
python -m admin.migrate_desafios_google_sheet                       # confere
python -m admin.migrate_desafios_google_sheet --apply --confirm-hash <hash>
```

A CLI detecta `ja_migrado = true`, **pula a Fase 1** e executa somente a Fase 2.
Isso é seguro: a Fase 1 nunca roda duas vezes.

**(b) Reverter.** Restaure a partir do backup da Fase 1:

```sql
SELECT restore_desafio_legacy_migracao(<migracao_id>);
```

A função devolve os totais de clã e de coach exatamente aos valores anteriores
(a partir de `clan_before` / `coach_before`) e desarquiva os desafios legados a
partir do backup. Depois de uma restauração, a migração fica em
`status = 'rolled_back'` e uma nova Fase 1 pode ser executada do zero.

> **Escopo:** esta função só serve para este desfecho — Fase 1 commitada,
> Fase 2 **nunca** aplicada. Ela **recusa-se incondicionalmente** a rodar se
> existir uma `desafio_sync_runs` com `status = 'succeeded'` posterior à
> migração (erro `desafio_legacy_migration_restore_blocked_by_sync`). O
> segundo argumento `p_force` **não é mais um bypass**: passá-lo falha com
> `desafio_legacy_migration_force_removed`. Se a Fase 2 já aplicou, vá para a
> **seção 7.4** — não existe rollback de um comando só, e não há como forçar
> um.

### 7.3 As duas fases aplicaram, mas uma validação falhou (código `6`)

Os pontos já estão no estado novo. **Não reverta por reflexo**: leia a falha
impressa pela CLI.

- Divergência entre pontos por clã e `tokens elegíveis × valor`: normalmente
  significa que a planilha mudou durante a janela. Rode a sincronização de novo
  (`Executar Contabilidade`) e reconfira.
- Pontos de desafio sobrando no ranking de coach: indica desafio legado que não
  foi arquivado. Investigue com a consulta da seção 8 antes de qualquer escrita.
- Reexecução sem delta zero: alguém editou a planilha entre a Fase 2 e a
  validação. Confirme com o responsável e reconfira.

Se, mesmo assim, a decisão for reverter tudo e voltar à contabilidade legada,
**não existe comando único** — `restore_desafio_legacy_migracao` recusa
(inclusive com `p_force`, que deixou de ser um bypass). Siga a seção 7.4.

### 7.4 Reverter depois que a Fase 2 já aplicou — roteiro manual

> **Último recurso.** Prefira sempre corrigir para frente (7.3). Este roteiro
> devolve a pontuação à contabilidade legada e desliga a pontuação vinda da
> planilha; ele é longo de propósito — cada passo tem uma conferência que pode
> abortar tudo.

#### 7.4.1 Por que não há um comando só

`restore_desafio_legacy_migracao` restaura **apenas** os totais de clã/coach
(`clan_before` / `coach_before`) e o estado dos desafios legados. Ela nunca
tocou — e continua não tocando — em `desafio_submissions_current`, em
`desafio_submission_versions` nem nos desafios `origem = 'google_sheets'`
criados pela Fase 2. Rodá-la nesse estado (o antigo `p_force := TRUE`) deixava
o banco assim:

- os pontos da planilha saíam de `pontos_ultimate_totais_por_clan`, mas
- todo token continuava `active_counted` em `desafio_submissions_current`, e a
  sincronização seguinte, ao comparar planilha × estado, encontrava **delta
  zero** — nunca somava os pontos de volta;
- os desafios legados voltavam a `contabilizar_pontos = TRUE` enquanto a fatia
  "Desafios" do dashboard (`get_tipo_clan_totals('desafios')`, que lê os
  tokens, não `desafio_registros`) continuava reportando os pontos da planilha
  que já não estavam no total do clã.

Resultado: divergência contábil permanente, e nenhuma sincronização posterior a
consertava. Por isso a guarda é incondicional agora.

E por que a função não desfaz a Fase 2 sozinha: **nada no schema diz qual
`desafio_sync_runs` foi a Fase 2**. O registro da migração é gravado antes de
essa execução existir; a reexecução documentada em 7.2a pode produzir uma
segunda execução `succeeded`; a própria seção 7.3 manda ressincronizar antes de
decidir reverter. E as versões por token são imutáveis por trigger (migração
`008`), com `desafio_submissions_current` como alvo de FK — as linhas da Fase 2
não podem ser apagadas. Escolher a execução errada para desfazer seria pior que
recusar.

#### 7.4.2 Antes de começar

- [ ] **Congele a janela.** Ninguém roda `Executar Contabilidade` (ele
      sincroniza desafios a cada execução) e ninguém edita a planilha.
- [ ] **Snapshot do banco** (PITR/dump) tirado agora, antes de qualquer escrita.
- [ ] Anote o `<migracao_id>` (`SELECT id FROM desafio_legacy_migracoes WHERE
      status = 'applied';`).
- [ ] Tenha um `psql` conectado como papel de serviço. **Tudo abaixo roda em
      uma única transação**, aberta com o mesmo advisory lock da sincronização:

```sql
BEGIN;
SELECT pg_advisory_xact_lock(7345901220834561);
```

Se qualquer conferência abaixo devolver linha onde o texto diz "deve ser
vazio", execute `ROLLBACK;` e pare. Substitua `<id>` pelo `<migracao_id>` em
todas as consultas.

As duas tabelas temporárias criadas no roteiro (`rev_planilha_por_clan`, no
passo 2, e `rev_neutralizados`, no passo 5) são `ON COMMIT DROP`: somem no
`COMMIT` **e** no `ROLLBACK`. Elas existem para uma coisa só — amarrar, no
passo 8, o que o passo 3 subtraiu ao que o passo 5 de fato zerou.

#### 7.4.3 Passo 1 — quais execuções serão desfeitas

```sql
SELECT r.id, r.started_at, r.finished_at, r.snapshot_hash, r.clan_deltas,
       r.started_at >= (SELECT started_at FROM desafio_legacy_migracoes WHERE id = <id>)
         AS posterior_a_migracao
  FROM desafio_sync_runs r
 WHERE r.status = 'succeeded'
 ORDER BY r.started_at;
```

Cole o resultado no registro do incidente. **Todas** essas execuções serão
revertidas — não só a Fase 2, e não só as posteriores à migração. Este roteiro
desliga o pipeline da planilha por inteiro: o passo 5 neutraliza **todo** token,
independentemente de qual execução o viu primeiro.

Uma execução com `posterior_a_migracao = false` é possível e não é anomalia:
a migração `009` é aplicada em produção antes de a CLI rodar (§4.1) e
`Executar Contabilidade` sincroniza desafios em toda execução, então pode haver
sincronização bem-sucedida **anterior** à Fase 1. A coluna é informativa aqui;
ela volta a importar no passo 4, onde o retrato `clan_before` já contém essa
contribuição.

Não existe reversão parcial suportada: se alguma dessas execuções não deveria
ser desfeita, `ROLLBACK;` e reavalie.

#### 7.4.4 Passo 2 — quanto a planilha tem hoje nos totais de clã

A fonte de verdade da subtração é **o estado atual por token**, não o log de
execuções. Motivo: o passo 5 zera todo token que não esteja já em
`inactive_missing`, sem filtro de data. Subtrair um recorte menor que esse (por
exemplo, só as execuções posteriores à migração) deixaria nos totais de clã a
contribuição das execuções anteriores, com a fatia "Desafios" marcando zero —
exatamente a divergência silenciosa que este roteiro existe para evitar.

Primeiro a invariante que torna essa fonte utilizável. **Deve vir vazia:**

```sql
-- No pipeline da planilha, `points > 0` só existe em `active_counted`, e um
-- `active_counted` sempre tem clã (o parser marca `invalid`/`conflicted` quando
-- não consegue resolver o clã, e `points = 0` para tudo que não é elegível).
-- Se algo aparecer aqui, o passo 3 subtrairia menos do que o passo 5 zera:
-- `ROLLBACK;` e investigue antes de qualquer escrita.
SELECT token, status, clan, points
  FROM desafio_submissions_current
 WHERE (points <> 0 AND status <> 'active_counted')
    OR (status = 'active_counted' AND clan IS NULL)
 ORDER BY token;
```

Agora materialize a fonte, dentro da mesma transação:

```sql
CREATE TEMP TABLE rev_planilha_por_clan ON COMMIT DROP AS
SELECT clan, SUM(points)::INTEGER AS pontos
  FROM desafio_submissions_current
 WHERE status = 'active_counted'
 GROUP BY clan;

SELECT clan, pontos FROM rev_planilha_por_clan ORDER BY clan;
```

Cole esse resultado no registro do incidente — é o número que o passo 3 vai
subtrair.

Duas reconstruções independentes têm de chegar ao mesmo número, clã a clã, e
elas somam **todas** as execuções `succeeded` (sem filtro de data), que é
exatamente o escopo da tabela acima. A identidade vale por construção: cada
execução registra `-pontos` no clã antigo e `+pontos` no novo, de modo que a
soma de todas as execuções telescopa nos pontos que cada token carrega hoje.

```sql
-- as três fontes têm de fechar; esta consulta deve vir VAZIA
WITH por_execucao AS (
  SELECT d.key AS clan, SUM(d.value::INTEGER) AS pontos
    FROM desafio_sync_runs r
    CROSS JOIN LATERAL JSONB_EACH_TEXT(r.clan_deltas) AS d
   WHERE r.status = 'succeeded'
   GROUP BY d.key
), por_token AS (
  SELECT d.key AS clan, SUM(d.value::INTEGER) AS pontos
    FROM desafio_submission_versions v
    JOIN desafio_sync_runs r ON r.id = v.sync_run_id
    CROSS JOIN LATERAL JSONB_EACH_TEXT(v.clan_deltas) AS d
   WHERE r.status = 'succeeded'
   GROUP BY d.key
), chaves AS (
  SELECT clan FROM rev_planilha_por_clan
  UNION SELECT clan FROM por_execucao
  UNION SELECT clan FROM por_token
)
SELECT k.clan,
       COALESCE(s.pontos, 0) AS estado_atual,
       COALESCE(e.pontos, 0) AS por_execucao,
       COALESCE(t.pontos, 0) AS por_token
  FROM chaves k
  LEFT JOIN rev_planilha_por_clan s ON s.clan IS NOT DISTINCT FROM k.clan
  LEFT JOIN por_execucao          e ON e.clan IS NOT DISTINCT FROM k.clan
  LEFT JOIN por_token             t ON t.clan IS NOT DISTINCT FROM k.clan
 WHERE COALESCE(s.pontos, 0) <> COALESCE(e.pontos, 0)
    OR COALESCE(s.pontos, 0) <> COALESCE(t.pontos, 0)
 ORDER BY k.clan;
```

`por_execucao` × `por_token` divergirem é impossível pelo pipeline — a migração
`009` recusa aplicar um plano em que o agregado da execução não bate com a soma
por token —, então qualquer linha aqui significa escrita fora do pipeline.
Se vier linha: `ROLLBACK;` e investigue antes de qualquer coisa.

#### 7.4.5 Passo 3 — tirar os pontos da planilha dos totais de clã

Sempre por delta, nunca por valor absoluto (o absoluto apagaria toda
contabilidade legítima feita depois da migração). A fonte é a tabela do passo 2
— o mesmo conjunto que o passo 5 vai zerar:

```sql
UPDATE pontos_ultimate_totais_por_clan t
   SET total_pontos = t.total_pontos - s.pontos
  FROM rev_planilha_por_clan s
 WHERE t.clan = s.clan;
```

Conferências imediatas — **as duas devem vir vazias**:

```sql
-- nenhum clã com pontos da planilha ficou sem linha de total (o UPDATE acima
-- não teria casado com nada, silenciosamente)
SELECT s.clan, s.pontos
  FROM rev_planilha_por_clan s
  LEFT JOIN pontos_ultimate_totais_por_clan t ON t.clan = s.clan
 WHERE t.clan IS NULL;

-- nenhum total negativo (nunca truncar para zero — mesma regra da migração)
SELECT clan, total_pontos FROM pontos_ultimate_totais_por_clan WHERE total_pontos < 0;
```

#### 7.4.6 Passo 4 — devolver a contribuição legada removida pela Fase 1

Também por delta, a partir de `clan_removido` / `coach_removido` (o que a Fase 1
efetivamente subtraiu):

```sql
UPDATE pontos_ultimate_totais_por_clan t
   SET total_pontos = t.total_pontos + (m.clan_removido->>t.clan)::INTEGER
  FROM desafio_legacy_migracoes m
 WHERE m.id = <id> AND m.clan_removido ? t.clan;

UPDATE pontos_ultimate_totais_por_coach t
   SET total_pontos = t.total_pontos + (m.coach_removido->>t.coach)::INTEGER,
       updated_at = NOW()
  FROM desafio_legacy_migracoes m
 WHERE m.id = <id> AND m.coach_removido ? t.coach;
```

Conferência contra o retrato de antes da migração (é o mesmo `clan_before` /
`coach_before` que a função automática usaria).

Atenção ao termo `planilha_antes_da_fase_1`: `clan_before` é o total **imediato
antes da Fase 1** e, por definição, já contém o efeito líquido de qualquer
execução `succeeded` anterior a ela (as `posterior_a_migracao = false` do passo
1). Esses pontos saíram no passo 3, e com razão — depois da reversão a planilha
não pode contribuir com nada. Numa migração inicial esse termo é `0` para todos
os clãs; se não for, ele é a explicação exata da diferença, e não um desvio.

```sql
WITH planilha_pre AS (
  SELECT d.key AS clan, SUM(d.value::INTEGER) AS pontos
    FROM desafio_sync_runs r
    CROSS JOIN LATERAL JSONB_EACH_TEXT(r.clan_deltas) AS d
   WHERE r.status = 'succeeded'
     AND r.started_at < (SELECT started_at FROM desafio_legacy_migracoes WHERE id = <id>)
   GROUP BY d.key
)
SELECT t.clan,
       t.total_pontos                              AS agora,
       (m.clan_before->>t.clan)::INTEGER           AS antes_da_migracao,
       COALESCE(p.pontos, 0)                       AS planilha_antes_da_fase_1,
       t.total_pontos - (m.clan_before->>t.clan)::INTEGER + COALESCE(p.pontos, 0)
                                                   AS diferenca
  FROM pontos_ultimate_totais_por_clan t
  JOIN desafio_legacy_migracoes m ON m.id = <id>
  LEFT JOIN planilha_pre p ON p.clan = t.clan
 WHERE m.clan_before ? t.clan
 ORDER BY t.clan;

SELECT t.coach,
       t.total_pontos                               AS agora,
       (m.coach_before->>t.coach)::INTEGER          AS antes_da_migracao,
       t.total_pontos - (m.coach_before->>t.coach)::INTEGER AS diferenca
  FROM pontos_ultimate_totais_por_coach t
  JOIN desafio_legacy_migracoes m ON m.id = <id>
 WHERE m.coach_before ? t.coach
 ORDER BY t.coach;
```

A consulta de coach não tem o termo da planilha porque o pipeline da planilha
nunca escreve em `pontos_ultimate_totais_por_coach` (desafios deixaram de
pontuar o ranking individual).

Nas duas, `diferenca` só pode ser diferente de zero por contabilidade legítima
rodada **depois** da migração. Se houver uma diferença que você não sabe
explicar: `ROLLBACK;`.

#### 7.4.7 Passo 5 — neutralizar o estado derivado da planilha

**É o passo que a restauração automática nunca fez, e o motivo de a guarda ser
incondicional.** As linhas de `desafio_submissions_current` não podem ser
apagadas: `desafio_submission_versions.token` as referencia e aquela tabela é
imutável por trigger (`008`). O que se faz é colocá-las exatamente no estado que
uma sincronização normal produz para um token que saiu da planilha:

São duas instruções com **exatamente o mesmo `WHERE`**, uma atrás da outra
dentro da transação (ninguém mais escreve: o advisory lock está retido e a
janela está congelada). A primeira só registra o que a segunda vai zerar; é ela
que o passo 8 confronta com o passo 3.

```sql
-- 5a — registra, antes de escrever, quantos pontos serão zerados por clã
CREATE TEMP TABLE rev_neutralizados ON COMMIT DROP AS
SELECT clan, SUM(points)::INTEGER AS pontos
  FROM desafio_submissions_current
 WHERE status <> 'inactive_missing'
 GROUP BY clan
HAVING SUM(points) <> 0;

-- 5b — neutraliza
UPDATE desafio_submissions_current
   SET status = 'inactive_missing',
       points = 0,
       inactivated_at = NOW(),
       updated_at = NOW()
 WHERE status <> 'inactive_missing';
```

Isto **não** mexe em `pontos_ultimate_totais_por_clan` — os totais já foram
corrigidos no passo 3, a partir do mesmo conjunto de tokens que o `WHERE` acima
alcança. Note que `clan` é preservado, do mesmo jeito que a migração `009` faz
ao inativar um token.

Por que este estado e não outro: com `points = 0` e `inactive_missing`, todo
leitor fica coerente (a fatia "Desafios" passa a mostrar zero, que é a verdade
depois da reversão) e, se um dia se decidir voltar ao pipeline da planilha, a
sincronização seguinte enxerga cada token como **reaparecido** e soma os pontos
de volta com o delta correto. É isso que torna o banco ressincronizável — o que
o antigo `p_force := TRUE` destruía.

Arquive também os desafios criados pela planilha (sem apagar nada):

```sql
UPDATE desafios
   SET status = 'arquivado',
       arquivado_at = COALESCE(arquivado_at, NOW()),
       updated_at = NOW()
 WHERE origem = 'google_sheets' AND status <> 'arquivado';
```

#### 7.4.8 Passo 6 — desarquivar os desafios legados

Exatamente o que a função automática faz, a partir do backup imutável:

```sql
UPDATE desafios d
   SET status = b.conteudo->>'status',
       contabilizar_pontos = (b.conteudo->>'contabilizar_pontos')::BOOLEAN,
       arquivado_at = (b.conteudo->>'arquivado_at')::TIMESTAMPTZ,
       updated_at = NOW()
  FROM desafio_legacy_migracao_backup b
 WHERE b.migracao_id = <id>
   AND b.tabela = 'desafios'
   AND d.id = (b.conteudo->>'id')::INTEGER;
```

#### 7.4.9 Passo 7 — marcar a migração como revertida

Sem isso o índice único parcial impede uma futura Fase 1 (só pode existir uma
migração `applied`):

```sql
UPDATE desafio_legacy_migracoes
   SET status = 'rolled_back', rolled_back_at = NOW()
 WHERE id = <id> AND status = 'applied';
```

#### 7.4.10 Passo 8 — conferência final, ainda dentro da transação

As quatro **devem vir vazias / zero**:

```sql
-- O passo 3 subtraiu exatamente o que o passo 5 zerou.
--
-- É a conferência que amarra os dois escopos. Enquanto o passo 3 subtraía só
-- as execuções posteriores à migração e o passo 5 zerava todo token, uma
-- sincronização anterior à Fase 1 deixava o total do clã inflado pela sua
-- contribuição, com a fatia "Desafios" em zero — divergência que nenhuma das
-- outras conferências enxerga (elas olham negativos, tokens ativos e
-- restauração dos legados, e todas as três passariam).
WITH chaves AS (
  SELECT clan FROM rev_planilha_por_clan
  UNION SELECT clan FROM rev_neutralizados
)
SELECT k.clan,
       COALESCE(s.pontos, 0) AS subtraido_no_passo_3,
       COALESCE(n.pontos, 0) AS zerado_no_passo_5
  FROM chaves k
  LEFT JOIN rev_planilha_por_clan s ON s.clan IS NOT DISTINCT FROM k.clan
  LEFT JOIN rev_neutralizados     n ON n.clan IS NOT DISTINCT FROM k.clan
 WHERE COALESCE(s.pontos, 0) <> COALESCE(n.pontos, 0)
 ORDER BY k.clan;

-- nenhum total negativo
SELECT 'clan' AS escopo, clan AS chave, total_pontos
  FROM pontos_ultimate_totais_por_clan WHERE total_pontos < 0
UNION ALL
SELECT 'coach', coach, total_pontos
  FROM pontos_ultimate_totais_por_coach WHERE total_pontos < 0;

-- nenhum token ainda pontuando pela planilha
SELECT COUNT(*) FROM desafio_submissions_current WHERE status = 'active_counted';

-- todo desafio legado de volta ao estado do backup
SELECT COUNT(*)
  FROM desafio_legacy_migracao_backup b
  JOIN desafios d ON d.id = (b.conteudo->>'id')::INTEGER
 WHERE b.migracao_id = <id> AND b.tabela = 'desafios'
   AND (d.status IS DISTINCT FROM b.conteudo->>'status'
     OR d.contabilizar_pontos IS DISTINCT FROM (b.conteudo->>'contabilizar_pontos')::BOOLEAN);
```

Se tudo bateu:

```sql
COMMIT;
```

Caso contrário, `ROLLBACK;` — nada terá acontecido.

#### 7.4.11 Depois do commit

- **Desligue o pipeline da planilha**, ou a próxima `Executar Contabilidade`
  ressomará os pontos (por desenho: os tokens voltam como "reaparecidos").
  Basta esvaziar `GSHEET_DESAFIOS_SPREADSHEET_ID` (ou revogar o acesso da
  service account) no ambiente: a sincronização passa a terminar em `failed`,
  que não escreve nada e não bloqueia o resto da contabilidade.
- **Espere que a fatia "Desafios" mostre zero.** Depois da reversão, os pontos
  de desafio estão nos totais de clã (contribuição legada), mas as telas de
  desafio leem os tokens da planilha, que agora estão inativos. Não há mais
  caminho de leitura legado no app — é uma das razões para preferir 7.3.
- Registre no incidente: `<migracao_id>`, as execuções listadas no passo 1 (com
  a coluna `posterior_a_migracao`), `rev_planilha_por_clan` do passo 2, os
  números do passo 4 (incluindo `planilha_antes_da_fase_1`) e a saída completa
  do passo 8 — as tabelas temporárias somem no `COMMIT`, então o que não foi
  colado se perde.
- Uma nova Fase 1 pode ser executada do zero quando a causa estiver resolvida
  (a migração está `rolled_back`).

---

## 8. O backup

Retenção **indeterminada** (PRD seção 19) e **imutável**: `UPDATE`, `DELETE` e
`TRUNCATE` em `desafio_legacy_migracao_backup` são recusados por trigger.

```sql
-- Cabeçalho das migrações
SELECT id, status, started_at, finished_at, rolled_back_at,
       desafios_arquivados, backup_rows, backup_checksum,
       clan_before, clan_after, clan_removido,
       coach_before, coach_after, coach_removido
  FROM desafio_legacy_migracoes ORDER BY id DESC;

-- Cobertura do backup por tabela
SELECT tabela, COUNT(*)
  FROM desafio_legacy_migracao_backup
 WHERE migracao_id = <id>
 GROUP BY tabela ORDER BY tabela;

-- Verificação do checksum (tem de bater com backup_checksum)
SELECT ENCODE(SHA256(CONVERT_TO(
         STRING_AGG(tabela || '|' || chave || '|' || conteudo::TEXT,
                    E'\n' ORDER BY tabela, chave), 'UTF8')), 'hex')
  FROM desafio_legacy_migracao_backup
 WHERE migracao_id = <id>;

-- Conferir se algum desafio legado escapou do arquivamento
SELECT id, nome, origem, status, contabilizar_pontos
  FROM desafios
 WHERE origem <> 'google_sheets'
   AND (status <> 'arquivado' OR contabilizar_pontos);
```

O backup cobre, para os desafios de origem `manual` e `csv_import`:
`desafios`, `desafio_registros`, `desafio_registros_coach`,
`desafio_importacao_linhas` — e, integralmente,
`pontos_ultimate_totais_por_clan` e `pontos_ultimate_totais_por_coach`. A
restauração, por sua vez, reescreve **apenas** as chaves que a migração
alterou, para não clobberar mudanças legítimas feitas depois.

---

## 9. Referências

- PRD: `docs/superpowers/specs/2026-08-19-contabilidade-desafios-google-sheets-prd.md`
  (RF-17, RF-18, RF-19, RF-20; seções 20.5 e 21).
- Migrations: `backend/migrations/008`, `009`, `010`.
- CLI: `backend/admin/migrate_desafios_google_sheet.py`.
- Testes: `backend/tests/test_migrate_desafios_google_sheet.py` (lógica Python)
  e `backend/tests/test_migrate_desafios_legacy_postgres.py` (SQL real, exige
  `TEST_POSTGRES_DSN`).
