import sys, os, io, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from routers.desafio_import import preview, confirmar

MAPPING = {
    "clan": "clã",
    "nome": "nome",
    "validado": "validado",
    "submitted_at": "data",
    "token": "token",
}

CSV_CONTENT = (
    "clã,nome,validado,data,token\n"
    "1,Ana Albertim,Sim,20/05/2026 10:00:00,T1\n"
    "1,Vini Marini,Sim,21/05/2026 10:00:00,T2\n"
).encode("utf-8")

CSV_CONTENT_SINGLE = (
    "clã,nome,validado,data,token\n"
    "1,Ana Albertim,Sim,20/05/2026 10:00:00,T1\n"
).encode("utf-8")


class _FakeUploadFile:
    def __init__(self, content: bytes):
        self.file = io.BytesIO(content)


def _config(desafio_id=None):
    return json.dumps({
        "nome": "Desafio Teste",
        "desafio_id": desafio_id,
        "data_inicio": "2026-05-11",
        "data_fim": "2026-06-30",
        "pontos_por_participacao": 10,
    })


class TestPreviewIncluiCoach:

    def test_preview_retorna_pontos_e_participacoes_por_coach(self):
        with patch("google_sheets_client.fetch_ranking", return_value=[{"clan": "CLÃ 1"}]), \
             patch("supabase_client.get_tokens_importados", return_value=set()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}):
            result = preview(
                file=_FakeUploadFile(CSV_CONTENT),
                mapping=json.dumps(MAPPING),
                config=_config(),
            )
        assert result["pontos_por_coach"] == {"Ana Albertim": 10, "Vinicius Marini": 10}
        assert result["participacoes_por_coach"] == {"Ana Albertim": 1, "Vinicius Marini": 1}


class TestConfirmarPersisteRegistrosDeCoach:

    def test_cria_registro_de_coach_novo_e_soma_delta(self):
        desafio_criado = {"id": 42, "nome": "Desafio Teste", "origem": "csv_import"}
        campos = [
            {"id": 1, "nome": "Participações Validadas", "tipo": "texto", "ordem": 0},
            {"id": 2, "nome": "Pontuação", "tipo": "pontuacao", "ordem": 1},
        ]
        with patch("google_sheets_client.fetch_ranking", return_value=[{"clan": "CLÃ 1"}]), \
             patch("supabase_client.get_tokens_importados", return_value=set()), \
             patch("supabase_client.get_coach_alias_map",
                   return_value={"Vini Marini": "Vinicius Marini"}), \
             patch("supabase_client.create_desafio", return_value=desafio_criado), \
             patch("supabase_client.insert_desafio_campos", return_value=campos), \
             patch("supabase_client.insert_desafio_importacao_linhas", return_value=[]), \
             patch("supabase_client.get_desafio_registro_by_clan", return_value=None), \
             patch("supabase_client.create_desafio_registro", return_value={}), \
             patch("supabase_client.add_delta_to_clan_total", return_value={}), \
             patch("supabase_client.get_desafio_registro_coach_by_coach", return_value=None), \
             patch("supabase_client.create_desafio_registro_coach", return_value={}) as mock_create_coach, \
             patch("supabase_client.add_delta_to_coach_total", return_value={}) as mock_delta_coach, \
             patch("supabase_client.list_desafio_campos", return_value=campos), \
             patch("supabase_client.list_desafio_registros", return_value=[]), \
             patch("supabase_client.get_desafio", return_value=desafio_criado):
            confirmar(
                file=_FakeUploadFile(CSV_CONTENT),
                mapping=json.dumps(MAPPING),
                config=_config(),
            )

        mock_create_coach.assert_any_call(42, "Ana Albertim", {"1": "1", "2": 10}, 10)
        mock_create_coach.assert_any_call(42, "Vinicius Marini", {"1": "1", "2": 10}, 10)
        mock_delta_coach.assert_any_call("Ana Albertim", 10)
        mock_delta_coach.assert_any_call("Vinicius Marini", 10)

    def test_atualiza_registro_de_coach_existente_e_aplica_delta(self):
        desafio_existente = {"id": 42, "nome": "Desafio Teste", "origem": "csv_import"}
        campos = [
            {"id": 1, "nome": "Participações Validadas", "tipo": "texto", "ordem": 0},
            {"id": 2, "nome": "Pontuação", "tipo": "pontuacao", "ordem": 1},
        ]
        existente_coach = {"id": 7, "coach": "Ana Albertim", "valores": {"1": "0", "2": 0}, "total_pontos": 0}
        with patch("google_sheets_client.fetch_ranking", return_value=[{"clan": "CLÃ 1"}]), \
             patch("supabase_client.get_tokens_importados", return_value=set()), \
             patch("supabase_client.get_coach_alias_map", return_value={}), \
             patch("supabase_client.get_desafio", return_value=desafio_existente), \
             patch("supabase_client.update_desafio_periodo_e_pontos", return_value=None), \
             patch("supabase_client.list_desafio_campos", return_value=campos), \
             patch("supabase_client.insert_desafio_importacao_linhas", return_value=[]), \
             patch("supabase_client.get_desafio_registro_by_clan", return_value=None), \
             patch("supabase_client.create_desafio_registro", return_value={}), \
             patch("supabase_client.add_delta_to_clan_total", return_value={}), \
             patch("supabase_client.get_desafio_registro_coach_by_coach", return_value=existente_coach), \
             patch("supabase_client.update_desafio_registro_coach_pontos", return_value={}) as mock_update_coach, \
             patch("supabase_client.add_delta_to_coach_total", return_value={}) as mock_delta_coach, \
             patch("supabase_client.list_desafio_registros", return_value=[]):
            confirmar(
                file=_FakeUploadFile(CSV_CONTENT_SINGLE),
                mapping=json.dumps(MAPPING),
                config=_config(desafio_id=42),
            )

        mock_update_coach.assert_any_call(7, {"1": "1", "2": 10}, 10)
        mock_delta_coach.assert_any_call("Ana Albertim", 10)
