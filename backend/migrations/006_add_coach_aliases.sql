-- backend/migrations/006_add_coach_aliases.sql
CREATE TABLE IF NOT EXISTS pontos_ultimate_coach_aliases (
    id SERIAL PRIMARY KEY,
    alias VARCHAR NOT NULL UNIQUE,
    coach_canonico VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
