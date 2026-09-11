"""Testes unitários para o motor de apuração por percentual (backend/desafio_percentual_clan.py)."""

import pytest
from desafio_percentual_clan import (
    ApuracaoClan,
    apurar_desafio,
    calcular_pontos_por_percentual,
    normalize_clan,
)


def test_normalize_clan():
    assert normalize_clan("1") == "CLÃ 1"
    assert normalize_clan("CLÃ 2") == "CLÃ 2"
    assert normalize_clan("clã 3") == "CLÃ 3"
    assert normalize_clan(None) == "CLÃ DESCONHECIDO"


def test_calcular_pontos_por_percentual_faixas_exatas():
    # 0% a <10% -> 0
    assert calcular_pontos_por_percentual(0.0) == 0
    assert calcular_pontos_por_percentual(9.99) == 0

    # 10% a 30% -> 300
    assert calcular_pontos_por_percentual(10.0) == 300
    assert calcular_pontos_por_percentual(17.647) == 300  # Exemplo do PRD: 3 de 17 = 17.64...%
    assert calcular_pontos_por_percentual(30.0) == 300

    # 31% a 40% -> 400
    assert calcular_pontos_por_percentual(30.01) == 400
    assert calcular_pontos_por_percentual(40.0) == 400

    # 41% a 50% -> 500
    assert calcular_pontos_por_percentual(40.1) == 500
    assert calcular_pontos_por_percentual(50.0) == 500

    # 51% a 60% -> 600
    assert calcular_pontos_por_percentual(50.1) == 600
    assert calcular_pontos_por_percentual(60.0) == 600

    # 61% a 70% -> 700
    assert calcular_pontos_por_percentual(60.1) == 700
    assert calcular_pontos_por_percentual(70.0) == 700

    # 71% a 80% -> 800
    assert calcular_pontos_por_percentual(70.1) == 800
    assert calcular_pontos_por_percentual(80.0) == 800

    # 81% a 90% -> 900
    assert calcular_pontos_por_percentual(80.1) == 900
    assert calcular_pontos_por_percentual(90.0) == 900

    # 91% a 100% -> 1000
    assert calcular_pontos_por_percentual(90.1) == 1000
    assert calcular_pontos_por_percentual(100.0) == 1000
    assert calcular_pontos_por_percentual(120.0) == 1000


def test_apurar_desafio_precedencia_e_deduplicacao():
    submissoes = [
        # Coach 1 cadastrado no Clã 1 na base, mas planilha declarou Clã 2 -> Deve ir para Clã 1
        {"coach": "Coach Um", "clan_planilha": "CLÃ 2"},
        # Coach 1 enviou duas vezes -> Deve ser deduplicado (1 participante)
        {"coach": "Coach Um", "clan_planilha": "CLÃ 2"},
        # Coach 2 cadastrado no Clã 1 -> Conta no Clã 1 (2º participante)
        {"coach": "Coach Dois", "clan_planilha": "CLÃ 1"},
        # Coach 3 NÃO cadastrado -> Cai no Clã 2 pela planilha
        {"coach": "Coach Tres Nao Cadastrado", "clan_planilha": "CLÃ 2"},
    ]

    coach_clas = {
        "Coach Um": "CLÃ 1",
        "Coach Dois": "CLÃ 1",
    }

    tamanho_grupo = {
        "CLÃ 1": 10,
        "CLÃ 2": 5,
    }

    todos_os_clas = ["CLÃ 1", "CLÃ 2", "CLÃ 3"]

    resultado = apurar_desafio(
        submissoes_aprovadas=submissoes,
        coach_clas=coach_clas,
        tamanho_grupo_por_clan=tamanho_grupo,
        todos_os_clas=todos_os_clas,
    )

    # Clã 1: 2 participantes de 10 -> 20.0% -> 300 pts
    assert resultado["CLÃ 1"].participantes == 2
    assert resultado["CLÃ 1"].total_grupo == 10
    assert resultado["CLÃ 1"].percentual == 20.0
    assert resultado["CLÃ 1"].pontos == 300

    # Clã 2: 1 participante (Coach 3) de 5 -> 20.0% -> 300 pts
    assert resultado["CLÃ 2"].participantes == 1
    assert resultado["CLÃ 2"].total_grupo == 5
    assert resultado["CLÃ 2"].percentual == 20.0
    assert resultado["CLÃ 2"].pontos == 300

    # Clã 3: 0 participantes de 0 cadastrados -> 0% -> 0 pts
    assert resultado["CLÃ 3"].participantes == 0
    assert resultado["CLÃ 3"].total_grupo == 0
    assert resultado["CLÃ 3"].percentual == 0.0
    assert resultado["CLÃ 3"].pontos == 0


def test_apurar_desafio_cap_100_percent():
    # Caso de coach não cadastrado elevando participantes acima do tamanho cadastrado
    submissoes = [
        {"coach": "Nao Cadastrado 1", "clan_planilha": "CLÃ 1"},
        {"coach": "Nao Cadastrado 2", "clan_planilha": "CLÃ 1"},
        {"coach": "Nao Cadastrado 3", "clan_planilha": "CLÃ 1"},
    ]

    tamanho_grupo = {"CLÃ 1": 2}  # Só tem 2 cadastrados, mas 3 participaram

    resultado = apurar_desafio(
        submissoes_aprovadas=submissoes,
        coach_clas={},
        tamanho_grupo_por_clan=tamanho_grupo,
    )

    # Participantes = 3, Total Grupo = 2 -> Percentual travado em 100% -> 1000 pts
    assert resultado["CLÃ 1"].participantes == 3
    assert resultado["CLÃ 1"].total_grupo == 2
    assert resultado["CLÃ 1"].percentual == 100.0
    assert resultado["CLÃ 1"].pontos == 1000
