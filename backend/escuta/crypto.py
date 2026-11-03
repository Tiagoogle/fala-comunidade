"""Cifragem de dados de contato e anexos em repouso (spec §8.2, §11.2).

Em produção, ``ESCUTA_CHAVE_CIFRA`` deve vir do cofre de segredos corporativo
(KMS). Sem ela, gera-se uma chave local de desenvolvimento — com aviso.
"""

from __future__ import annotations

import hashlib
import logging

from cryptography.fernet import Fernet

from .config import get_settings

log = logging.getLogger(__name__)
_fernet: Fernet | None = None


def _obter_fernet() -> Fernet:
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
    _fernet = Fernet(chave.encode() if isinstance(chave, str) else chave)
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
    return _obter_fernet().decrypt(cifrado.encode()).decode("utf-8")


def cifrar_bytes(dados: bytes) -> bytes:
    return _obter_fernet().encrypt(dados)


def decifrar_bytes(dados: bytes) -> bytes:
    return _obter_fernet().decrypt(dados)


def sha256(dados: bytes | str) -> str:
    if isinstance(dados, str):
        dados = dados.encode("utf-8")
    return hashlib.sha256(dados).hexdigest()
