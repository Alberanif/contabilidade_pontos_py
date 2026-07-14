-- backend/migrations/007_add_desafio_registros_coach.sql
ALTER TABLE desafio_importacao_linhas ADD COLUMN coach VARCHAR;

CREATE TABLE desafio_registros_coach (
  id           SERIAL PRIMARY KEY,
  desafio_id   INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  coach        VARCHAR NOT NULL,
  valores      JSONB NOT NULL,
  total_pontos INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(desafio_id, coach)
);
