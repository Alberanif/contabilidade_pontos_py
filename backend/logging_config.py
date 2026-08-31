r"""Configuração mínima de logging estruturado do backend.

Não existe nenhuma configuração de logging no projeto antes desta Task —
greenfield, stdlib puro, sem dependência nova (`grep -r "^import logging\|
getLogger\|structlog" backend/` não achava nada). `configure_logging()` é
idempotente e é chamada uma vez, na importação de `main.py`, para que os
eventos estruturados emitidos por `desafio_sync_service` (e qualquer módulo
futuro que siga o mesmo padrão: `logger.info(msg, extra={"desafio_sync": {...}})`)
cheguem a um handler quando o processo sobe de verdade. Em teste, o `caplog`
do pytest já captura os registros pelo `propagate` padrão do logger,
independentemente desta configuração ter rodado ou não.
"""

from __future__ import annotations

import json
import logging
import os


class StructuredFormatter(logging.Formatter):
    """Anexa `record.<namespace>` (se presente) como um bloco JSON na linha.

    O texto humano (timestamp, nível, logger, mensagem) continua na frente —
    grep-ável em terminal — e os campos estruturados (fase, duração,
    contagens, categoria de erro, `correlation_id`/`run_id`) vão depois, como
    JSON de uma linha só, para que qualquer coletor de log (que só sabe
    indexar linhas de texto) consiga parsear o payload sem heurística.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        payload = getattr(record, "desafio_sync", None)
        if payload is None:
            return base
        return f"{base} {json.dumps(payload, default=str, ensure_ascii=False)}"


_configured = False


def configure_logging() -> None:
    """Configura um `StreamHandler` estruturado no logger raiz (idempotente).

    Nível controlável por `LOG_LEVEL` (padrão `INFO`). Chamar mais de uma vez
    é seguro e não duplica handlers — importar `main` várias vezes (testes,
    reload do uvicorn) não deve multiplicar linhas de log.
    """
    global _configured
    if _configured:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(
        StructuredFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _configured = True
