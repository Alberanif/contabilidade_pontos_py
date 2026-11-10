# Notas para o Claude

## Autenticação e deploy
- O app usa login próprio (sessão por cookie assinado) e gestão de usuários, em substituição ao antigo HTTP Basic Auth. Escopo no PRD #54; implementação nas issues #55-#62 (parte pode ainda não existir no código).
- Variáveis: `SESSION_SECRET` (obrigatória; gere com `python -c "import secrets; print(secrets.token_urlsafe(48))"`), `APP_USER` (e-mail) e `APP_PASSWORD`, que só semeiam o primeiro admin com troca de senha obrigatória no primeiro login.
- Somente `/api/health` e `/api/auth/login` são públicos.
- A migration de usuários deve ser aplicada no Supabase antes do deploy. Passo a passo e roteiro de fumaça em `docs/DEPLOY_EASYPANEL.md`.
- `.env.easypanel` é local e ignorado pelo git; não versionar nem ler segredos.
