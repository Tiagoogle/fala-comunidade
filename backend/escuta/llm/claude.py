"""Adaptador Claude (API Anthropic) com saída estruturada.

- Modelo padrão ``claude-opus-5-5`` (configurável por ``ESCUTA_LLM_MODELO``).
- Esforço ``low`` por padrão: as tarefas são curtas (resumo, classificação).
- Saída validada por esquema Pydantic via ``messages.parse``.
- ``fallbacks="default"`` (beta server-side-fallback): se o modelo recusar por
  política de segurança, a API reexecuta em modelo de reserva; se ainda assim
  houver recusa, levantamos ``ErroProvedor`` e o chamador cai no modo
  determinístico — o registro nunca é perdido.
- O prompt de sistema (cap. 7) vai em bloco com cache: é estável entre chamadas.
- O relato entra delimitado em <relato_usuario> e é tratado como dado.
"""

from __future__ import annotations

import logging
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from ..triage import PRIORIDADES, TEMAS, TIPOS, SugestaoModelo
from .base import ErroProvedor, ProvedorLLM, montar_prompt_sistema

log = logging.getLogger(__name__)

BETA_FALLBACK = "server-side-fallback-2026-07-01"

TipoLit = Literal[TIPOS]  # type: ignore[valid-type]
TemaLit = Literal[TEMAS]  # type: ignore[valid-type]
PrioLit = Literal[PRIORIDADES]  # type: ignore[valid-type]


class SaidaResumo(BaseModel):
    resumo: str = Field(description="Resumo fiel em até 3 frases curtas, só com fatos do relato, nas palavras da pessoa.")


class SaidaTriagem(BaseModel):
    tipo: TipoLit
    tema: TemaLit
    prioridade: PrioLit
    justificativa: str = Field(description="Motivos em linguagem simples, citando o relato. Sem juízo sobre a pessoa, sem causalidade.")
    trechos_citados: list[str] = Field(description="Trechos literais do relato que fundamentam a sugestão.")
    confianca: Literal["baixa", "media", "alta"]


INSTRUCAO_RESUMO = (
    "Tarefa interna: escreva um resumo fiel do relato abaixo para confirmação com a própria pessoa. "
    "Use linguagem simples e as palavras dela. Não acrescente números, datas, nomes, causas, culpados ou promessas "
    "que não estejam no relato. Não comente o relato."
)

INSTRUCAO_TRIAGEM = (
    "Tarefa interna: sugira a triagem do relato abaixo (é SUGESTÃO para revisão humana, nunca decisão). "
    "Tipos: informacao, solicitacao, reclamacao, denuncia, sugestao, elogio, conflito, emergencia. "
    "Temas: impacto_ambiental, impacto_social, infraestrutura_patrimonio, saude, seguranca, direitos_humanos, "
    "risco_operacional, administrativo_relacional. "
    "Prioridades: P1 risco atual à vida/integridade/segurança ou dano ambiental em curso; P2 indício de dano à saúde, água, "
    "segurança patrimonial, direitos humanos, conflito em curso, denúncia grave ou atraso relevante; P3 reclamações e "
    "solicitações com efeito concreto na rotina sem indício de dano imediato; P4 informações, sugestões, elogios e demandas "
    "administrativas. Prioridade alta exige indicador concreto no relato; na dúvida entre dois níveis, escolha o mais protetor "
    "e diga isso na justificativa. Não infira atributos sensíveis da pessoa e não conclua causalidade."
)


class ProvedorClaude(ProvedorLLM):
    nome = "claude"
    usa_modelo = True

    def __init__(self, modelo: str, esforco: str = "low", timeout: float = 30.0):
        self.modelo = modelo
        self.esforco = esforco
        self.client = anthropic.Anthropic(timeout=timeout, max_retries=2)
        self._sistema = [{"type": "text", "text": montar_prompt_sistema(), "cache_control": {"type": "ephemeral"}}]

    def _parse(self, instrucao: str, relato: str, formato: type[BaseModel]) -> BaseModel:
        conteudo = f"{instrucao}\n\n<relato_usuario>\n{relato}\n</relato_usuario>"
        try:
            resp = self.client.beta.messages.parse(
                model=self.modelo,
                max_tokens=4000,
                system=self._sistema,
                messages=[{"role": "user", "content": conteudo}],
                output_format=formato,
                output_config={"effort": self.esforco},
                betas=[BETA_FALLBACK],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise ErroProvedor(f"limite de taxa: {e}") from e
        except anthropic.APIStatusError as e:
            raise ErroProvedor(f"erro de API {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise ErroProvedor("falha de conexão com o provedor") from e
        if resp.stop_reason == "refusal":
            raise ErroProvedor("recusa do modelo")
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            raise ErroProvedor(f"saída incompleta ({resp.stop_reason})")
        return resp.parsed_output

    def resumir(self, relato: str) -> str:
        saida = self._parse(INSTRUCAO_RESUMO, relato, SaidaResumo)
        return saida.resumo.strip()  # type: ignore[attr-defined]

    def sugerir_triagem(self, relato: str) -> SugestaoModelo | None:
        s = self._parse(INSTRUCAO_TRIAGEM, relato, SaidaTriagem)
        return SugestaoModelo(
            tipo=s.tipo, tema=s.tema, prioridade=s.prioridade,  # type: ignore[attr-defined]
            justificativa=s.justificativa, trechos_citados=list(s.trechos_citados), confianca=s.confianca,  # type: ignore[attr-defined]
        )
