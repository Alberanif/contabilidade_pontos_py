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
