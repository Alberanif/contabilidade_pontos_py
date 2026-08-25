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
    origem: str
    nome_normalizado: str | None = None
    status: str
    arquivado_at: datetime | None = None
    reativado_at: datetime | None = None
    updated_at: datetime
    created_at: datetime


class DesafioDetailResponse(DesafioResponse):
    pontos_por_clan: dict[str, int] = {}


class DesafioSubmissionResponse(BaseModel):
    token: str
    row_numbers: list[int] = []
    raw_cells: list[Any] = []
    raw_clan_legacy: str | None = None
    raw_name: str | None = None
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
    return submissao


@router.get(
    "/submissoes/{token}/versoes",
    response_model=list[DesafioSubmissionVersionResponse],
)
def listar_versoes_submissao(token: str):
    """Lista o histórico imutável de versões de um token. Um token existente
    sem nenhuma versão retorna lista vazia (não é 404) — 404 é reservado para
    token desconhecido."""
    submissao = supabase_client.get_desafio_submission_current(token)
    if not submissao:
        raise HTTPException(status_code=404, detail="Token de submissão não encontrado")
    return supabase_client.list_desafio_submission_versions(token)


# --- Rotas genéricas: /{desafio_id}... (registradas por último) ---


@router.get("/{desafio_id:int}", response_model=DesafioDetailResponse)
def obter_desafio(desafio_id: int):
    """Detalha um desafio, incluindo o total de pontos contabilizados por clã."""
    desafio = supabase_client.get_desafio(desafio_id)
    if not desafio:
        raise HTTPException(status_code=404, detail="Desafio não encontrado")
    pontos_por_clan = supabase_client.get_desafio_clan_totals(desafio_id)
    return {**desafio, "pontos_por_clan": pontos_por_clan}


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
    return supabase_client.list_desafio_submissions_current(
        desafio_id=desafio_id, clan=clan, status=status, limit=limit, offset=offset
    )
