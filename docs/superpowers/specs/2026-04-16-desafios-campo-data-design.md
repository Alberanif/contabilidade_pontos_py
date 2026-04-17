
# Design: Campo de Data Obrigatório nos Desafios

**Data:** 2026-04-16  
**Status:** Aprovado

## Contexto

O sistema de Desafios permite criar desafios com campos configuráveis e registrar pontos por clã. Atualmente, os desafios não possuem uma data associada. A necessidade é permitir que o usuário selecione uma data ao criar (ou editar) um desafio, representando a data de referência para contabilização dos pontos.

## Decisão de Design

Campo `data` (tipo `date`, obrigatório) adicionado diretamente na entidade `desafio`. A data é propriedade do desafio como um todo — não de cada registro individual de clã.

## Componentes Afetados

### 1. Banco de Dados (Supabase)

- Adicionar coluna `data date NOT NULL` na tabela `desafios`.
- Migration manual via painel do Supabase (o projeto não possui sistema de migrations automáticas).
- Desafios existentes precisarão ter um valor preenchido; recomendar usar `CURRENT_DATE` como default temporário ao rodar a migration.

### 2. Backend (`backend/`)

**`supabase_client.py`**
- `create_desafio(nome, contabilizar_pontos, data)` — inclui `data` no payload de insert.
- `update_desafio(desafio_id, nome, contabilizar_pontos, data)` — inclui `data` no payload de update.

**`routers/desafios.py`**
- `DesafioCreate`: novo campo `data: date` (obrigatório).
- `DesafioUpdate`: novo campo `data: date` (obrigatório).
- `criar_desafio`: repassa `body.data` para `supabase_client.create_desafio`.
- `editar_desafio`: repassa `body.data` para `supabase_client.update_desafio`.

### 3. Frontend (`frontend/src/`)

**`api/client.ts`**
- Interface `Desafio`: adicionar `data: string` (ISO date string, ex: `"2026-04-16"`).
- `createDesafio`: payload inclui campo `data: string`.
- `updateDesafio`: payload inclui campo `data: string`.

**`pages/Desafios.tsx`**
- Estado de formulário: `formData: string` (inicializado com string vazia).
- Formulário (criar/editar): `<input type="date">` obrigatório, exibido após o campo "Nome do desafio".
- Validação no frontend: bloquear submissão se `formData` estiver vazio.
- Modo lista: adicionar coluna "Data" na tabela, formatada como `dd/mm/aaaa`.
- Modo detalhe: exibir a data do desafio no cabeçalho, junto ao badge de pontuação.
- Ao abrir o formulário de edição (`openEditForm`): inicializar `formData` com o valor existente do desafio.

## Fluxo de Dados

```
Usuário preenche data no formulário
  → estado formData (string ISO)
  → createDesafio / updateDesafio (API)
  → POST/PUT /api/desafios
  → DesafioCreate / DesafioUpdate (Pydantic, campo data: date)
  → supabase_client.create_desafio / update_desafio
  → INSERT/UPDATE na tabela desafios (coluna data)
```

## Tratamento de Erros

- Frontend bloqueia submissão se data estiver vazia (validação local).
- Backend rejeita requisições sem `data` via validação automática do Pydantic (HTTP 422).

## O que NÃO está no escopo

- Filtrar desafios por data.
- Usar a data para qualquer cálculo automático de pontos.
- Desafios recorrentes ou períodos (data de início/fim).
