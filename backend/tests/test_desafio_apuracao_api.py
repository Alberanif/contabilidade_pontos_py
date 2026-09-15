"""Testes unitários dos endpoints de API de apuração, prazo e revisão de desafios."""

from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_definir_prazo_desafio_success():
    with patch("supabase_client.get_desafio") as mock_get, \
         patch("supabase_client.set_desafio_prazo") as mock_set:
        mock_get.return_value = {"id": 42, "nome": "Desafio Teste"}
        mock_set.return_value = {
            "id": 42,
            "nome": "Desafio Teste",
            "contabilizar_pontos": True,
            "origem": "sheet",
            "status": "ativo",
            "prazo_apuracao": "2026-09-30T23:59:59+00:00",
            "created_at": "2026-09-11T00:00:00+00:00",
            "updated_at": "2026-09-11T00:00:00+00:00",
        }

        response = client.patch(
            "/api/desafios/42/prazo",
            json={"prazo_apuracao": "2026-09-30T23:59:59+00:00"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 42
        assert data["prazo_apuracao"].startswith("2026-09-30T23:59:59")


def test_definir_prazo_desafio_not_found():
    with patch("supabase_client.get_desafio") as mock_get:
        mock_get.return_value = None

        response = client.patch(
            "/api/desafios/999/prazo",
            json={"prazo_apuracao": "2026-09-30T23:59:59+00:00"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Desafio não encontrado"


def test_revisar_submissao_success():
    with patch("supabase_client.get_desafio_submission_current") as mock_get, \
         patch("supabase_client.revisar_submissao") as mock_rev:
        mock_get.return_value = {"token": "token_abc123"}
        mock_rev.return_value = {
            "token": "token_abc123",
            "status": "aprovado",
            "revisado_por": "admin@igt.com",
            "revisado_em": "2026-09-11T01:00:00+00:00",
        }

        response = client.post(
            "/api/desafios/submissoes/token_abc123/revisar",
            json={"status": "aprovado", "revisado_por": "admin@igt.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["token"] == "token_abc123"
        assert data["status"] == "aprovado"


def test_revisar_submissao_desafio_ja_apurado_dispara_reapuracao():
    with patch("supabase_client.get_desafio_submission_current") as mock_get_sub, \
         patch("supabase_client.revisar_submissao") as mock_rev, \
         patch("supabase_client.get_desafio") as mock_get_desafio, \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_get_sub.return_value = {"token": "tok1", "desafio_id": 7}
        mock_rev.return_value = {"token": "tok1", "status": "reprovado"}
        mock_get_desafio.return_value = {"id": 7, "apurado_em": "2026-09-01T00:00:00+00:00"}

        response = client.post(
            "/api/desafios/submissoes/tok1/revisar", json={"status": "reprovado"}
        )

        assert response.status_code == 200
        mock_reapurar.assert_called_once_with(7)


def test_revisar_submissao_desafio_nao_apurado_nao_dispara_reapuracao():
    with patch("supabase_client.get_desafio_submission_current") as mock_get_sub, \
         patch("supabase_client.revisar_submissao") as mock_rev, \
         patch("supabase_client.get_desafio") as mock_get_desafio, \
         patch("supabase_client.reapurar_desafio_e_aplicar_delta") as mock_reapurar:
        mock_get_sub.return_value = {"token": "tok1", "desafio_id": 7}
        mock_rev.return_value = {"token": "tok1", "status": "reprovado"}
        mock_get_desafio.return_value = {"id": 7, "apurado_em": None}

        response = client.post(
            "/api/desafios/submissoes/tok1/revisar", json={"status": "reprovado"}
        )

        assert response.status_code == 200
        mock_reapurar.assert_not_called()


def test_obter_apuracao_desafio():
    with patch("supabase_client.get_desafio") as mock_get, \
         patch("supabase_client.get_desafio_apuracao") as mock_ap:
        mock_get.return_value = {"id": 10, "nome": "Desafio 10"}
        mock_ap.return_value = {
            "desafio_id": 10,
            "prazo_apuracao": "2026-09-30T23:59:59+00:00",
            "apurado_em": None,
            "provisorio": True,
            "clas": [
                {"clan": "CLÃ 1", "participantes": 5, "total_grupo": 10, "percentual": 50.0, "pontos": 500}
            ],
        }

        response = client.get("/api/desafios/10/apuracao")

        assert response.status_code == 200
        data = response.json()
        assert data["desafio_id"] == 10
        assert data["provisorio"] is True
        assert len(data["clas"]) == 1
        assert data["clas"][0]["clan"] == "CLÃ 1"
        assert data["clas"][0]["pontos"] == 500
