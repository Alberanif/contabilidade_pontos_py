# Identidade canônica de coach (fusão de nomes duplicados)

## Problema

O campo `coach` em `pontos_ultimate_registros_contabilizados` e `pontos_ultimate_totais_por_coach` vem de texto livre digitado na planilha Google Sheets ("Nome do Coach responsável"), sem nenhuma normalização — diferente de `clan`, que já passa por `_normalize_clan` (`routers/contabilidade.py`). Isso fragmenta a pontuação de uma mesma pessoa real em múltiplas linhas de `pontos_ultimate_totais_por_coach`, uma por variação de grafia (maiúsculas/minúsculas, espaços, acentos, erro de digitação, apelido, nome abreviado). Isso afeta diretamente o ranking de coaches mostrado no Dashboard (`frontend/src/pages/Dashboard.tsx`), que hoje lista cada variação como se fosse uma pessoa diferente.

Levantamento na base atual (155 nomes distintos de coach): 18 grupos são duplicata "boba" (só case/acento/espaço), 8 grupos adicionais são erro de digitação/apelido/abreviação já confirmados, e ~17 pares adicionais são candidatos plausíveis que exigem conhecimento local do usuário para confirmar (ex: sobrenome mais completo pode ser a mesma pessoa ou pode ser coincidência de nome).

## Objetivo

1. Resolver agora as fusões de alta confiança (as 18 automáticas + as 8 confirmadas).
2. Dar ao usuário um jeito simples e duradouro de ir confirmando as fusões restantes ao seu próprio ritmo, sem depender de código ou deploy.
3. Garantir que registros novos (ingeridos da planilha dali pra frente) já nasçam sob o nome canônico, sem necessidade de reprocessamento futuro — reprocessamento só é necessário para corrigir dados **já ingeridos antes** de um alias existir.

## Não-objetivos

- Não haverá tela nova no Dashboard para gerenciar aliases (usuário decidiu editar direto no Supabase Table Editor).
- Não tentaremos resolver algoritmicamente os pares de "nome curto vs. nome completo" ambíguos (risco de fundir pessoas diferentes por coincidência de sobrenome). Ficam em backlog para revisão humana.
- Não mexe na identidade de clã (`_normalize_clan` já resolve isso e não está em escopo aqui).

## Arquitetura

### 1. Tabela `pontos_ultimate_coach_aliases`

```sql
CREATE TABLE pontos_ultimate_coach_aliases (
    id SERIAL PRIMARY KEY,
    alias VARCHAR NOT NULL UNIQUE,
    coach_canonico VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

- `alias`: uma grafia bruta observada (ex.: `"Tati Pellicel"`).
- `coach_canonico`: o nome "oficial" para onde os pontos dessa grafia devem ser somados (ex.: `"Tatiane Pellicel"`).
- O usuário mantém essa tabela manualmente pelo Supabase Table Editor, adicionando uma linha por alias confirmado.

### 2. Normalização em duas camadas

**Camada A — automática, sem tabela (código apenas).** Uma chave de comparação: maiúsculas, sem acento, espaços colapsados/aparados. Resolve para sempre variações triviais de case/acento/espaço, sem exigir manutenção manual. Mesmo princípio de `_normalize_clan`, mas sem parsing numérico.

**Camada B — tabela `pontos_ultimate_coach_aliases`.** Aplicada depois da camada A (o lookup na tabela também usa a chave normalizada da camada A, então o usuário não precisa digitar a grafia exata byte-a-byte, só precisa bater a versão normalizada). Cobre erro de digitação, apelido e nome abreviado — casos que a camada A não resolve porque as strings são realmente diferentes.

Nova função em `routers/contabilidade.py`, ao lado de `_normalize_clan`:

```python
def _normalize_coach(coach_raw: str) -> str:
    ...  # aplica camada A, depois consulta o mapa de aliases (camada B) e retorna coach_canonico ou o próprio valor normalizado
```

### 3. Pontos de ingestão a atualizar

Todo lugar que hoje lê `row[COL_COACH]` diretamente passa a chamar `_normalize_coach(...)`:

- `_build_and_insert` / `_build_and_insert_pro_bono` (via `points_engine.build_record_data`, mesmo padrão já usado para `clan` com `_normalize_clan`)
- Agregação de pessoas pendentes em `_process_group_records` e `importar_inicial` (Fase 4/6/7)
- `aprovar_coach` — normaliza `body.coach` recebido, para que aprovar usando qualquer grafia conhecida funcione
- `get_pending_group_records_by_coach`, `get_coach_carry_over` (chamadas já recebem o nome já normalizado do chamador acima — não precisam de mudança própria)

### 4. Endpoint de reprocessamento (`POST /contabilidade/reprocessar-coaches`)

Único código que faz a fusão de fato — tanto a migração inicial quanto qualquer atualização futura da tabela de aliases usam este mesmo caminho (evita ter uma lógica "de migração" separada da lógica "de manutenção"):

1. Para cada `coach` distinto em `pontos_ultimate_registros_contabilizados`, calcula o canônico via `_normalize_coach` e faz `UPDATE` na coluna `coach` (só a chave de agrupamento muda; `pontos_coach`/`status_coach` de cada linha permanecem os mesmos).
2. Para cada grupo afetado, apaga as linhas antigas de `pontos_ultimate_totais_por_coach` dos aliases e recalcula do zero o total do nome canônico a partir dos registros já reescritos — reaproveitando a fórmula validada nesta conversa (CI: soma direta; grupo: `((pessoas em registros contabilizados) - carry_over) / 5 * 30`; pro-bono: soma direta).
3. Roda `aprovar_coach` novamente para cada canônico afetado, para promover lotes que só ficaram completos depois da fusão (ex.: duas pessoas com 3 pendentes cada, que separadas nunca fecham lote de 5, juntas fecham).

É idempotente: chamar sem nenhuma mudança na tabela de aliases não altera nenhum total (nenhum `coach` precisa de `UPDATE`, passo 2 não encontra grupo afetado).

### 5. Migração inicial (executada uma vez, agora)

1. Insere as linhas de seed na tabela `pontos_ultimate_coach_aliases` (lista abaixo).
2. Chama `POST /contabilidade/reprocessar-coaches` uma vez.

## Seed inicial da tabela de aliases (entra na migração de agora)

| `coach_canonico` | `alias` |
|---|---|
| Jose George Canuto Pereira Junior | JOSE GEORGE C PEREIRA JUNIOR |
| Jose George Canuto Pereira Junior | Jose George C Pereira Junior |
| Jose George Canuto Pereira Junior | Jose George C. Pereira Junior |
| Karlla Andrade | KARLLA ANDADE |
| Kátia Aparecida dos Santos | KATIA APARECIDA DOS SANTOSQ |
| Claudete Maria da Silva | Claudete M Silva |
| Claudete Maria da Silva | Claudete M da Silva |
| Camilla Crivelaro Rentroia | Camilla C Rentroia |
| Camilla Crivelaro Rentroia | Camilla Rentroia |
| Vinicius Marini | Vini Marini |
| Tatiane Pellicel | Tati Pellicel |
| Solamita dos Santos Mariano Rovarotto | solamita dos santos mariano |
| Solamita dos Santos Mariano Rovarotto | solamita dos santos mariano rovarotto |

(Os 18 grupos de duplicata só-case/acento/espaço não precisam de linha — resolvidos pela Camada A automaticamente: Alexsandre Naves, Cássia Fajardo, Clarissa Boeira, Damaris Alfredo Silva de Oliveira, Hérverton Ferreira de Souza Sobrinho, Ivan Pereira Vieira, Maria Bernadete Lima de Oliveira, Patrícia Pereira da Silva, Paula Petroli Pierozzi, Rapha Freitas, Victor Lucena, Vinícius Gonçalves Missiaggia, Wagner Mendes Faria, entre outros.)

## Backlog — candidatos para o usuário revisar quando quiser

Pares onde um nome é um subconjunto de palavras do outro (possível nome curto vs. nome completo da mesma pessoa, mas não confirmado — pode também ser coincidência de sobrenome entre pessoas diferentes):

| Nome curto | Nome completo |
|---|---|
| Alberto Nonato | Alberto Junior Pereira Lopes Nonato |
| Alex Bruno | Alex Bruno de Carvalho Leite |
| Amanda Nagamati | Amanda Nagamati Zanella da Costa |
| Ana Paula Benet | Ana Paula Benet Sanches Rodrigues da Silva |
| André Diniz | André Alexandre R. Diniz |
| Arthur Bueno | Arthur Soares Bueno |
| Damaris Alfredo | Damaris Alfredo Silva de Oliveira |
| Dione Palmeira | Dione Palmeira Duarte de Oliveira |
| Flavia Godoi | Flavia Cristina de Godoi |
| Jefferson Tolentino | Jefferson dos Santos Tolentino |
| Jéssica Mano | Jéssica dos Santos Ramos Mano |
| Karlla Andrade | Karlla Carneiro Andrade |
| Marcos Ranieri | Marcos Guimarães Ranieri |
| Milena Meirelles | Milena Meirelles Marini |
| Patricia Bezerra | Patricia de Sousa Bezerra |
| Sidicley Cabral | Sidicley de Souza Cabral Filho |
| Victor Lucena | Victor de Miranda Lucena |

**Como confirmar um par no futuro:** inserir uma linha em `pontos_ultimate_coach_aliases` com `alias` = o nome que deve ser absorvido e `coach_canonico` = o nome que deve prevalecer, depois chamar `POST /contabilidade/reprocessar-coaches`.

## Tratamento de erros

- Alias apontando para um `coach_canonico` que também é `alias` de outra linha (cadeia): o reprocessamento resolve um nível só; se acontecer, o endpoint deve retornar aviso listando cadeias detectadas em vez de aplicar silenciosamente (evita loops/inconsistência).
- `alias` duplicado (usuário insere a mesma grafia duas vezes apontando pra canônicos diferentes): bloqueado pela constraint `UNIQUE` na coluna `alias`.
- Reprocessar sem nenhuma linha nova na tabela: idempotente, não deve alterar nenhum total (será validado no plano de testes).

## Testes

- Teste de unidade para `_normalize_coach`: camada A (case/acento/espaço) e camada B (via tabela, com mock).
- Teste de idempotência do endpoint de reprocessamento: rodar duas vezes seguidas, segunda vez não altera nada.
- Reaproveitar o script de auditoria já usado nesta conversa (`audit_coach.py`, formato pessoas-ponderado) como checagem pós-migração: 0 divergências entre `total_pagante`/`total_pro_bono` recalculado e armazenado, para todo `coach_canonico`.
- Conferir que a soma total de pontos de coach antes e depois da migração é a mesma (a fusão só reagrupa, nunca cria ou destrói pontos).

## Rollout

1. Migração roda uma vez em produção (mesma base já usada nesta conversa), consolidando o seed inicial.
2. Endpoint novo fica disponível para reprocessamentos futuros.
3. Usuário revisa a lista de backlog no seu próprio ritmo, adicionando linhas em `coach_aliases` e chamando o endpoint quando quiser aplicar.
