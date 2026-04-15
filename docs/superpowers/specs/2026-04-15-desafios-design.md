# Desafios — Design Spec

**Data:** 2026-04-15  
**Status:** Aprovado

---

## Contexto

O sistema atual contabiliza pontos de clãs exclusivamente via registros de coaching importados de planilhas Google Sheets. A nova feature "Desafios" permite que administradores criem desafios personalizados com campos livres e registrem pontos obtidos por cada clã. Ao criar um desafio, o administrador define se os pontos serão somados ao total geral do clã (afetando o ranking principal) ou apenas registrados para controle interno, sem impacto no ranking.

---

## Regras de negócio

- Ao criar um desafio, o administrador define o modo via switch:
  - **"Registrar Pontos"** — os pontos dos campos `pontuacao` são somados ao `total_pontos` do clã no ranking geral.
  - **"Não Registrar Pontos"** — os pontos são armazenados apenas para controle interno e **não** afetam o ranking geral.
- O modo (`contabilizar_pontos: boolean`) pode ser alterado ao editar o desafio. Ao mudar de `true` para `false`, os pontos já aplicados ao ranking são descontados; ao mudar de `false` para `true`, os pontos dos registros existentes são aplicados ao ranking.
- Cada clã pode ter **no máximo um registro** por desafio.
- Os clãs disponíveis para registro são **apenas os clãs presentes no ranking geral** (`GET /api/clans/ranking`).
- Ao criar um registro em desafio com `contabilizar_pontos = true`, os valores de todos os campos do tipo `pontuacao` são somados e adicionados ao `total_pontos` do clã em `pontos_ultimate_totais_por_clan`.
- Ao **excluir um registro** de desafio com `contabilizar_pontos = true`, o `total_pontos` do clã é decrementado pelo valor que havia sido somado.
- Ao **excluir um desafio** com `contabilizar_pontos = true`, os pontos de todos os registros são descontados dos respectivos clãs.
- Ao **editar um desafio** (campos alterados), todos os registros existentes são recalculados. Se `contabilizar_pontos = true`, o delta (`novo_total - antigo_total`) é aplicado ao `total_pontos` de cada clã.
- A planilha Google Sheets (coluna K da seção PONTUAÇÃO GERAL) **só é atualizada quando o usuário clicar em "Atualizar Planilha"** — o endpoint reutilizado já escreve o total absoluto do banco, portanto nenhum novo endpoint é necessário.

---

## Banco de dados

### Novas tabelas (migration `003_add_desafios.sql`)

```sql
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
  valores      JSONB NOT NULL DEFAULT '{}',  -- { "<campo_id>": <valor>, ... }
  total_pontos INTEGER NOT NULL DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(desafio_id, clan)
);
```

### Efeitos colaterais em `pontos_ultimate_totais_por_clan`

Aplicam-se **apenas quando `contabilizar_pontos = true`**.

| Ação                                        | Efeito                                             |
|---------------------------------------------|----------------------------------------------------|
| POST registro                               | `total_pontos += novo_total_pontos`                |
| DELETE registro                             | `total_pontos -= total_pontos_do_registro`         |
| DELETE desafio                              | Para cada registro: `total_pontos -= total_pontos` |
| PUT desafio (edita campos, contabilizar=true) | Para cada registro: `total_pontos += delta`       |
| PUT desafio: `true → false`                 | Para cada registro: `total_pontos -= total_pontos` |
| PUT desafio: `false → true`                 | Para cada registro: `total_pontos += total_pontos` |

---

## Backend

**Novo arquivo:** `backend/routers/desafios.py`  
**Alteração:** `backend/main.py` — registrar router em `/api/desafios`

### Endpoints

```
GET    /api/desafios
       → Lista todos os desafios com contagem de campos e clãs registrados

POST   /api/desafios
       Body: { nome, contabilizar_pontos: bool, campos: [{ nome, tipo, ordem }] }
       → Cria desafio com seus campos

PUT    /api/desafios/{id}
       Body: { nome, contabilizar_pontos: bool, campos: [{ id?, nome, tipo, ordem }] }
       → Atualiza nome, modo e campos; recalcula total_pontos de todos os registros
         e aplica efeitos colaterais conforme mudança de contabilizar_pontos

DELETE /api/desafios/{id}
       → Remove desafio, campos e registros (CASCADE);
         desconta pontos de todos os clãs com registro

GET    /api/desafios/{id}/registros
       → Lista registros do desafio: clan, valores, total_pontos

POST   /api/desafios/{id}/registros
       Body: { clan, valores: { "<campo_id>": <valor> } }
       → Cria registro; soma pontos ao total do clã

DELETE /api/desafios/{id}/registros/{registro_id}
       → Remove registro; desconta pontos do clã
```

**"Atualizar Planilha"** reutiliza `POST /api/contabilidade/atualizar-planilha` — nenhum novo endpoint necessário.

---

## Frontend

### Arquivos novos/alterados

| Arquivo | Tipo | Descrição |
|---|---|---|
| `frontend/src/pages/Desafios.tsx` | Novo | Página principal da feature |
| `frontend/src/App.tsx` | Alterado | Nova rota `/desafios` |
| `frontend/src/components/Layout.tsx` | Alterado | NavLink "Desafios" |
| `frontend/src/api/client.ts` | Alterado | Novos tipos e funções de API |

### Fluxo de navegação (Opção B — lista + detalhe)

```
/desafios
 ├── [Modo lista]
 │    ├── Botão "Atualizar Planilha"
 │    ├── Botão "Novo Desafio" → [Modo formulário]
 │    └── Tabela: Nome | Nº campos | Clãs registrados | Editar | Excluir
 │         └── Clicar no nome → [Modo detalhe]
 │
 ├── [Modo formulário] (criar ou editar)
 │    ├── Input: nome do desafio
 │    ├── Switch: "Registrar Pontos" | "Não Registrar Pontos" (contabilizar_pontos)
 │    ├── Lista de campos (nome + tipo: texto|pontuacao) com + / remove
 │    └── Botões: Salvar | Cancelar
 │
 └── [Modo detalhe]
      ├── Breadcrumb: Desafios > [Nome]
      ├── Botão "Atualizar Planilha"
      ├── Seção: campos do desafio (somente leitura)
      ├── Botão "Registrar Pontos" → exibe formulário inline
      │    ├── Dropdown clã (apenas clãs do ranking geral)
      │    ├── Inputs por campo (text ou number conforme tipo)
      │    └── Botão Salvar
      └── Tabela de registros: Clã | [colunas por campo] | Total | Excluir
```

### Novos tipos em `api/client.ts`

```typescript
interface DesafioCampo {
  id: number;
  desafio_id: number;
  nome: string;
  tipo: 'texto' | 'pontuacao';
  ordem: number;
}

interface Desafio {
  id: number;
  nome: string;
  contabilizar_pontos: boolean;
  campos: DesafioCampo[];
  total_registros: number;
  created_at: string;
}

interface DesafioRegistro {
  id: number;
  desafio_id: number;
  clan: string;
  valores: Record<string, string | number>;
  total_pontos: number;
  created_at: string;
}
```

### Novas funções em `api/client.ts`

```typescript
fetchDesafios(): Promise<Desafio[]>
createDesafio(data): Promise<Desafio>
updateDesafio(id, data): Promise<Desafio>
deleteDesafio(id): Promise<void>
fetchDesafioRegistros(desafioId): Promise<DesafioRegistro[]>
createDesafioRegistro(desafioId, data): Promise<DesafioRegistro>
deleteDesafioRegistro(desafioId, registroId): Promise<void>
```

---

## Verificação end-to-end

1. **Criar desafio (Registrar Pontos):** "Novo Desafio" → nome + switch "Registrar Pontos" + 3 campos (2 pontuação, 1 texto) → salvar → aparece na lista com badge indicando modo
2. **Criar desafio (Não Registrar):** "Novo Desafio" → switch "Não Registrar Pontos" → salvar → registros desse desafio não afetam o Dashboard
3. **Registrar pontos:** Clicar no desafio → "Registrar Pontos" → selecionar clã → preencher campos → salvar → se `contabilizar_pontos=true`, total do clã aumenta no Dashboard; caso contrário, sem mudança no Dashboard
4. **Editar desafio (recálculo):** Editar removendo um campo de pontuação → pontos descontados do total dos clãs (se `contabilizar_pontos=true`)
5. **Mudar modo pelo switch:** Editar desafio de "Registrar" para "Não Registrar" → pontos existentes descontados do ranking; inverso aplica os pontos
6. **Excluir registro:** Excluir registro de um clã → pontos descontados se desafio for de contabilização
7. **Excluir desafio:** Excluir desafio → pontos de todos os registros descontados (se aplicável)
8. **Atualizar Planilha:** Clicar "Atualizar Planilha" → coluna K da planilha reflete o total atualizado
9. **Unicidade:** Clã já registrado não aparece no dropdown ao registrar novo
