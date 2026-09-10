# Runbook — Release e Rollout: Contabilidade de Desafios via Google Sheets

Este documento consolida o **checklist de rollout** e os procedimentos operacionais para a publicação e entrada em produção da funcionalidade descrita no **PRD #11**.

---

## 1. Pré-requisitos de Implantação

Antes de executar a migração em produção, confirme que as seguintes variáveis de ambiente e pré-condições operacionais foram preenchidas no ambiente (ex.: Railway / servidor de produção):

| Parâmetro | Descrição | Status de Verificação |
|---|---|---|
| `GSHEET_DESAFIOS_SPREADSHEET_ID` | ID da planilha oficial do Google Sheets contendo a aba de Desafios | [ ] Configurado |
| `GSHEET_DESAFIOS_SHEET_NAME` | Nome exato da aba na planilha (ex.: `Desafios Pontuais`) | [ ] Configurado |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Credencial JSON da Service Account de integração com Google APIs | [ ] Configurado |
| `POINTS_PER_DESAFIO_SUBMISSION` | Valor em pontos por submissão elegível (padrão: `10`) | [ ] Configurado / Default ok |
| **Permissão da Service Account** | A Service Account possui acesso de leitura (`spreadsheets.readonly`) na planilha oficial | [ ] Concedido |
| **Saneamento Histórico** | A Coluna F (Desafio) foi devidamente preenchida nos 85 registros históricos da planilha | [ ] Confirmado |

---

## 2. Passo a Passo do Rollout (Janela Operacional)

### Passo 1 — Deploy do Código e Aplicar Migrations

1. Efetue o deploy do branch `codex/desafios-google-sheets` no ambiente de produção.
2. Verifique se as migrations de banco de dados (`008_desafio_google_sheets_reconciliation.sql`, `009_apply_desafio_reconciliation.sql` e `010_migrate_desafio_legacy_contribution.sql`) foram executadas com sucesso pelo Supabase / Postgres.

### Passo 2 — Executar o Dry-Run da Migração Administrativa

No container/terminal de backend de produção, execute a CLI em modo somente-leitura:

```bash
python -m admin.migrate_desafios_google_sheet
```

**Validações no Dry-Run:**
- Confirme que o status reportado é `PRONTO PARA APLICAR`.
- Verifique a contagem de submissões válidas lidas da planilha oficial.
- Compare a prévia dos totais antigos de clãs vs. novos totais esperados.
- Anote o `snapshot_hash` exibido no relatório (necessário para a confirmação no Passo 3).

### Passo 3 — Executar a Migração Administrativa em Produção

Com o `snapshot_hash` copiado do dry-run, invoque a migração com a flag de aplicação:

```bash
python -m admin.migrate_desafios_google_sheet --apply --confirm-hash <HASH_GERADO_NO_DRY_RUN>
```

O comando irá:
1. Adquirir lock exclusivo de migração (`7345901220834561`).
2. Criar backup imutável das tabelas afetadas em `desafio_legacy_migracao_backup`.
3. Remover a pontuação legada de desafios de clãs e coaches.
4. Aplicar a reconciliação inicial do snapshot da planilha oficial.
5. Imprimir o relatório de conclusão.

---

## 3. Validação Pós-Release

Após a conclusão do Passo 3, execute a seguinte validação:

1. **Re-execução de Teste (Delta Zero):**
   Dispare uma segunda execução manual da sincronização ou do dry-run. O resultado deve ter **delta zero** (`clan_deltas = {}`), confirmando a idempotência.
2. **Auditoria de Desafios na Interface Web:**
   Acesse a aba **Desafios** no dashboard. Verifique que:
   - A tela está em modo consulta/auditoria.
   - Não existem botões de inclusão, edição ou remoção manual nem upload de CSV.
   - O histórico de versões por token e os filtros funcionam normalmente.
3. **Executar Contabilidade:**
   Acione a ação **Executar Contabilidade** e confirme no modal o resumo da sincronização de desafios sem erros.

---

## 4. Plano de Rollback

Caso ocorra qualquer inconsistência grave durante a janela de migração:

1. **Se o erro ocorrer na Fase 1 ou no Dry-Run:**
   Nenhuma alteração foi commitada no banco. Corrija o problema na fonte e refaça a partir do Passo 2.
2. **Se o erro ocorrer pós-aplicação (Fase 2 aplicada):**
   - O backup do estado anterior pré-migração estará preservado na tabela `desafio_legacy_migracao_backup`.
   - Consulte o procedimento detalhado de restauração em [`docs/runbooks/migracao-desafios-google-sheets.md`](./migracao-desafios-google-sheets.md#74-restauracao-manual-pelo-backup).
