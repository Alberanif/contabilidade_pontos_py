-- Aplicação transacional de um plano de reconciliação de desafios.
--
-- Toda a etapa de desafios acontece dentro desta única função: execução,
-- estado atual por token, versão imutável de auditoria, ciclo de vida dos
-- desafios e delta líquido nos totais por clã. Qualquer falha aborta tudo
-- (PRD RNF-01/RNF-04, CA-19) e nenhum total de clã pode ficar negativo — a
-- operação falha em vez de truncar para zero (PRD RF-19, decisão 32.6).
--
-- O plano em si é calculado fora do banco (backend/desafio_reconciliation.py);
-- esta função apenas persiste o que já foi decidido, com verificação
-- otimista de pré-condição para nunca aplicar um plano obsoleto.

CREATE OR REPLACE FUNCTION apply_desafio_reconciliation(p_payload JSONB)
RETURNS JSONB
LANGUAGE plpgsql
-- Resolução de nomes fixa: nenhum schema de quem chama pode interpor uma
-- tabela ou função homônima entre esta função e os objetos que ela escreve.
SET search_path = public, pg_temp
AS $$
DECLARE
  -- Chave fixa do advisory lock da sincronização de desafios. Vale para o
  -- banco inteiro e é liberada automaticamente no fim da transação.
  c_lock_key       CONSTANT BIGINT := 7345901220834561;

  v_run_id         BIGINT;
  v_started_at     TIMESTAMPTZ;
  v_finished_at    TIMESTAMPTZ;
  v_points_per_submission INTEGER;

  v_transition     JSONB;
  v_version        JSONB;
  v_state          JSONB;
  v_previous       JSONB;
  v_token          TEXT;

  v_desafio_id     INTEGER;
  v_raw_cells      JSONB;
  v_row_numbers    INTEGER[];
  v_next_version   INTEGER;
  v_existing       RECORD;

  v_clan           TEXT;
  v_delta          INTEGER;
  v_current_total  INTEGER;
  v_new_total      INTEGER;

  v_plan_deltas       JSONB;
  v_token_deltas      JSONB;

  v_tokens_versioned  INTEGER := 0;
  v_created           INTEGER := 0;
  v_archived          INTEGER := 0;
  v_reactivated       INTEGER := 0;
  v_transitions_out   JSONB := '[]'::JSONB;
  v_totals_after      JSONB := '{}'::JSONB;
BEGIN
  -- Concorrência (PRD RNF-03, CA-18): tentativa não-bloqueante. Uma segunda
  -- execução simultânea desiste imediatamente em vez de enfileirar.
  IF NOT pg_try_advisory_xact_lock(c_lock_key) THEN
    RETURN JSONB_BUILD_OBJECT(
      'status', 'already_running',
      'run_id', NULL,
      'snapshot_hash', p_payload->>'snapshot_hash',
      'sheet_row_count', 0,
      'state_counts', '{}'::JSONB,
      'clan_deltas', '{}'::JSONB,
      'clan_totals_after', '{}'::JSONB,
      'challenge_transitions', '[]'::JSONB,
      'challenges_created', 0,
      'challenges_archived', 0,
      'challenges_reactivated', 0,
      'tokens_versioned', 0,
      'started_at', NULL,
      'finished_at', NULL
    );
  END IF;

  -- A taxa de pontos vem do plano (que a calculou) e não tem default aqui de
  -- propósito: um fallback silencioso faria `desafio_sync_runs` registrar uma
  -- taxa diferente da que produziu os pontos gravados. Ausência é violação de
  -- contrato de quem chama, e precisa ser barulhenta.
  v_points_per_submission := (p_payload->>'points_per_submission')::INTEGER;
  IF v_points_per_submission IS NULL THEN
    RAISE EXCEPTION
      'desafio_reconciliation_missing_points_per_submission: o plano precisa informar points_per_submission';
  END IF;

  INSERT INTO desafio_sync_runs (
    status, snapshot_hash, sheet_row_count, state_counts, clan_deltas,
    challenges_created, challenges_archived, challenges_reactivated,
    points_per_submission, mass_removal_required, mass_removal_confirmed,
    mass_removal_count
  ) VALUES (
    'running',
    p_payload->>'snapshot_hash',
    COALESCE((p_payload->>'sheet_row_count')::INTEGER, 0),
    COALESCE(p_payload->'state_counts', '{}'::JSONB),
    COALESCE(p_payload->'clan_deltas', '{}'::JSONB),
    -- Contagens de ciclo de vida ficam zeradas aqui e são preenchidas no fim
    -- com o que de fato aconteceu: a intenção declarada no plano não é fonte
    -- de verdade para a auditoria do efeito.
    0, 0, 0,
    v_points_per_submission,
    COALESCE((p_payload->>'mass_removal_required')::BOOLEAN, FALSE),
    COALESCE((p_payload->>'mass_removal_confirmed')::BOOLEAN, FALSE),
    COALESCE((p_payload->>'mass_removal_count')::INTEGER, 0)
  )
  RETURNING id, started_at INTO v_run_id, v_started_at;

  -- ---------------------------------------------------------------------
  -- Ciclo de vida dos desafios (criar / arquivar / reativar).
  -- Arquivar nunca apaga histórico: apenas marca o desafio.
  -- ---------------------------------------------------------------------
  FOR v_transition IN
    SELECT value
    FROM JSONB_ARRAY_ELEMENTS(
      COALESCE(p_payload->'challenge_transitions', '[]'::JSONB)
    )
  LOOP
    v_desafio_id := NULL;

    IF v_transition->>'transition' IN ('create', 'reactivate') THEN
      UPDATE desafios
         SET status = 'ativo',
             reativado_at = CASE
               WHEN status = 'arquivado' THEN NOW() ELSE reativado_at
             END,
             updated_at = NOW()
       WHERE origem = 'google_sheets'
         AND nome_normalizado = v_transition->>'challenge_normalized'
      RETURNING id INTO v_desafio_id;

      IF v_desafio_id IS NULL THEN
        INSERT INTO desafios (
          nome, nome_normalizado, origem, status, contabilizar_pontos,
          data, updated_at
        ) VALUES (
          COALESCE(
            NULLIF(BTRIM(v_transition->>'challenge_display'), ''),
            v_transition->>'challenge_normalized'
          ),
          v_transition->>'challenge_normalized',
          'google_sheets',
          'ativo',
          TRUE,
          CURRENT_DATE,
          NOW()
        )
        RETURNING id INTO v_desafio_id;
      END IF;

      IF v_transition->>'transition' = 'create' THEN
        v_created := v_created + 1;
      ELSE
        v_reactivated := v_reactivated + 1;
      END IF;

    ELSIF v_transition->>'transition' = 'archive' THEN
      UPDATE desafios
         SET status = 'arquivado',
             arquivado_at = NOW(),
             updated_at = NOW()
       WHERE origem = 'google_sheets'
         AND nome_normalizado = v_transition->>'challenge_normalized'
      RETURNING id INTO v_desafio_id;

      -- Nenhuma linha correspondente: nada foi arquivado. Reportar o contrário
      -- faria a auditoria afirmar uma mudança que não existe.
      IF v_desafio_id IS NULL THEN
        CONTINUE;
      END IF;

      v_archived := v_archived + 1;

    ELSE
      RAISE EXCEPTION
        'desafio_reconciliation_unknown_transition: %',
        v_transition->>'transition';
    END IF;

    v_transitions_out := v_transitions_out || JSONB_BUILD_ARRAY(
      JSONB_BUILD_OBJECT(
        'challenge_normalized', v_transition->>'challenge_normalized',
        'transition', v_transition->>'transition',
        'desafio_id', v_desafio_id
      )
    );
  END LOOP;

  -- ---------------------------------------------------------------------
  -- Estado atual por token + versão imutável de auditoria.
  -- ---------------------------------------------------------------------
  FOR v_version IN
    SELECT value
    FROM JSONB_ARRAY_ELEMENTS(COALESCE(p_payload->'token_versions', '[]'::JSONB))
  LOOP
    v_token := v_version->>'token';
    v_state := v_version->'current_state';
    v_previous := v_version->'previous_state';
    IF v_state IS NOT NULL AND JSONB_TYPEOF(v_state) = 'null' THEN
      v_state := NULL;
    END IF;
    IF v_previous IS NOT NULL AND JSONB_TYPEOF(v_previous) = 'null' THEN
      v_previous := NULL;
    END IF;

    SELECT status, clan, points, raw_cells, row_numbers, desafio_id
      INTO v_existing
      FROM desafio_submissions_current
     WHERE token = v_token
       FOR UPDATE;

    -- Concorrência otimista: o plano foi calculado a partir de um estado
    -- lido antes desta transação. Se esse estado mudou nesse intervalo (ou
    -- se o mesmo plano está sendo reaplicado), abortar em vez de contabilizar
    -- deltas em cima de uma base diferente da prevista.
    --
    -- A existência é testada por `v_existing.status IS NULL` (a coluna é NOT
    -- NULL na 008, então só é nula quando o SELECT não achou linha) em vez de
    -- por `FOUND`, que é global do bloco e pode ser sobrescrito por qualquer
    -- comando intermediário que venha a ser inserido aqui no futuro.
    IF v_previous IS NULL THEN
      IF v_existing.status IS NOT NULL THEN
        RAISE EXCEPTION
          'desafio_reconciliation_stale_plan: token % já existe mas o plano o tratava como novo',
          v_token;
      END IF;
    ELSE
      IF v_existing.status IS NULL THEN
        RAISE EXCEPTION
          'desafio_reconciliation_stale_plan: token % desapareceu do estado atual',
          v_token;
      END IF;
      IF v_existing.status IS DISTINCT FROM (v_previous->>'status')
         OR v_existing.points IS DISTINCT FROM COALESCE((v_previous->>'points')::INTEGER, 0)
         OR v_existing.clan IS DISTINCT FROM (v_previous->>'clan') THEN
        RAISE EXCEPTION
          'desafio_reconciliation_stale_plan: token % mudou desde a leitura (esperado %/%/%, encontrado %/%/%)',
          v_token,
          v_previous->>'status', v_previous->>'points', v_previous->>'clan',
          v_existing.status, v_existing.points, v_existing.clan;
      END IF;
    END IF;

    IF v_state IS NULL THEN
      -- Token ausente da planilha: inativa e estorna, preservando os dados
      -- brutos já registrados (a exclusão de uma linha não apaga história).
      UPDATE desafio_submissions_current
         SET status = v_version->>'current_status',
             points = 0,
             inactivated_at = NOW(),
             updated_at = NOW()
       WHERE token = v_token
      RETURNING raw_cells, row_numbers, desafio_id
        INTO v_raw_cells, v_row_numbers, v_desafio_id;

      IF v_raw_cells IS NULL THEN
        RAISE EXCEPTION
          'desafio_reconciliation_stale_plan: token % não tem estado atual para inativar',
          v_token;
      END IF;

      v_state := JSONB_BUILD_OBJECT(
        'status', v_version->>'current_status',
        'clan', NULL,
        'points', 0,
        'challenge_normalized', v_version->>'challenge_normalized',
        'submitted_at', NULL,
        'raw_cells', v_raw_cells
      );
    ELSE
      v_raw_cells := v_state->'variants'->0;
      IF v_raw_cells IS NULL THEN
        RAISE EXCEPTION
          'desafio_reconciliation_missing_variants: token %', v_token;
      END IF;

      v_row_numbers := ARRAY(
        SELECT value::INTEGER
        FROM JSONB_ARRAY_ELEMENTS_TEXT(
          COALESCE(v_state->'row_numbers', '[]'::JSONB)
        )
      );

      SELECT id INTO v_desafio_id
        FROM desafios
       WHERE origem = 'google_sheets'
         AND nome_normalizado = NULLIF(v_version->>'challenge_normalized', '');

      INSERT INTO desafio_submissions_current (
        token, row_numbers, raw_cells,
        raw_clan_legacy, raw_name, raw_validation, raw_link, raw_observation,
        raw_challenge, raw_clan_current, raw_submitted_at, raw_token,
        clan, challenge_normalized, desafio_id, submitted_at, status,
        invalid_reasons, points, content_hash,
        first_seen_run_id, last_seen_run_id, inactivated_at, updated_at
      ) VALUES (
        v_token, v_row_numbers, v_raw_cells,
        v_raw_cells->>0, v_raw_cells->>1, v_raw_cells->>2, v_raw_cells->>3,
        v_raw_cells->>4, v_raw_cells->>5, v_raw_cells->>6, v_raw_cells->>7,
        v_raw_cells->>8,
        v_state->>'clan',
        NULLIF(v_state->>'challenge_normalized', ''),
        v_desafio_id,
        (v_state->>'submitted_at')::TIMESTAMPTZ,
        v_state->>'status',
        COALESCE(v_state->'reasons', '[]'::JSONB),
        COALESCE((v_state->>'points')::INTEGER, 0),
        v_version->>'content_hash',
        v_run_id, v_run_id, NULL, NOW()
      )
      ON CONFLICT (token) DO UPDATE SET
        row_numbers = EXCLUDED.row_numbers,
        raw_cells = EXCLUDED.raw_cells,
        raw_clan_legacy = EXCLUDED.raw_clan_legacy,
        raw_name = EXCLUDED.raw_name,
        raw_validation = EXCLUDED.raw_validation,
        raw_link = EXCLUDED.raw_link,
        raw_observation = EXCLUDED.raw_observation,
        raw_challenge = EXCLUDED.raw_challenge,
        raw_clan_current = EXCLUDED.raw_clan_current,
        raw_submitted_at = EXCLUDED.raw_submitted_at,
        raw_token = EXCLUDED.raw_token,
        clan = EXCLUDED.clan,
        challenge_normalized = EXCLUDED.challenge_normalized,
        desafio_id = EXCLUDED.desafio_id,
        submitted_at = EXCLUDED.submitted_at,
        status = EXCLUDED.status,
        invalid_reasons = EXCLUDED.invalid_reasons,
        points = EXCLUDED.points,
        content_hash = EXCLUDED.content_hash,
        last_seen_run_id = EXCLUDED.last_seen_run_id,
        inactivated_at = NULL,
        updated_at = NOW();
    END IF;

    SELECT COALESCE(MAX(version_number), 0) + 1
      INTO v_next_version
      FROM desafio_submission_versions
     WHERE token = v_token;

    INSERT INTO desafio_submission_versions (
      token, sync_run_id, version_number, row_numbers, raw_cells,
      raw_clan_legacy, raw_name, raw_validation, raw_link, raw_observation,
      raw_challenge, raw_clan_current, raw_submitted_at, raw_token,
      previous_state, current_state, previous_status, current_status,
      point_delta, clan_deltas, change_reason
    ) VALUES (
      v_token, v_run_id, v_next_version,
      COALESCE(v_row_numbers, ARRAY[]::INTEGER[]), v_raw_cells,
      v_raw_cells->>0, v_raw_cells->>1, v_raw_cells->>2, v_raw_cells->>3,
      v_raw_cells->>4, v_raw_cells->>5, v_raw_cells->>6, v_raw_cells->>7,
      v_raw_cells->>8,
      v_previous, v_state,
      v_version->>'previous_status', v_version->>'current_status',
      COALESCE((v_version->>'point_delta')::INTEGER, 0),
      COALESCE(v_version->'clan_deltas', '{}'::JSONB),
      v_version->>'change_reason'
    );

    v_tokens_versioned := v_tokens_versioned + 1;
  END LOOP;

  -- ---------------------------------------------------------------------
  -- Conferência contábil antes de mexer em qualquer total: o agregado
  -- `clan_deltas` do plano precisa bater, clã a clã, com a soma dos deltas
  -- por token que acabaram de ser gravados nesta mesma transação. Sem isso,
  -- um agregado corrompido moveria totais que nenhuma versão justifica —
  -- exatamente o tipo de desvio que só apareceria semanas depois.
  -- ---------------------------------------------------------------------
  SELECT COALESCE(JSONB_OBJECT_AGG(clan, total), '{}'::JSONB)
    INTO v_token_deltas
    FROM (
      SELECT d.key AS clan, SUM(d.value::INTEGER) AS total
        FROM desafio_submission_versions v
        CROSS JOIN LATERAL JSONB_EACH_TEXT(
          COALESCE(v.clan_deltas, '{}'::JSONB)
        ) AS d
       WHERE v.sync_run_id = v_run_id
       GROUP BY d.key
      HAVING SUM(d.value::INTEGER) <> 0
    ) AS somado;

  SELECT COALESCE(JSONB_OBJECT_AGG(key, value::INTEGER), '{}'::JSONB)
    INTO v_plan_deltas
    FROM JSONB_EACH_TEXT(COALESCE(p_payload->'clan_deltas', '{}'::JSONB))
   WHERE value::INTEGER <> 0;

  IF v_plan_deltas IS DISTINCT FROM v_token_deltas THEN
    RAISE EXCEPTION
      'desafio_reconciliation_clan_delta_mismatch: agregado do plano % difere da soma por token %',
      v_plan_deltas, v_token_deltas;
  END IF;

  -- ---------------------------------------------------------------------
  -- Delta líquido por clã. Um total que ficaria negativo aborta a transação
  -- inteira: truncar para zero esconderia uma inconsistência contábil.
  -- ---------------------------------------------------------------------
  FOR v_clan, v_delta IN
    SELECT key, value::INTEGER
    FROM JSONB_EACH_TEXT(COALESCE(p_payload->'clan_deltas', '{}'::JSONB))
    ORDER BY key
  LOOP
    SELECT total_pontos INTO v_current_total
      FROM pontos_ultimate_totais_por_clan
     WHERE clan = v_clan
       FOR UPDATE;

    v_new_total := COALESCE(v_current_total, 0) + v_delta;

    IF v_new_total < 0 THEN
      RAISE EXCEPTION
        'desafio_reconciliation_negative_clan_total: clã % ficaria com % pontos (atual %, delta %)',
        v_clan, v_new_total, COALESCE(v_current_total, 0), v_delta;
    END IF;

    INSERT INTO pontos_ultimate_totais_por_clan (clan, total_pontos)
    VALUES (v_clan, v_new_total)
    ON CONFLICT (clan) DO UPDATE SET total_pontos = EXCLUDED.total_pontos;

    v_totals_after := v_totals_after || JSONB_BUILD_OBJECT(v_clan, v_new_total);
  END LOOP;

  -- As contagens de ciclo de vida são regravadas com o que de fato aconteceu
  -- (um `archive` sem linha correspondente não conta), para que a auditoria
  -- descreva o efeito e não a intenção do plano.
  UPDATE desafio_sync_runs
     SET status = 'succeeded',
         finished_at = NOW(),
         challenges_created = v_created,
         challenges_archived = v_archived,
         challenges_reactivated = v_reactivated
   WHERE id = v_run_id
  RETURNING finished_at INTO v_finished_at;

  RETURN JSONB_BUILD_OBJECT(
    'status', 'applied',
    'run_id', v_run_id,
    'snapshot_hash', p_payload->>'snapshot_hash',
    'sheet_row_count', COALESCE((p_payload->>'sheet_row_count')::INTEGER, 0),
    'state_counts', COALESCE(p_payload->'state_counts', '{}'::JSONB),
    'clan_deltas', COALESCE(p_payload->'clan_deltas', '{}'::JSONB),
    'clan_totals_after', v_totals_after,
    'challenge_transitions', v_transitions_out,
    'challenges_created', v_created,
    'challenges_archived', v_archived,
    'challenges_reactivated', v_reactivated,
    'tokens_versioned', v_tokens_versioned,
    'started_at', v_started_at,
    'finished_at', v_finished_at
  );
END;
$$;

COMMENT ON FUNCTION apply_desafio_reconciliation(JSONB) IS
  'Aplica um plano de reconciliação de desafios em uma única transação, com '
  'advisory lock não-bloqueante, auditoria imutável e rejeição de total de clã negativo.';

-- Esta função reescreve totais de clã: nenhum papel público pode executá-la.
-- Revogar de PUBLIC é o que efetivamente fecha a porta (anon/authenticated
-- herdam de PUBLIC); o GRANT explícito garante o papel de serviço, e cada
-- bloco tolera ambientes (schemas de teste) sem os papéis do Supabase.
REVOKE ALL ON FUNCTION apply_desafio_reconciliation(JSONB) FROM PUBLIC;

DO $$
BEGIN
  BEGIN
    EXECUTE 'REVOKE ALL ON FUNCTION apply_desafio_reconciliation(JSONB) FROM anon, authenticated';
  EXCEPTION WHEN undefined_object THEN NULL;
  END;

  BEGIN
    EXECUTE 'GRANT EXECUTE ON FUNCTION apply_desafio_reconciliation(JSONB) TO service_role';
  EXCEPTION WHEN undefined_object THEN NULL;
  END;
END
$$;
