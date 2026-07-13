import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coach_identity import (
    normalize_key,
    resolve_coach,
    aggregate_by_canonical,
    detect_alias_chains,
)


class TestNormalizeKey:

    def test_colapsa_case(self):
        assert normalize_key("Karlla Andrade") == normalize_key("KARLLA ANDRADE")

    def test_colapsa_acento(self):
        assert normalize_key("Cássia Fajardo") == normalize_key("Cassia Fajardo")

    def test_colapsa_espaco_duplo(self):
        assert normalize_key("Karlla  Andrade") == normalize_key("Karlla Andrade")

    def test_aparado_nas_pontas(self):
        assert normalize_key("  Karlla Andrade  ") == normalize_key("Karlla Andrade")


class TestResolveCoach:

    def test_sem_alias_retorna_proprio_nome_aparado(self):
        assert resolve_coach("  Vivian Gaspar  ", {}) == "Vivian Gaspar"

    def test_vazio_retorna_desconhecido(self):
        assert resolve_coach("", {}) == "DESCONHECIDO"
        assert resolve_coach(None, {}) == "DESCONHECIDO"

    def test_resolve_por_alias_exato(self):
        alias_map = {"Tati Pellicel": "Tatiane Pellicel"}
        assert resolve_coach("Tati Pellicel", alias_map) == "Tatiane Pellicel"

    def test_resolve_por_chave_normalizada_variante_nao_cadastrada(self):
        # Alias cadastrado com uma grafia; entrada chega com outra caixa/espaço.
        alias_map = {"KARLLA ANDADE": "Karlla Andrade"}
        assert resolve_coach("karlla   andade", alias_map) == "Karlla Andrade"

    def test_nome_igual_ao_canonico_nao_precisa_de_alias_proprio(self):
        alias_map = {"KARLLA ANDADE": "Karlla Andrade"}
        assert resolve_coach("Karlla Andrade", alias_map) == "Karlla Andrade"


class TestAggregateByCanonical:

    def test_soma_colisoes_apos_fundir(self):
        raw = {"Vini Marini": 30, "Vinicius Marini": 60}
        alias_map = {"Vini Marini": "Vinicius Marini"}
        assert aggregate_by_canonical(raw, alias_map) == {"Vinicius Marini": 90}

    def test_sem_colisao_mantem_entradas_separadas(self):
        raw = {"Coach A": 30, "Coach B": 60}
        assert aggregate_by_canonical(raw, {}) == {"Coach A": 30, "Coach B": 60}

    def test_dict_vazio_retorna_vazio(self):
        assert aggregate_by_canonical({}, {}) == {}


class TestDetectAliasChains:

    def test_sem_cadeia_retorna_vazio(self):
        alias_map = {"Tati Pellicel": "Tatiane Pellicel", "Vini Marini": "Vinicius Marini"}
        assert detect_alias_chains(alias_map) == []

    def test_detecta_cadeia_de_dois_saltos(self):
        alias_map = {"A": "B", "B": "C"}
        avisos = detect_alias_chains(alias_map)
        assert len(avisos) == 1
        assert "A" in avisos[0] and "B" in avisos[0] and "C" in avisos[0]
