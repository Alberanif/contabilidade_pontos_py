-- backend/migrations/005_add_desafio_importacao_linhas.sql
CREATE TABLE desafio_importacao_linhas (
  id                 SERIAL PRIMARY KEY,
  desafio_id         INTEGER NOT NULL REFERENCES desafios(id) ON DELETE CASCADE,
  clan               VARCHAR NOT NULL,
  nome_participante  VARCHAR NOT NULL,
  validado           BOOLEAN NOT NULL,
  contabilizado      BOOLEAN NOT NULL DEFAULT FALSE,
  submitted_at       TIMESTAMP,
  token_original     VARCHAR NOT NULL,
  created_at         TIMESTAMP DEFAULT NOW(),
  UNIQUE(desafio_id, token_original)
);
