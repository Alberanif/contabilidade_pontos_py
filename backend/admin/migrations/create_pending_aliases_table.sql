-- Migration: Criar tabela para fila de sugestões de aliases pendentes (Groq / RapidFuzz)
-- Tabela: pontos_ultimate_coach_aliases_pendentes

CREATE TABLE IF NOT EXISTS pontos_ultimate_coach_aliases_pendentes (
    id SERIAL PRIMARY KEY,
    alias_raw VARCHAR NOT NULL UNIQUE,
    coach_sugerido VARCHAR NOT NULL,
    confianca NUMERIC(5,2) NOT NULL, -- ex: 92.50
    origem VARCHAR NOT NULL DEFAULT 'groq-llm', -- 'groq-llm' ou 'rapidfuzz'
    status VARCHAR NOT NULL DEFAULT 'pendente', -- 'pendente', 'aprovado', 'rejeitado'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Índices para otimização de busca por status e alias_raw
CREATE INDEX IF NOT EXISTS idx_coach_aliases_pendentes_status ON pontos_ultimate_coach_aliases_pendentes(status);
CREATE INDEX IF NOT EXISTS idx_coach_aliases_pendentes_alias_raw ON pontos_ultimate_coach_aliases_pendentes(alias_raw);
