"""Mascaramento de dados pessoais para telas comuns, filas e painéis (§10, A5)."""

from __future__ import annotations

import re

_PADROES = [
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[CPF]"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}(?!\d)"), "[TELEFONE]"),
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), "[CNPJ]"),
]


def mascarar(texto: str | None) -> str | None:
    if texto is None:
        return None
    for padrao, rotulo in _PADROES:
        texto = padrao.sub(rotulo, texto)
    return texto
