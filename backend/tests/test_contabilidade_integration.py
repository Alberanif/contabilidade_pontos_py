import pytest
import sys
import os
from unittest.mock import patch, MagicMock

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import points_engine
from fastapi import HTTPException
from desafio_sync_service import DesafioSyncResult
from routers.contabilidade import (
    ConfirmarDesafiosRequest,
    confirmar_desafios,
    executar_contabilidade,
)


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


def _desafios_ok(**overrides) -> DesafioSyncResult:
    base = dict(status="success", run_id=1, tokens_versioned=2, mensagem="ok")
    base.update(overrides)
    return DesafioSyncResult(**base)


class TestExecutarIncluiDesafiosIsolado:
    """`/executar` ganha o campo `desafios`, mas a fonte é isolada: uma falha
    de um lado nunca contamina (nem bloqueia) o outro."""

    def test_sucesso_de_desafios_aparece_na_resposta(self):
        with patch("google_sheets_client.fetch_records", return_value=[]), \
             patch(
                 "desafio_sync_service.sync_desafios",
                 return_value=_desafios_ok(),
             ) as mock_sync:
            response = executar_contabilidade()

        assert response.desafios.status == "success"
        assert response.desafios.tokens_versioned == 2
        assert response.novos_registros == 0
        mock_sync.assert_called_once_with()

    def test_falha_em_desafios_nao_impede_as_demais_fontes(self):
        """Se `sync_desafios` lançar (não deveria, mas é o cenário de
        isolamento final), `/executar` continua respondendo normalmente para
        as demais fontes em vez de virar um 500 geral."""
        with patch("google_sheets_client.fetch_records", return_value=[]), \
             patch(
                 "desafio_sync_service.sync_desafios",
                 side_effect=RuntimeError("boom"),
             ):
            response = executar_contabilidade()

        assert response.desafios.status == "failed"
        assert "boom" in response.desafios.mensagem
        assert response.novos_registros == 0
        assert response.mensagem == "Nenhum dado encontrado na planilha de registros."

    def test_falha_das_demais_fontes_nao_impede_nem_duplica_desafios(self):
        """Se a planilha principal falhar (500 pelo handler já existente), a
        sincronização de desafios já deve ter sido concluída (exatamente uma
        vez) antes disso — nunca parcialmente, nunca duas vezes."""
        with patch(
            "google_sheets_client.fetch_records",
            side_effect=RuntimeError("planilha principal indisponível"),
        ), patch(
            "desafio_sync_service.sync_desafios", return_value=_desafios_ok()
        ) as mock_sync:
            with pytest.raises(HTTPException) as exc_info:
                executar_contabilidade()

        assert exc_info.value.status_code == 500
        mock_sync.assert_called_once_with()


class TestConfirmarDesafiosEndpoint:
    """O endpoint de confirmação nunca aceita plano/deltas do cliente: só
    repassa o hash mostrado na prévia e o consentimento de remoção em massa,
    e a fachada recalcula o plano de verdade a partir do estado atual."""

    def test_delega_hash_e_confirmacao_de_remocao_em_massa(self):
        with patch(
            "desafio_sync_service.sync_desafios",
            return_value=_desafios_ok(status="success"),
        ) as mock_sync, patch(
            "routers.contabilidade._refresh_desafio_coach_totals"
        ):
            result = confirmar_desafios(
                ConfirmarDesafiosRequest(
                    snapshot_hash="hash-abc",
                    confirmar_remocao_em_massa=True,
                )
            )

        mock_sync.assert_called_once_with(
            confirm_snapshot_hash="hash-abc", confirm_mass_removal=True
        )
        assert result.status == "success"

    def test_confirmacao_padrao_nao_aceita_remocao_em_massa_implicitamente(self):
        with patch(
            "desafio_sync_service.sync_desafios",
            return_value=_desafios_ok(status="awaiting_confirmation"),
        ) as mock_sync:
            confirmar_desafios(ConfirmarDesafiosRequest(snapshot_hash="hash-abc"))

        mock_sync.assert_called_once_with(
            confirm_snapshot_hash="hash-abc", confirm_mass_removal=False
        )

    def test_erro_inesperado_vira_500_e_nao_propaga_cru(self):
        with patch(
            "desafio_sync_service.sync_desafios",
            side_effect=RuntimeError("falha inesperada"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                confirmar_desafios(ConfirmarDesafiosRequest(snapshot_hash="hash-abc"))

        assert exc_info.value.status_code == 500
