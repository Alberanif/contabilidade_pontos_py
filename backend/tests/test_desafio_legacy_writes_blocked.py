import io
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import HTTPException

from routers.desafios import (
    criar_desafio,
    editar_desafio,
    excluir_desafio,
    criar_registro,
    excluir_registro,
    DesafioCreate,
    DesafioUpdate,
    RegistroCreate,
)
from routers.desafio_import import preview, confirmar


class _FakeUploadFile:
    def __init__(self, content: bytes = b""):
        self.file = io.BytesIO(content)


def _assert_410_domain_message(exc_info):
    exc = exc_info.value
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 410
    detail = exc.detail.lower()
    assert "google sheet" in detail or "planilha" in detail


class TestDesafiosRouterEscritaBloqueada:

    def test_criar_desafio_bloqueado(self):
        body = DesafioCreate(
            nome="Novo Desafio",
            contabilizar_pontos=True,
            data_inicio="2026-01-01",
            data_fim="2026-01-31",
            registros=[],
        )
        with pytest.raises(HTTPException) as exc_info:
            criar_desafio(body)
        _assert_410_domain_message(exc_info)

    def test_editar_desafio_bloqueado(self):
        body = DesafioUpdate(
            nome="Desafio Editado",
            contabilizar_pontos=True,
            data_inicio="2026-01-01",
            data_fim="2026-01-31",
            registros=[],
        )
        with pytest.raises(HTTPException) as exc_info:
            editar_desafio(1, body)
        _assert_410_domain_message(exc_info)

    def test_excluir_desafio_bloqueado(self):
        with pytest.raises(HTTPException) as exc_info:
            excluir_desafio(1)
        _assert_410_domain_message(exc_info)

    def test_criar_registro_bloqueado(self):
        body = RegistroCreate(clan="CLÃ 1", valores={"1": 10})
        with pytest.raises(HTTPException) as exc_info:
            criar_registro(1, body)
        _assert_410_domain_message(exc_info)

    def test_excluir_registro_bloqueado(self):
        with pytest.raises(HTTPException) as exc_info:
            excluir_registro(1, 1)
        _assert_410_domain_message(exc_info)


class TestDesafioImportRouterEscritaBloqueada:

    def test_preview_bloqueado(self):
        with pytest.raises(HTTPException) as exc_info:
            preview(
                file=_FakeUploadFile(),
                mapping=json.dumps({}),
                config=json.dumps({
                    "nome": "x", "desafio_id": None,
                    "data_inicio": "2026-01-01", "data_fim": "2026-01-31",
                    "pontos_por_participacao": 1,
                }),
            )
        _assert_410_domain_message(exc_info)

    def test_confirmar_bloqueado(self):
        with pytest.raises(HTTPException) as exc_info:
            confirmar(
                file=_FakeUploadFile(),
                mapping=json.dumps({}),
                config=json.dumps({
                    "nome": "x", "desafio_id": None,
                    "data_inicio": "2026-01-01", "data_fim": "2026-01-31",
                    "pontos_por_participacao": 1,
                }),
            )
        _assert_410_domain_message(exc_info)
