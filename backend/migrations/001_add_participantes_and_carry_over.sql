-- Adiciona num_participantes em registros (default 1 para compatibilidade)
ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN IF NOT EXISTS num_participantes INTEGER NOT NULL DEFAULT 1;

-- Adiciona carry-over por clã em totais
ALTER TABLE pontos_ultimate_totais_por_clan
ADD COLUMN IF NOT EXISTS pessoas_em_espera INTEGER NOT NULL DEFAULT 0;
