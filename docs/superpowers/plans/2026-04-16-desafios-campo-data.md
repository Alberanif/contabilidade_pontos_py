# Desafios — Campo de Data Obrigatório: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um campo `data` (obrigatório) aos Desafios, permitindo que o usuário selecione a data de referência para contabilização dos pontos ao criar ou editar um desafio.

**Architecture:** Campo `data date NOT NULL` adicionado na tabela `desafios` do Supabase. Backend atualizado (Pydantic models + supabase_client). Frontend atualizado (TypeScript interfaces + formulário + exibição na lista e no detalhe).

**Tech Stack:** FastAPI + Pydantic (backend), Supabase Python client, React + TypeScript (frontend), Tailwind CSS.

---

## Arquivos Modificados

| Arquivo | O que muda |
|---|---|
| `backend/supabase_client.py` | Assinaturas de `create_desafio` e `update_desafio` recebem `data` |
| `backend/routers/desafios.py` | `DesafioCreate` e `DesafioUpdate` ganham `data: date`; handlers repassam o campo |
| `frontend/src/api/client.ts` | Interface `Desafio` ganha `data: string`; payloads de create/update incluem `data` |
| `frontend/src/pages/Desafios.tsx` | Estado `formData`, input de data, validação, exibição na lista e no detalhe |

---

## Task 1: Migração do Banco de Dados (Supabase)

**Files:**
- Nenhum arquivo de código — passo manual no painel do Supabase.

- [ ] **Step 1: Abrir o SQL Editor no painel do Supabase**

Acesse o projeto no Supabase → SQL Editor → New query.

- [ ] **Step 2: Executar a migration**

```sql
-- Adiciona coluna com DEFAULT temporário para não quebrar linhas existentes
ALTER TABLE desafios ADD COLUMN data date NOT NULL DEFAULT CURRENT_DATE;

-- Remove o DEFAULT para garantir que novas inserções sem data falhem
ALTER TABLE desafios ALTER COLUMN data DROP DEFAULT;
```

Confirme que a query retorna sem erros.

- [ ] **Step 3: Verificar a coluna**

```sql
SELECT id, nome, data FROM desafios LIMIT 5;
```

Esperado: linhas existentes aparecem com `data = hoje` (data de hoje como valor preenchido pelo DEFAULT).

---

## Task 2: Backend — `supabase_client.py`

**Files:**
- Modify: `backend/supabase_client.py` (funções `create_desafio` e `update_desafio`)

- [ ] **Step 1: Atualizar `create_desafio` para aceitar e persistir `data`**

Localizar a função `create_desafio` (linha ~285) e substituir por:

```python
def create_desafio(nome: str, contabilizar_pontos: bool, data) -> dict:
    """Cria um novo desafio."""
    client = _get_client()
    result = client.table(TABLE_DESAFIOS).insert(
        {"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)}
    ).execute()
    return result.data[0]
```

- [ ] **Step 2: Atualizar `update_desafio` para aceitar e persistir `data`**

Localizar a função `update_desafio` (linha ~308) e substituir por:

```python
def update_desafio(desafio_id: int, nome: str, contabilizar_pontos: bool, data) -> dict:
    """Atualiza nome, modo de contabilização e data de um desafio."""
    client = _get_client()
    result = (
        client.table(TABLE_DESAFIOS)
        .update({"nome": nome, "contabilizar_pontos": contabilizar_pontos, "data": str(data)})
        .eq("id", desafio_id)
        .execute()
    )
    return result.data[0]
```

- [ ] **Step 3: Commit**

```bash
git add backend/supabase_client.py
git commit -m "feat(desafios): add data param to create_desafio and update_desafio"
```

---

## Task 3: Backend — `routers/desafios.py`

**Files:**
- Modify: `backend/routers/desafios.py`

- [ ] **Step 1: Importar `date` do módulo `datetime`**

Na linha 1 do arquivo, após `from fastapi import APIRouter, HTTPException`, adicionar:

```python
from datetime import date
```

- [ ] **Step 2: Adicionar `data: date` em `DesafioCreate`**

Substituir o modelo `DesafioCreate` por:

```python
class DesafioCreate(BaseModel):
    nome: str
    contabilizar_pontos: bool = True
    data: date
    campos: list[CampoInput]
```

- [ ] **Step 3: Adicionar `data: date` em `DesafioUpdate`**

Substituir o modelo `DesafioUpdate` por:

```python
class DesafioUpdate(BaseModel):
    nome: str
    contabilizar_pontos: bool
    data: date
    campos: list[CampoInput]
```

- [ ] **Step 4: Repassar `body.data` em `criar_desafio`**

Na função `criar_desafio`, substituir a linha que chama `supabase_client.create_desafio` por:

```python
    desafio = supabase_client.create_desafio(body.nome, body.contabilizar_pontos, body.data)
```

- [ ] **Step 5: Repassar `body.data` em `editar_desafio`**

Na função `editar_desafio`, substituir a linha que chama `supabase_client.update_desafio` por:

```python
    updated = supabase_client.update_desafio(desafio_id, body.nome, new_contabilizar, body.data)
```

- [ ] **Step 6: Verificar que o servidor sobe sem erros**

```bash
cd backend && uvicorn main:app --reload
```

Esperado: servidor inicia sem erros de importação ou sintaxe.

- [ ] **Step 7: Testar manualmente via curl que `data` é obrigatória**

```bash
curl -s -X POST http://localhost:8000/api/desafios \
  -H "Content-Type: application/json" \
  -d '{"nome": "Teste", "contabilizar_pontos": true, "campos": []}' \
  | python3 -m json.tool
```

Esperado: resposta HTTP 422 com detalhe informando que `data` é campo obrigatório.

- [ ] **Step 8: Testar criação com `data` válida**

```bash
curl -s -X POST http://localhost:8000/api/desafios \
  -H "Content-Type: application/json" \
  -d '{"nome": "Teste Data", "contabilizar_pontos": true, "data": "2026-04-16", "campos": []}' \
  | python3 -m json.tool
```

Esperado: resposta HTTP 200 com o desafio criado contendo `"data": "2026-04-16"`.

- [ ] **Step 9: Commit**

```bash
git add backend/routers/desafios.py
git commit -m "feat(desafios): require data field in DesafioCreate and DesafioUpdate"
```

---

## Task 4: Frontend — `api/client.ts`

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Adicionar `data: string` na interface `Desafio`**

Substituir a interface `Desafio` por:

```typescript
export interface Desafio {
  id: number;
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  campos: DesafioCampo[];
  total_registros: number;
  created_at: string;
}
```

- [ ] **Step 2: Atualizar `createDesafio` para incluir `data`**

Substituir a função `createDesafio` por:

```typescript
export function createDesafio(data: {
  nome: string;
  contabilizar_pontos: boolean;
  data: string;
  campos: { nome: string; tipo: string; ordem: number }[];
}): Promise<Desafio> {
  return request('/api/desafios', { method: 'POST', body: JSON.stringify(data) });
}
```

- [ ] **Step 3: Atualizar `updateDesafio` para incluir `data`**

Substituir a função `updateDesafio` por:

```typescript
export function updateDesafio(
  id: number,
  data: {
    nome: string;
    contabilizar_pontos: boolean;
    data: string;
    campos: { id?: number; nome: string; tipo: string; ordem: number }[];
  }
): Promise<Desafio> {
  return request(`/api/desafios/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(desafios): add data field to Desafio interface and API functions"
```

---

## Task 5: Frontend — `pages/Desafios.tsx`

**Files:**
- Modify: `frontend/src/pages/Desafios.tsx`

- [ ] **Step 1: Adicionar helper `formatDate` antes do componente**

Logo antes da linha `type Mode = "list" | "form" | "detail";`, inserir:

```typescript
function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  const [year, month, day] = dateStr.split("-");
  return `${day}/${month}/${year}`;
}
```

- [ ] **Step 2: Adicionar estado `formData`**

Após a linha `const [formContabilizar, setFormContabilizar] = useState(true);`, adicionar:

```typescript
  const [formData, setFormData] = useState("");
```

- [ ] **Step 3: Inicializar `formData` em `openCreateForm`**

Na função `openCreateForm`, após `setFormContabilizar(true);`, adicionar:

```typescript
    setFormData("");
```

- [ ] **Step 4: Inicializar `formData` em `openEditForm`**

Na função `openEditForm`, após `setFormContabilizar(desafio.contabilizar_pontos);`, adicionar:

```typescript
    setFormData(desafio.data ?? "");
```

- [ ] **Step 5: Adicionar validação de `formData` em `handleSaveDesafio`**

Na função `handleSaveDesafio`, após a validação de `formNome`:

```typescript
    if (!formNome.trim()) {
      setError("O nome do desafio é obrigatório.");
      return;
    }
    if (!formData) {
      setError("A data do desafio é obrigatória.");
      return;
    }
```

- [ ] **Step 6: Passar `formData` nas chamadas de API dentro de `handleSaveDesafio`**

Substituir o bloco `if (editingDesafio) { ... } else { ... }` por:

```typescript
      if (editingDesafio) {
        await updateDesafio(editingDesafio.id, {
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          data: formData,
          campos,
        });
        setSuccess("Desafio atualizado com sucesso.");
      } else {
        await createDesafio({
          nome: formNome,
          contabilizar_pontos: formContabilizar,
          data: formData,
          campos,
        });
        setSuccess("Desafio criado com sucesso.");
      }
```

- [ ] **Step 7: Adicionar coluna "Data" no modo lista**

No `<thead>` da tabela do modo lista, adicionar a coluna após `<th>Nome</th>`:

```tsx
                  <th className="py-3 px-4 font-medium">Data</th>
```

No `<tbody>`, dentro do `.map((d) => ...)`, adicionar a célula após o `<td>` do nome:

```tsx
                    <td className="py-3 px-4 text-gray-600">
                      {formatDate(d.data)}
                    </td>
```

- [ ] **Step 8: Exibir data no modo detalhe**

No modo detalhe, após o `<span>` do badge de pontuação (dentro do `{selectedDesafio && (...)}` do cabeçalho), adicionar:

```tsx
          {selectedDesafio?.data && (
            <span className="text-sm text-gray-500">
              {formatDate(selectedDesafio.data)}
            </span>
          )}
```

- [ ] **Step 9: Adicionar input de data no formulário**

No modo formulário, após o bloco `<div>` do campo "Nome do desafio" (após o `</div>` que fecha esse grupo), inserir:

```tsx
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Data do desafio
            </label>
            <input
              type="date"
              value={formData}
              onChange={(e) => setFormData(e.target.value)}
              required
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
```

- [ ] **Step 10: Verificar o frontend em desenvolvimento**

```bash
cd frontend && npm run dev
```

Abrir `http://localhost:5173` no navegador, navegar até "Desafios":
- Clicar "Novo Desafio": confirmar que o campo "Data do desafio" aparece abaixo de "Nome".
- Tentar salvar sem data: confirmar que a mensagem "A data do desafio é obrigatória." aparece.
- Salvar com data preenchida: confirmar que o desafio é criado e a data aparece na lista.
- Editar um desafio existente: confirmar que a data já vem preenchida no formulário.
- Abrir o detalhe de um desafio: confirmar que a data aparece no cabeçalho.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/Desafios.tsx
git commit -m "feat(desafios): add required date field to form, list, and detail views"
```
