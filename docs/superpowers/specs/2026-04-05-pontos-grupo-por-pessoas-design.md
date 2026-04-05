# Design: Pontos de Grupo por Número de Pessoas

**Data:** 2026-04-05
**Status:** Aprovado

---

## Contexto

Atualmente, o sistema contabiliza pontos de coaching em grupo e empresa contando **registros** (sessões): a cada 5 registros de um clã → 30 pontos. A nova regra é contar **pessoas atendidas** em cada sessão: a cada 5 pessoas → 30 pontos, com carry-over do saldo restante entre aprovações.

**Exemplo:**
- CLÃ 5 fecha um coaching em grupo com 6 pessoas → 1 lote completo (5 pessoas) = 30 pts + 1 pessoa em espera
- CLÃ 5 fecha outro coaching com 4 pessoas → 1 + 4 = 5 pessoas = mais 30 pts + 0 em espera

---

## Fonte de Dados

A planilha de registros já possui a coluna **"Número de pessoas atendidas por você nesse contrato"** na posição **I** (índice 8). Nenhuma mudança na planilha é necessária.

```python
COL_PARTICIPANTES = 8  # coluna I da planilha
```

---

## Alterações no Banco de Dados (Supabase)

### Tabela `pontos_ultimate_registros_contabilizados`

```sql
ALTER TABLE pontos_ultimate_registros_contabilizados
ADD COLUMN num_participantes INTEGER NOT NULL DEFAULT 1;
```

- Preenchido na leitura da coluna I ao inserir registros pendentes de grupo/empresa
- Default `1` preserva compatibilidade com registros individuais já existentes
- Registros históricos de grupo (já contabilizados) ficam com `num_participantes = 1` — aceitável, pois não serão reprocessados sem um `/reprocessar` explícito

### Tabela `pontos_ultimate_totais_por_clan`

```sql
ALTER TABLE pontos_ultimate_totais_por_clan
ADD COLUMN pessoas_em_espera INTEGER NOT NULL DEFAULT 0;
```

- Carry-over de pessoas após cada aprovação via `/aprovar-clan`
- Zerado junto com os totais ao executar `/reprocessar`

---

## Alterações no Código

### `config.py`

Adicionar constante para o índice da nova coluna:

```python
COL_PARTICIPANTES_GROUP = 8  # coluna I: "Número de pessoas atendidas..."
```

### `points_engine.py`

Adicionar nova função (a antiga `compute_batch_promotions` permanece para não quebrar outros usos futuros, mas não será mais chamada para grupo):

```python
def compute_batch_promotions_by_people(
    pending_records: list[dict],
    pessoas_em_espera: int,
    batch_size: int,
) -> tuple[list[int], int, int]:
    """Calcula lotes baseados em número de pessoas (não registros).

    Soma os participantes de todos os registros pendentes com o carry-over
    existente. Todos os registros pendentes são promovidos de uma vez.

    Retorna (ids_para_promover, n_lotes_completos, novo_carry_over).
    """
    total_pessoas = pessoas_em_espera + sum(
        r.get("num_participantes", 1) for r in pending_records
    )
    n_lotes = total_pessoas // batch_size
    novo_carry_over = total_pessoas % batch_size
    ids_to_promote = [r["id"] for r in pending_records]
    return ids_to_promote, n_lotes, novo_carry_over
```

### `supabase_client.py`

**`upsert_clan_total`** — aceitar `pessoas_em_espera` opcional:

```python
def upsert_clan_total(clan: str, total: int, pessoas_em_espera: int | None = None) -> dict:
    payload = {"clan": clan, "total_pontos": total}
    if pessoas_em_espera is not None:
        payload["pessoas_em_espera"] = pessoas_em_espera
    ...
```

**`get_clan_carry_over`** — nova função para buscar carry-over de um clã:

```python
def get_clan_carry_over(clan: str) -> int:
    """Retorna o carry-over (pessoas_em_espera) atual do clã."""
    client = _get_client()
    result = (
        client.table(TABLE_TOTAIS)
        .select("pessoas_em_espera")
        .eq("clan", clan)
        .execute()
    )
    return result.data[0]["pessoas_em_espera"] if result.data else 0
```

**`reset_all_totals`** — já deleta todas as linhas, o que zera `pessoas_em_espera` implicitamente. Sem mudança necessária.

### `routers/contabilidade.py`

**`_process_group_records`** — ler `num_participantes` da coluna I ao inserir pendentes:

```python
for record_hash, row in new_records:
    num_participantes_raw = row[config.COL_PARTICIPANTES_GROUP] if config.COL_PARTICIPANTES_GROUP < len(row) else ""
    try:
        num_participantes = int(num_participantes_raw.strip())
        if num_participantes < 1:
            num_participantes = 1
    except (ValueError, AttributeError):
        num_participantes = 1  # fallback seguro

    _build_and_insert(
        record_hash, row, header, data_rows,
        pontos=0,
        extra_fields={"status": "pendente", "num_participantes": num_participantes},
    )
```

**`/aprovar-clan`** — substituir lógica de batch:

```python
# Antes:
ids_to_promote, n_complete = points_engine.compute_batch_promotions(
    pending, config.BATCH_SIZE_GROUP
)

# Depois:
carry_over = supabase_client.get_clan_carry_over(clan)
ids_to_promote, n_complete, novo_carry_over = points_engine.compute_batch_promotions_by_people(
    pending, carry_over, config.BATCH_SIZE_GROUP
)
```

Ao salvar o total atualizado, incluir o novo carry-over:

```python
supabase_client.upsert_clan_total(clan, novo_total, pessoas_em_espera=novo_carry_over)
```

**`AprovarClanResponse`** — novos campos:

```python
class AprovarClanResponse(BaseModel):
    clan: str
    lotes_aprovados: int
    registros_promovidos: int
    pessoas_contabilizadas: int   # total de pessoas nos registros promovidos + carry-over anterior
    pessoas_em_espera: int        # carry-over após esta aprovação
    pontos_adicionados: int
    novo_total: int
    pendentes_restantes: int
    mensagem: str
```

---

## Fluxo Completo (Aprovação)

```
1. /aprovar-clan recebe { clan: "CLÃ 5" }
2. Busca registros pendentes do clã (grupo/empresa) em ordem FIFO
3. Busca carry-over atual: get_clan_carry_over("CLÃ 5")
4. compute_batch_promotions_by_people(pending, carry_over, 5)
   → ids_to_promote, n_lotes, novo_carry_over
5. Se n_lotes == 0: retorna sem alterar nada
6. promote_pending_to_contabilizado(ids_to_promote, pontos_each=POINTS_PER_RECORD_IN_BATCH)
7. pontos_adicionados = n_lotes * POINTS_PER_BATCH_GROUP
8. novo_total = total_atual + pontos_adicionados
9. upsert_clan_total(clan, novo_total, pessoas_em_espera=novo_carry_over)
10. Retorna AprovarClanResponse com todos os campos
```

---

## Casos de Borda

| Situação | Comportamento |
|---|---|
| Coluna I vazia ou não numérica | Fallback para `num_participantes = 1` com comportamento silencioso |
| `num_participantes < 1` | Normalizado para `1` |
| Clã sem entrada em `pontos_ultimate_totais_por_clan` | `get_clan_carry_over` retorna `0` |
| Exclusão de registro contabilizado (`DELETE /registros/{id}`) | `pessoas_em_espera` não é recalculado — carry-over permanece, pois as pessoas já foram contabilizadas em lotes concluídos |
| `/reprocessar` | Zera toda a tabela de totais (inclusive `pessoas_em_espera`) e reprocessa tudo do zero |

---

## Arquivos Modificados

| Arquivo | Tipo de mudança |
|---|---|
| `backend/config.py` | Nova constante `COL_PARTICIPANTES_GROUP = 8` |
| `backend/points_engine.py` | Nova função `compute_batch_promotions_by_people` |
| `backend/supabase_client.py` | `upsert_clan_total` + nova `get_clan_carry_over` |
| `backend/routers/contabilidade.py` | `_process_group_records`, `/aprovar-clan`, `AprovarClanResponse` |
| Supabase (migration) | 2 novas colunas nas tabelas existentes |

---

## O que NÃO muda

- Lógica de Coaching Individual (continua 30 pts por registro)
- Estrutura de hashes e deduplicação
- Endpoint `/executar` (apenas insere pendentes, não contabiliza pontos de grupo)
- Endpoint `/importar`
- Frontend (campos novos na resposta são aditivos)
