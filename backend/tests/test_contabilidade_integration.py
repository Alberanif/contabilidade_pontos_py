import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import points_engine


class TestFluxoAprovacaoCompleto:
    """Testa a composição de compute_batch_promotions_by_people com cenários reais."""

    def test_cenario_usuario_6_pessoas(self):
        """CLÃ 5 tem 1 registro com 6 pessoas. Deve ganhar 30 pts, 1 em espera."""
        pending = [{"id": 1, "num_participantes": 6}]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 0, 5)
        assert lotes == 1
        assert carry == 1
        assert ids == [1]

    def test_cenario_usuario_6_mais_4_pessoas(self):
        """Depois do cenário anterior (carry=1), novo registro com 4 pessoas.
        Total: 1 + 4 = 5. Deve ganhar mais 30 pts, carry=0."""
        pending = [{"id": 2, "num_participantes": 4}]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 1, 5)
        assert lotes == 1
        assert carry == 0
        assert ids == [2]

    def test_cenario_multiplos_registros_acumulados(self):
        """3 registros: 2 + 2 + 3 pessoas = 7. Carry inicial 0.
        Resultado: 1 lote (5 pts), carry=2."""
        pending = [
            {"id": 1, "num_participantes": 2},
            {"id": 2, "num_participantes": 2},
            {"id": 3, "num_participantes": 3},
        ]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 0, 5)
        assert lotes == 1
        assert carry == 2
        assert sorted(ids) == [1, 2, 3]

    def test_cenario_sem_lote_completo_nao_promove(self):
        """4 pessoas no total. Nenhum lote completo. IDs ainda são retornados
        (chamador decide não promover quando n_lotes == 0)."""
        pending = [{"id": 1, "num_participantes": 4}]
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(pending, 0, 5)
        assert lotes == 0
        assert carry == 4
        assert ids == [1]  # IDs retornados mas não devem ser promovidos (n_lotes == 0)

    def test_cenario_carry_over_acumulado_varios_ciclos(self):
        """Simula 3 ciclos: carry cresce até completar lote."""
        # Ciclo 1: 3 pessoas, carry=0 → carry=3
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(
            [{"id": 1, "num_participantes": 3}], 0, 5
        )
        assert lotes == 0
        assert carry == 3

        # Ciclo 2: 1 pessoa, carry=3 → carry=4
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(
            [{"id": 2, "num_participantes": 1}], carry, 5
        )
        assert lotes == 0
        assert carry == 4

        # Ciclo 3: 3 pessoas, carry=4 → total=7 → 1 lote, carry=2
        ids, lotes, carry = points_engine.compute_batch_promotions_by_people(
            [{"id": 3, "num_participantes": 3}], carry, 5
        )
        assert lotes == 1
        assert carry == 2
