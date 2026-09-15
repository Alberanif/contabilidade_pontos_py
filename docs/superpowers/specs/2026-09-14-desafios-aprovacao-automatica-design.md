# Design: Aprovação Automática de Submissões de Desafio (pós-corte)

**Data:** 14/09/2026
**Status:** Aprovado — pronto para implementação
**Substitui:** PRD `2026-09-11-desafios-percentual-por-cla-prd.md` §6 (Novo Critério Único de Elegibilidade) e §8.4 (Congelamento e reabertura), só na parte de aprovação manual — a regra de faixas de percentual do clã (§4) e o corte de 01/08/2026 (§5) continuam valendo.

## Contexto

O PRD de 11/09/2026 introduziu aprovação manual (check/X) como pré-requisito para qualquer submissão pós-corte contar — tanto para os 100 pontos individuais do coach quanto para a apuração de percentual de engajamento do clã. Na prática isso criou um gargalo: em 14/09/2026, **123 submissões pós-corte** estavam com revisão pendente (nunca revisadas) e por isso não contavam nada, e só 9 haviam sido explicitamente aprovadas.

## Mudança de regra

A partir desta mudança, para submissões pós-corte (`submitted_at >= config.DESAFIO_PERCENTUAL_CLAN_CORTE`):

- **Toda submissão `active_counted` conta por padrão** — tanto para os 100 pontos individuais do coach (`config.POINTS_PER_DESAFIO_SUBMISSION_COACH`) quanto para a contagem de participação no percentual do clã.
- **Só `revisao_status == "reprovado"` exclui.** Os valores `"pendente"` (nunca revisado) e `"aprovado"` (valor legado de quando a aprovação era exigida) contam exatamente igual — não há mais distinção funcional entre eles.
- **Reprovar é reversível a qualquer momento**, inclusive depois que o desafio já apurou a pontuação de clã (ver abaixo) — grava `status: "pendente"` de volta, que agora significa "válido".
- Submissões pré-corte não mudam: continuam sempre contando, sem UI de revisão.

## Reprovação após apuração já congelada (muda o PRD §8.4)

O PRD original dizia que, uma vez apurado, um desafio só é recalculado se o prazo for reaberto manualmente — aprovar/reprovar depois disso "não dispara recálculo automático". Isso deixa de valer: **reprovar (ou desfazer a reprovação) de uma submissão cujo desafio já está apurado (`desafios.apurado_em` não nulo) dispara, na mesma operação, o recálculo daquele desafio específico e a aplicação do delta resultante ao total do clã** — sem precisar tocar no prazo. Ver `supabase_client.reapurar_desafio_e_aplicar_delta`.

## Backfill

Desafios pós-corte que já estavam apurados antes desta mudança usaram a regra antiga (só "aprovado" contava). Um script administrativo (`backend/admin/backfill_desafio_apuracao_automatica.py`) reaplica a apuração desses desafios sob a regra nova, com um modo dry-run que mostra o delta por clã antes de gravar. Em 14/09/2026 há 0 desafios nessa situação em produção — o backfill é um no-op na prática, mas o mecanismo existe para qualquer desafio que venha a se enquadrar.

## UI

Duas visualizações no lugar de três: badge **VÁLIDO** (verde, padrão) / **REPROVADO** (vermelho), com um único botão que alterna entre "✗ Reprovar" e "↶ Desfazer reprovação". O conceito de "aprovar" manualmente deixa de existir na interface — o valor `"aprovado"` continua sendo um valor válido no banco (compatibilidade com as 9 linhas já gravadas), mas nada na UI volta a gravá-lo.
