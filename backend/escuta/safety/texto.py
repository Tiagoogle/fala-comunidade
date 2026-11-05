"""Normalização de texto em português para detecção léxica robusta."""

from __future__ import annotations

import re
import unicodedata

_NEGACOES = {"nao", "sem", "nenhum", "nenhuma", "nunca", "nem"}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^\w\s?!.,-]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def negado(texto_norm: str, inicio: int, janela: int = 4) -> bool:
    """True se uma das ``janela`` palavras antes da posição é uma negação.

    Interrompe na pontuação: em "Não. Tem fogo!" a negação não se aplica.
    """
    antes = texto_norm[:inicio]
    corte = max(antes.rfind("."), antes.rfind("!"), antes.rfind("?"), antes.rfind(","))
    if corte >= 0:
        antes = antes[corte + 1 :]
    palavras = antes.split()[-janela:]
    return any(p in _NEGACOES for p in palavras)


def buscar(padroes: list[tuple[str, object]], texto: str) -> list[tuple[str, object, bool]]:
    """Retorna (trecho, rótulo, negado) para cada padrão encontrado."""
    norm = normalizar(texto)
    achados = []
    for padrao, rotulo in padroes:
        for m in re.finditer(padrao, norm):
            achados.append((m.group(0), rotulo, negado(norm, m.start())))
    return achados
