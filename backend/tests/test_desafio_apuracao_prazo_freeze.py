"""`_calcular_apuracao_atual_desafio` deve congelar a apuração por percentual
no `prazo_apuracao` do desafio (issue #43): submissões cuja data de
calendário local (América/São_Paulo) é posterior à data local do prazo não
contam, mesmo que `active_counted` e aprovadas — nem na prévia
(`get_desafio_apuracao`, provisorio) nem no fechamento
(`reapurar_desafio_e_aplicar_delta`), já que ambos chamam a mesma função.

O corte é por DIA de calendário local, não pelo instante exato do
`prazo_apuracao`: `prazo_apuracao` costuma carregar um horário sem
significado de negócio (ex.: hora em que o registro foi criado/importado,
não um deadline real dentro do dia) — comparar o instante exato excluiria
submissões legítimas feitas mais tarde no mesmo dia do prazo. Mesma
convenção de data local já usada em `get_period_desafio_totals`/
`_submitted_at_local_date` para o eixo coach.

Sem prazo definido (`prazo_apuracao is None`), o comportamento não muda:
todas as submissões `active_counted` elegíveis contam, sem corte de data.
"""

import os
import sys
from unittest.mock import patch

os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
os.environ.setdefault("GSHEET_RECORDS_SPREADSHEET_ID", "test-records")
os.environ.setdefault("GSHEET_RECORDS_SHEET_NAME", "Records")
os.environ.setdefault("GSHEET_TOTALS_SPREADSHEET_ID", "test-totals")
os.environ.setdefault("GSHEET_TOTALS_SHEET_NAME", "Totals")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import supabase_client


DESAFIO_ID = 18
# Horário sem significado de negócio (08:38 em América/São_Paulo) — só a
# data (31/08) importa para o corte.
PRAZO = "2026-08-31T11:38:00+00:00"

COACH_CLAS = [
    {"coach_canonico": "Ana", "clan": "CLÃ 1"},
    {"coach_canonico": "Bruno", "clan": "CLÃ 1"},
]


def _sub(token, coach, submitted_at, clan="CLÃ 1", desafio_id=DESAFIO_ID):
    return {
        "token": token,
        "desafio_id": desafio_id,
        "raw_name": coach,
        "clan": clan,
        "status": "active_counted",
        "submitted_at": submitted_at,
    }


def _run(desafio, submissoes):
    # `side_effect` (em vez de `return_value`) espelha o contrato real de
    # `fetch_active_counted_desafio_submissions`: quando chamada com
    # `desafio_id`, filtra no servidor — `_calcular_apuracao_atual_desafio`
    # não filtra mais em Python.
    def _fetch(desafio_id=None):
        if desafio_id is None:
            return submissoes
        return [s for s in submissoes if s.get("desafio_id") == desafio_id]

    with patch("supabase_client.get_desafio", return_value=desafio), \
         patch("supabase_client.fetch_active_counted_desafio_submissions", side_effect=_fetch), \
         patch("supabase_client.list_submissoes_revisoes", return_value={}), \
         patch("supabase_client.get_coach_alias_map", return_value={}), \
         patch("supabase_client.list_coach_clas", return_value=COACH_CLAS):
        return supabase_client._calcular_apuracao_atual_desafio(desafio["id"])


class TestFreezePorDiaDeCalendarioLocal:

    def test_submissao_antes_do_dia_do_prazo_conta(self):
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [_sub("T1", "Ana", "2026-08-20T10:00:00+00:00")]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 1

    def test_submissao_no_mes_seguinte_nao_conta(self):
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [_sub("T1", "Ana", "2026-09-10T10:00:00+00:00")]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 0

    def test_submissao_exatamente_no_instante_do_prazo_conta(self):
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [_sub("T1", "Ana", PRAZO)]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 1

    def test_submissao_depois_do_instante_mas_no_mesmo_dia_local_conta(self):
        """PRAZO é 08:38 em São Paulo — uma submissão às 20:46 UTC do mesmo
        31/08 (17:46 local) é depois do instante exato, mas ainda dentro do
        dia do prazo: deve contar (issue real encontrada em produção: 15
        submissões legítimas de 31/08 à tarde/noite estavam sendo excluídas
        pelo corte por instante exato)."""
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [_sub("T1", "Ana", "2026-08-31T20:46:38+00:00")]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 1

    def test_submissao_que_vira_o_dia_em_utc_mas_ainda_31_08_local_conta(self):
        """00:11 UTC de 01/09 é 21:11 de 31/08 em São Paulo (UTC-3) — ainda
        dentro do dia do prazo pela data de calendário local."""
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [_sub("T1", "Ana", "2026-09-01T00:11:53+00:00")]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 1

    def test_submissao_de_fato_no_dia_seguinte_local_nao_conta(self):
        """05:10 UTC de 01/09 é 02:10 de 01/09 em São Paulo — já é o dia
        seguinte ao prazo, não conta."""
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [_sub("T1", "Ana", "2026-09-01T05:10:53+00:00")]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 0

    def test_mistura_dentro_e_fora_do_dia_do_prazo_so_conta_as_de_dentro(self):
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": PRAZO}
        submissoes = [
            _sub("T1", "Ana", "2026-08-31T20:46:38+00:00"),
            _sub("T2", "Bruno", "2026-09-10T10:00:00+00:00"),
        ]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 1

    def test_sem_prazo_definido_conta_tudo_sem_corte(self):
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": None}
        submissoes = [
            _sub("T1", "Ana", "2026-08-20T10:00:00+00:00"),
            _sub("T2", "Bruno", "2026-09-10T10:00:00+00:00"),
        ]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 2


class TestSemTruncamentoPorPaginacao:
    """`_calcular_apuracao_atual_desafio` deve considerar TODAS as submissões
    `active_counted` do desafio, não só as 100 mais recentes. A busca antiga
    (`list_desafio_submissions_current`, sem `limit` explícito) é uma função
    de auditoria paginada com `limit=100` por padrão — um desafio com mais de
    100 submissões tinha as mais antigas descartadas silenciosamente (issue
    real: "Desafio Pontual A" com 131 submissões perdia participantes em
    todos os clãs, ex.: clã 4 caía de 20 para 13 participantes)."""

    def test_desafio_com_mais_de_100_submissoes_conta_todas(self):
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": None}
        submissoes = [
            _sub(f"T{i}", f"Coach {i}", "2026-08-20T10:00:00+00:00") for i in range(150)
        ]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 150

    def test_submissoes_de_outro_desafio_no_mesmo_fetch_nao_contam(self):
        """`_calcular_apuracao_atual_desafio` precisa passar `desafio_id` para
        `fetch_active_counted_desafio_submissions` (que agora filtra no
        servidor) — sem isso, submissões de outros desafios vazariam para
        cá."""
        desafio = {"id": DESAFIO_ID, "prazo_apuracao": None}
        submissoes = [
            _sub("T1", "Ana", "2026-08-20T10:00:00+00:00", desafio_id=DESAFIO_ID),
            _sub("T2", "Bruno", "2026-08-20T10:00:00+00:00", desafio_id=DESAFIO_ID + 1),
        ]
        result = _run(desafio, submissoes)
        assert result["CLÃ 1"].participantes == 1
