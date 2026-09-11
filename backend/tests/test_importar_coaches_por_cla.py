"""Testes da issue #3 (Task 3): script de importação dos CSVs de `coaches/`
para `pontos_ultimate_coach_clas`.

Mocka apenas as bordas de I/O do banco (`supabase_client.get_coach_alias_map`,
`supabase_client.list_coach_clas`, `supabase_client.upsert_coach_cla`) e
deixa o parser de CSV e `coach_identity.resolve_coach` (Tasks 1-2, já
mergeadas) rodarem de verdade. Um dos testes roda o parser real contra os 8
CSVs de verdade em `coaches/` (dry-run) como checagem de regressão contra os
dados reais, não só fixtures sintéticas.
"""

import csv
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from admin import importar_coaches_por_cla as script  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_COACHES_DIR = REPO_ROOT / "coaches"


# ---------------------------------------------------------------------------
# parse_clan_from_filename
# ---------------------------------------------------------------------------


class TestParseClanFromFilename:

    def test_extrai_cla_dos_8_arquivos_reais(self):
        for n in range(1, 9):
            filename = f"[EDIÇÃO] ULTIMATES _ Clãs _ Agosto 26.xlsx - Clã {n}.csv"
            assert script.parse_clan_from_filename(filename) == f"CLÃ {n}"

    def test_levanta_erro_sem_cla_no_nome(self):
        import pytest

        with pytest.raises(ValueError):
            script.parse_clan_from_filename("arquivo_sem_cla.csv")


# ---------------------------------------------------------------------------
# parse_coach_cla_csv
# ---------------------------------------------------------------------------


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


class TestParseCoachClaCsv:

    def test_le_as_6_colunas_e_ignora_celulas_vazias(self, tmp_path):
        path = tmp_path / "arquivo - Clã 2.csv"
        _write_csv(
            path,
            ["Coach", "Coach Action", "Coach Pro", "Coach Hero", "Sem Categoria", "Novos ULTIMATES"],
            [
                ["Fulano", "Ciclana", "", "Beltrano", "", "Ana"],
                ["", "Outra Pessoa", "", "", "", ""],
            ],
        )
        rows = script.parse_coach_cla_csv(path)
        assert rows == [
            {"raw_name": "Fulano", "clan": "CLÃ 2", "categoria": "Coach"},
            {"raw_name": "Ciclana", "clan": "CLÃ 2", "categoria": "Coach Action"},
            {"raw_name": "Beltrano", "clan": "CLÃ 2", "categoria": "Coach Hero"},
            {"raw_name": "Ana", "clan": "CLÃ 2", "categoria": "Novos ULTIMATES"},
            {"raw_name": "Outra Pessoa", "clan": "CLÃ 2", "categoria": "Coach Action"},
        ]

    def test_ignora_colunas_extras_depois_da_6a(self, tmp_path):
        """Pelo menos um clã real tem cabeçalhos vazios sobrando depois de
        'Novos ULTIMATES' — o parser deve ler só as 6 primeiras colunas."""
        path = tmp_path / "arquivo - Clã 5.csv"
        _write_csv(
            path,
            ["Coach", "Coach Action", "Coach Pro", "Coach Hero", "Sem Categoria", "Novos ULTIMATES", "", ""],
            [["Fulano", "", "", "", "", "", "lixo", "lixo2"]],
        )
        rows = script.parse_coach_cla_csv(path)
        assert rows == [{"raw_name": "Fulano", "clan": "CLÃ 5", "categoria": "Coach"}]

    def test_arquivo_so_com_cabecalho_nao_gera_linhas(self, tmp_path):
        path = tmp_path / "arquivo - Clã 1.csv"
        _write_csv(
            path,
            ["Coach", "Coach Action", "Coach Pro", "Coach Hero", "Sem Categoria", "Novos ULTIMATES"],
            [],
        )
        assert script.parse_coach_cla_csv(path) == []


# ---------------------------------------------------------------------------
# build_import_plan
# ---------------------------------------------------------------------------


class TestBuildImportPlan:

    def test_resolve_raw_name_via_alias_map(self):
        rows = [{"raw_name": "Fulano Da Silva", "clan": "CLÃ 1", "categoria": "Coach"}]
        alias_map = {"Fulano Da Silva": "Fulano Da Silva Canônico"}
        plan = script.build_import_plan(rows, alias_map)
        assert plan == [
            {"coach_canonico": "Fulano Da Silva Canônico", "clan": "CLÃ 1", "categoria": "Coach"}
        ]

    def test_sem_alias_correspondente_mantem_nome_bruto(self):
        rows = [{"raw_name": "Ninguem Conhecido", "clan": "CLÃ 3", "categoria": "Coach Pro"}]
        plan = script.build_import_plan(rows, alias_map={})
        assert plan == [
            {"coach_canonico": "Ninguem Conhecido", "clan": "CLÃ 3", "categoria": "Coach Pro"}
        ]


# ---------------------------------------------------------------------------
# run_import — fixtures sintéticas (mocka a camada Supabase inteira)
# ---------------------------------------------------------------------------


class _FakeCoachClasStore:
    """Substitui get_coach_alias_map/list_coach_clas/upsert_coach_cla por um
    estado em memória, para testar idempotência e reimportação sem banco."""

    def __init__(self, alias_map: dict[str, str] | None = None):
        self.alias_map = alias_map or {}
        self.rows: dict[str, dict] = {}  # coach_canonico -> row
        self.upsert_calls: list[tuple[str, str, str]] = []

    def get_coach_alias_map(self) -> dict[str, str]:
        return dict(self.alias_map)

    def list_coach_clas(self, clan: str | None = None) -> list[dict]:
        rows = list(self.rows.values())
        if clan:
            rows = [r for r in rows if r["clan"] == clan]
        return rows

    def upsert_coach_cla(self, coach_canonico: str, clan: str, categoria: str) -> dict:
        self.upsert_calls.append((coach_canonico, clan, categoria))
        row = {"coach_canonico": coach_canonico, "clan": clan, "categoria": categoria}
        self.rows[coach_canonico] = row
        return row


def _make_single_clan_csv(tmp_path: Path, clan_n: int, names: list[str]) -> Path:
    path = tmp_path / f"arquivo - Clã {clan_n}.csv"
    _write_csv(
        path,
        ["Coach", "Coach Action", "Coach Pro", "Coach Hero", "Sem Categoria", "Novos ULTIMATES"],
        [[name, "", "", "", "", ""] for name in names],
    )
    return path


class TestRunImportDryRunVsApply:

    def test_dry_run_nao_escreve_nada(self, tmp_path):
        _make_single_clan_csv(tmp_path, 1, ["Fulano", "Ciclana"])
        store = _FakeCoachClasStore()
        with patch.object(script.supabase_client, "get_coach_alias_map", store.get_coach_alias_map), \
             patch.object(script.supabase_client, "list_coach_clas", store.list_coach_clas), \
             patch.object(script.supabase_client, "upsert_coach_cla", store.upsert_coach_cla):
            report = script.run_import(apply=False, csv_dir=tmp_path)

        assert report == {
            "processados": 2,
            "inseridos": 2,
            "atualizados": 0,
            "inalterados": 0,
        }
        assert store.upsert_calls == []
        assert store.rows == {}

    def test_apply_grava_via_upsert(self, tmp_path):
        _make_single_clan_csv(tmp_path, 1, ["Fulano", "Ciclana"])
        store = _FakeCoachClasStore()
        with patch.object(script.supabase_client, "get_coach_alias_map", store.get_coach_alias_map), \
             patch.object(script.supabase_client, "list_coach_clas", store.list_coach_clas), \
             patch.object(script.supabase_client, "upsert_coach_cla", store.upsert_coach_cla):
            report = script.run_import(apply=True, csv_dir=tmp_path)

        assert report == {
            "processados": 2,
            "inseridos": 2,
            "atualizados": 0,
            "inalterados": 0,
        }
        assert len(store.upsert_calls) == 2
        assert store.rows["Fulano"] == {"coach_canonico": "Fulano", "clan": "CLÃ 1", "categoria": "Coach"}


class TestRunImportIdempotency:

    def test_reimportar_mesmo_csv_nao_duplica_nem_atualiza(self, tmp_path):
        _make_single_clan_csv(tmp_path, 1, ["Fulano", "Ciclana"])
        store = _FakeCoachClasStore()
        with patch.object(script.supabase_client, "get_coach_alias_map", store.get_coach_alias_map), \
             patch.object(script.supabase_client, "list_coach_clas", store.list_coach_clas), \
             patch.object(script.supabase_client, "upsert_coach_cla", store.upsert_coach_cla):
            script.run_import(apply=True, csv_dir=tmp_path)
            second_report = script.run_import(apply=True, csv_dir=tmp_path)

        assert second_report == {
            "processados": 2,
            "inseridos": 0,
            "atualizados": 0,
            "inalterados": 2,
        }
        # duas execuções de 2 linhas cada = 4 chamadas de upsert, mas o
        # estado final continua com só 2 coaches (idempotente).
        assert len(store.rows) == 2

    def test_reimportar_com_coach_movido_de_cla_atualiza(self, tmp_path):
        store = _FakeCoachClasStore()
        first_dir = tmp_path / "primeira"
        first_dir.mkdir()
        _make_single_clan_csv(first_dir, 1, ["Fulano"])

        with patch.object(script.supabase_client, "get_coach_alias_map", store.get_coach_alias_map), \
             patch.object(script.supabase_client, "list_coach_clas", store.list_coach_clas), \
             patch.object(script.supabase_client, "upsert_coach_cla", store.upsert_coach_cla):
            first_report = script.run_import(apply=True, csv_dir=first_dir)

            second_dir = tmp_path / "segunda"
            second_dir.mkdir()
            _make_single_clan_csv(second_dir, 4, ["Fulano"])
            second_report = script.run_import(apply=True, csv_dir=second_dir)

        assert first_report == {
            "processados": 1, "inseridos": 1, "atualizados": 0, "inalterados": 0,
        }
        assert second_report == {
            "processados": 1, "inseridos": 0, "atualizados": 1, "inalterados": 0,
        }
        assert store.rows["Fulano"]["clan"] == "CLÃ 4"
        assert len(store.rows) == 1  # não duplicou: mesma linha, clã atualizado


class TestRunImportResolvesAlias:

    def test_nome_com_alias_cadastrado_importa_com_canonico(self, tmp_path):
        _make_single_clan_csv(tmp_path, 1, ["Nome Bruto"])
        store = _FakeCoachClasStore(alias_map={"Nome Bruto": "Nome Canônico"})
        with patch.object(script.supabase_client, "get_coach_alias_map", store.get_coach_alias_map), \
             patch.object(script.supabase_client, "list_coach_clas", store.list_coach_clas), \
             patch.object(script.supabase_client, "upsert_coach_cla", store.upsert_coach_cla):
            script.run_import(apply=True, csv_dir=tmp_path)

        assert "Nome Canônico" in store.rows
        assert "Nome Bruto" not in store.rows


# ---------------------------------------------------------------------------
# Regressão contra os CSVs reais de coaches/
# ---------------------------------------------------------------------------


class TestRunImportRealCsvs:

    def test_dry_run_contra_csvs_reais_encontra_154_nomes_em_8_clas(self):
        assert REAL_COACHES_DIR.is_dir(), f"pasta coaches/ não encontrada em {REAL_COACHES_DIR}"
        real_csvs = sorted(REAL_COACHES_DIR.glob("*.csv"))
        assert len(real_csvs) == 8

        store = _FakeCoachClasStore()
        with patch.object(script.supabase_client, "get_coach_alias_map", store.get_coach_alias_map), \
             patch.object(script.supabase_client, "list_coach_clas", store.list_coach_clas), \
             patch.object(script.supabase_client, "upsert_coach_cla", store.upsert_coach_cla):
            report = script.run_import(apply=False, csv_dir=REAL_COACHES_DIR)

        assert report["processados"] == 154
        assert report["inseridos"] == 154
        assert report["atualizados"] == 0
        assert report["inalterados"] == 0
        # dry-run de verdade: nada foi escrito.
        assert store.rows == {}
        assert store.upsert_calls == []

    def test_dry_run_contra_csvs_reais_distribui_por_8_clas_sem_erro(self):
        clans_encontrados = set()
        total_linhas = 0
        for path in sorted(REAL_COACHES_DIR.glob("*.csv")):
            rows = script.parse_coach_cla_csv(path)
            assert rows, f"{path.name} não produziu nenhuma linha"
            for row in rows:
                clans_encontrados.add(row["clan"])
                assert row["categoria"] in {
                    "Coach", "Coach Action", "Coach Pro", "Coach Hero",
                    "Sem Categoria", "Novos ULTIMATES",
                }
                assert row["raw_name"]
            total_linhas += len(rows)

        assert clans_encontrados == {f"CLÃ {n}" for n in range(1, 9)}
        assert total_linhas == 154


# ---------------------------------------------------------------------------
# CLI (render_report / parse_args)
# ---------------------------------------------------------------------------


class TestCli:

    def test_parse_args_default_e_dry_run(self):
        args = script.parse_args([])
        assert args.apply is False

    def test_parse_args_apply(self):
        args = script.parse_args(["--apply"])
        assert args.apply is True

    def test_render_report_dry_run_menciona_nada_foi_escrito(self):
        report = {"processados": 1, "inseridos": 1, "atualizados": 0, "inalterados": 0}
        texto = script.render_report(report, apply=False)
        assert "DRY-RUN" in texto
        assert "nada foi escrito" in texto

    def test_render_report_apply_nao_menciona_dry_run(self):
        report = {"processados": 1, "inseridos": 1, "atualizados": 0, "inalterados": 0}
        texto = script.render_report(report, apply=True)
        assert "APLICAÇÃO" in texto
        assert "DRY-RUN" not in texto
