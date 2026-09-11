-- backend/migrations/011_add_coach_clas.sql
CREATE TABLE IF NOT EXISTS pontos_ultimate_coach_clas (
    id SERIAL PRIMARY KEY,
    coach_canonico VARCHAR NOT NULL UNIQUE,
    clan VARCHAR NOT NULL,
    categoria VARCHAR NOT NULL
        CHECK (categoria IN (
            'Coach', 'Coach Action', 'Coach Pro', 'Coach Hero',
            'Sem Categoria', 'Novos ULTIMATES'
        )),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_coach_clas_clan ON pontos_ultimate_coach_clas(clan);
