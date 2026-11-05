"""Cifragem de dados de contato, turnos de conversa e anexos em repouso (spec §8.2, §11.2).

Em produção, ``ESCUTA_CHAVE_CIFRA`` deve vir do cofre de segredos corporativo
(KMS). Sem ela, gera-se uma chave local de desenvolvimento — com aviso.

Rotação sem parada: ``ESCUTA_CHAVE_CIFRA="nova,antiga"``. A primeira chave cifra;
todas decifram (MultiFernet). Depois, ``python -m escuta.admin rotacionar-chave``
re-cifra tudo com a nova, e a antiga pode sair da lista.
"""

from __future__ import annotations

import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from .config import get_settings

log = logging.getLogger(__name__)
_fernet: MultiFernet | None = None


class ChaveIndisponivel(RuntimeError):
    """Dado cifrado com uma chave que não está mais na lista configurada."""


def chaves_da_config(valor: str) -> list[Fernet]:
    return [Fernet(k.strip().encode()) for k in valor.split(",") if k.strip()]


def _obter_fernet() -> MultiFernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    s = get_settings()
    chave = s.chave_cifra
    if not chave:
        caminho = s.arquivo_chave_dev
        if caminho.exists():
            chave = caminho.read_text().strip()
        else:
            chave = Fernet.generate_key().decode()
            caminho.write_text(chave)
            caminho.chmod(0o600)
        log.warning("ESCUTA_CHAVE_CIFRA ausente: usando chave local de DESENVOLVIMENTO em %s", caminho)
    _fernet = MultiFernet(chaves_da_config(chave))
    return _fernet


def reset() -> None:
    global _fernet
    _fernet = None


def cifrar_texto(texto: str | None) -> str | None:
    if not texto:
        return None
    return _obter_fernet().encrypt(texto.encode("utf-8")).decode()


def decifrar_texto(cifrado: str | None) -> str | None:
    if not cifrado:
        return None
    try:
        return _obter_fernet().decrypt(cifrado.encode()).decode("utf-8")
    except InvalidToken as e:
        raise ChaveIndisponivel("dado cifrado com chave fora de ESCUTA_CHAVE_CIFRA — rotação incompleta?") from e


def cifrar_bytes(dados: bytes) -> bytes:
    return _obter_fernet().encrypt(dados)


def decifrar_bytes(dados: bytes) -> bytes:
    try:
        return _obter_fernet().decrypt(dados)
    except InvalidToken as e:
        raise ChaveIndisponivel("anexo cifrado com chave fora de ESCUTA_CHAVE_CIFRA — rotação incompleta?") from e


def recifrar_texto(cifrado: str | None) -> str | None:
    """Re-cifra com a chave primária (MultiFernet.rotate). Idempotente."""
    if not cifrado:
        return cifrado
    try:
        return _obter_fernet().rotate(cifrado.encode()).decode()
    except InvalidToken as e:
        raise ChaveIndisponivel("dado cifrado com chave fora da lista; inclua a chave antiga antes de rotacionar") from e


def recifrar_bytes(dados: bytes) -> bytes:
    try:
        return _obter_fernet().rotate(dados)
    except InvalidToken as e:
        raise ChaveIndisponivel("anexo cifrado com chave fora da lista; inclua a chave antiga antes de rotacionar") from e


def sha256(dados: bytes | str) -> str:
    if isinstance(dados, str):
        dados = dados.encode("utf-8")
    return hashlib.sha256(dados).hexdigest()
