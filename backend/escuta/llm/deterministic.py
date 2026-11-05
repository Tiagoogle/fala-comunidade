"""Provedor sem modelo de linguagem.

Usado quando não há credencial, quando o kill switch do LLM está desligado ou
quando o provedor real falha. O fluxo continua íntegro: resumo = fala da
pessoa (sem reescrita) e triagem apenas por regras.
"""

from __future__ import annotations

import re

from ..triage import SugestaoModelo
from .base import ProvedorLLM


class ProvedorDeterministico(ProvedorLLM):
    nome = "deterministico"
    usa_modelo = False

    def resumir(self, relato: str) -> str:
        texto = re.sub(r"\s+", " ", relato).strip()
        if len(texto) > 600:
            texto = texto[:600].rsplit(" ", 1)[0] + "…"
        return texto

    def sugerir_triagem(self, relato: str) -> SugestaoModelo | None:
        return None
