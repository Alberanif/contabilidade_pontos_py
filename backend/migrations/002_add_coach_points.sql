-- Adiciona coach e metadados na tabela principal
ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN IF NOT EXISTS coach VARCHAR NOT NULL DEFAULT 'DESCONHECIDO';

ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN IF NOT EXISTS status_coach VARCHAR NOT NULL DEFAULT 'pendente';

ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN IF NOT EXISTS pontos_coach INTEGER NOT NULL DEFAULT 0;

-- Cria a tabela de totais por coach
CREATE TABLE IF NOT EXISTS pontos_ultimate_totais_por_coach (
    id SERIAL PRIMARY KEY,
    coach VARCHAR NOT NULL UNIQUE,
    total_pontos INTEGER NOT NULL DEFAULT 0,
    pessoas_em_espera INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
