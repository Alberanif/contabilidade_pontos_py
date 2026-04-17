# Spec: Fix — Filtro de Data para Registros Importados

**Data**: 2026-04-17  
**Status**: Aprovado

---

## Contexto

O filtro de data do Dashboard exibe o ranking "como estava em uma data passada", subtraindo do total atual os pontos de registros com `data_registro` posterior à data de corte:

```
total_historico = total_atual - SUM(pontos WHERE data_registro > ate)
```

Registros processados via `executar()` têm `pontos` correto (ex: `POINTS_PER_COACHING_INDIVIDUAL` por sessão). Registros inseridos via `importar_inicial()` sempre recebiam `pontos = 0`, tornando a subtração inoperante: aplicar qualquer data de corte não alterava os totais exibidos.

**Impacto**: Ao importar dados do dia 17/04/2026 e aplicar filtro para 01/04/2026, registros de 02/04 em diante não eram subtraídos — o ranking histórico estava sempre igual ao atual.

---

## Solução

Corrigir `importar_inicial()` para atribuir os valores de `pontos` e `pontos_coach` corretos por tipo de registro, espelhando o comportamento de `executar()`.

A abordagem de subtração **não exige** `SUM(todos os pontos) == total_atual`. Ela apenas precisa que registros **após o corte** tenham `pontos` corretos. O `total_atual` semeado da planilha de ranking permanece como ponto de partida inalterado.

---

## Arquivo Modificado

`backend/routers/contabilidade.py`

---

## Mudanças Detalhadas

### Fase 3 — CI Coaching (linhas ~655–665)

Antes de iterar os registros, pré-computar quais são elegíveis para `pontos_coach` (mesma lógica já usada na Fase 7):

```python
coach_eligible_set = {
    h for h, _ in points_engine.filter_records_by_date_from(
        coaching_records, config.COL_DATE_PAYING, config.COACH_RANKING_START_DATE
    )
}
for record_hash, row in coaching_records:
    _build_and_insert(
        record_hash, row, header, data_rows,
        pontos=config.POINTS_PER_COACHING_INDIVIDUAL,          # era 0
        extra_fields={
            "status": "contabilizado",
            "status_coach": "contabilizado",
            "pontos_coach": (
                config.POINTS_PER_COACHING_INDIVIDUAL
                if record_hash in coach_eligible_set else 0    # era sempre 0
            ),
        },
        date_col=config.COL_DATE_PAYING,
    )
```

### Fase 4 — Group/Empresa (linhas ~715–724)

```python
_build_and_insert(
    record_hash, row, header, data_rows,
    pontos=config.POINTS_PER_RECORD_IN_BATCH if status == "contabilizado" else 0,  # era 0
    extra_fields={
        "status": status,
        "status_coach": status_coach,
        "num_participantes": num_participantes,
        "pontos_coach": 0,   # inalterado: coach totals semeados apenas com CI na Fase 7
    },
    date_col=config.COL_DATE_PAYING,
)
```

### Fase 8 — Pro-bono (linhas ~776–786)

```python
_build_and_insert_pro_bono(
    record_hash, row, pb_header, pb_data_rows,
    pontos=config.POINTS_PER_PRO_BONO,   # era 0
    extra_fields={
        "status": "contabilizado",
        "status_coach": "contabilizado",
        "pontos_coach": 0,   # inalterado
    },
    date_col=config.COL_DATE_PRO_BONO,
)
```

### Comentário desatualizado — `backend/supabase_client.py` linha ~502

Remover ou atualizar o comentário:
```python
# antes: "Correto porque TABLE_TOTAIS já contém o total acumulado completo
#         e apenas registros do executar_contabilidade têm pontos > 0."
# depois: comentário removido (invariante agora válida também para importar_inicial)
```

---

## Invariantes Mantidas

| Caso | Comportamento esperado após o fix |
|------|------------------------------------|
| Filtro `ate = hoje` | `SUM(pontos onde data > hoje) = 0` → total inalterado ✓ |
| Filtro `ate = 01/04/2026` | CI, grupo e pro-bono após 01/04 subtraídos corretamente ✓ |
| Coach filter CI inelegível | `pontos_coach = 0` para registros antes de `COACH_RANKING_START_DATE` ✓ |
| Registros grupo pendentes | `pontos = 0` (status pendente = ainda não contabilizado) ✓ |
| Registros sem `data_registro` | Incluídos no total histórico (fail-open existente mantido) ✓ |

---

## Verificação

1. Executar `POST /api/contabilidade/importar-inicial`
2. Verificar no Supabase que registros CI têm `pontos = POINTS_PER_COACHING_INDIVIDUAL` e `pontos_coach` correto
3. Verificar que registros grupo contabilizados têm `pontos = POINTS_PER_RECORD_IN_BATCH`
4. Verificar que registros pro-bono têm `pontos = POINTS_PER_PRO_BONO`
5. No Dashboard, aplicar filtro para data anterior à importação → totais devem diminuir
6. Aplicar filtro para hoje → totais devem ser idênticos ao display sem filtro
7. Aplicar filtro para data anterior a `COACH_RANKING_START_DATE` → ranking de coaches deve zerar/diminuir
