import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from points_engine import compute_batch_promotions_by_people


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


from points_engine import build_record_data


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
