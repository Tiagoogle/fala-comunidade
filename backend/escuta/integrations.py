"""Integrações corporativas por eventos (spec §8.5).

Outbox transacional: o encaminhamento é gravado junto com o registro e enviado
depois, com retry e dead-letter. A indisponibilidade de CRM/ouvidoria/ERP
NUNCA impede o registro — o pior caso aceitável é adiar o envio.

No MVP (§18.5) as integrações de escrita estão fora do escopo; os adaptadores
abaixo são stubs que registram o envio. Substitua ``ADAPTADORES`` pelos
clientes reais quando as APIs forem confirmadas (pergunta S1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .models import Encaminhamento

log = logging.getLogger(__name__)
MAX_TENTATIVAS = 5


def _stub(nome: str) -> Callable[[Encaminhamento], None]:
    def enviar(enc: Encaminhamento) -> None:
        log.info("[stub %s] encaminhamento %s -> %s", nome, enc.id_encaminhamento, enc.area_destino)

    return enviar


ADAPTADORES: dict[str, Callable[[Encaminhamento], None]] = {
    "crm": _stub("crm"),
    "ouvidoria": _stub("ouvidoria"),
    "erp": _stub("erp"),
}


def processar_pendentes(db: Session) -> dict[str, int]:
    resultado = {"enviado": 0, "erro": 0, "dead_letter": 0}
    pendentes = db.execute(select(Encaminhamento).where(Encaminhamento.estado_integracao.in_(("pendente", "erro")))).scalars().all()
    for enc in pendentes:
        enc.tentativas += 1
        try:
            ADAPTADORES[enc.sistema_destino](enc)
            enc.estado_integracao = "enviado"
            resultado["enviado"] += 1
        except Exception as e:  # noqa: BLE001 — qualquer falha externa vai para retry/dead-letter
            enc.estado_integracao = "dead_letter" if enc.tentativas >= MAX_TENTATIVAS else "erro"
            resultado[enc.estado_integracao] += 1
            audit.registrar(db, "incidente" if enc.estado_integracao == "dead_letter" else "encaminhamento",
                            f"encaminhamento:{enc.id_encaminhamento}", "sistema:integracao",
                            {"estado": enc.estado_integracao, "tentativas": enc.tentativas, "erro": str(e)[:200]})
    return resultado
