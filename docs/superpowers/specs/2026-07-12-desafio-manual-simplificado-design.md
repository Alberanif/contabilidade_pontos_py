# Simplificação do Cadastro Manual de Desafios — Design Spec

**Data:** 2026-07-12
**Status:** Aprovado (via sessão de brainstorming)

---

## Contexto

Hoje o cadastro manual de desafio (`frontend/src/pages/Desafios.tsx`) tem dois passos separados:

1. Criar o desafio com nome, uma única data e uma lista de "Campos" customizados (texto/pontuação), configurados um a um.
2. Ir para a tela de detalhe do desafio e, ali, registrar cada clã individualmente preenchendo os valores desses campos.

Isso é mais flexível do que o necessário no caso comum: na prática o usuário só quer dizer "esse desafio vale de tal data a tal data, e cada clã que participou fez tantos pontos". Esta feature simplifica o fluxo: o formulário de criação/edição passa a ter diretamente nome, período (`data_inicio`/`data_fim`), o toggle "Registrar Pontos" (já existente) e uma lista de linhas **Clã + Pontuação**, tudo salvo de uma vez.

`data_inicio`, `data_fim` e `origem` já foram especificados e migrados (via SQL manual) na feature de importação de CSV (`docs/superpowers/specs/2026-07-12-desafio-import-csv-design.md`) — esta feature reaproveita as mesmas colunas, sem schema novo.

---

## Regras de negócio

1. **Campo implícito "Pontos".** Todo desafio `origem='manual'` passa a ter automaticamente, gerenciado pelo backend (nunca exposto na UI como "Campos"), exatamente um `desafio_campo` com `nome='Pontos'`, `tipo='pontuacao'`. Isso permite reaproveitar `calculate_desafio_pontos` e `desafio_registros` sem mudança de schema: cada linha Clã+Pontuação vira um `desafio_registro` com `valores={"<id_do_campo_pontos>": pontos}` e `total_pontos=pontos`.
2. **Criação em um único passo.** `POST /api/desafios` recebe nome, `data_inicio`, `data_fim`, `contabilizar_pontos` e a lista completa `registros: [{clan, pontos}]`. O backend cria o desafio, o campo implícito e todos os registros, aplicando delta no total de cada clã se `contabilizar_pontos=true`.
3. **Edição com diff por clã.** `PUT /api/desafios/{id}` recebe o mesmo formato e faz um diff entre os registros existentes e os enviados, clã a clã: clã removido da lista → registro é excluído e os pontos descontados (se `contabilizar_pontos` valia); clã novo → registro criado e pontos somados; clã com pontuação alterada → registro atualizado e o delta líquido aplicado. As 4 combinações de `contabilizar_pontos` antigo/novo (true→true, true→false, false→true, false→false) seguem a mesma lógica de delta já implementada em `editar_desafio` hoje.
4. **Conversão de desafios legados.** Um desafio criado antes desta feature (com campos customizados variados, um ou mais por clã) pode ser aberto para edição normalmente. Ao editar, a lista Clã+Pontuação vem pré-preenchida com o `total_pontos` atual de cada clã (não o breakdown por campo). Ao salvar, os campos customizados antigos são apagados e substituídos pelo campo implícito `"Pontos"` — a conversão é permanente e definitiva a partir do primeiro salvamento no novo formulário.
5. **Desafios de importação CSV não usam este formulário.** Desafios com `origem='csv_import'` mantêm sua estrutura de dois campos (`pontuacao` = total calculado, `texto` = contagem bruta de participações) intocada. O botão "Editar" não aparece para eles na listagem — atualização é feita exclusivamente pelo fluxo "Atualizar existente" do wizard de importação (já implementado).
6. **`data` (coluna legada, `NOT NULL`) recebe `data_fim`.** Mesma convenção já usada pela importação CSV — mantém compatibilidade com qualquer código que ainda leia só `data`.
7. **Validação:** `data_fim >= data_inicio`; pontuação por clã é inteiro `>= 0`; um mesmo clã não pode aparecer duas vezes na lista de registros de uma mesma submissão.

---

## Backend

**Alterados:** `backend/routers/desafios.py`, `backend/supabase_client.py`. Nenhum arquivo novo, nenhuma migration nova.

### Contrato dos endpoints existentes (payload muda)

```
POST /api/desafios
PUT  /api/desafios/{id}
  body: {
    nome: string,
    contabilizar_pontos: bool,
    data_inicio: date,
    data_fim: date,
    registros: [{ clan: string, pontos: int }]
  }
  → retorna o desafio no mesmo shape de hoje (campos + total_registros),
    exceto que `campos` sempre terá exatamente 1 item ("Pontos") para
    desafios origem='manual'.
```

`GET /api/desafios`, `DELETE /api/desafios/{id}`, `GET/POST/DELETE /api/desafios/{id}/registros` continuam como estão (endpoints granulares de registro seguem existindo, só não são mais usados pela tela de detalhe).

### `supabase_client.py`

- `update_desafio(desafio_id, nome, contabilizar_pontos, data, data_inicio=None, data_fim=None)` — ganha os dois parâmetros novos, opcionais para não quebrar nenhum outro chamador.
- Nenhuma função nova é necessária além dessa extensão — `create_desafio`, `insert_desafio_campos`, `delete_desafio_campos`, `create_desafio_registro`, `update_desafio_registro_pontos`, `delete_desafio_registro`, `add_delta_to_clan_total` já cobrem tudo.

### `routers/desafios.py`

- `criar_desafio`: cria o desafio (`origem='manual'`, `data=data_fim`), cria o campo `"Pontos"`, itera `body.registros` criando um `desafio_registro` por linha e aplicando delta.
- `editar_desafio`: busca campos atuais; se não for exatamente `[{"nome": "Pontos", "tipo": "pontuacao"}]`, apaga todos e recria o campo implícito (conversão de legado, regra 4). Constrói `old_por_clan` a partir de `list_desafio_registros`, `new_por_clan` a partir de `body.registros`, e aplica o diff descrito na regra 3, reaproveitando o padrão de delta que já existe na função hoje (adaptado de "por campo" para "por clã ausente/novo/alterado").

---

## Frontend

**Alterado:** `frontend/src/pages/Desafios.tsx`, `frontend/src/api/client.ts`. Nenhum componente novo.

### `client.ts`

- `Desafio` ganha `data_inicio?: string`, `data_fim?: string`, `origem?: string` (opcionais — legado pode não ter).
- `createDesafio`/`updateDesafio`: parâmetro `campos` é substituído por `data_inicio: string`, `data_fim: string`, `registros: { clan: string; pontos: number }[]`.

### Formulário único (`mode === "form"`, cobre criar e editar)

```
Nome do desafio          [__________________]
Data Início   [____]     Data Fim   [____]
( Registrar Pontos | Não Registrar Pontos )   ← toggle já existente

Clãs e pontuação
  [Clã 1 ▾]  [90___] pontos   ✕
  [Clã 3 ▾]  [40___] pontos   ✕
  + Adicionar clã

[Salvar Desafio]  [Cancelar]
```

- Dropdown de clã usa `fetchRanking()` (já carregado hoje) filtrando os clãs já adicionados nas outras linhas, igual à lógica `availableClans` que já existe.
- No modo edição, a lista de linhas vem pré-preenchida a partir de `fetchDesafioRegistros(id)` (`clan` + `total_pontos`).
- Validação no cliente: nome, data início e fim obrigatórios, `data_fim >= data_inicio`, pelo menos os clãs adicionados têm pontuação numérica válida.

### Modo detalhe (`mode === "detail"`) — somente leitura

- Mostra nome, badge Registrar/Não Registrar, período, e uma tabela Clã | Pontos (sem forma de editar/remover linha por linha ali).
- Botão "Editar" leva ao formulário unificado. Some para desafios com `origem === 'csv_import'`.
- Formulário inline de "Registrar Pontos" e botão "Remover" por registro são removidos desta tela (a edição agora é sempre pelo formulário completo).

### Listagem (`mode === "list"`)

- Coluna "Data" passa a exibir `dd/mm - dd/mm` quando `data_inicio`/`data_fim` estiverem presentes; cai para o `formatDate(d.data)` atual quando não (desafios legados nunca editados no novo formulário).
- Botão "Editar" oculto quando `d.origem === 'csv_import'`.

---

## Verificação end-to-end

1. **Criar desafio novo:** nome "Desafio Teste", período 01/07–10/07, Registrar Pontos ligado, adiciona Clã 1 (50 pts) e Clã 2 (30 pts) → salva → lista mostra período 01/07-10/07, total do Clã 1 sobe 50 e do Clã 2 sobe 30 no Dashboard.
2. **Editar desafio novo:** abre o desafio criado acima, remove Clã 2, muda Clã 1 para 80 pts, adiciona Clã 3 (20 pts) → salva → Clã 1 sobe +30 (delta), Clã 2 desconta -30, Clã 3 sobe +20.
3. **Toggle Registrar Pontos:** cria desafio com toggle desligado e Clã 1 (40 pts) → nenhum ponto é somado ao ranking; liga o toggle depois e salva de novo (mesmos registros) → +40 é aplicado ao Clã 1.
4. **Conversão de legado:** abre um desafio antigo (criado antes desta feature, com campos customizados) → tela de edição mostra a lista Clã+Pontuação já convertida com os totais atuais → salva sem mudar nada → campos customizados antigos somem, desafio passa a ter só o campo implícito "Pontos", pontos dos clãs permanecem inalterados (delta líquido = 0).
5. **Desafio de importação CSV:** na listagem, um desafio com origem "csv_import" não mostra botão "Editar".
6. **Exclusão:** excluir um desafio criado pelo novo formulário desconta corretamente os pontos de todos os clãs registrados (comportamento já existente, sem mudança).
