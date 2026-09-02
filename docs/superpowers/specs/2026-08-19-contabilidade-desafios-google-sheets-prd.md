# PRD — Contabilidade de Pontos de Desafios via Google Sheets

**Status:** Aprovado para planejamento técnico  
**Data:** 19/08/2026  
**Versão:** 1.0  
**Produto:** Contabilidade de Pontos — IGT Ultimate  
**Área:** Desafios pontuais  
**Fonte das decisões:** sessão de levantamento e validação com o responsável pelo produto

---

## 1. Resumo executivo

O sistema deixará de aceitar lançamentos manuais e importações CSV para a contabilidade de desafios. Uma Google Sheet dedicada passará a ser a única fonte oficial dos registros, e sua sincronização ocorrerá junto da ação existente **Executar Contabilidade**.

Cada submissão válida é identificada permanentemente pelo `Token` e vale, inicialmente, 10 pontos para o clã informado. Múltiplas submissões do mesmo coach são permitidas e pontuam separadamente quando possuem tokens diferentes. Nesta fase, nenhum ponto de desafio será atribuído ao ranking individual dos coaches; o nome bruto será preservado para uma implementação futura de identidade individual.

A sincronização funcionará por reconciliação integral da aba: novos tokens serão incluídos, tokens alterados serão corrigidos, tokens removidos serão inativados e estornados, e execuções repetidas sem mudanças produzirão delta zero. O processo terá auditoria completa, histórico imutável de versões, proteção contra exclusões em massa, transação atômica e bloqueio contra execuções simultâneas.

Os pontos atualmente registrados serão removidos em uma migração administrativa única, após backup recuperável, e reconstruídos exclusivamente a partir da planilha oficial.

---

## 2. Contexto e problema

### 2.1 Situação atual

O projeto possui três mecanismos relacionados a desafios:

1. Cadastro manual de desafios e lançamento manual de pontos por clã.
2. Um fluxo de upload e importação de CSV com mapeamento visual de colunas.
3. Lógica recente que tenta atribuir os pontos importados também aos coaches.

Esses mecanismos permitem divergências entre o sistema e a origem dos dados, exigem intervenção manual e não tratam corretamente correções ou remoções posteriores na fonte.

### 2.2 Evidências do arquivo de referência

O arquivo `Desafios Pontuais - IGT ULTIMATE_ Desafios _ Pontuais.csv` foi analisado como amostra da aba que será conectada ao sistema. Ele contém:

- 147 linhas de dados e 9 colunas;
- 147 tokens preenchidos e únicos na amostra;
- 140 nomes preenchidos;
- 139 respostas `Sim`, 1 resposta `Não` e 7 respostas vazias;
- duas colunas com o mesmo cabeçalho de clã;
- 85 linhas usando a primeira coluna de clã;
- 55 linhas usando a segunda coluna de clã;
- 7 linhas sem clã;
- 85 registros históricos sem desafio identificado;
- 62 registros com seleção explícita de desafio;
- múltiplos tokens pertencentes ao mesmo nome e ao mesmo desafio.

O parser CSV atual utiliza cabeçalhos como chaves. Como o cabeçalho de clã aparece duas vezes, a última coluna sobrescreve a primeira e 85 registros podem ser ignorados silenciosamente. O novo fluxo posicional elimina esse risco.

### 2.3 Problema a resolver

É necessário tornar a contabilidade de desafios:

- derivada de uma única fonte oficial;
- idempotente;
- capaz de refletir inclusões, alterações e remoções;
- auditável por token;
- segura contra falhas parciais e exclusões acidentais;
- compatível com o layout real da planilha;
- integrada aos totais e filtros históricos existentes.

---

## 3. Visão do produto

Ao acionar **Executar Contabilidade**, o administrador deve obter uma representação fiel do estado atual da aba oficial de desafios. O sistema deve aplicar apenas os deltas necessários, explicar o que ocorreu e conservar evidências suficientes para reconstruir qualquer alteração.

A interface de Desafios deixa de ser uma ferramenta de lançamento e passa a ser uma ferramenta de consulta e auditoria.

---

## 4. Princípios do produto

1. **Fonte única:** a Google Sheet é a única autoridade para a existência e o estado contábil de uma submissão.
2. **Token como identidade:** cada token representa uma submissão individual e permanente.
3. **Reconciliação, não simples importação:** o banco é uma projeção auditável do snapshot atual da planilha.
4. **Sem correções silenciosas:** inconsistências são explicitadas e nunca mascaradas com ajustes arbitrários.
5. **Tudo ou nada por fonte:** a etapa de desafios não pode deixar alterações parciais.
6. **Outras fontes independentes:** falhas nos desafios não interrompem a contabilidade dos demais tipos.
7. **Auditabilidade:** toda versão observada e todo delta aplicado são preservados.
8. **Separação de fases:** nesta entrega, desafios pontuam apenas clãs; identidade e pontuação individual de coaches ficam para uma evolução posterior.

---

## 5. Objetivos

### 5.1 Objetivos de negócio

- Eliminar o lançamento manual dos pontos de desafios.
- Reduzir divergências entre planilha e sistema.
- Permitir correções retroativas confiáveis.
- Oferecer rastreabilidade por submissão.
- Manter os rankings dos clãs atualizados com os pontos de desafios.

### 5.2 Objetivos de produto

- Integrar a planilha de desafios à ação **Executar Contabilidade**.
- Processar toda a aba de maneira idempotente.
- Contabilizar 10 pontos por token elegível.
- Exibir os pontos no total geral e no filtro `Desafios`.
- Disponibilizar consulta somente leitura e auditoria detalhada.
- Remover do fluxo operacional as ações manuais e o upload CSV.

### 5.3 Objetivos técnicos

- Usar configuração dedicada para a planilha.
- Garantir atomicidade da etapa de desafios.
- Impedir sincronizações concorrentes.
- Registrar execuções, snapshots, versões e deltas.
- Suportar migração e rollback seguros.

---

## 6. Fora de escopo

Esta entrega não inclui:

- pontuação individual de coaches por desafios;
- resolução definitiva de aliases ou variações de nomes de coaches;
- edição de desafios pela interface;
- cadastro manual de desafios;
- exclusão manual de desafios;
- upload de CSV;
- agendamento automático da sincronização;
- valor diferente por desafio;
- configuração do valor dos pontos pela interface;
- alteração do layout da Google Sheet;
- expurgo automático do histórico de auditoria.

---

## 7. Usuários e partes interessadas

### 7.1 Administrador da contabilidade

Responsável por executar a contabilidade, acompanhar o resultado da sincronização, corrigir dados inválidos na planilha e confirmar alterações em massa quando necessário.

### 7.2 Gestor do produto

Responsável pelas regras de pontuação, pela integridade da fonte oficial e pela aprovação da migração inicial.

### 7.3 Consultores e participantes

Consumidores dos rankings e relatórios. Não alteram desafios pelo sistema.

### 7.4 Operador de deploy

Responsável por configurar o acesso à planilha e executar a migração administrativa única.

---

## 8. Escopo funcional

### 8.1 Fonte oficial

A aplicação lerá uma Google Sheet dedicada usando as credenciais de serviço já adotadas pelo projeto.

Novas configurações obrigatórias:

- `GSHEET_DESAFIOS_SPREADSHEET_ID` — ID do arquivo;
- `GSHEET_DESAFIOS_SHEET_NAME` — nome da aba;
- `POINTS_PER_DESAFIO_SUBMISSION` — valor por submissão, padrão `10`.

O ID e o nome da aba são parâmetros operacionais a serem fornecidos no deploy. Sua ausência deve falhar apenas a etapa de desafios, com diagnóstico explícito.

### 8.2 Disparo

A etapa será executada junto da ação existente **Executar Contabilidade**.

O resultado geral deve apresentar o status de cada fonte separadamente. Se desafios falharem, as outras fontes continuam; a projeção anterior de desafios permanece inalterada.

### 8.3 Contrato posicional da aba

A primeira linha contém cabeçalhos. Os dados começam na segunda linha.

| Coluna | Índice | Campo | Uso contábil |
|---|---:|---|---|
| A | 0 | Clã legado | Sim, como primeira alternativa de clã |
| B | 1 | Nome | Obrigatório para auditoria; não gera pontos individuais nesta fase |
| C | 2 | Validação | Obrigatório; apenas `Sim` pontua |
| D | 3 | Link da postagem | Auditoria somente |
| E | 4 | Observação | Auditoria somente |
| F | 5 | Desafio | Obrigatório; define o agrupamento do desafio |
| G | 6 | Clã atual | Sim, como segunda alternativa de clã |
| H | 7 | Submitted At | Obrigatório; define a data contábil |
| I | 8 | Token | Obrigatório; identidade global da submissão |

A ordem é um contrato fixo. A aplicação deve validar que cada linha pode ser lida até a coluna I. Cabeçalhos podem ser usados apenas para diagnóstico humano, nunca para determinar o mapeamento.

---

## 9. Regras de normalização

### 9.1 Token

- Remover somente espaços nas extremidades.
- Preservar todos os demais caracteres exatamente.
- Tratar maiúsculas e minúsculas como diferentes.
- Considerar o token único globalmente, independentemente do desafio.
- Token vazio invalida a linha.

### 9.2 Clã

- Ler os valores das colunas A e G.
- Se somente uma estiver preenchida, usá-la.
- Se ambas estiverem preenchidas e normalizarem para o mesmo clã, usar esse clã.
- Se ambas estiverem preenchidas e apontarem para clãs diferentes, marcar conflito e não pontuar.
- Aceitar variações como `1`, `01`, `Clã 1`, `CLA 1` e `CLÃ 1`.
- Normalizar a saída para `CLÃ 1` até `CLÃ 8`.
- Valor vazio, ambíguo ou fora de 1 a 8 invalida contabilmente a linha.

### 9.3 Validação

- Aplicar trim e comparação sem diferença entre maiúsculas e minúsculas.
- Somente o valor normalizado exatamente igual a `sim` é elegível.
- `Não`, vazio ou qualquer outro valor não pontua.
- O valor bruto deve permanecer na auditoria.

### 9.4 Nome

- Preservar o valor bruto da planilha na auditoria.
- Remover espaços apenas para verificar se está vazio.
- Nome vazio invalida a linha.
- Não deduplicar submissões por nome.
- Não resolver aliases e não atribuir pontos a coaches nesta fase.

### 9.5 Desafio

- Remover espaços nas extremidades.
- Reduzir sequências de espaços internos a um único espaço para comparação.
- Comparar sem diferença entre maiúsculas e minúsculas.
- Preservar para exibição a primeira grafia válida encontrada.
- Valores normalizados diferentes representam desafios diferentes.
- Desafio vazio invalida a linha.

### 9.6 Data

- Interpretar `Submitted At` no fuso `America/Sao_Paulo`.
- Aceitar o formato oficial da aba: `dd/mm/aaaa HH:MM:SS`.
- Armazenar o instante de forma padronizada, preservando também o valor bruto.
- Usar a data local de São Paulo em filtros e relatórios.
- Data vazia ou ilegível invalida a linha.

### 9.7 Link e observação

- Não influenciam os pontos.
- Devem ser preservados em cada versão de auditoria.
- Alterações somente nesses campos geram nova versão, mas delta contábil zero.

---

## 10. Regras de contabilização

1. Cada token ativo, válido e com resposta `Sim` vale `POINTS_PER_DESAFIO_SUBMISSION` pontos para seu clã.
2. O valor inicial e padrão é 10.
3. Múltiplos tokens do mesmo nome, clã e desafio pontuam separadamente.
4. Um mesmo token nunca pode gerar mais de uma contribuição ativa.
5. Não existe deduplicação por coach.
6. Não existem pontos individuais de coach nesta fase.
7. Alterar a configuração de pontos recalcula retroativamente todas as submissões ativas na próxima execução.
8. Os pontos entram no total geral do clã e no tipo `desafios`.
9. O período histórico de cada contribuição é determinado pelo `Submitted At` do token.
10. Correções na fonte alteram retroativamente rankings e relatórios passados.

### 10.1 Estados de uma submissão

Cada token pode estar em um dos seguintes estados atuais:

- `active_counted` — válido, resposta `Sim`, ativo e pontuado;
- `active_not_counted` — estruturalmente válido, mas resposta diferente de `Sim`;
- `invalid` — faltam dados obrigatórios ou há valor inválido;
- `conflicted` — token ou clãs possuem versões conflitantes no mesmo snapshot;
- `inactive_missing` — existia anteriormente, mas não está mais na fonte;
- `blocked_by_guardrail` — mudança calculada, mas não aplicada por proteção operacional.

---

## 11. Duplicidade de tokens no snapshot

### 11.1 Duplicatas idênticas

Se o mesmo token aparecer mais de uma vez com os mesmos valores nas colunas A a I:

- considerar apenas uma submissão;
- manter na auditoria as posições das linhas duplicadas;
- gerar no máximo uma contribuição de pontos.

### 11.2 Duplicatas conflitantes

Se o mesmo token aparecer em linhas com qualquer diferença:

- não pontuar o token naquele snapshot;
- não escolher uma linha arbitrariamente;
- registrar todas as variantes e suas posições;
- manter ou estornar a contribuição anterior de acordo com a reconciliação do novo estado conflitante;
- exigir correção na Google Sheet.

Por ser a fonte oficial, um conflito atual torna o token não elegível até sua resolução.

---

## 12. Reconciliação integral

### 12.1 Estratégia

A etapa lê a aba inteira em toda execução. O snapshot normalizado é comparado com o estado atual persistido.

Resultados possíveis por token:

- **Novo:** criar estado e, se elegível, somar pontos.
- **Inalterado:** delta zero.
- **Alterado sem efeito contábil:** atualizar auditoria, delta zero.
- **Alterado com efeito contábil:** estornar a contribuição anterior e aplicar a nova.
- **Ausente:** inativar e estornar eventual contribuição.
- **Reaparecido:** reativar e aplicar a contribuição correspondente ao estado atual.

### 12.2 Exemplos de correção

- `Sim` → `Não`: estornar 10 pontos.
- `Não` → `Sim`: adicionar 10 pontos.
- `CLÃ 1` → `CLÃ 2`: subtrair 10 do Clã 1 e adicionar 10 ao Clã 2.
- `DESAFIO A` → `DESAFIO B`: mover a contribuição entre os agrupamentos, mantendo o clã.
- alteração de nome: atualizar auditoria; nesta fase, delta zero se os demais campos não mudarem.
- alteração de link/observação: nova versão; delta zero.
- alteração de data: mover a contribuição entre períodos históricos.
- remoção do token: estornar e marcar como inativo.

### 12.3 Idempotência

Duas execuções consecutivas sobre o mesmo snapshot e a mesma configuração devem produzir:

- zero novos tokens;
- zero tokens alterados;
- zero inativações;
- delta total zero para todos os clãs;
- nova execução registrada, sem duplicar contribuições.

---

## 13. Ciclo de vida dos desafios

### 13.1 Criação automática

Um desafio é criado automaticamente quando surge o primeiro token:

- ativo;
- estruturalmente válido;
- com validação `Sim`;
- associado ao nome normalizado do desafio.

Linhas inválidas, testes e respostas não elegíveis ficam na auditoria, mas não criam desafios vazios.

### 13.2 Arquivamento

Quando um desafio deixa de possuir tokens ativos e pontuáveis:

- arquivá-lo automaticamente;
- removê-lo das consultas ativas padrão;
- manter seu histórico e suas relações para auditoria;
- nunca apagá-lo fisicamente pela sincronização rotineira.

### 13.3 Reativação

Se o desafio arquivado voltar a ter tokens válidos e pontuáveis:

- reativá-lo automaticamente;
- restaurá-lo nas consultas ativas;
- aplicar os pontos correspondentes;
- registrar a transição na auditoria.

### 13.4 Renomeação

Quando os tokens mudam do nome antigo para um novo nome normalizado:

- reconciliar cada token para o novo desafio;
- arquivar o desafio antigo se ficar sem tokens pontuáveis;
- preservar a trilha histórica da mudança.

---

## 14. Fluxos do usuário

### 14.1 Execução normal sem alterações

1. Administrador aciona **Executar Contabilidade**.
2. Outras fontes são processadas por suas rotinas atuais.
3. A etapa de desafios obtém o bloqueio exclusivo.
4. A aba é lida e validada.
5. O snapshot é comparado com o banco.
6. Nenhuma diferença é encontrada.
7. O sistema registra sucesso com delta zero.
8. A interface apresenta o resumo por fonte.

### 14.2 Execução com novos tokens

1. A aba contém novos tokens válidos.
2. O sistema calcula 10 pontos por token.
3. A transação cria os estados, versões, desafios necessários e deltas por clã.
4. Dashboard e relatórios passam a refletir os novos pontos.

### 14.3 Execução com correções

1. Um token conhecido apresenta conteúdo diferente.
2. O sistema registra uma nova versão.
3. Calcula o estorno da contribuição anterior.
4. Calcula a nova contribuição.
5. Aplica o delta líquido em uma única transação.

### 14.4 Execução com remoção em massa

1. Mais de 20% dos tokens ativos deixam de aparecer.
2. A etapa não aplica alterações.
3. Outras fontes continuam normalmente.
4. A interface mostra contagem de tokens e pontos que seriam removidos.
5. O administrador confirma explicitamente a reconciliação.
6. Uma segunda operação, vinculada ao snapshot validado, aplica a mudança.

### 14.5 Planilha indisponível ou inválida

1. A leitura falha ou a estrutura não permite acessar as colunas A a I.
2. Nenhuma mudança de desafios é persistida.
3. O último estado válido permanece ativo.
4. Outras fontes continuam.
5. O erro aparece no resultado da execução e nos logs.

---

## 15. Experiência e interface

### 15.1 Tela Contabilidade

A ação **Executar Contabilidade** permanece como ponto de entrada.

O resultado deve mostrar, para a fonte `desafios`:

- status: sucesso, falha, aguardando confirmação ou já em execução;
- quantidade total de linhas lidas;
- tokens únicos;
- tokens novos;
- tokens alterados;
- tokens inativados;
- tokens inválidos;
- tokens conflitantes;
- desafios criados, arquivados e reativados;
- delta de pontos por clã;
- duração da etapa;
- link ou ação para abrir a auditoria.

Quando a proteção de 20% for acionada, a confirmação deve exibir o snapshot e os efeitos calculados. A confirmação não pode aplicar dados diferentes dos apresentados; se a planilha mudar entre a prévia e a confirmação, uma nova análise é obrigatória.

### 15.2 Tela Desafios

A tela passa a ser somente leitura e deve oferecer:

- lista de desafios ativos;
- opção de visualizar arquivados;
- total de submissões pontuadas;
- pontos por clã;
- filtros por desafio, clã, status, token e período;
- detalhes de cada token;
- histórico de versões do token;
- motivo de invalidação ou conflito;
- link e observação de auditoria;
- identificação da execução que aplicou cada versão.

Devem ser removidas da interface:

- criação manual;
- edição manual;
- exclusão manual;
- lançamento manual de pontos;
- importação ou atualização por CSV.

### 15.3 Dashboard

- Os pontos de desafios compõem o total geral dos clãs.
- O filtro `Desafios` mostra apenas contribuições dessa fonte.
- Filtros de período usam a data de `Submitted At` no fuso de São Paulo.
- Nenhum ranking individual de coaches por desafios é exibido nesta fase.

---

## 16. Requisitos funcionais

### RF-01 — Ler origem dedicada

O sistema deve ler a planilha e a aba definidas nas configurações de desafios.

### RF-02 — Executar junto da contabilidade

A sincronização deve integrar a ação **Executar Contabilidade** e retornar status independente das outras fontes.

### RF-03 — Interpretar layout por posição

O sistema deve ler os campos exclusivamente pelas posições A a I descritas neste PRD.

### RF-04 — Validar linhas

O sistema deve validar token, nome, clã, desafio, validação e data antes de pontuar.

### RF-05 — Pontuar por token

Cada token elegível deve gerar exatamente o valor configurado para seu clã.

### RF-06 — Permitir múltiplas submissões

Tokens distintos devem pontuar separadamente, mesmo quando nome, clã e desafio são iguais.

### RF-07 — Reconciliar alterações

O sistema deve detectar alterações em tokens conhecidos e aplicar os deltas necessários.

### RF-08 — Reconciliar remoções

Tokens ausentes no snapshot devem ser inativados e ter suas contribuições estornadas.

### RF-09 — Tratar duplicatas

Duplicatas idênticas devem ser consolidadas; duplicatas conflitantes não devem pontuar.

### RF-10 — Manter histórico

Toda mudança observada em um token deve criar uma versão de auditoria imutável.

### RF-11 — Criar desafios automaticamente

O sistema deve criar desafios somente quando houver ao menos um token válido e pontuável.

### RF-12 — Arquivar e reativar

O sistema deve gerenciar automaticamente o estado ativo/arquivado dos desafios.

### RF-13 — Aplicar datas individualmente

Cada contribuição deve ser atribuída ao período de seu próprio `Submitted At`.

### RF-14 — Não pontuar coaches

O sistema deve preservar nomes para auditoria, mas não criar nem atualizar totais individuais de coach.

### RF-15 — Bloquear escritas manuais

Endpoints de criação, edição, exclusão e importação CSV devem rejeitar operações com mensagem sobre a fonte oficial.

### RF-16 — Consultar auditoria

O sistema deve expor dados atuais e históricos de sincronizações e tokens em modo somente leitura.

### RF-17 — Confirmar remoções em massa

O sistema deve exigir confirmação quando mais de 20% dos tokens ativos desaparecerem.

### RF-18 — Bloquear planilha vazia

Se houver tokens ativos e a origem retornar vazia, nenhuma alteração deve ser aplicada.

### RF-19 — Impedir totais negativos

Qualquer operação que produziria total geral negativo deve falhar e preservar o estado anterior.

### RF-20 — Migrar dados atuais

Uma ação administrativa separada deve fazer backup, remover a contabilidade antiga e reconstruir desafios pela fonte oficial.

---

## 17. Requisitos não funcionais

### RNF-01 — Atomicidade

Todas as mudanças da etapa de desafios devem ser aplicadas em uma única transação de banco. Falha em qualquer parte desfaz toda a etapa.

### RNF-02 — Idempotência

Reexecutar o mesmo snapshot com a mesma configuração não altera pontos.

### RNF-03 — Concorrência

Somente uma sincronização de desafios pode estar ativa. Uma segunda solicitação deve receber status `já em execução` sem iniciar trabalho concorrente.

### RNF-04 — Isolamento entre fontes

Falhas em desafios não devem reverter ou impedir fontes processadas independentemente.

### RNF-05 — Rastreabilidade

Toda execução e mudança de token deve possuir timestamp, snapshot, valores anteriores, valores novos e deltas.

### RNF-06 — Retenção

Backup pré-migração, execuções e versões de tokens devem ser mantidos por tempo indeterminado.

### RNF-07 — Segurança

A migração destrutiva deve existir apenas como comando administrativo protegido, fora da interface comum.

### RNF-08 — Desempenho

A sincronização deve processar o snapshot completo atual sem comprometer a responsividade das consultas. Índices devem cobrir token, desafio, clã, status e data de submissão.

### RNF-09 — Observabilidade

Erros e métricas de sincronização devem ser estruturados e correlacionados por identificador de execução.

### RNF-10 — Integridade temporal

Datas devem ser interpretadas consistentemente em `America/Sao_Paulo`.

---

## 18. Arquitetura funcional proposta

### 18.1 Componentes

1. **Leitor da Google Sheet de desafios**  
   Obtém todas as linhas da aba dedicada sem alterar a fonte.

2. **Parser posicional**  
   Converte A a I em registros tipados e preserva valores brutos.

3. **Normalizador e validador**  
   Produz valores canônicos, estados e motivos de erro sem I/O.

4. **Construtor de snapshot**  
   Agrupa tokens, detecta duplicatas e calcula um hash imutável do snapshot.

5. **Motor de reconciliação**  
   Compara o snapshot com o estado persistido e produz um plano de deltas.

6. **Guardas operacionais**  
   Detectam planilha vazia, remoção superior a 20%, totais negativos e concorrência.

7. **Aplicador transacional**  
   Persiste execuções, versões, estados, desafios, agregados e deltas atomically.

8. **Consulta e auditoria**  
   Expõe dados somente leitura para as telas e relatórios.

### 18.2 Fluxo de dados

```text
Google Sheet
    → leitura integral
    → parser posicional
    → normalização/validação
    → snapshot por token
    → comparação com estado atual
    → guardas de segurança
    → transação de reconciliação
    → totais por clã + auditoria + dashboards
```

---

## 19. Modelo conceitual de dados

Os nomes finais podem seguir as convenções existentes, mas o produto requer os seguintes conceitos persistidos.

### 19.1 Execução de sincronização

Campos mínimos:

- identificador;
- início e término;
- status;
- hash do snapshot;
- total de linhas;
- totais por estado;
- deltas por clã;
- quantidade de desafios criados, arquivados e reativados;
- configuração de pontos usada;
- necessidade e confirmação de remoção em massa;
- erro estruturado, quando houver.

### 19.2 Estado atual da submissão

Uma linha por token global:

- token;
- posição ou posições atuais na aba;
- valores brutos A a I;
- clã normalizado;
- nome bruto;
- desafio normalizado e referência ao desafio;
- data submetida;
- status atual;
- pontos atuais;
- hash do conteúdo;
- primeira e última execução em que foi visto;
- data de inativação, quando aplicável.

### 19.3 Versão da submissão

Registro imutável para cada estado observado:

- token;
- execução;
- número da versão;
- valores anteriores e novos;
- status anterior e novo;
- deltas de pontos;
- motivo da mudança;
- timestamp.

### 19.4 Desafio

- nome de exibição;
- nome normalizado único;
- estado ativo/arquivado;
- datas de criação, arquivamento e reativação;
- origem exclusiva `google_sheets`.

### 19.5 Agregados compatíveis

Os agregados por desafio e clã podem continuar alimentando estruturas existentes para compatibilidade, mas devem ser sempre derivados dos tokens ativos. Nenhum agregado pode ser editado diretamente.

### 19.6 Estruturas de coach

- Remover, durante a migração, contribuições de desafios nos totais individuais.
- Não criar novos registros em `desafio_registros_coach` nesta fase.
- Preservar nomes brutos no histórico de tokens para uso futuro.

---

## 20. APIs e operações

### 20.1 Executar Contabilidade

O contrato de resposta deve incluir um resultado independente para desafios, com status e resumo da reconciliação.

### 20.2 Confirmação de remoção em massa

Deve existir uma operação específica que receba a identificação e o hash do snapshot analisado. A confirmação falha se o conteúdo atual não corresponder ao snapshot apresentado.

### 20.3 Consultas

Endpoints somente leitura devem permitir:

- listar desafios ativos e arquivados;
- detalhar um desafio;
- listar tokens com filtros;
- detalhar token e versões;
- listar execuções de sincronização;
- detalhar deltas de uma execução.

### 20.4 Escritas legadas

Endpoints manuais e endpoints de upload CSV devem responder com erro de domínio, preferencialmente `410 Gone` para fluxos removidos, explicando que a Google Sheet é a fonte oficial.

### 20.5 Migração administrativa

Deve ser disponibilizada como comando de backend/deploy, não como endpoint público da interface.

---

## 21. Migração dos dados existentes

### 21.1 Pré-condições

- Configurações da Google Sheet disponíveis.
- Service account com acesso de leitura à planilha.
- As 85 linhas históricas sem desafio preenchidas corretamente na coluna F.
- Backup do banco habilitado e testado.
- Nenhuma execução de contabilidade em andamento.

### 21.2 Etapas

1. Obter bloqueio administrativo exclusivo.
2. Registrar totais atuais de desafios por clã e coach.
3. Criar backup recuperável das tabelas afetadas.
4. Ler e validar o snapshot oficial sem persistir alterações.
5. Produzir relatório prévio de novos totais e diferenças.
6. Exigir confirmação explícita do operador.
7. Em transação:
   - remover a contribuição atual de desafios dos totais dos clãs;
   - remover a contribuição atual de desafios dos totais individuais dos coaches;
   - desativar estruturas manuais e importações CSV antigas;
   - criar o novo estado derivado da Google Sheet;
   - aplicar os novos totais por clã;
   - registrar a execução de migração e as versões iniciais.
8. Validar invariantes e encerrar o bloqueio.

### 21.3 Validações pós-migração

- Soma dos pontos de desafios por clã igual a `tokens ativos elegíveis × valor configurado`.
- Nenhum ponto individual de coach proveniente de desafios.
- Reexecução imediata produz delta zero.
- Dashboard geral e filtro `Desafios` apresentam os mesmos agregados do banco.
- Relatórios por período usam a data individual dos tokens.
- Backup permanece acessível e fora das consultas normais.

### 21.4 Rollback

Se a migração falhar, a transação deve restaurar o estado anterior automaticamente. Se uma falha operacional ocorrer após a transação, o backup deve permitir restauração administrativa documentada.

---

## 22. Tratamento de erros e proteções

| Situação | Comportamento esperado |
|---|---|
| Planilha indisponível | Falhar apenas desafios; manter estado anterior |
| Configuração ausente | Falhar apenas desafios com mensagem objetiva |
| Planilha vazia com tokens ativos | Bloquear reconciliação |
| Linha com menos de 9 colunas | Marcar inválida; continuar linhas válidas |
| Token vazio | Invalidar linha |
| Nome vazio | Invalidar linha |
| Desafio vazio | Invalidar linha |
| Data inválida | Invalidar linha |
| Clã inválido | Invalidar linha |
| Colunas A e G conflitantes | Marcar conflito; não pontuar |
| Token duplicado idêntico | Consolidar em uma submissão |
| Token duplicado divergente | Marcar conflito; não pontuar |
| Mais de 20% dos tokens removidos | Exigir confirmação adicional |
| Total de clã ficaria negativo | Abortar transação e diagnosticar divergência |
| Sincronização já em andamento | Não iniciar outra; informar estado |
| Falha durante persistência | Rollback integral da etapa |
| Snapshot mudou antes da confirmação | Invalidar confirmação e recalcular |

---

## 23. Auditoria e retenção

Devem ser preservados indefinidamente:

- backup pré-migração;
- execuções de sincronização;
- snapshots ou hashes verificáveis;
- todas as versões de cada token;
- valores brutos da planilha;
- link e observação;
- motivos de invalidação e conflito;
- deltas por clã;
- transições de desafios;
- confirmações administrativas.

A exclusão de uma linha da planilha não apaga sua história; apenas inativa o estado atual.

---

## 24. Segurança e privacidade

- Usar credenciais de serviço armazenadas como segredo de ambiente.
- A rotina de desafios deve realizar apenas leitura na planilha de origem.
- Não registrar credenciais, tokens de acesso ou conteúdo integral da service account em logs.
- Tratar os tokens das submissões como identificadores potencialmente sensíveis.
- Restringir a auditoria detalhada aos mesmos perfis administrativos que acessam a contabilidade.
- Restringir a migração a comando administrativo protegido.
- Registrar quem ou qual processo confirmou uma remoção em massa ou migração.

---

## 25. Observabilidade

### 25.1 Logs estruturados

Cada log da etapa deve incluir:

- `sync_run_id`;
- fase do processamento;
- duração;
- quantidade de linhas e tokens;
- resultado;
- erro categorizado;
- nunca o segredo de acesso.

### 25.2 Métricas

- taxa de sucesso das sincronizações;
- duração da leitura e da transação;
- tokens ativos;
- tokens inválidos e conflitantes;
- tokens novos, alterados e inativados;
- deltas positivos e negativos por execução;
- quantidade de bloqueios pela regra de 20%;
- quantidade de tentativas concorrentes;
- idade da última sincronização bem-sucedida.

### 25.3 Alertas recomendados

- falhas consecutivas na fonte de desafios;
- ausência de sincronização bem-sucedida por período operacional relevante;
- planilha vazia;
- crescimento súbito de inválidos;
- divergência que produziria total negativo.

---

## 26. Métricas de sucesso

### 26.1 Critérios de lançamento

- 100% dos tokens válidos da planilha representados no banco.
- 0 contribuições duplicadas por token.
- 0 pontos individuais de coaches derivados de desafios.
- Reexecução do mesmo snapshot com delta zero.
- Correções e remoções refletidas corretamente.
- Migração concluída com backup verificável.

### 26.2 Indicadores após lançamento

- Taxa de sincronização bem-sucedida superior a 99% das execuções iniciadas, desconsiderando bloqueios deliberados de segurança.
- Zero lançamentos manuais de desafios.
- Zero divergências conhecidas entre tokens elegíveis e contribuições ativas.
- Tempo de diagnóstico de uma submissão reduzido pela consulta de auditoria por token.

---

## 27. Critérios de aceitação

### CA-01 — Token válido

Dada uma linha com token inédito, nome, desafio, data válida, clã 1 a 8 e `Sim`, ao executar a contabilidade o clã recebe 10 pontos.

### CA-02 — Múltiplas submissões

Dadas três linhas válidas com tokens diferentes e o mesmo nome, clã e desafio, o clã recebe 30 pontos.

### CA-03 — Idempotência

Dado um snapshot já sincronizado, uma nova execução sem alterações produz delta zero.

### CA-04 — Duplicata idêntica

Dado o mesmo token repetido em duas linhas idênticas, somente 10 pontos são contabilizados.

### CA-05 — Duplicata conflitante

Dado o mesmo token com dois clãs diferentes, o token não pontua e aparece como conflito.

### CA-06 — Correção de clã

Dado um token anteriormente atribuído ao Clã 1, quando a planilha o altera para Clã 2, 10 pontos são estornados do Clã 1 e adicionados ao Clã 2.

### CA-07 — Correção de validação

Dado um token `Sim`, quando passa a `Não`, seus pontos são estornados retroativamente.

### CA-08 — Remoção

Dado um token ativo que desaparece da planilha, ele é inativado, seus pontos são estornados e sua auditoria permanece disponível.

### CA-09 — Duas colunas de clã

Dada uma linha com A vazia e G igual a `5`, o token pontua `CLÃ 5`. Dada uma linha com A igual a `1` e G igual a `2`, ela não pontua e é marcada como conflito.

### CA-10 — Linha incompleta

Dada uma linha sem nome, clã, desafio, token ou data válida, ela não pontua e informa o motivo.

### CA-11 — Criação automática

Dado o primeiro token elegível de `DESAFIO PONTUAL C`, o desafio é criado automaticamente.

### CA-12 — Desafio vazio

Dado um nome novo presente apenas em linhas inválidas ou com `Não`, nenhum desafio vazio é criado.

### CA-13 — Arquivamento e reativação

Dado um desafio sem tokens pontuáveis após reconciliação, ele é arquivado. Quando um token elegível reaparece, ele é reativado.

### CA-14 — Data histórica

Dado um token submetido em maio, seus pontos aparecem em relatórios que incluem maio, independentemente da data de sincronização.

### CA-15 — Falha isolada

Dada uma indisponibilidade da planilha de desafios, as demais fontes são processadas e os desafios conservam o último estado válido.

### CA-16 — Planilha vazia

Dado um banco com tokens ativos e uma leitura vazia, nenhum ponto de desafio é estornado automaticamente.

### CA-17 — Remoção acima de 20%

Dada uma redução superior a 20% dos tokens ativos, a etapa exige confirmação e não aplica alterações antes dela.

### CA-18 — Concorrência

Dada uma sincronização em andamento, uma segunda tentativa não processa o snapshot novamente.

### CA-19 — Atomicidade

Dada uma falha durante a persistência, nenhum estado, versão, desafio ou total parcial permanece aplicado.

### CA-20 — Sem pontos de coach

Dado qualquer token válido, nenhum total individual de coach é alterado.

### CA-21 — Bloqueio manual

Dada uma tentativa de criar, editar, excluir ou importar desafio por endpoint legado, a operação é rejeitada e aponta a Google Sheet como fonte oficial.

### CA-22 — Mudança do valor configurado

Dada a alteração do valor de 10 para outro número, a próxima sincronização recalcula retroativamente todos os tokens ativos e aplica apenas o delta.

---

## 28. Estratégia de testes

### 28.1 Testes unitários

- parser posicional;
- normalização de clãs;
- normalização de desafio;
- validação `Sim`;
- parsing temporal e fuso;
- duplicatas idênticas e conflitantes;
- cálculo de estado e pontos;
- diff entre snapshots;
- regra de 20%;
- detecção de totais negativos.

### 28.2 Testes de integração

- leitura simulada da Google Sheets API;
- transação de reconciliação completa;
- rollback em falha;
- lock de concorrência;
- atualização dos totais dos clãs;
- filtros históricos;
- bloqueio dos endpoints legados;
- independência entre fontes.

### 28.3 Testes de migração

- backup criado e restaurável;
- remoção de pontos antigos de clãs;
- remoção de pontos de desafios dos coaches;
- reconstrução pelo snapshot;
- reexecução com delta zero;
- rollback do processo.

### 28.4 Testes de interface

- resumo da execução;
- confirmação de remoção em massa;
- consultas somente leitura;
- filtros e auditoria por token;
- ausência das ações manuais;
- ausência do ranking de coaches para desafios.

### 28.5 Teste com o arquivo de referência

Antes do lançamento, usar uma cópia saneada do arquivo analisado para verificar:

- leitura correta das colunas A e G;
- invalidação das 7 linhas incompletas;
- exigência de preenchimento dos 85 desafios históricos;
- unicidade dos 147 tokens da amostra;
- comportamento de múltiplas submissões do mesmo nome.

---

## 29. Plano de lançamento

### Fase 1 — Preparação

- Criar configurações de ambiente.
- Conceder acesso à service account.
- Preencher a coluna F dos registros históricos.
- Aplicar migrations de banco.
- Implantar código com sincronização ainda não migrada.

### Fase 2 — Validação sem escrita

- Executar leitura e reconciliação em modo diagnóstico.
- Comparar contagens e totais esperados.
- Corrigir linhas inválidas na fonte.

### Fase 3 — Migração administrativa

- Criar backup.
- Revisar relatório prévio.
- Confirmar e executar reconstrução.
- Validar invariantes e delta zero na reexecução.

### Fase 4 — Ativação operacional

- Habilitar desafios dentro de **Executar Contabilidade**.
- Remover ações manuais da interface.
- Bloquear endpoints legados.
- Monitorar as primeiras execuções.

### Fase 5 — Estabilização

- Acompanhar métricas e inválidos.
- Validar relatórios históricos.
- Documentar o procedimento operacional.

---

## 30. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Exclusão acidental da aba | Estorno em massa | Bloqueio de vazio e confirmação acima de 20% |
| Layout alterado | Leitura incorreta | Contrato posicional documentado e validação de largura |
| Histórico sem desafio | Pontos sem agrupamento | Preenchimento obrigatório antes da migração |
| Falha parcial no banco | Totais divergentes | Transação única e rollback |
| Duas execuções simultâneas | Deltas duplicados | Lock exclusivo |
| Token conflitante | Atribuição incorreta | Não pontuar até correção |
| Data ou fuso incorretos | Relatório histórico incorreto | Parsing estrito em America/Sao_Paulo |
| Pontos antigos duplicados | Ranking inflado | Migração com remoção e reconstrução |
| Pontos de coach mantidos | Ranking individual incorreto | Estorno explícito na migração |
| Mudança de configuração | Alterações amplas | Reconciliação auditada e proteção operacional |
| Falha da Google API | Dados desatualizados | Manter último estado válido e informar falha |

---

## 31. Dependências

- Acesso da service account à Google Sheet de desafios.
- ID da planilha e nome da aba no ambiente de deploy.
- Coluna F preenchida nos 85 registros históricos.
- Banco capaz de executar transação/RPC atômica e lock exclusivo.
- Rotina atual de **Executar Contabilidade** preparada para retornar resultados por fonte.
- Dashboard e histórico capazes de consumir contribuições datadas por token.
- Processo seguro de backup e restauração.

---

## 32. Alternativas consideradas e rejeitadas

### 32.1 Continuar com lançamento manual

Rejeitada porque mantém duas fontes, aumenta trabalho operacional e permite divergências.

### 32.2 Manter upload CSV

Rejeitada porque exige exportação e ação manual, além de não refletir naturalmente correções e remoções.

### 32.3 Processar somente tokens novos

Rejeitada porque não detecta alterações, invalidações e exclusões na fonte oficial.

### 32.4 Deduplicar por nome do coach

Rejeitada porque múltiplas submissões legítimas devem pontuar e o tratamento de identidade individual será feito posteriormente.

### 32.5 Mapear por cabeçalho

Rejeitada porque o layout é fixo e contém cabeçalhos duplicados de clã. O contrato posicional é determinístico.

### 32.6 Corrigir totais negativos para zero

Rejeitada porque ocultaria uma inconsistência contábil.

### 32.7 Apagar definitivamente o histórico

Rejeitada porque inviabiliza auditoria, explicação de estornos e recuperação.

---

## 33. Decisões consolidadas

1. Google Sheet como única fonte oficial.
2. Sincronização junto de **Executar Contabilidade**.
3. Valor inicial de 10 pontos por token elegível.
4. Apenas `Sim` pontua.
5. Desafios separados pelo valor da coluna F.
6. Clã obtido das colunas A/G e normalizado.
7. Registros históricos sem desafio devem ser corrigidos na fonte.
8. Múltiplos tokens do mesmo coach pontuam separadamente.
9. Alterações no mesmo token são reconciliadas.
10. Tokens removidos são inativados e estornados.
11. Nenhum ponto individual de coach nesta fase.
12. Desafios são criados automaticamente.
13. Linhas inválidas não bloqueiam as válidas; falha estrutural bloqueia a etapa.
14. Duplicata idêntica conta uma vez; conflito não pontua.
15. Datas usam `Submitted At` em São Paulo.
16. Renomeações arquivam desafios vazios sem apagar histórico.
17. Interface e APIs manuais são removidas ou bloqueadas.
18. A etapa é transacional e independente das outras fontes.
19. Planilha vazia e remoções acima de 20% possuem guardas.
20. Layout é interpretado por posição fixa.
21. Link e observação ficam na auditoria.
22. Origem usa configuração dedicada.
23. Pontos atuais de clãs e coaches são removidos e reconstruídos conforme o novo escopo.
24. O valor por submissão é variável de ambiente e recalcula retroativamente.
25. Histórico de versões é permanente.
26. Token é opaco e sensível a maiúsculas/minúsculas.
27. Desafios sem submissões pontuáveis não são criados.
28. Desafios arquivados podem ser reativados.
29. Migração possui backup e ação administrativa separada.
30. Snapshot completo, idempotência e lock de concorrência são obrigatórios.
31. Correções afetam retroativamente relatórios históricos.

---

## 34. Entradas operacionais pendentes antes do deploy

Não existem dúvidas de regra de produto em aberto. Antes do deploy, o operador deve fornecer:

- valor de `GSHEET_DESAFIOS_SPREADSHEET_ID`;
- valor de `GSHEET_DESAFIOS_SHEET_NAME`;
- confirmação de que a service account possui acesso;
- confirmação de que os 85 registros históricos foram classificados na coluna F;
- janela operacional para executar a migração administrativa.

Esses itens são parâmetros de implantação e não alteram o comportamento definido neste PRD.

---

## 35. Definição de pronto

A entrega estará concluída quando:

- todos os requisitos funcionais e não funcionais estiverem implementados;
- os critérios de aceitação estiverem automatizados ou validados com evidência;
- migrations e rollback estiverem documentados e testados;
- backup pré-migração estiver verificado;
- pontos antigos de desafios tiverem sido removidos de clãs e coaches;
- o estado tiver sido reconstruído pela Google Sheet;
- uma segunda execução produzir delta zero;
- Dashboard, histórico e tela de Desafios refletirem os dados reconciliados;
- ações manuais e CSV estiverem indisponíveis;
- auditoria por token e por execução estiver disponível;
- logs e métricas essenciais estiverem ativos;
- procedimento operacional estiver documentado.

