# Deploy na VPS Hostinger com Easypanel

O app é uma única imagem Docker: build do React + FastAPI servindo API (`/api`) e frontend (`/`) na porta **8080**. É stateless (dados no Supabase e Google Sheets) — não precisa de volume nem banco.

## 1. Criar o serviço
1. Easypanel → projeto → **+ Service → App**.
2. **Source → GitHub**: repositório `Alberanif/contabilidade_pontos_py`, branch `master`.
3. **Build → Dockerfile** (caminho `Dockerfile`, na raiz).
4. **Domains**: adicione o domínio, porta do proxy **8080**, HTTPS (Let's Encrypt) ligado.
5. **Environment**: cole as variáveis abaixo (aba Environment).
6. **Deploy**. Para auto-deploy a cada push em `master`, ative o webhook/Auto Deploy do serviço (GitHub App ou webhook copiado da aba Deploy para Settings → Webhooks do repositório).

## 2. Variáveis de ambiente
Obrigatórias (o app não sobe sem elas):

```
APP_USER=admin
APP_PASSWORD=<senha forte>
GOOGLE_SERVICE_ACCOUNT_JSON=<JSON da service account em UMA linha>
GSHEET_RECORDS_SPREADSHEET_ID=...
GSHEET_RECORDS_SHEET_NAME=...
GSHEET_TOTALS_SPREADSHEET_ID=...
GSHEET_TOTALS_SHEET_NAME=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Demais (ver `.env.example`): `GSHEET_RECORDS_PRO_BONO_*`, `GSHEET_DESAFIOS_*`, `POINTS_PER_*`, `GROQ_*`.

- **Não** defina `APP_AUTH_DISABLED` em produção.
- `CORS_ORIGINS` normalmente fica vazio (frontend e API são same-origin).
- Não precisa definir `PORT` (default 8080).
- Para colocar o JSON da service account em uma linha: `jq -c . service-account.json`.

## 3. Acesso e verificação
- Ao abrir o domínio o navegador pede usuário/senha (`APP_USER`/`APP_PASSWORD`).
- `GET /api/health` é público e usado pelo `HEALTHCHECK` do container.
- Logs: aba **Logs** do serviço no Easypanel.

## 4. Testar a imagem localmente
```
docker compose up --build   # lê .env da raiz; abre http://localhost:8080
```
(No `.env` local defina `APP_PASSWORD`.)

## 5. Dev local
Sem Docker, defina `APP_AUTH_DISABLED=true` no `.env` (ou `APP_PASSWORD`) — caso contrário o backend não inicia.
