"""API somente-leitura de auditoria de desafios (issue #18).

Substitui por completo os antigos `listar_desafios`/`listar_registros` de
`routers/desafios.py` (issue #17 já bloqueou toda escrita legada; issue #18
troca a leitura pelo contrato orientado a auditoria abaixo — desafios,
submissões (tokens) e execuções de sincronização da Google Sheet).

Nenhum handler deste router escreve no banco — só consultas via
`supabase_client`.

Ordem das rotas: os segmentos literais (`/sincronizacoes`, `/submissoes/...`)
são registrados antes dos genéricos (`/{desafio_id}`, `/{desafio_id}/...`)
para que não haja ambiguidade de shadowing entre eles — reforçado também pelo
conversor `:int` explícito em `{desafio_id:int}`/`{run_id:int}` (sintaxe de
path do Starlette, não só a tipagem do parâmetro Python), que faz o roteador
pular a rota — em vez de só falhar a validação com 422 — quando o segmento
não é um inteiro (ex.: "sincronizacoes")."""

from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import coach_identity
import supabase_client

router = APIRouter()


# --- Schemas ---


class DesafioResponse(BaseModel):
    id: int
    nome: str
    contabilizar_pontos: bool
    data: date | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    prazo_apuracao: datetime | None = None
    apurado_em: datetime | None = None
    origem: str
    nome_normalizado: str | None = None
    status: str
    arquivado_at: datetime | None = None
    reativado_at: datetime | None = None
    updated_at: datetime
    created_at: datetime


class DesafioDetailResponse(DesafioResponse):
    pontos_por_clan: dict[str, int] = {}
    pontos_por_coach: dict[str, int] = {}


class SetDesafioPrazoRequest(BaseModel):
    prazo_apuracao: datetime | None = None


class RevisarSubmissaoRequest(BaseModel):
    status: Literal["aprovado", "reprovado", "pendente"]
    revisado_por: str | None = None


class ClanApuracaoEntry(BaseModel):
    clan: str
    participantes: int
    total_grupo: int
    percentual: float
    pontos: int


class DesafioApuracaoResponse(BaseModel):
    desafio_id: int
    prazo_apuracao: datetime | None = None
    apurado_em: datetime | None = None
    provisorio: bool
    clas: list[ClanApuracaoEntry] = []


class DesafioSubmissionResponse(BaseModel):
    token: str
    row_numbers: list[int] = []
    raw_cells: list[Any] = []
    raw_clan_legacy: str | None = None
    raw_name: str | None = None
    coach: str | None = None
    raw_validation: str | None = None
    raw_link: str | None = None
    raw_observation: str | None = None
    raw_challenge: str | None = None
    raw_clan_current: str | None = None
    raw_submitted_at: str | None = None
    raw_token: str | None = None
    clan: str | None = None
    challenge_normalized: str | None = None
    desafio_id: int | None = None
    submitted_at: datetime | None = None
    status: str
    revisao_status: str = "pendente"
    revisado_por: str | None = None
    revisado_em: datetime | None = None
    invalid_reasons: list[str] = []
    points: int = 0
    content_hash: str
    first_seen_run_id: int
    last_seen_run_id: int
    inactivated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DesafioSubmissionVersionResponse(BaseModel):
    id: int
    token: str
    sync_run_id: int
    version_number: int
    row_numbers: list[int] = []
    raw_cells: list[Any] = []
    raw_clan_legacy: str | None = None
    raw_name: str | None = None
    coach: str | None = None
    raw_validation: str | None = None
    raw_link: str | None = None
    raw_observation: str | None = None
    raw_challenge: str | None = None
    raw_clan_current: str | None = None
    raw_submitted_at: str | None = None
    raw_token: str | None = None
    previous_state: dict[str, Any] | None = None
    current_state: dict[str, Any]
    previous_status: str | None = None
    current_status: str
    point_delta: int = 0
    clan_deltas: dict[str, int] = {}
    change_reason: str
    observed_at: datetime


class DesafioSyncRunResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    snapshot_hash: str | None = None
    sheet_row_count: int = 0
    state_counts: dict[str, int] = {}
    clan_deltas: dict[str, int] = {}
    challenges_created: int = 0
    challenges_archived: int = 0
    challenges_reactivated: int = 0
    points_per_submission: int
    mass_removal_required: bool = False
    mass_removal_confirmed: bool = False
    mass_removal_count: int = 0
    error: dict[str, Any] | None = None
    created_at: datetime


# --- Status da API (inglês) -> status do banco (português) ---

_STATUS_PARA_BANCO = {"active": "ativo", "archived": "arquivado"}


def _status_filtro_banco(status: Literal["active", "archived", "all"]) -> str | None:
    """Mapeia o `status` da API (inglês) para o valor gravado no banco
    (português) — `all` não filtra."""
    if status == "all":
        return None
    return _STATUS_PARA_BANCO[status]


def _com_coach(row: dict, alias_map: dict[str, str], revisoes_map: dict[str, dict] | None = None) -> dict:
    """Injeta `coach` (nome canônico da coluna B) e dados de revisão manual na
    linha de submissão/versão. Quando `revisoes_map` é dado (linhas de
    submissão — não de histórico de versão, que não tem esse parâmetro),
    também substitui `points` pelo valor individual do coach para aquela
    linha (`supabase_client.desafio_submission_pontos_individuais_coach`),
    já que o `points` gravado é a taxa de clã, não a do coach."""
    nome = (row.get("raw_name") or "").strip()
    row["coach"] = coach_identity.resolve_coach(nome, alias_map) if nome else None
    token = row.get("token")
    if token and revisoes_map is not None:
        rev = revisoes_map.get(token, {})
        revisao_status = rev.get("status", "pendente")
        row["revisao_status"] = revisao_status
        row["revisado_por"] = rev.get("revisado_por")
        row["revisado_em"] = rev.get("revisado_em")
        row["points"] = supabase_client.desafio_submission_pontos_individuais_coach(
            row.get("status"), row.get("submitted_at"), revisao_status
        )
    return row


# --- Rotas: desafios ---


@router.get("", response_model=list[DesafioResponse])
def listar_desafios(
    status: Literal["active", "archived", "all"] = Query("all"),
):
    """Lista desafios, opcionalmente filtrados por status (`active`/`archived`;
    `all` não filtra)."""
    return supabase_client.list_desafios(status=_status_filtro_banco(status))


# --- Rotas: sincronizações (literais antes de /{desafio_id}) ---


@router.get("/sincronizacoes", response_model=list[DesafioSyncRunResponse])
def listar_sincronizacoes(limit: int = 50, offset: int = 0):
    """Lista execuções de sincronização da Google Sheet, mais recente primeiro."""
    return supabase_client.list_desafio_sync_runs(limit=limit, offset=offset)


@router.get("/sincronizacoes/{run_id:int}", response_model=DesafioSyncRunResponse)
def obter_sincronizacao(run_id: int):
    """Detalha uma execução de sincronização específica."""
    execucao = supabase_client.get_desafio_sync_run(run_id)
    if not execucao:
        raise HTTPException(status_code=404, detail="Execução de sincronização não encontrada")
    return execucao


# --- Rotas: submissões (literais antes de /{desafio_id}/...) ---


@router.get("/submissoes/{token}", response_model=DesafioSubmissionResponse)
def obter_submissao(token: str):
    """Detalha o estado atual de um token de submissão."""
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    revisoes = supabase_client.list_submissoes_revisoes()
    return _com_coach(submissao, supabase_client.get_coach_alias_map(), revisoes)


@router.post("/submissoes/{token}/revisar")
def revisar_submissao(token: str, req: RevisarSubmissaoRequest):
    """Aprova ou reprova uma submissão individual. Se o desafio dessa
    submissão já estiver apurado (`apurado_em` não nulo), reabre e refecha a
    apuração daquele desafio na mesma chamada (`reapurar_desafio_e_aplicar_delta`)
    — reprovar/desfazer depois de apurado não fica congelado."""
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    resultado = supabase_client.revisar_submissao(
        token=token, status=req.status, revisado_por=req.revisado_por
    )
    desafio_id = submissao.get("desafio_id")
    if desafio_id is not None:
        desafio = supabase_client.get_desafio(desafio_id)
        if desafio and desafio.get("apurado_em"):
            supabase_client.reapurar_desafio_e_aplicar_delta(desafio_id)
    return resultado


@router.get(
    "/submissoes/{token}/versoes",
    response_model=list[DesafioSubmissionVersionResponse],
)
def listar_versoes_submissao(token: str):
    """Lista o histórico imutável de versões de um token."""
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    alias_map = supabase_client.get_coach_alias_map()
    return [
        _com_coach(v, alias_map)
        for v in supabase_client.list_desafio_submission_versions(token)
    ]


# --- Rotas genéricas: /{desafio_id}... (registradas por último) ---


@router.get("/{desafio_id:int}", response_model=DesafioDetailResponse)
def obter_desafio(desafio_id: int):
    """Detalha um desafio, incluindo o total de pontos contabilizados por clã."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return {
        **desafio,
        "pontos_por_clan": supabase_client.get_desafio_clan_totals(desafio_id),
        "pontos_por_coach": supabase_client.get_desafio_coach_totals(desafio_id),
    }


@router.patch("/{desafio_id:int}/prazo", response_model=DesafioResponse)
def definir_prazo_desafio(desafio_id: int, req: SetDesafioPrazoRequest):
    """Define ou altera o prazo de apuração de um desafio."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return supabase_client.set_desafio_prazo(desafio_id=desafio_id, prazo=req.prazo_apuracao)


@router.get("/{desafio_id:int}/apuracao", response_model=DesafioApuracaoResponse)
def obter_apuracao_desafio(desafio_id: int):
    """Retorna o estado de apuração do desafio (resultado final se apurado, prévia se em andamento)."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    return supabase_client.get_desafio_apuracao(desafio_id)


@router.get("/{desafio_id:int}/submissoes", response_model=list[DesafioSubmissionResponse])
def listar_submissoes_do_desafio(
    desafio_id: int,
    clan: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Lista as submissões (tokens) associadas a um desafio."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    alias_map = supabase_client.get_coach_alias_map()
    revisoes_map = supabase_client.list_submissoes_revisoes(desafio_id)
    return [
        _com_coach(s, alias_map, revisoes_map)
        for s in supabase_client.list_desafio_submissions_current(
            desafio_id=desafio_id, clan=clan, status=status, limit=limit, offset=offset
        )
    ]
