-- Migração 012: Apuração de Desafios por Clã — Percentual de Participação e Revisão Manual
-- Suporta o PRD de 11/09/2026

-- 1. Tabela de revisões manuais por submissão (pós-corte 01/08/2026)
CREATE TABLE IF NOT EXISTS desafio_submissao_revisoes (
    token         TEXT PRIMARY KEY REFERENCES desafio_submissions_current(token) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'pendente'
                      CHECK (status IN ('pendente', 'aprovado', 'reprovado')),
    revisado_por  TEXT,
    revisado_em   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_desafio_submissao_revisoes_status
    ON desafio_submissao_revisoes (status);

-- 2. Novas colunas na tabela desafios (gestão de prazo e data de apuração)
ALTER TABLE desafios ADD COLUMN IF NOT EXISTS prazo_apuracao TIMESTAMPTZ;
ALTER TABLE desafios ADD COLUMN IF NOT EXISTS apurado_em TIMESTAMPTZ;

-- 3. Tabela de resultados de apuração por clã
CREATE TABLE IF NOT EXISTS desafio_clan_apuracoes (
    id                    SERIAL PRIMARY KEY,
    desafio_id            INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
    clan                  TEXT NOT NULL,
    participantes         INTEGER NOT NULL CHECK (participantes >= 0),
    total_grupo           INTEGER NOT NULL CHECK (total_grupo >= 0),
    percentual            NUMERIC NOT NULL,
    pontos                INTEGER NOT NULL CHECK (pontos >= 0),
    apurado_em            TIMESTAMPTZ NOT NULL DEFAULT NOW(),z
    UNIQUE (desafio_id, clan)
);
