-- Fundação token-centric da contabilização de desafios via Google Sheets.
-- A migração é aditiva: estruturas e dados legados permanecem disponíveis
-- até a migração administrativa prevista no PRD.

ALTER TABLE desafios ADD COLUMN IF NOT EXISTS origem TEXT;
UPDATE desafios SET origem = 'manual' WHERE origem IS NULL;
ALTER TABLE desafios ALTER COLUMN origem SET DEFAULT 'manual';
ALTER TABLE desafios ALTER COLUMN origem SET NOT NULL;

ALTER TABLE desafios ADD COLUMN IF NOT EXISTS nome_normalizado TEXT;
ALTER TABLE desafios ADD COLUMN IF NOT EXISTS status TEXT;
UPDATE desafios SET status = 'ativo' WHERE status IS NULL;
ALTER TABLE desafios ALTER COLUMN status SET DEFAULT 'ativo';
ALTER TABLE desafios ALTER COLUMN status SET NOT NULL;
ALTER TABLE desafios ADD COLUMN IF NOT EXISTS arquivado_at TIMESTAMPTZ;
ALTER TABLE desafios ADD COLUMN IF NOT EXISTS reativado_at TIMESTAMPTZ;
ALTER TABLE desafios ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'desafios_status_check'
      AND conrelid = 'desafios'::REGCLASS
  ) THEN
    ALTER TABLE desafios
      ADD CONSTRAINT desafios_status_check CHECK (status IN ('ativo', 'arquivado'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'desafios_origem_check'
      AND conrelid = 'desafios'::REGCLASS
  ) THEN
    ALTER TABLE desafios
      ADD CONSTRAINT desafios_origem_check
      CHECK (origem IN ('manual', 'csv_import', 'google_sheets'));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'desafios_google_nome_normalizado_check'
      AND conrelid = 'desafios'::REGCLASS
  ) THEN
    ALTER TABLE desafios
      ADD CONSTRAINT desafios_google_nome_normalizado_check
      CHECK (
        origem <> 'google_sheets'
        OR NULLIF(BTRIM(nome_normalizado), '') IS NOT NULL
      );
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_desafios_google_nome_normalizado
  ON desafios (nome_normalizado)
  WHERE origem = 'google_sheets';
CREATE INDEX IF NOT EXISTS ix_desafios_status ON desafios (status);

CREATE TABLE IF NOT EXISTS desafio_sync_runs (
  id                         BIGSERIAL PRIMARY KEY,
  started_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at                TIMESTAMPTZ,
  status                     TEXT NOT NULL,
  snapshot_hash              TEXT,
  sheet_row_count            INTEGER NOT NULL DEFAULT 0 CHECK (sheet_row_count >= 0),
  state_counts               JSONB NOT NULL DEFAULT '{}'::JSONB,
  clan_deltas                JSONB NOT NULL DEFAULT '{}'::JSONB,
  challenges_created         INTEGER NOT NULL DEFAULT 0 CHECK (challenges_created >= 0),
  challenges_archived        INTEGER NOT NULL DEFAULT 0 CHECK (challenges_archived >= 0),
  challenges_reactivated     INTEGER NOT NULL DEFAULT 0 CHECK (challenges_reactivated >= 0),
  points_per_submission      INTEGER NOT NULL CHECK (points_per_submission > 0),
  mass_removal_required      BOOLEAN NOT NULL DEFAULT FALSE,
  mass_removal_confirmed     BOOLEAN NOT NULL DEFAULT FALSE,
  mass_removal_count         INTEGER NOT NULL DEFAULT 0 CHECK (mass_removal_count >= 0),
  error                      JSONB,
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT desafio_sync_runs_status_check CHECK (
    status IN ('running', 'succeeded', 'failed', 'awaiting_confirmation', 'cancelled')
  )
);

CREATE TABLE IF NOT EXISTS desafio_submissions_current (
  token                 TEXT PRIMARY KEY,
  row_numbers           INTEGER[] NOT NULL DEFAULT '{}',
  raw_cells             JSONB NOT NULL,
  raw_clan_legacy       TEXT,
  raw_name              TEXT,
  raw_validation        TEXT,
  raw_link              TEXT,
  raw_observation       TEXT,
  raw_challenge         TEXT,
  raw_clan_current      TEXT,
  raw_submitted_at      TEXT,
  raw_token             TEXT,
  clan                  TEXT,
  challenge_normalized  TEXT,
  desafio_id            INTEGER REFERENCES desafios(id) ON DELETE SET NULL,
  submitted_at          TIMESTAMPTZ,
  status                TEXT NOT NULL,
  invalid_reasons       JSONB NOT NULL DEFAULT '[]'::JSONB,
  points                INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0),
  content_hash          TEXT NOT NULL,
  first_seen_run_id     BIGINT NOT NULL REFERENCES desafio_sync_runs(id),
  last_seen_run_id      BIGINT NOT NULL REFERENCES desafio_sync_runs(id),
  inactivated_at        TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT desafio_submissions_current_status_check CHECK (
    status IN (
      'active_counted',
      'active_not_counted',
      'invalid',
      'conflicted',
      'inactive_missing',
      'blocked_by_guardrail'
    )
  ),
  CONSTRAINT desafio_submissions_current_raw_cells_check CHECK (
    JSONB_TYPEOF(raw_cells) = 'array' AND JSONB_ARRAY_LENGTH(raw_cells) = 9
  )
);

CREATE TABLE IF NOT EXISTS desafio_submission_versions (
  id                       BIGSERIAL PRIMARY KEY,
  token                    TEXT NOT NULL REFERENCES desafio_submissions_current(token),
  sync_run_id              BIGINT NOT NULL REFERENCES desafio_sync_runs(id),
  version_number           INTEGER NOT NULL CHECK (version_number > 0),
  row_numbers              INTEGER[] NOT NULL DEFAULT '{}',
  raw_cells                JSONB NOT NULL,
  raw_clan_legacy          TEXT,
  raw_name                 TEXT,
  raw_validation           TEXT,
  raw_link                 TEXT,
  raw_observation          TEXT,
  raw_challenge            TEXT,
  raw_clan_current         TEXT,
  raw_submitted_at         TEXT,
  raw_token                TEXT,
  previous_state           JSONB,
  current_state            JSONB NOT NULL,
  previous_status          TEXT,
  current_status           TEXT NOT NULL,
  point_delta              INTEGER NOT NULL DEFAULT 0,
  clan_deltas              JSONB NOT NULL DEFAULT '{}'::JSONB,
  change_reason            TEXT NOT NULL,
  observed_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (token, version_number),
  CONSTRAINT desafio_submission_versions_status_check CHECK (
    current_status IN (
      'active_counted',
      'active_not_counted',
      'invalid',
      'conflicted',
      'inactive_missing',
      'blocked_by_guardrail'
    )
    AND (
      previous_status IS NULL
      OR previous_status IN (
        'active_counted',
        'active_not_counted',
        'invalid',
        'conflicted',
        'inactive_missing',
        'blocked_by_guardrail'
      )
    )
  ),
  CONSTRAINT desafio_submission_versions_raw_cells_check CHECK (
    JSONB_TYPEOF(raw_cells) = 'array' AND JSONB_ARRAY_LENGTH(raw_cells) = 9
  )
);

CREATE INDEX IF NOT EXISTS ix_desafio_submissions_current_desafio
  ON desafio_submissions_current (desafio_id);
CREATE INDEX IF NOT EXISTS ix_desafio_submissions_current_clan
  ON desafio_submissions_current (clan);
CREATE INDEX IF NOT EXISTS ix_desafio_submissions_current_status
  ON desafio_submissions_current (status);
CREATE INDEX IF NOT EXISTS ix_desafio_submissions_current_submitted_at
  ON desafio_submissions_current (submitted_at);
CREATE INDEX IF NOT EXISTS ix_desafio_submissions_current_last_run
  ON desafio_submissions_current (last_seen_run_id);
CREATE INDEX IF NOT EXISTS ix_desafio_submission_versions_run
  ON desafio_submission_versions (sync_run_id);
CREATE INDEX IF NOT EXISTS ix_desafio_submission_versions_token_version
  ON desafio_submission_versions (token, version_number DESC);
CREATE INDEX IF NOT EXISTS ix_desafio_sync_runs_status
  ON desafio_sync_runs (status);
CREATE INDEX IF NOT EXISTS ix_desafio_sync_runs_snapshot_hash
  ON desafio_sync_runs (snapshot_hash);
CREATE INDEX IF NOT EXISTS ix_desafio_sync_runs_started_at
  ON desafio_sync_runs (started_at DESC);

CREATE OR REPLACE FUNCTION prevent_desafio_submission_version_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'desafio_submission_versions is immutable';
END;
$$;

DROP TRIGGER IF EXISTS desafio_submission_versions_immutable
  ON desafio_submission_versions;
CREATE TRIGGER desafio_submission_versions_immutable
  BEFORE UPDATE OR DELETE ON desafio_submission_versions
  FOR EACH ROW
  EXECUTE FUNCTION prevent_desafio_submission_version_mutation();

DROP TRIGGER IF EXISTS desafio_submission_versions_no_truncate
  ON desafio_submission_versions;
CREATE TRIGGER desafio_submission_versions_no_truncate
  BEFORE TRUNCATE ON desafio_submission_versions
  FOR EACH STATEMENT
  EXECUTE FUNCTION prevent_desafio_submission_version_mutation();
