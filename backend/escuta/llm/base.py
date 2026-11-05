"""Contrato do provedor de linguagem.

O modelo só executa tarefas internas delimitadas. Ele nunca decide fluxo,
prioridade final, encaminhamento, prazo ou encerramento.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..config import SERVICOS_EMERGENCIA, BASE_DIR, get_settings
from ..triage import SugestaoModelo


class ErroProvedor(RuntimeError):
    pass


class ProvedorLLM(ABC):
    nome: str = "abstrato"
    usa_modelo: bool = False

    @abstractmethod
    def resumir(self, relato: str) -> str:
        """Resumo fiel, em linguagem simples, apenas com fatos do relato."""

    @abstractmethod
    def sugerir_triagem(self, relato: str) -> SugestaoModelo | None:
        """Sugestão de tipo/tema/prioridade com justificativa e confiança."""


def montar_prompt_sistema() -> str:
    s = get_settings()
    texto = (BASE_DIR / "prompts" / f"system_prompt_{s.versao_prompt.split('.')[0]}.md").read_text(encoding="utf-8")
    janelas = "; ".join(f"{j.codigo} ({j.nome}): {j.janela_texto}" for j in s.janelas.values())
    servicos = ", ".join(f"{n} {c}" for c, n in SERVICOS_EMERGENCIA.items())
    return (
        texto.replace("[TERRITORIOS]", "Minas Gerais, Rio de Janeiro e Corredor Sul")
        .replace("[SERVICOS-EMERGENCIA]", servicos)
        .replace("[JANELA-ESCALONAMENTO]", s.janela_escalonamento)
        .replace("[JANELAS-CONFIGURADAS]", janelas)
    )


def caminho_prompt() -> Path:
    s = get_settings()
    return BASE_DIR / "prompts" / f"system_prompt_{s.versao_prompt.split('.')[0]}.md"
