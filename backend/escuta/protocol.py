"""Gestão de protocolos (spec §8.2, §9.2.2, UC-07, UC-09).

Formato legível ``ANO-UF-SEQUENCIAL`` (ex.: 2026-MG-000123). Toda manifestação
recebe também um **código de consulta** curto, conhecido só pelo autor e
armazenado apenas como hash (scrypt). Isso vale inclusive para casos
identificados: a consulta de status nunca depende só do número, que é
sequencial e portanto enumerável.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SequenciaProtocolo, agora

PADRAO_PROTOCOLO = re.compile(r"\b(20\d{2})-([A-Z]{2})-(\d{6})\b")


def proximo_protocolo(db: Session, uf: str) -> str:
    ano = agora().year
    uf = uf.upper()[:2]
    seq = db.execute(select(SequenciaProtocolo).where(SequenciaProtocolo.ano == ano, SequenciaProtocolo.uf == uf).with_for_update()).scalar_one_or_none()
    if seq is None:
        seq = SequenciaProtocolo(ano=ano, uf=uf, ultimo=0)
        db.add(seq)
    seq.ultimo += 1
    db.flush()
    return f"{ano}-{uf}-{seq.ultimo:06d}"


def gerar_codigo_consulta() -> str:
    """Código numérico de 6 dígitos, fácil de anotar e ditar por telefone."""
    return f"{secrets.randbelow(10**6):06d}"


def formatar_codigo(codigo: str) -> str:
    return "-".join(codigo[i : i + 3] for i in range(0, len(codigo), 3))


def hash_codigo(codigo: str) -> str:
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(_normalizar(codigo).encode(), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${sal.hex()}${dk.hex()}"


def verificar_codigo(codigo: str, armazenado: str) -> bool:
    try:
        _, sal_hex, dk_hex = armazenado.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(_normalizar(codigo).encode(), salt=bytes.fromhex(sal_hex), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _normalizar(codigo: str) -> str:
    return re.sub(r"\D", "", codigo or "")


def extrair_protocolo(texto: str) -> str | None:
    m = PADRAO_PROTOCOLO.search(texto.upper())
    return m.group(0) if m else None
