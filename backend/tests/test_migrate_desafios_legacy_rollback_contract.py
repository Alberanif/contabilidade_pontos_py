"""Contrato do rollback da migração 010 — texto do SQL e do runbook.

Estes testes rodam sempre (não dependem de PostgreSQL) e travam a decisão
tomada depois da revisão da Task 11: **depois que a Fase 2 sincronizou com
sucesso não existe rollback automático**. `restore_desafio_legacy_migracao`
restaura apenas totais de clã/coach e o estado dos desafios legados; ela não
toca em `desafio_submissions_current` nem nos desafios `origem='google_sheets'`
criados pela Fase 2. Deixar `p_force` furar essa guarda produzia um estado que
nenhuma sincronização posterior conseguia consertar (tokens continuavam
`active_counted`, logo o próximo sync calculava delta zero) — divergência
contábil permanente alcançável seguindo o runbook.

O teste de integração real está em `test_migrate_desafios_legacy_postgres.py`
(exige `TEST_POSTGRES_DSN`); aqui ficam as invariantes que podem ser
verificadas sem banco: a guarda não pode voltar a ser condicional e o runbook
não pode voltar a recomendar o bypass.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT / "backend" / "migrations" / "010_migrate_legacy_desafio_contribution.sql"
)
RUNBOOK = ROOT / "docs" / "runbooks" / "migracao-desafios-google-sheets.md"


def _normalized_sql() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8")).lower()


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def _passo(numero: int) -> str:
    """Recorta uma subseção `#### 7.4.N Passo X — ...` do runbook.

    O roteiro manual da 7.4 é a única forma documentada de reverter depois da
    Fase 2, e a consistência **entre** seus passos é o que impede divergência
    contábil silenciosa. Por isso os testes olham passo a passo, e não o
    arquivo inteiro: uma asserção sobre o documento todo passaria com o texto
    certo no passo errado.
    """
    runbook = _runbook()
    marcador = re.search(
        rf"^#### 7\.4\.\d+ Passo {numero} —.*$", runbook, re.MULTILINE
    )
    assert marcador, f"o runbook precisa ter um 'Passo {numero}' na seção 7.4"
    resto = runbook[marcador.end():]
    proximo = re.search(r"^#### ", resto, re.MULTILINE)
    return resto[: proximo.start()] if proximo else resto


def test_passo_3_subtrai_exatamente_o_conjunto_que_o_passo_5_zera():
    """O finding: passo 3 recortado por data, passo 5 zerando tudo.

    Se o passo 3 subtrai só as execuções posteriores à migração enquanto o
    passo 5 neutraliza todo token, uma sincronização bem-sucedida **anterior**
    à Fase 1 (possível: a migração 009 é aplicada antes de a CLI rodar e
    `Executar Contabilidade` sincroniza desafios sem portão) deixa o total do
    clã inflado por ela, com a fatia "Desafios" em zero — e nenhuma das
    conferências do passo 8 via isso.
    """
    passo2, passo3, passo5 = _passo(2), _passo(3), _passo(5)

    # A fonte da subtração é o estado atual por token, materializado no passo 2.
    fonte = re.search(
        r"CREATE TEMP TABLE rev_planilha_por_clan ON COMMIT DROP AS(.*?);",
        passo2,
        re.DOTALL,
    )
    assert fonte, "o passo 2 precisa materializar `rev_planilha_por_clan`"
    corpo = fonte.group(1)
    assert "FROM desafio_submissions_current" in corpo
    assert "WHERE status = 'active_counted'" in corpo
    assert "started_at" not in corpo, (
        "a fonte da subtração não pode ser recortada por data: o passo 5 zera "
        "todo token, inclusive os vistos por execuções anteriores à Fase 1"
    )

    # O passo 3 subtrai daquela tabela — e de mais nada.
    update3 = re.search(
        r"UPDATE pontos_ultimate_totais_por_clan t\s+SET total_pontos = "
        r"t\.total_pontos - (.*?);",
        passo3,
        re.DOTALL,
    )
    assert update3, "o passo 3 precisa subtrair por delta dos totais de clã"
    assert "rev_planilha_por_clan" in update3.group(1)
    assert "desafio_sync_runs" not in update3.group(1)
    assert "started_at" not in update3.group(1)

    # O passo 5 zera exatamente esse conjunto, e registra quanto zerou com o
    # mesmo predicado.
    registro = re.search(
        r"CREATE TEMP TABLE rev_neutralizados ON COMMIT DROP AS(.*?);",
        passo5,
        re.DOTALL,
    )
    assert registro, "o passo 5 precisa registrar o que zerou em `rev_neutralizados`"
    update5 = re.search(
        r"UPDATE desafio_submissions_current(.*?);", passo5, re.DOTALL
    )
    assert update5, "o passo 5 precisa neutralizar os tokens"
    assert "SET status = 'inactive_missing'" in update5.group(1)
    assert "points = 0" in update5.group(1)

    predicado = "WHERE status <> 'inactive_missing'"
    assert predicado in registro.group(1)
    assert predicado in update5.group(1), (
        "o registro do passo 5 e o UPDATE do passo 5 precisam do mesmo WHERE"
    )


def test_passo_2_guarda_a_invariante_que_liga_pontos_a_active_counted():
    """`rev_planilha_por_clan` só é fonte de verdade se ponto ⇒ active_counted.

    O pipeline garante isso (`points = points_per_submission if eligible`, e
    `eligible == (status == 'active_counted')`, com clã sempre resolvido nesse
    caso), mas nenhum CHECK do banco garante. O roteiro tem de abortar em vez
    de subtrair menos do que zera.
    """
    passo2 = _passo(2)
    assert "points <> 0 AND status <> 'active_counted'" in passo2
    assert "status = 'active_counted' AND clan IS NULL" in passo2


def test_passo_8_amarra_a_subtracao_do_passo_3_a_neutralizacao_do_passo_5():
    """A conferência que teria pego o finding, com valores da própria transação."""
    passo8 = _passo(8)
    assert "rev_planilha_por_clan" in passo8
    assert "rev_neutralizados" in passo8
    assert "subtraido_no_passo_3" in passo8
    assert "zerado_no_passo_5" in passo8
    assert re.search(
        r"WHERE COALESCE\(s\.pontos, 0\) <> COALESCE\(n\.pontos, 0\)", passo8
    ), "o passo 8 precisa falhar quando os dois escopos divergem"


def test_runbook_nao_manda_mais_pular_a_conferencia_dos_tokens_ativos():
    """O texto antigo tratava a conferência decisiva como caso particular."""
    runbook = _runbook()
    assert "não havia nenhum token antes da Fase 1" not in runbook, (
        "a conferência contra os tokens ativos passou a ser a fonte da "
        "subtração; não pode voltar a ser opcional"
    )


def test_passo_4_explica_a_sincronizacao_anterior_a_fase_1():
    """`clan_before` já contém o que um sync pré-Fase-1 somou; o passo 3 tira."""
    passo4 = _passo(4)
    assert "planilha_antes_da_fase_1" in passo4
    assert "r.started_at < (SELECT started_at FROM desafio_legacy_migracoes" in passo4


def test_guarda_de_sync_posterior_e_incondicional():
    """Pega a volta do bypass: `p_force` não pode desbloquear a restauração."""
    sql = _normalized_sql()

    # A busca pela sincronização posterior continua existindo...
    assert "select id into v_sync_depois from desafio_sync_runs where status = 'succeeded'" in sql
    assert "and started_at >= v_started_at" in sql

    # ...e o disparo da exceção não pode depender de `p_force`.
    assert re.search(
        r"if v_sync_depois is not null then raise exception "
        r"'desafio_legacy_migration_restore_blocked_by_sync",
        sql,
    ), "a guarda precisa levantar a exceção sem nenhuma condição adicional"

    # Nenhuma condição pode voltar a pendurar a guarda em `p_force` (o bypass
    # antigo era literalmente `IF v_sync_depois IS NOT NULL AND NOT p_force`).
    assert "and not p_force" not in sql
    assert "or not p_force" not in sql
    assert "if not p_force" not in sql


def test_mensagem_da_guarda_diz_que_force_nao_desbloqueia_e_aponta_o_roteiro():
    """Quem bate na guarda durante um incidente precisa saber o que fazer."""
    sql = _normalized_sql()

    bloco = sql.split("'desafio_legacy_migration_restore_blocked_by_sync")[1][:900]
    assert "p_force" in bloco, "a mensagem precisa dizer que p_force não desbloqueia"
    assert "7.4" in bloco, "a mensagem precisa apontar a seção do roteiro manual"
    assert "docs/runbooks/migracao-desafios-google-sheets.md" in bloco


def test_p_force_continua_na_assinatura_mas_e_rejeitado_explicitamente():
    """Chamadas antigas (`restore(<id>, TRUE)`) falham alto, nunca pela metade."""
    sql = _normalized_sql()

    # Assinatura preservada: os GRANT/REVOKE e os callers existentes continuam válidos.
    assert "restore_desafio_legacy_migracao( p_migracao_id bigint, p_force boolean default false )" in sql
    assert "restore_desafio_legacy_migracao(bigint, boolean)" in sql

    assert "desafio_legacy_migration_force_removed" in sql


def test_runbook_nao_recomenda_mais_o_bypass_e_traz_o_roteiro_manual():
    """O finding era, literalmente, o runbook recomendar um comando que diverge."""
    runbook = _runbook()

    # A forma de dois argumentos só pode aparecer onde o runbook diz que ela
    # falha — nunca mais como o caminho para reverter.
    for linha in runbook.splitlines():
        alvo = linha.lower()
        if "restore_desafio_legacy_migracao(" in alvo and ", true)" in alvo:
            assert "deve falhar" in alvo, (
                "o runbook não pode recomendar o bypass: " + linha
            )

    # A seção nova existe e cobre os três passos que a função nunca fez.
    assert "### 7.4" in runbook
    assert "desafio_submissions_current" in runbook
    assert "inactive_missing" in runbook
    assert "clan_removido" in runbook
    assert "coach_removido" in runbook
    assert "pg_advisory_xact_lock(7345901220834561)" in runbook
