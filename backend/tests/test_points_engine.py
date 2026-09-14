import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date

from points_engine import (
    compute_batch_promotions_by_people,
    build_record_data,
    sum_registros_pontos_from_date,
    build_totais_recalculo_plan,
)


def make_records(counts: list[int]) -> list[dict]:
    """Cria lista de registros com num_participantes para uso nos testes."""
    return [{"id": i + 1, "num_participantes": n} for i, n in enumerate(counts)]


class TestComputeBatchPromotionsByPeople:

    def test_sem_registros_sem_carry_over(self):
        ids, lotes, carry = compute_batch_promotions_by_people([], 0, 5)
        assert ids == []
        assert lotes == 0
        assert carry == 0

    def test_exatamente_um_lote(self):
        records = make_records([5])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 0

    def test_registro_com_mais_de_um_lote(self):
        records = make_records([10])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1]
        assert lotes == 2
        assert carry == 0

    def test_registro_com_sobra(self):
        # 6 pessoas → 1 lote + 1 em espera
        records = make_records([6])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 1

    def test_carry_over_completa_lote(self):
        # carry_over=1, novo registro com 4 → total 5 → 1 lote
        records = make_records([4])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 1, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 0

    def test_multiplos_registros_sem_lote_completo(self):
        # 2 + 2 = 4 pessoas → 0 lotes, todos ficam pendentes
        records = make_records([2, 2])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert ids == [1, 2]
        assert lotes == 0
        assert carry == 4

    def test_multiplos_registros_dois_lotes(self):
        # 3 + 4 + 3 = 10 → 2 lotes, carry=0
        records = make_records([3, 4, 3])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 0, 5)
        assert sorted(ids) == [1, 2, 3]
        assert lotes == 2
        assert carry == 0

    def test_carry_over_sem_registros_novos(self):
        # Apenas carry-over acumulado, sem registros pendentes
        ids, lotes, carry = compute_batch_promotions_by_people([], 5, 5)
        assert ids == []
        assert lotes == 1
        assert carry == 0

    def test_fallback_num_participantes_ausente(self):
        # Registro sem chave num_participantes usa default 1
        records = [{"id": 1}]
        ids, lotes, carry = compute_batch_promotions_by_people(records, 4, 5)
        assert ids == [1]
        assert lotes == 1
        assert carry == 0

    def test_sem_lote_completo_retorna_carry_acumulado(self):
        # carry=3 + 1 pessoa = 4 → 0 lotes, carry=4
        records = make_records([1])
        ids, lotes, carry = compute_batch_promotions_by_people(records, 3, 5)
        assert ids == [1]
        assert lotes == 0
        assert carry == 4


def _make_row_and_header():
    row = [
        "1",                       # col 0: clan
        "Coach A",                 # col 1: coach
        "", "", "",
        "Coaching Individual",     # col 5: modalidade
        "", "", "", "",
        "06/04/2026 13:58:38",     # col 10: data (col K)
        "HASH_KEY_123",            # col 11: chave
    ]
    header = [f"col_{i}" for i in range(len(row))]
    return row, header


def test_build_record_data_inclui_data_registro_quando_date_col_fornecido():
    row, header = _make_row_and_header()
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
        date_col=10,
    )
    assert result["data_registro"] == "2026-04-06"


def test_build_record_data_data_registro_none_quando_data_invalida():
    row, header = _make_row_and_header()
    row[10] = "data-invalida"
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
        date_col=10,
    )
    assert result["data_registro"] is None


def test_build_record_data_sem_data_registro_quando_date_col_none():
    row, header = _make_row_and_header()
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
    )
    assert "data_registro" not in result


def test_build_record_data_data_registro_none_quando_coluna_ausente():
    row = ["1", "Coach A", "", "", "", "Coaching Individual"]  # só 6 colunas
    header = [f"col_{i}" for i in range(len(row))]
    result = build_record_data(
        record_hash="abc123",
        row=row,
        header=header,
        modalidade_col=5,
        clan_col=0,
        coach_col=1,
        spreadsheet_id="sheet1",
        sheet_name="Sheet1",
        row_number=2,
        pontos=30,
        date_col=10,  # índice fora do range da row
    )
    assert result["data_registro"] is None


def _registro(clan, coach, pontos, pontos_coach, data_registro, modalidade="Coaching Individual"):
    return {
        "clan": clan, "coach": coach, "pontos": pontos, "pontos_coach": pontos_coach,
        "modalidade": modalidade, "data_registro": data_registro,
    }


class TestSumRegistrosPontosFromDate:
    """Correção retroativa não-destrutiva: soma `pontos`/`pontos_coach` de
    linhas já gravadas em `pontos_ultimate_registros_contabilizados`,
    filtrando por `data_registro >= start_date` — sem apagar/alterar nenhuma
    linha (a leitura é só-leitura; quem escreve é o chamador)."""

    CORTE = date(2026, 8, 1)

    def test_registro_pagante_apos_o_corte_conta_em_total_pagante(self):
        rows = [_registro("CLÃ 1", "Ana", 30, 30, "2026-08-15")]
        por_clan, por_coach = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {"CLÃ 1": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30}}
        assert por_coach == {"Ana": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30}}

    def test_registro_pro_bono_apos_o_corte_conta_em_total_pro_bono(self):
        rows = [_registro("CLÃ 1", "Ana", 10, 10, "2026-08-15", modalidade="Pro-bono")]
        por_clan, por_coach = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {"CLÃ 1": {"total_pagante": 0, "total_pro_bono": 10, "total_pontos": 10}}
        assert por_coach == {"Ana": {"total_pagante": 0, "total_pro_bono": 10, "total_pontos": 10}}

    def test_registro_anterior_ao_corte_e_ignorado(self):
        rows = [_registro("CLÃ 1", "Ana", 30, 30, "2026-07-31")]
        por_clan, por_coach = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {}
        assert por_coach == {}

    def test_registro_exatamente_no_corte_conta(self):
        rows = [_registro("CLÃ 1", "Ana", 30, 30, "2026-08-01")]
        por_clan, _ = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {"CLÃ 1": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30}}

    def test_soma_multiplos_registros_do_mesmo_cla_e_coach(self):
        rows = [
            _registro("CLÃ 1", "Ana", 30, 30, "2026-08-10"),
            _registro("CLÃ 1", "Ana", 30, 30, "2026-08-20"),
            _registro("CLÃ 1", "Ana", 10, 10, "2026-08-25", modalidade="Pro-bono"),
        ]
        por_clan, por_coach = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {"CLÃ 1": {"total_pagante": 60, "total_pro_bono": 10, "total_pontos": 70}}
        assert por_coach == {"Ana": {"total_pagante": 60, "total_pro_bono": 10, "total_pontos": 70}}

    def test_registro_sem_coach_ainda_conta_para_o_cla(self):
        rows = [_registro("CLÃ 1", "", 30, 0, "2026-08-10")]
        por_clan, por_coach = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {"CLÃ 1": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30}}
        assert por_coach == {}

    def test_data_registro_ausente_ou_invalida_e_incluida_por_seguranca(self):
        """Mesma política fail-open de `filter_records_by_date_from`: sem uma
        data confirmada anterior ao corte, não há motivo para excluir."""
        rows = [
            _registro("CLÃ 1", "Ana", 30, 30, None),
            _registro("CLÃ 2", "Bruno", 30, 30, "data-invalida"),
        ]
        por_clan, por_coach = sum_registros_pontos_from_date(rows, self.CORTE)
        assert por_clan == {
            "CLÃ 1": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30},
            "CLÃ 2": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30},
        }


class TestBuildTotaisRecalculoPlan:
    """Une a soma não-destrutiva (`sum_registros_pontos_from_date`) com a
    fatia de desafios (já calculada ao vivo, fora de escopo aqui) e os totais
    hoje persistidos, para o relatório antes/depois de
    `admin/recalcular_totais_data_inicio.py`. Pura — não lê nem escreve nada."""

    def test_calcula_delta_contra_o_total_existente(self):
        por_tipo = {"CLÃ 1": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30}}
        desafio = {"CLÃ 1": 100}
        existing = {"CLÃ 1": {"total_pontos": 200, "pessoas_em_espera": 2}}
        plan = build_totais_recalculo_plan(por_tipo, desafio, existing)
        assert plan == {
            "CLÃ 1": {
                "antigo": 200, "novo": 130, "delta": -70,
                "total_pagante": 30, "total_pro_bono": 0, "pessoas_em_espera": 2,
            }
        }

    def test_nome_so_em_desafios_ainda_aparece_no_plano(self):
        plan = build_totais_recalculo_plan({}, {"CLÃ 2": 50}, {})
        assert plan == {
            "CLÃ 2": {
                "antigo": 0, "novo": 50, "delta": 50,
                "total_pagante": 0, "total_pro_bono": 0, "pessoas_em_espera": 0,
            }
        }

    def test_nome_so_em_existing_sem_nenhuma_contribuicao_nova_zera(self):
        existing = {"CLÃ 3": {"total_pontos": 90, "pessoas_em_espera": 0}}
        plan = build_totais_recalculo_plan({}, {}, existing)
        assert plan == {
            "CLÃ 3": {
                "antigo": 90, "novo": 0, "delta": -90,
                "total_pagante": 0, "total_pro_bono": 0, "pessoas_em_espera": 0,
            }
        }

    def test_sem_mudanca_delta_e_zero(self):
        por_tipo = {"CLÃ 1": {"total_pagante": 30, "total_pro_bono": 0, "total_pontos": 30}}
        existing = {"CLÃ 1": {"total_pontos": 30, "pessoas_em_espera": 0}}
        plan = build_totais_recalculo_plan(por_tipo, {}, existing)
        assert plan["CLÃ 1"]["delta"] == 0
