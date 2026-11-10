# Deploy na VPS Hostinger com Easypanel

O app é uma única imagem Docker: build do React + FastAPI servindo API (`/api`) e frontend (`/`) na porta **8080**. É stateless (dados no Supabase e Google Sheets) — não precisa de volume nem banco.

## 1. Criar o serviço
1. Easypanel → projeto → **+ Service → App**.
2. **Source → Git** (opção genérica, sem o GitHub App):
   - **Repository URL**: `https://github.com/Alberanif/contabilidade_pontos_py.git`. Se o repositório for privado, use SSH (`git@github.com:Alberanif/contabilidade_pontos_py.git`) e cadastre a chave pública que o Easypanel mostra em GitHub → Settings → Deploy keys (somente leitura).
   - **Branch**: `master`.
   - **Build path**: `/` (raiz do repositório).
3. **Build → Dockerfile** (caminho `Dockerfile`, na raiz).
4. **Domains**: use o domínio padrão do Easypanel (`<projeto>-<serviço>.<id>.easypanel.host`), que já é criado com o serviço. Ajuste a porta do proxy para **8080**. O HTTPS é emitido automaticamente para esse domínio, e não é preciso configurar DNS.
5. **Environment**: cole as variáveis abaixo (aba Environment).
6. **Deploy**. Com a fonte Git genérica, o Easypanel não faz auto-deploy sozinho. Para deploy a cada push em `master`, copie a URL do webhook na aba **Deploy** do serviço e cadastre em GitHub → Settings → Webhooks (Content type `application/json`, evento `push`). Sem o webhook, clique em **Deploy** manualmente após cada merge.

## 2. Variáveis de ambiente
Obrigatórias (o app não sobe sem elas):

```
SESSION_SECRET=<valor aleatório longo>
APP_USER=<e-mail do primeiro admin>
APP_PASSWORD=<senha provisória forte, mínimo 10 caracteres>
GOOGLE_SERVICE_ACCOUNT_JSON=<JSON da service account em UMA linha>
GSHEET_RECORDS_SPREADSHEET_ID=...
GSHEET_RECORDS_SHEET_NAME=...
GSHEET_TOTALS_SPREADSHEET_ID=...
GSHEET_TOTALS_SHEET_NAME=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Demais (ver `.env.example`): `GSHEET_RECORDS_PRO_BONO_*`, `GSHEET_DESAFIOS_*`, `POINTS_PER_*`, `GROQ_*`.

- `SESSION_SECRET` assina o cookie de sessão. Gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Trocar o valor invalida todas as sessões abertas.
- `APP_USER` (deve ser um e-mail) e `APP_PASSWORD` **só semeiam o primeiro admin**, quando a tabela de usuários está vazia. Depois da primeira subida não são mais usadas para login (mudar a variável não altera a senha de ninguém).
- **Não** defina `APP_AUTH_DISABLED` em produção.
- `CORS_ORIGINS` normalmente fica vazio (frontend e API são same-origin).
- Não precisa definir `PORT` (default 8080).
- Para colocar o JSON da service account em uma linha: `jq -c . service-account.json`.

## 3. Acesso e verificação
- Login por sessão (cookie `HttpOnly`, 7 dias). Em produção com HTTPS mantenha `SESSION_COOKIE_SECURE=true` (padrão); em HTTP puro (teste local) defina `SESSION_COOKIE_SECURE=false`.

**Ordem do deploy**
1. Aplicar a migration de usuários (`app_users` e `auth_events`, em `backend/migrations`) no Supabase **antes** de subir a nova versão.
2. Definir `SESSION_SECRET`, `APP_USER` (e-mail) e `APP_PASSWORD` no Environment do serviço.
3. Fazer o deploy.

**Primeiro acesso**
- Na primeira subida, com a tabela de usuários vazia, o backend cria o admin com `APP_USER`/`APP_PASSWORD`.
- Ao abrir o domínio você cai na tela `/login`. Entre com esse e-mail e senha; a troca de senha é obrigatória no primeiro login (até trocar, só a tela de troca e o logout funcionam).
- Em seguida, na tela `/usuarios` (somente admin), crie os demais usuários com senha provisória; cada um troca a própria senha no primeiro login. Usuários são desativados, nunca apagados.

**Roteiro de fumaça**
1. Subir a imagem (Easypanel ou `docker compose up --build`).
2. `GET /api/health` responde 200 sem sessão; qualquer outra rota da API responde 401 sem sessão.
3. Entrar em `/login` com o admin semeado.
4. Trocar a senha quando solicitado e confirmar que o app abre normalmente.
5. Em `/usuarios`, criar um usuário; entrar com ele em outra janela, trocar a senha provisória e conferir que um não-admin não vê `/usuarios`.
6. Desativar esse usuário e confirmar que a próxima requisição dele cai em `/login`.

- `GET /api/health` é público e usado pelo `HEALTHCHECK` do container.
- Logs: aba **Logs** do serviço no Easypanel.

## 4. Testar a imagem localmente
```
docker compose up --build   # lê .env da raiz; abre http://localhost:8080
```
(No `.env` local defina `SESSION_SECRET`, `APP_USER` e `APP_PASSWORD`, e aplique a migration de usuários no Supabase.)

## 5. Dev local
Sem Docker, defina `APP_AUTH_DISABLED=true` no `.env` para desligar o login, ou configure `SESSION_SECRET`, `APP_USER` e `APP_PASSWORD` como em produção. Nunca use `APP_AUTH_DISABLED` em produção.
