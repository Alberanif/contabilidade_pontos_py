-- Fase 1 do corte de produção dos desafios: remover a contribuição legada
-- (manual / importação CSV) dos totais reais de clã e coach, arquivar as
-- estruturas antigas e guardar um backup verificável — tudo em uma única
-- transação do Postgres (PRD RF-20, seção 21.2).
--
-- O que esta migração NÃO faz: aplicar o snapshot da Google Sheet. Isso é a
-- Fase 2, e continua sendo a transação já existente de
-- `apply_desafio_reconciliation` (migração 009), chamada logo em seguida pela
-- CLI `admin.migrate_desafios_google_sheet`. São **duas transações atômicas
-- sequenciais**, não uma só: o cliente REST do Supabase não consegue manter
-- uma transação aberta entre duas chamadas, e replicar o pipeline das Tasks
-- 2-4 aqui dentro duplicaria uma fronteira de atomicidade já revisada. O
-- backup criado aqui é o que torna o desfecho "Fase 1 aplicada / Fase 2
-- falhou" recuperável — ver `docs/runbooks/migracao-desafios-google-sheets.md`.
--
-- Invariantes desta fase:
--   * nada é apagado — desafios legados são marcados como arquivados e não
--     contabilizáveis, e todas as linhas afetadas vão para o backup;
--   * nenhum total pode ficar negativo: a transação inteira aborta em vez de
--     truncar para zero (PRD RF-19, mesma decisão da migração 009);
--   * a subtração é explícita (`total_atual - contribuicao_legada`), nunca um
--     delta aplicado por helper que faz `max(0, ...)`;
--   * a fase 1 só pode ser aplicada uma vez (índice único + verificação
--     explícita), porque uma segunda execução subtrairia os mesmos pontos
--     duas vezes.

-- ---------------------------------------------------------------------------
-- Registro da migração e backup
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS desafio_legacy_migracoes (
  id                   BIGSERIAL PRIMARY KEY,
  status               TEXT NOT NULL,
  started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at          TIMESTAMPTZ,
  rolled_back_at       TIMESTAMPTZ,
  -- Totais absolutos antes/depois, por chave, apenas das linhas efetivamente
  -- alteradas. É o que a restauração administrativa reescreve.
  clan_before          JSONB NOT NULL DEFAULT '{}'::JSONB,
  clan_after           JSONB NOT NULL DEFAULT '{}'::JSONB,
  clan_removido        JSONB NOT NULL DEFAULT '{}'::JSONB,
  coach_before         JSONB NOT NULL DEFAULT '{}'::JSONB,
  coach_after          JSONB NOT NULL DEFAULT '{}'::JSONB,
  coach_removido       JSONB NOT NULL DEFAULT '{}'::JSONB,
  desafios_arquivados  INTEGER NOT NULL DEFAULT 0 CHECK (desafios_arquivados >= 0),
  backup_rows          INTEGER NOT NULL DEFAULT 0 CHECK (backup_rows >= 0),
  backup_checksum      TEXT,
  CONSTRAINT desafio_legacy_migracoes_status_check
    CHECK (status IN ('applied', 'rolled_back'))
);

-- Garantia de banco (além da verificação explícita na função): no máximo uma
-- migração aplicada. Uma segunda subtrairia a mesma contribuição de novo.
CREATE UNIQUE INDEX IF NOT EXISTS ux_desafio_legacy_migracoes_applied
  ON desafio_legacy_migracoes (status)
  WHERE status = 'applied';

CREATE TABLE IF NOT EXISTS desafio_legacy_migracao_backup (
  id           BIGSERIAL PRIMARY KEY,
  migracao_id  BIGINT NOT NULL REFERENCES desafio_legacy_migracoes(id),
  tabela       TEXT NOT NULL,
  chave        TEXT NOT NULL,
  conteudo     JSONB NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_desafio_legacy_migracao_backup_migracao
  ON desafio_legacy_migracao_backup (migracao_id, tabela);

-- Um backup que pode ser editado depois não é um backup: as linhas são
-- imutáveis (PRD seção 19 — retenção por tempo indeterminado). O aborto de uma
-- transação continua desfazendo os INSERTs normalmente, porque isso é rollback
-- e não UPDATE/DELETE.
CREATE OR REPLACE FUNCTION prevent_desafio_legacy_backup_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'desafio_legacy_migracao_backup is immutable';
END;
$$;

DROP TRIGGER IF EXISTS desafio_legacy_migracao_backup_immutable
  ON desafio_legacy_migracao_backup;
CREATE TRIGGER desafio_legacy_migracao_backup_immutable
  BEFORE UPDATE OR DELETE ON desafio_legacy_migracao_backup
  FOR EACH ROW
  EXECUTE FUNCTION prevent_desafio_legacy_backup_mutation();

DROP TRIGGER IF EXISTS desafio_legacy_migracao_backup_no_truncate
  ON desafio_legacy_migracao_backup;
CREATE TRIGGER desafio_legacy_migracao_backup_no_truncate
  BEFORE TRUNCATE ON desafio_legacy_migracao_backup
  FOR EACH STATEMENT
  EXECUTE FUNCTION prevent_desafio_legacy_backup_mutation();

-- ---------------------------------------------------------------------------
-- Relatório (somente leitura) — base do dry-run e da própria aplicação
-- ---------------------------------------------------------------------------

-- A contribuição legada de um clã é a soma de `desafio_registros.total_pontos`
-- dos desafios que ainda contabilizam pontos e não vieram da Google Sheet — o
-- mesmo conjunto que os antigos endpoints somavam via
-- `add_delta_to_clan_total`. Para coaches, `desafio_registros_coach`.
--
-- O filtro `contabilizar_pontos` é o que fecha a conta: desligar esse flag já
-- estornava os pontos na época (`points_engine.diff_desafio_registros` ->
-- `add_delta_to_clan_total`, e `excluir_desafio` do lado do coach), então um
-- desafio com o flag desligado não tem mais nada nos totais para remover.
-- Incluí-lo aqui subtrairia pontos que já saíram.

CREATE OR REPLACE FUNCTION desafio_legacy_migration_report()
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
  v_migracao_id  BIGINT;
  v_clans        JSONB;
  v_coaches      JSONB;
  v_negativos    JSONB;
BEGIN
  SELECT id INTO v_migracao_id
    FROM desafio_legacy_migracoes
   WHERE status = 'applied'
   LIMIT 1;

  -- Clãs: todos os que têm total registrado, mais qualquer clã com
  -- contribuição legada que (por inconsistência) não tenha linha de total.
  SELECT COALESCE(JSONB_AGG(item ORDER BY chave), '[]'::JSONB)
    INTO v_clans
    FROM (
      SELECT
        chave,
        JSONB_BUILD_OBJECT(
          'clan', chave,
          'total_antes', total_antes,
          'contribuicao_legada', contribuicao,
          'total_depois', total_antes - contribuicao
        ) AS item
      FROM (
        SELECT
          COALESCE(t.clan, l.clan) AS chave,
          COALESCE(t.total_pontos, 0) AS total_antes,
          COALESCE(l.contribuicao, 0) AS contribuicao
        FROM pontos_ultimate_totais_por_clan t
        FULL OUTER JOIN (
          SELECT r.clan, SUM(r.total_pontos)::INTEGER AS contribuicao
            FROM desafio_registros r
            JOIN desafios d ON d.id = r.desafio_id
           WHERE d.origem <> 'google_sheets'
             AND d.contabilizar_pontos
           GROUP BY r.clan
        ) l ON l.clan = t.clan
      ) base
    ) ordenado;

  -- Coaches: só os que têm contribuição legada. A lista completa de coaches
  -- pode ser longa e nada nela mudaria.
  SELECT COALESCE(JSONB_AGG(item ORDER BY chave), '[]'::JSONB)
    INTO v_coaches
    FROM (
      SELECT
        chave,
        JSONB_BUILD_OBJECT(
          'coach', chave,
          'total_antes', total_antes,
          'contribuicao_legada', contribuicao,
          'total_depois', total_antes - contribuicao
        ) AS item
      FROM (
        SELECT
          l.coach AS chave,
          COALESCE(t.total_pontos, 0) AS total_antes,
          l.contribuicao AS contribuicao
        FROM (
          SELECT rc.coach, SUM(rc.total_pontos)::INTEGER AS contribuicao
            FROM desafio_registros_coach rc
            JOIN desafios d ON d.id = rc.desafio_id
           WHERE d.origem <> 'google_sheets'
             AND d.contabilizar_pontos
           GROUP BY rc.coach
        ) l
        LEFT JOIN pontos_ultimate_totais_por_coach t ON t.coach = l.coach
      ) base
    ) ordenado;

  SELECT COALESCE(JSONB_AGG(item), '[]'::JSONB)
    INTO v_negativos
    FROM (
      SELECT JSONB_BUILD_OBJECT(
               'escopo', 'clan',
               'chave', elem->>'clan',
               'total_antes', elem->'total_antes',
               'contribuicao_legada', elem->'contribuicao_legada',
               'total_depois', elem->'total_depois'
             ) AS item
        FROM JSONB_ARRAY_ELEMENTS(v_clans) AS elem
       WHERE (elem->>'total_depois')::INTEGER < 0
      UNION ALL
      SELECT JSONB_BUILD_OBJECT(
               'escopo', 'coach',
               'chave', elem->>'coach',
               'total_antes', elem->'total_antes',
               'contribuicao_legada', elem->'contribuicao_legada',
               'total_depois', elem->'total_depois'
             ) AS item
        FROM JSONB_ARRAY_ELEMENTS(v_coaches) AS elem
       WHERE (elem->>'total_depois')::INTEGER < 0
    ) n;

  RETURN JSONB_BUILD_OBJECT(
    'ja_migrado', v_migracao_id IS NOT NULL,
    'migracao_id', v_migracao_id,
    'clans', v_clans,
    'coaches', v_coaches,
    'negativos', v_negativos,
    'desafios_legados', (
      SELECT COUNT(*) FROM desafios WHERE origem <> 'google_sheets'
    ),
    'desafios_legados_contabilizando', (
      SELECT COUNT(*) FROM desafios
       WHERE origem <> 'google_sheets' AND contabilizar_pontos
    ),
    'registros_clan', (
      SELECT COUNT(*) FROM desafio_registros r
        JOIN desafios d ON d.id = r.desafio_id
       WHERE d.origem <> 'google_sheets'
    ),
    'registros_coach', (
      SELECT COUNT(*) FROM desafio_registros_coach rc
        JOIN desafios d ON d.id = rc.desafio_id
       WHERE d.origem <> 'google_sheets'
    ),
    'linhas_importacao', (
      SELECT COUNT(*) FROM desafio_importacao_linhas il
        JOIN desafios d ON d.id = il.desafio_id
       WHERE d.origem <> 'google_sheets'
    )
  );
END;
$$;

COMMENT ON FUNCTION desafio_legacy_migration_report() IS
  'Relatório somente leitura da contribuição legada de desafios em totais de clã e coach.';

-- ---------------------------------------------------------------------------
-- Fase 1: aplicação transacional
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION migrate_desafio_legacy_contribution()
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
  -- Mesma chave da sincronização de desafios (migração 009): esta fase e uma
  -- sincronização real jamais podem se intercalar.
  c_lock_key       CONSTANT BIGINT := 7345901220834561;

  v_report         JSONB;
  v_migracao_id    BIGINT;
  v_chave          TEXT;
  v_contribuicao   INTEGER;
  v_atual          INTEGER;
  v_novo           INTEGER;

  v_clan_before    JSONB := '{}'::JSONB;
  v_clan_after     JSONB := '{}'::JSONB;
  v_clan_removido  JSONB := '{}'::JSONB;
  v_coach_before   JSONB := '{}'::JSONB;
  v_coach_after    JSONB := '{}'::JSONB;
  v_coach_removido JSONB := '{}'::JSONB;

  v_arquivados     INTEGER := 0;
  v_backup_rows    INTEGER := 0;
  v_checksum       TEXT;
  v_finished_at    TIMESTAMPTZ;
BEGIN
  IF NOT pg_try_advisory_xact_lock(c_lock_key) THEN
    RAISE EXCEPTION
      'desafio_legacy_migration_locked: uma sincronização ou migração de desafios já está em andamento';
  END IF;

  IF EXISTS (SELECT 1 FROM desafio_legacy_migracoes WHERE status = 'applied') THEN
    RAISE EXCEPTION
      'desafio_legacy_migration_already_applied: a fase 1 já foi aplicada (migração #%)',
      (SELECT id FROM desafio_legacy_migracoes WHERE status = 'applied' LIMIT 1);
  END IF;

  v_report := desafio_legacy_migration_report();

  INSERT INTO desafio_legacy_migracoes (status) VALUES ('applied')
  RETURNING id INTO v_migracao_id;

  -- -------------------------------------------------------------------------
  -- Backup — antes de qualquer escrita nas tabelas de negócio.
  -- -------------------------------------------------------------------------
  INSERT INTO desafio_legacy_migracao_backup (migracao_id, tabela, chave, conteudo)
  SELECT v_migracao_id, 'desafios', d.id::TEXT, TO_JSONB(d)
    FROM desafios d
   WHERE d.origem <> 'google_sheets';

  INSERT INTO desafio_legacy_migracao_backup (migracao_id, tabela, chave, conteudo)
  SELECT v_migracao_id, 'desafio_registros', r.id::TEXT, TO_JSONB(r)
    FROM desafio_registros r
    JOIN desafios d ON d.id = r.desafio_id
   WHERE d.origem <> 'google_sheets';

  INSERT INTO desafio_legacy_migracao_backup (migracao_id, tabela, chave, conteudo)
  SELECT v_migracao_id, 'desafio_registros_coach', rc.id::TEXT, TO_JSONB(rc)
    FROM desafio_registros_coach rc
    JOIN desafios d ON d.id = rc.desafio_id
   WHERE d.origem <> 'google_sheets';

  INSERT INTO desafio_legacy_migracao_backup (migracao_id, tabela, chave, conteudo)
  SELECT v_migracao_id, 'desafio_importacao_linhas', il.id::TEXT, TO_JSONB(il)
    FROM desafio_importacao_linhas il
    JOIN desafios d ON d.id = il.desafio_id
   WHERE d.origem <> 'google_sheets';

  -- Totais completos das duas tabelas: são poucas linhas e o operador precisa
  -- da foto inteira para conferir. A restauração, essa sim, só reescreve as
  -- chaves que esta migração alterou (`clan_before` / `coach_before`).
  INSERT INTO desafio_legacy_migracao_backup (migracao_id, tabela, chave, conteudo)
  SELECT v_migracao_id, 'pontos_ultimate_totais_por_clan', t.clan, TO_JSONB(t)
    FROM pontos_ultimate_totais_por_clan t;

  INSERT INTO desafio_legacy_migracao_backup (migracao_id, tabela, chave, conteudo)
  SELECT v_migracao_id, 'pontos_ultimate_totais_por_coach', t.coach, TO_JSONB(t)
    FROM pontos_ultimate_totais_por_coach t;

  SELECT COUNT(*),
         ENCODE(
           SHA256(
             CONVERT_TO(
               COALESCE(
                 STRING_AGG(b.tabela || '|' || b.chave || '|' || b.conteudo::TEXT,
                            E'\n' ORDER BY b.tabela, b.chave),
                 ''
               ),
               'UTF8'
             )
           ),
           'hex'
         )
    INTO v_backup_rows, v_checksum
    FROM desafio_legacy_migracao_backup b
   WHERE b.migracao_id = v_migracao_id;

  -- -------------------------------------------------------------------------
  -- Subtração explícita da contribuição legada nos totais de clã.
  -- Nunca `max(0, ...)`: um total que ficaria negativo aborta tudo (RF-19).
  -- -------------------------------------------------------------------------
  FOR v_chave, v_contribuicao IN
    SELECT elem->>'clan', (elem->>'contribuicao_legada')::INTEGER
      FROM JSONB_ARRAY_ELEMENTS(v_report->'clans') AS elem
     WHERE (elem->>'contribuicao_legada')::INTEGER <> 0
     ORDER BY elem->>'clan'
  LOOP
    SELECT total_pontos INTO v_atual
      FROM pontos_ultimate_totais_por_clan
     WHERE clan = v_chave
       FOR UPDATE;

    v_novo := COALESCE(v_atual, 0) - v_contribuicao;

    IF v_novo < 0 THEN
      RAISE EXCEPTION
        'desafio_legacy_migration_negative_clan_total: clã % ficaria com % pontos (atual %, contribuição legada %)',
        v_chave, v_novo, COALESCE(v_atual, 0), v_contribuicao;
    END IF;

    -- Contribuição legada sem linha de total é inconsistência de dados; sem
    -- este teste, um UPDATE que não casa com nada passaria silenciosamente
    -- (só chega aqui quando a contribuição é negativa — caso contrário o teste
    -- de total negativo acima já teria abortado).
    IF v_atual IS NULL THEN
      RAISE EXCEPTION
        'desafio_legacy_migration_missing_clan_total: clã % tem contribuição legada % mas nenhum total registrado',
        v_chave, v_contribuicao;
    END IF;

    UPDATE pontos_ultimate_totais_por_clan
       SET total_pontos = v_novo
     WHERE clan = v_chave;

    v_clan_before   := v_clan_before   || JSONB_BUILD_OBJECT(v_chave, COALESCE(v_atual, 0));
    v_clan_after    := v_clan_after    || JSONB_BUILD_OBJECT(v_chave, v_novo);
    v_clan_removido := v_clan_removido || JSONB_BUILD_OBJECT(v_chave, v_contribuicao);
  END LOOP;

  -- -------------------------------------------------------------------------
  -- Mesma subtração explícita nos totais individuais de coach. Depois desta
  -- migração nenhum ponto de desafio pode restar no ranking individual.
  -- -------------------------------------------------------------------------
  FOR v_chave, v_contribuicao IN
    SELECT elem->>'coach', (elem->>'contribuicao_legada')::INTEGER
      FROM JSONB_ARRAY_ELEMENTS(v_report->'coaches') AS elem
     WHERE (elem->>'contribuicao_legada')::INTEGER <> 0
     ORDER BY elem->>'coach'
  LOOP
    SELECT total_pontos INTO v_atual
      FROM pontos_ultimate_totais_por_coach
     WHERE coach = v_chave
       FOR UPDATE;

    v_novo := COALESCE(v_atual, 0) - v_contribuicao;

    IF v_novo < 0 THEN
      RAISE EXCEPTION
        'desafio_legacy_migration_negative_coach_total: coach % ficaria com % pontos (atual %, contribuição legada %)',
        v_chave, v_novo, COALESCE(v_atual, 0), v_contribuicao;
    END IF;

    IF v_atual IS NULL THEN
      RAISE EXCEPTION
        'desafio_legacy_migration_missing_coach_total: coach % tem contribuição legada % mas nenhum total registrado',
        v_chave, v_contribuicao;
    END IF;

    UPDATE pontos_ultimate_totais_por_coach
       SET total_pontos = v_novo
     WHERE coach = v_chave;

    v_coach_before   := v_coach_before   || JSONB_BUILD_OBJECT(v_chave, COALESCE(v_atual, 0));
    v_coach_after    := v_coach_after    || JSONB_BUILD_OBJECT(v_chave, v_novo);
    v_coach_removido := v_coach_removido || JSONB_BUILD_OBJECT(v_chave, v_contribuicao);
  END LOOP;

  -- -------------------------------------------------------------------------
  -- Desativação (nunca exclusão) das estruturas manuais/CSV. O marcador fica
  -- no `desafios`, que é o pai por FK de `desafio_registros`,
  -- `desafio_registros_coach` e `desafio_importacao_linhas` — e é por ele que
  -- todas as leituras de pontos passam (`contabilizar_pontos`). As linhas
  -- filhas continuam intactas e também estão no backup.
  -- -------------------------------------------------------------------------
  UPDATE desafios
     SET status = 'arquivado',
         contabilizar_pontos = FALSE,
         arquivado_at = COALESCE(arquivado_at, NOW()),
         updated_at = NOW()
   WHERE origem <> 'google_sheets'
     AND (status <> 'arquivado' OR contabilizar_pontos);
  GET DIAGNOSTICS v_arquivados = ROW_COUNT;

  UPDATE desafio_legacy_migracoes
     SET finished_at = NOW(),
         clan_before = v_clan_before,
         clan_after = v_clan_after,
         clan_removido = v_clan_removido,
         coach_before = v_coach_before,
         coach_after = v_coach_after,
         coach_removido = v_coach_removido,
         desafios_arquivados = v_arquivados,
         backup_rows = v_backup_rows,
         backup_checksum = v_checksum
   WHERE id = v_migracao_id
  RETURNING finished_at INTO v_finished_at;

  RETURN JSONB_BUILD_OBJECT(
    'status', 'applied',
    'migracao_id', v_migracao_id,
    'finished_at', v_finished_at,
    'clan_before', v_clan_before,
    'clan_after', v_clan_after,
    'clan_removido', v_clan_removido,
    'coach_before', v_coach_before,
    'coach_after', v_coach_after,
    'coach_removido', v_coach_removido,
    'desafios_arquivados', v_arquivados,
    'backup_rows', v_backup_rows,
    'backup_checksum', v_checksum
  );
END;
$$;

COMMENT ON FUNCTION migrate_desafio_legacy_contribution() IS
  'Fase 1 do corte de desafios: backup verificável, remoção explícita da '
  'contribuição legada em totais de clã/coach e arquivamento das estruturas '
  'manuais/CSV, em uma única transação. Aborta se algum total ficaria negativo.';

-- ---------------------------------------------------------------------------
-- Restauração administrativa (rollback pós-transação)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION restore_desafio_legacy_migracao(
  p_migracao_id BIGINT,
  p_force BOOLEAN DEFAULT FALSE
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
  c_lock_key    CONSTANT BIGINT := 7345901220834561;

  v_status      TEXT;
  v_started_at  TIMESTAMPTZ;
  v_clan_before JSONB;
  v_coach_before JSONB;

  v_chave       TEXT;
  v_total       INTEGER;
  v_clans       INTEGER := 0;
  v_coaches     INTEGER := 0;
  v_desafios    INTEGER := 0;
  v_sync_depois BIGINT;
BEGIN
  IF NOT pg_try_advisory_xact_lock(c_lock_key) THEN
    RAISE EXCEPTION
      'desafio_legacy_migration_locked: uma sincronização ou migração de desafios já está em andamento';
  END IF;

  SELECT status, started_at, clan_before, coach_before
    INTO v_status, v_started_at, v_clan_before, v_coach_before
    FROM desafio_legacy_migracoes
   WHERE id = p_migracao_id
     FOR UPDATE;

  -- `status` é NOT NULL na tabela, então só vem nulo quando o SELECT não achou
  -- linha alguma (mesmo teste de existência da migração 009, que não depende
  -- do `FOUND` global do bloco).
  IF v_status IS NULL THEN
    RAISE EXCEPTION 'desafio_legacy_migration_not_found: migração #%', p_migracao_id;
  END IF;

  IF v_status <> 'applied' THEN
    RAISE EXCEPTION
      'desafio_legacy_migration_not_applied: migração #% está em %',
      p_migracao_id, v_status;
  END IF;

  -- Restaurar os totais para o estado pré-migração também desfaz os pontos que
  -- uma sincronização bem-sucedida tenha somado depois. Se isso aconteceu, o
  -- operador precisa dizer explicitamente que é o que quer.
  SELECT id INTO v_sync_depois
    FROM desafio_sync_runs
   WHERE status = 'succeeded'
     AND started_at >= v_started_at
   ORDER BY started_at
   LIMIT 1;

  IF v_sync_depois IS NOT NULL AND NOT p_force THEN
    RAISE EXCEPTION
      'desafio_legacy_migration_restore_blocked_by_sync: a execução de sincronização #% ocorreu depois da migração; restaurar os totais também desfaria seus pontos (use p_force := TRUE para prosseguir)',
      v_sync_depois;
  END IF;

  FOR v_chave, v_total IN
    SELECT key, value::INTEGER
      FROM JSONB_EACH_TEXT(v_clan_before)
     ORDER BY key
  LOOP
    UPDATE pontos_ultimate_totais_por_clan
       SET total_pontos = v_total
     WHERE clan = v_chave;
    v_clans := v_clans + 1;
  END LOOP;

  FOR v_chave, v_total IN
    SELECT key, value::INTEGER
      FROM JSONB_EACH_TEXT(v_coach_before)
     ORDER BY key
  LOOP
    UPDATE pontos_ultimate_totais_por_coach
       SET total_pontos = v_total
     WHERE coach = v_chave;
    v_coaches := v_coaches + 1;
  END LOOP;

  UPDATE desafios d
     SET status = b.conteudo->>'status',
         contabilizar_pontos = (b.conteudo->>'contabilizar_pontos')::BOOLEAN,
         arquivado_at = (b.conteudo->>'arquivado_at')::TIMESTAMPTZ,
         updated_at = NOW()
    FROM desafio_legacy_migracao_backup b
   WHERE b.migracao_id = p_migracao_id
     AND b.tabela = 'desafios'
     AND d.id = (b.conteudo->>'id')::INTEGER;
  GET DIAGNOSTICS v_desafios = ROW_COUNT;

  UPDATE desafio_legacy_migracoes
     SET status = 'rolled_back',
         rolled_back_at = NOW()
   WHERE id = p_migracao_id;

  RETURN JSONB_BUILD_OBJECT(
    'status', 'rolled_back',
    'migracao_id', p_migracao_id,
    'clans_restaurados', v_clans,
    'coaches_restaurados', v_coaches,
    'desafios_restaurados', v_desafios,
    'sync_posterior_ignorada', v_sync_depois
  );
END;
$$;

COMMENT ON FUNCTION restore_desafio_legacy_migracao(BIGINT, BOOLEAN) IS
  'Restaura, a partir do backup da fase 1, os totais de clã/coach e o estado '
  'dos desafios legados. Recusa-se a rodar se uma sincronização bem-sucedida '
  'ocorreu depois da migração, a menos que p_force seja TRUE.';

-- Estas funções reescrevem totais reais: nenhum papel público pode executá-las.
-- Revogar de PUBLIC é o que fecha a porta (anon/authenticated herdam de
-- PUBLIC); cada bloco tolera ambientes (schemas de teste) sem os papéis do
-- Supabase.
REVOKE ALL ON FUNCTION desafio_legacy_migration_report() FROM PUBLIC;
REVOKE ALL ON FUNCTION migrate_desafio_legacy_contribution() FROM PUBLIC;
REVOKE ALL ON FUNCTION restore_desafio_legacy_migracao(BIGINT, BOOLEAN) FROM PUBLIC;

DO $$
BEGIN
  BEGIN
    EXECUTE 'REVOKE ALL ON FUNCTION desafio_legacy_migration_report() FROM anon, authenticated';
    EXECUTE 'REVOKE ALL ON FUNCTION migrate_desafio_legacy_contribution() FROM anon, authenticated';
    EXECUTE 'REVOKE ALL ON FUNCTION restore_desafio_legacy_migracao(BIGINT, BOOLEAN) FROM anon, authenticated';
  EXCEPTION WHEN undefined_object THEN NULL;
  END;

  BEGIN
    EXECUTE 'GRANT EXECUTE ON FUNCTION desafio_legacy_migration_report() TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION migrate_desafio_legacy_contribution() TO service_role';
    EXECUTE 'GRANT EXECUTE ON FUNCTION restore_desafio_legacy_migracao(BIGINT, BOOLEAN) TO service_role';
  EXCEPTION WHEN undefined_object THEN NULL;
  END;
END
$$;
