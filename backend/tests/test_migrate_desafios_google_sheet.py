"""Testes da CLI administrativa de migração de desafios para a Google Sheet.

A CLI é o corte de produção: em `--apply` ela remove a contribuição legada de
desafios dos totais reais de clã e coach e aplica o primeiro snapshot oficial.
Estes testes cobrem o lado Python (pré-condições, relatório de dry-run,
sequenciamento das duas fases, validações pós-migração), mockando apenas as
bordas de I/O (`google_sheets_client.fetch_desafio_records`,
`supabase_client.call_rpc`/leituras de totais e o estado atual dos tokens) e
deixando parser/snapshot/reconciliação (Tasks 2-3) rodarem de verdade.

O comportamento que só existe dentro do Postgres (lock, subtração explícita,
aborto por total negativo, backup verificável e restauração) é coberto por
`test_migrate_desafios_legacy_postgres.py`, que exige `TEST_POSTGRES_DSN`.
"""

import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from admin import migrate_desafios_google_sheet as cli  # noqa: E402
from desafio_sync_service import DesafioSyncResult  # noqa: E402
from google_sheets_client import DesafioSheetConfigurationError  # noqa: E402


HEADER = [
    "Clã (legado)", "Nome", "Validado", "Link", "Observação",
    "Desafio", "Clã atual", "Enviado em", "Token",
]


def _row(token, clan="1", validado="Sim", desafio="Desafio A", nome="Ana"):
    return ["", nome, validado, "", "", desafio, clan, "19/08/2026 10:00:00", token]


SHEET = [HEADER, _row("TOK-1", clan="1"), _row("TOK-2", clan="2", nome="Bia")]


LEGACY_REPORT = {
    "ja_migrado": False,
    "migracao_id": None,
    "clans": [
        {
            "clan": "CLÃ 1",
            "total_antes": 100,
            "contribuicao_legada": 30,
            "total_depois": 70,
        },
        {
            "clan": "CLÃ 2",
            "total_antes": 50,
            "contribuicao_legada": 0,
            "total_depois": 50,
        },
    ],
    "coaches": [
        {
            "coach": "Ana",
            "total_antes": 60,
            "contribuicao_legada": 20,
            "total_depois": 40,
        },
    ],
    "negativos": [],
    "desafios_legados": 3,
    "desafios_legados_contabilizando": 2,
    "registros_clan": 5,
    "registros_coach": 2,
    "linhas_importacao": 40,
}

PHASE1_RESULT = {
    "status": "applied",
    "migracao_id": 7,
    "backup_rows": 52,
    "backup_checksum": "cafeb0ba",
    "clan_before": {"CLÃ 1": 100},
    "clan_after": {"CLÃ 1": 70},
    "coach_before": {"Ana": 60},
    "coach_after": {"Ana": 40},
    "desafios_arquivados": 3,
}


class _Recorder:
    """Registra chamadas de RPC e devolve respostas por nome de função."""

    def __init__(self, responses=None, errors=None):
        self.calls = []
        self.responses = responses or {}
        self.errors = errors or {}

    def __call__(self, function_name, params=None):
        self.calls.append((function_name, params))
        if function_name in self.errors:
            raise self.errors[function_name]
        return self.responses.get(function_name)

    @property
    def names(self):
        return [name for name, _ in self.calls]


def _sync_result(**kwargs):
    base = dict(
        status="success",
        snapshot_hash="ignored",
        clan_deltas={"CLÃ 1": 10, "CLÃ 2": 10},
        clan_totals_after={"CLÃ 1": 80, "CLÃ 2": 60},
        tokens_versioned=2,
        mensagem="ok",
    )
    base.update(kwargs)
    return DesafioSyncResult(**base)


def _zero_delta_result():
    return _sync_result(clan_deltas={}, tokens_versioned=0, mensagem="sem alterações")


class _SyncStub:
    """Devolve resultados em sequência e registra os argumentos recebidos."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not self.results:
            raise AssertionError("sync_desafios chamado mais vezes que o previsto")
        return self.results.pop(0)


def _run(
    argv,
    *,
    sheet=None,
    rpc=None,
    sync=None,
    current=None,
    clan_desafio_totals=None,
    coach_desafio_totals=None,
    spreadsheet_id="planilha-oficial",
    sheet_name="Desafios",
    service_account="{}",
):
    """Executa a CLI com todas as bordas de I/O mockadas."""
    rpc = rpc if rpc is not None else _Recorder({cli.RPC_REPORT: LEGACY_REPORT})
    sync = sync if sync is not None else _SyncStub(_sync_result(), _zero_delta_result())
    rows = SHEET if sheet is None else sheet

    fetch = (
        rows
        if isinstance(rows, Exception)
        else None
    )
    with patch.object(cli.config, "GSHEET_DESAFIOS_SPREADSHEET_ID", spreadsheet_id), \
         patch.object(cli.config, "GSHEET_DESAFIOS_SHEET_NAME", sheet_name), \
         patch.object(cli.config, "GOOGLE_SERVICE_ACCOUNT_JSON", service_account), \
         patch.object(cli.config, "POINTS_PER_DESAFIO_SUBMISSION", 10), \
         patch.object(
             cli.google_sheets_client,
             "fetch_desafio_records",
             side_effect=fetch if fetch else None,
             return_value=None if fetch else rows,
         ), \
         patch.object(
             cli.store,
             "get_current_desafio_submissions",
             return_value={} if current is None else current,
         ), \
         patch.object(cli.supabase_client, "call_rpc", rpc), \
         patch.object(
             cli.supabase_client,
             "get_tipo_clan_totals",
             return_value=(
                 {"CLÃ 1": 10, "CLÃ 2": 10}
                 if clan_desafio_totals is None
                 else clan_desafio_totals
             ),
         ), \
         patch.object(
             cli.supabase_client,
             "get_tipo_coach_totals",
             return_value=(
                 {} if coach_desafio_totals is None else coach_desafio_totals
             ),
         ), \
         patch.object(cli.desafio_sync_service, "sync_desafios", sync):
        code = cli.main(argv)
    return code, rpc, sync


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_nao_escreve_nada_e_relata_totais_antigos_e_novos(capsys):
    code, rpc, sync = _run([])
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    # Somente a função de relatório (somente leitura) foi chamada.
    assert rpc.names == [cli.RPC_REPORT]
    assert sync.calls == []

    # Totais antigos vs. novos por clã e por coach.
    assert "CLÃ 1" in out and "100" in out and "70" in out
    assert "CLÃ 2" in out
    assert "Ana" in out and "60" in out and "40" in out
    assert "DRY-RUN" in out.upper()


def test_dry_run_publica_o_hash_do_snapshot_para_confirmacao(capsys):
    code, _, _ = _run([])
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    preview_hash = _preview_hash()
    assert preview_hash in out
    assert "--confirm-hash" in out


def _preview_hash() -> str:
    """Hash do snapshot da planilha de teste, calculado pelos módulos reais."""
    import desafio_reconciliation
    import desafio_sheet_parser

    parsed = desafio_sheet_parser.build_parsed_rows(SHEET)
    return desafio_reconciliation.build_desafio_snapshot(parsed, 10).snapshot_hash


# ---------------------------------------------------------------------------
# Pré-condições
# ---------------------------------------------------------------------------


def test_config_ausente_bloqueia_antes_de_qualquer_leitura(capsys):
    rpc = _Recorder()
    code, rpc, sync = _run([], rpc=rpc, spreadsheet_id=None)
    out = capsys.readouterr().out

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == []
    assert sync.calls == []
    assert "GSHEET_DESAFIOS_SPREADSHEET_ID" in out


def test_credencial_google_ausente_bloqueia(capsys):
    code, rpc, _ = _run([], rpc=_Recorder(), service_account=None)
    out = capsys.readouterr().out

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == []
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in out


def test_erro_de_configuracao_da_planilha_bloqueia(capsys):
    code, rpc, _ = _run(
        [],
        sheet=DesafioSheetConfigurationError("aba inexistente"),
        rpc=_Recorder(),
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == []
    assert "aba inexistente" in out


def test_planilha_vazia_bloqueia(capsys):
    code, rpc, _ = _run([], sheet=[HEADER], rpc=_Recorder())
    out = capsys.readouterr().out

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == []
    assert "vazia" in out.lower()


def test_planilha_sem_nenhuma_linha_bloqueia(capsys):
    code, rpc, _ = _run([], sheet=[], rpc=_Recorder())

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == []
    assert "vazia" in capsys.readouterr().out.lower()


def test_coluna_f_nao_preenchida_bloqueia_e_lista_as_linhas(capsys):
    sheet = [HEADER, _row("TOK-1"), _row("TOK-2", desafio="", nome="Bia")]
    code, rpc, _ = _run([], sheet=sheet, rpc=_Recorder())
    out = capsys.readouterr().out

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == []
    assert "coluna F" in out
    # A linha 3 da planilha (2ª de dados) é a que está sem desafio.
    assert "3" in out


def test_total_que_ficaria_negativo_bloqueia_mesmo_em_dry_run(capsys):
    report = dict(
        LEGACY_REPORT,
        negativos=[
            {
                "escopo": "clan",
                "chave": "CLÃ 3",
                "total_antes": 5,
                "contribuicao_legada": 40,
                "total_depois": -35,
            }
        ],
    )
    code, rpc, sync = _run([], rpc=_Recorder({cli.RPC_REPORT: report}))
    out = capsys.readouterr().out

    assert code == cli.EXIT_PRECONDITION
    assert rpc.names == [cli.RPC_REPORT]
    assert sync.calls == []
    assert "CLÃ 3" in out
    assert "negativ" in out.lower()


# ---------------------------------------------------------------------------
# Confirmação
# ---------------------------------------------------------------------------


def test_apply_sem_confirm_hash_nao_escreve(capsys):
    code, rpc, sync = _run(["--apply"])
    out = capsys.readouterr().out

    assert code == cli.EXIT_CONFIRMATION
    assert rpc.names == [cli.RPC_REPORT]
    assert sync.calls == []
    assert "--confirm-hash" in out


def test_apply_com_hash_divergente_nao_escreve(capsys):
    code, rpc, sync = _run(["--apply", "--confirm-hash", "hash-errado"])
    out = capsys.readouterr().out

    assert code == cli.EXIT_CONFIRMATION
    assert rpc.names == [cli.RPC_REPORT]
    assert sync.calls == []
    assert "hash-errado" in out


def test_remocao_em_massa_exige_flag_explicita(capsys):
    """A CLI nunca aprova sozinha uma remoção em massa (RF-17)."""
    from desafio_reconciliation import CurrentSubmission, compute_content_hash

    current = {
        f"ANTIGO-{i}": CurrentSubmission(
            token=f"ANTIGO-{i}",
            raw_clan_legacy="", raw_name="X", raw_validation="Sim", raw_link="",
            raw_observation="", raw_challenge="Desafio Z", raw_clan_current="1",
            raw_submitted_at="19/08/2026 10:00:00", raw_token=f"ANTIGO-{i}",
            clan="CLÃ 1", challenge_normalized="desafio z", desafio_id=1,
            submitted_at=None, status="active_counted", points=10,
            content_hash=compute_content_hash(f"ANTIGO-{i}", "active_counted", []),
        )
        for i in range(10)
    }

    code, rpc, sync = _run(
        ["--apply", "--confirm-hash", _preview_hash()],
        rpc=_Recorder({cli.RPC_REPORT: LEGACY_REPORT}),
        sync=_SyncStub(),
        current=current,
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_CONFIRMATION
    assert rpc.names == [cli.RPC_REPORT]
    assert sync.calls == []
    assert "--confirm-mass-removal" in out


# ---------------------------------------------------------------------------
# Aplicação em duas fases
# ---------------------------------------------------------------------------


def test_apply_executa_fase1_depois_fase2_e_valida(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    sync = _SyncStub(_sync_result(), _zero_delta_result())
    code, rpc, sync = _run(
        ["--apply", "--confirm-hash", _preview_hash()], rpc=rpc, sync=sync
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert rpc.names == [cli.RPC_REPORT, cli.RPC_MIGRATE]
    # Fase 2 aplica o snapshot confirmado; a segunda chamada é a validação de
    # reexecução com delta zero.
    assert len(sync.calls) == 2
    assert sync.calls[0]["confirm_snapshot_hash"] == _preview_hash()
    assert sync.calls[0]["confirm_mass_removal"] is False
    # O backup precisa aparecer no relatório para o operador registrar.
    assert "cafeb0ba" in out
    assert "#7" in out


def test_apply_reporta_backup_verificavel_da_fase1(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    code, _, _ = _run(["--apply", "--confirm-hash", _preview_hash()], rpc=rpc)
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert "52" in out
    assert "cafeb0ba" in out


def test_falha_na_fase1_nao_dispara_a_fase2(capsys):
    rpc = _Recorder(
        {cli.RPC_REPORT: LEGACY_REPORT},
        errors={cli.RPC_MIGRATE: RuntimeError(
            "desafio_legacy_migration_negative_clan_total: CLÃ 1"
        )},
    )
    sync = _SyncStub()
    code, rpc, sync = _run(
        ["--apply", "--confirm-hash", _preview_hash()], rpc=rpc, sync=sync
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_PHASE1_FAILED
    assert sync.calls == []
    assert "negative_clan_total" in out
    # Nada foi aplicado: a fase 1 é uma transação única do banco.
    assert "nenhuma alteração" in out.lower()


def test_falha_na_fase2_avisa_que_a_fase1_ja_foi_commitada(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    sync = _SyncStub(_sync_result(status="failed", mensagem="planilha indisponível"))
    code, rpc, sync = _run(
        ["--apply", "--confirm-hash", _preview_hash()], rpc=rpc, sync=sync
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_PHASE2_FAILED
    assert rpc.names == [cli.RPC_REPORT, cli.RPC_MIGRATE]
    assert len(sync.calls) == 1
    assert "Fase 1" in out
    assert "#7" in out  # id da migração, necessário para o rollback
    assert "runbook" in out.lower()


def test_fase1_ja_aplicada_executa_somente_a_fase2(capsys):
    """Recuperação documentada de 'fase 1 ok / fase 2 falhou'."""
    report = dict(LEGACY_REPORT, ja_migrado=True, migracao_id=7)
    rpc = _Recorder({cli.RPC_REPORT: report})
    sync = _SyncStub(_sync_result(), _zero_delta_result())
    code, rpc, sync = _run(
        ["--apply", "--confirm-hash", _preview_hash()], rpc=rpc, sync=sync
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert rpc.names == [cli.RPC_REPORT]  # a fase 1 não é repetida
    assert len(sync.calls) == 2
    assert "Fase 1" in out


# ---------------------------------------------------------------------------
# Validações pós-migração
# ---------------------------------------------------------------------------


def test_validacao_falha_quando_pontos_por_cla_divergem_do_esperado(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    code, _, _ = _run(
        ["--apply", "--confirm-hash", _preview_hash()],
        rpc=rpc,
        clan_desafio_totals={"CLÃ 1": 10, "CLÃ 2": 999},
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_VALIDATION_FAILED
    assert "CLÃ 2" in out
    assert "999" in out


def test_validacao_falha_quando_sobra_ponto_de_coach_em_desafios(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    code, _, _ = _run(
        ["--apply", "--confirm-hash", _preview_hash()],
        rpc=rpc,
        coach_desafio_totals={"Ana": 20},
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_VALIDATION_FAILED
    assert "coach" in out.lower()
    assert "Ana" in out


def test_validacao_falha_quando_reexecucao_nao_tem_delta_zero(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    sync = _SyncStub(_sync_result(), _sync_result(clan_deltas={"CLÃ 1": 10}))
    code, _, sync = _run(
        ["--apply", "--confirm-hash", _preview_hash()], rpc=rpc, sync=sync
    )
    out = capsys.readouterr().out

    assert code == cli.EXIT_VALIDATION_FAILED
    assert len(sync.calls) == 2
    assert "delta zero" in out.lower()


def test_validacoes_passam_com_soma_igual_a_tokens_elegiveis_vezes_valor(capsys):
    rpc = _Recorder({cli.RPC_REPORT: LEGACY_REPORT, cli.RPC_MIGRATE: PHASE1_RESULT})
    code, _, _ = _run(["--apply", "--confirm-hash", _preview_hash()], rpc=rpc)
    out = capsys.readouterr().out

    assert code == cli.EXIT_OK
    assert "OK" in out.upper()


# ---------------------------------------------------------------------------
# Contrato da CLI
# ---------------------------------------------------------------------------


def test_dry_run_e_o_padrao_sem_argumentos():
    parsed = cli.parse_args([])
    assert parsed.apply is False
    assert parsed.confirm_hash is None
    assert parsed.confirm_mass_removal is False


def test_flags_do_contrato_sao_aceitas():
    parsed = cli.parse_args(["--apply", "--confirm-hash", "abc"])
    assert parsed.apply is True
    assert parsed.confirm_hash == "abc"
