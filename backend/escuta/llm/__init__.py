"""Adaptadores de modelo de linguagem (decisão técnica aberta, spec §8.7)."""

from __future__ import annotations

import logging
import os

from ..config import get_settings
from .base import ProvedorLLM
from .deterministic import ProvedorDeterministico

log = logging.getLogger(__name__)


def criar_provedor() -> ProvedorLLM:
    s = get_settings()
    escolha = s.llm_provedor
    tem_credencial = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if escolha == "claude" or (escolha == "auto" and tem_credencial):
        try:
            from .claude import ProvedorClaude

            return ProvedorClaude(modelo=s.llm_modelo, esforco=s.llm_esforco, timeout=s.llm_timeout_s)
        except Exception as e:  # pragma: no cover - depende de ambiente
            log.error("Falha ao iniciar provedor Claude (%s); usando modo determinístico.", e)
    return ProvedorDeterministico()
