"""Trilha de auditoria append-only com cadeia de hash (spec §9.2.9, critério 12).

Cada evento carrega o hash do anterior: qualquer edição ou remoção direta no
banco quebra a cadeia e é detectada por ``verificar_cadeia``. O contexto
registra identificadores e metadados — nunca o conteúdo do relato nem dados
de contato (minimização, §9.1).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import EventoAuditoria, agora

HASH_GENESE = "0" * 64

TIPOS_EVENTO = {
    "criacao", "acesso", "alteracao", "encaminhamento", "exportacao", "tentativa_negada", "incidente",
    "consentimento", "emergencia_detectada", "emergencia_notificada", "escalonamento", "triagem_sugerida",
    "avaliacao_humana", "adendo", "anexo_recebido", "anexo_acessado", "status", "consulta_status",
    "bloqueio_saida", "kill_switch", "fila", "llm_falha", "resposta_kb", "sessao",
}


def _canon(dados: dict) -> str:
    return json.dumps(dados, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _calcular_hash(tipo: str, objeto: str, ator: str, contexto: dict, carimbo: str, anterior: str) -> str:
    material = _canon({"tipo": tipo, "objeto": objeto, "ator": ator, "contexto": contexto, "carimbo": carimbo, "anterior": anterior})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def registrar(db: Session, tipo_evento: str, objeto: str, ator: str, contexto: dict | None = None) -> EventoAuditoria:
    if tipo_evento not in TIPOS_EVENTO:
        raise ValueError(f"tipo de evento de auditoria desconhecido: {tipo_evento}")
    contexto = contexto or {}
    db.flush()
    ultimo = db.execute(select(EventoAuditoria).order_by(EventoAuditoria.seq.desc()).limit(1)).scalar_one_or_none()
    anterior = ultimo.hash_evento if ultimo else HASH_GENESE
    carimbo = agora().isoformat()
    ev = EventoAuditoria(
        tipo_evento=tipo_evento,
        objeto=objeto,
        ator=ator,
        contexto=contexto,
        carimbo_tempo=carimbo,
        hash_anterior=anterior,
        hash_evento=_calcular_hash(tipo_evento, objeto, ator, contexto, carimbo, anterior),
    )
    db.add(ev)
    db.flush()
    return ev


@dataclass
class ResultadoVerificacao:
    integra: bool
    total_eventos: int
    primeiro_seq_invalido: int | None = None
    motivo: str | None = None


def verificar_cadeia(db: Session) -> ResultadoVerificacao:
    eventos = db.execute(select(EventoAuditoria).order_by(EventoAuditoria.seq)).scalars().all()
    anterior = HASH_GENESE
    for ev in eventos:
        if ev.hash_anterior != anterior:
            return ResultadoVerificacao(False, len(eventos), ev.seq, "elo quebrado (evento removido ou reordenado)")
        esperado = _calcular_hash(ev.tipo_evento, ev.objeto, ev.ator, ev.contexto, ev.carimbo_tempo, ev.hash_anterior)
        if esperado != ev.hash_evento:
            return ResultadoVerificacao(False, len(eventos), ev.seq, "conteúdo do evento alterado")
        anterior = ev.hash_evento
    return ResultadoVerificacao(True, len(eventos))
