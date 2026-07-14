# backend/routers/desafio_import.py
import csv
import io
import json
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import desafio_import_engine
import google_sheets_client
import points_engine
import supabase_client

router = APIRouter()

NOME_CAMPO_PARTICIPACOES = "Participações Validadas"
NOME_CAMPO_PONTUACAO = "Pontuação"


class ImportConfig(BaseModel):
    nome: str
    desafio_id: int | None = None
    data_inicio: date
    data_fim: date
    pontos_por_participacao: int


def _ler_csv(file_bytes: bytes) -> list[dict]:
    texto = file_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto)))


def _clans_validos() -> set[str]:
    ranking = google_sheets_client.fetch_ranking()
    return {entry["clan"] for entry in ranking}


def _tokens_ja_importados(desafio_id: int | None) -> set[str]:
    if desafio_id is None:
        return set()
    return supabase_client.get_tokens_importados(desafio_id)


def _processar(file: UploadFile, mapping_json: str, config_json: str) -> tuple[desafio_import_engine.ImportResult, ImportConfig]:
    mapping = json.loads(mapping_json)
    config = ImportConfig(**json.loads(config_json))
    raw_rows = _ler_csv(file.file.read())

    result = desafio_import_engine.processar_importacao(
        raw_rows=raw_rows,
        mapping=mapping,
        clans_validos=_clans_validos(),
        tokens_ja_importados=_tokens_ja_importados(config.desafio_id),
        data_inicio=config.data_inicio,
        data_fim=config.data_fim,
        pontos_por_participacao=config.pontos_por_participacao,
        coach_alias_map=supabase_client.get_coach_alias_map(),
    )
    return result, config


@router.post("/preview")
def preview(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    config: str = Form(...),
):
    """Calcula o resultado da importação SEM gravar nada."""
    result, _ = _processar(file, mapping, config)
    return {
        "pontos_por_clan": result.pontos_por_clan,
        "participacoes_por_clan": result.participacoes_por_clan,
        "pontos_por_coach": result.pontos_por_coach,
        "participacoes_por_coach": result.participacoes_por_coach,
        "avisos": result.avisos,
        "total_linhas_contabilizadas": sum(result.participacoes_por_clan.values()),
    }


@router.post("/confirmar")
def confirmar(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    config: str = Form(...),
):
    """Efetiva a importação: cria ou atualiza o desafio e aplica os pontos."""
    result, config_obj = _processar(file, mapping, config)

    if config_obj.desafio_id is not None:
        desafio = supabase_client.get_desafio(config_obj.desafio_id)
        if not desafio or desafio.get("origem") != "csv_import":
            raise HTTPException(
                status_code=404,
                detail="Desafio importável não encontrado (só desafios criados via importação podem ser atualizados).",
            )
        supabase_client.update_desafio_periodo_e_pontos(
            config_obj.desafio_id, config_obj.data_inicio, config_obj.data_fim,
            config_obj.pontos_por_participacao,
        )
        campos = supabase_client.list_desafio_campos(config_obj.desafio_id)
    else:
        desafio = supabase_client.create_desafio(
            nome=config_obj.nome,
            contabilizar_pontos=True,
            data=config_obj.data_fim,
            data_inicio=config_obj.data_inicio,
            data_fim=config_obj.data_fim,
            origem="csv_import",
            pontos_por_participacao=config_obj.pontos_por_participacao,
        )
        campos = supabase_client.insert_desafio_campos([
            {"desafio_id": desafio["id"], "nome": NOME_CAMPO_PARTICIPACOES, "tipo": "texto", "ordem": 0},
            {"desafio_id": desafio["id"], "nome": NOME_CAMPO_PONTUACAO, "tipo": "pontuacao", "ordem": 1},
        ])

    campo_participacoes = next(c for c in campos if c["nome"] == NOME_CAMPO_PARTICIPACOES)
    campo_pontuacao = next(c for c in campos if c["nome"] == NOME_CAMPO_PONTUACAO)

    if result.linhas_auditoria:
        supabase_client.insert_desafio_importacao_linhas(desafio["id"], result.linhas_auditoria)

    for clan, participacoes in result.participacoes_por_clan.items():
        pontos = result.pontos_por_clan[clan]
        valores = {str(campo_participacoes["id"]): str(participacoes), str(campo_pontuacao["id"]): pontos}

        existente = supabase_client.get_desafio_registro_by_clan(desafio["id"], clan)
        if existente:
            novo_total = points_engine.calculate_desafio_pontos(campos, valores)
            delta = novo_total - existente["total_pontos"]
            supabase_client.update_desafio_registro_pontos(existente["id"], valores, novo_total)
            if delta != 0:
                supabase_client.add_delta_to_clan_total(clan, delta)
        else:
            supabase_client.create_desafio_registro(desafio["id"], clan, valores, pontos)
            supabase_client.add_delta_to_clan_total(clan, pontos)

    for coach, participacoes in result.participacoes_por_coach.items():
        pontos = result.pontos_por_coach[coach]
        valores = {str(campo_participacoes["id"]): str(participacoes), str(campo_pontuacao["id"]): pontos}

        existente_coach = supabase_client.get_desafio_registro_coach_by_coach(desafio["id"], coach)
        if existente_coach:
            novo_total = points_engine.calculate_desafio_pontos(campos, valores)
            delta = novo_total - existente_coach["total_pontos"]
            supabase_client.update_desafio_registro_coach_pontos(existente_coach["id"], valores, novo_total)
            if delta != 0:
                supabase_client.add_delta_to_coach_total(coach, delta)
        else:
            supabase_client.create_desafio_registro_coach(desafio["id"], coach, valores, pontos)
            supabase_client.add_delta_to_coach_total(coach, pontos)

    campos_atualizados = supabase_client.list_desafio_campos(desafio["id"])
    registros = supabase_client.list_desafio_registros(desafio["id"])
    return {**supabase_client.get_desafio(desafio["id"]), "campos": campos_atualizados, "total_registros": len(registros)}
