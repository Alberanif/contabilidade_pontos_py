-- backend/migrations/003_add_desafios.sql
CREATE TABLE desafios (
  id                  SERIAL PRIMARY KEY,
  nome                VARCHAR NOT NULL,
  contabilizar_pontos BOOLEAN NOT NULL DEFAULT TRUE,
  created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE desafio_campos (
  id         SERIAL PRIMARY KEY,
  desafio_id INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  nome       VARCHAR NOT NULL,
  tipo       VARCHAR NOT NULL CHECK (tipo IN ('texto', 'pontuacao')),
  ordem      INTEGER DEFAULT 0
);

CREATE TABLE desafio_registros (
  id           SERIAL PRIMARY KEY,
  desafio_id   INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  clan         VARCHAR NOT NULL,
  valores      JSONB NOT NULL DEFAULT '{}',
  total_pontos INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(desafio_id, clan)
);
