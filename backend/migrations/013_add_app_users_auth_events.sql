-- backend/migrations/013_add_app_users_auth_events.sql
-- Login por usuário (PRD #54): contas da aplicação e trilha de eventos de auth.

CREATE TABLE IF NOT EXISTS app_users (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR NOT NULL CHECK (email = lower(email)),
    nome VARCHAR NOT NULL,
    senha_hash VARCHAR NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    deve_trocar_senha BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_login_em TIMESTAMP WITH TIME ZONE,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- E-mail único sem diferenciar maiúsculas de minúsculas.
CREATE UNIQUE INDEX IF NOT EXISTS uq_app_users_email_lower ON app_users (lower(email));

CREATE TABLE IF NOT EXISTS auth_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES app_users(id) ON DELETE SET NULL,
    email_tentado VARCHAR,
    tipo VARCHAR NOT NULL,
    ip VARCHAR,
    criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auth_events_user_id ON auth_events (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_events_criado_em ON auth_events (criado_em DESC);
