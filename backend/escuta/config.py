"""Parâmetros governados (spec §7.1, §7.3, Tabela 5).

Todo valor aqui é *referência de desenho a validar pela governança* (Fase 2).
Nenhum deles pode ser inventado pelo modelo em runtime: o prompt recebe estes
valores por substituição de marcadores ``[JANELA-*]``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class JanelaPrioridade:
    codigo: str
    nome: str
    janela_texto: str  # texto apresentado como alvo interno, nunca promessa
    horas_uteis_alvo: int  # usado para calcular prazo-alvo e alertas de atraso


JANELAS_PADRAO: dict[str, JanelaPrioridade] = {
    "P1": JanelaPrioridade("P1", "Emergência ou risco imediato", "contato humano prioritário em minutos (regime de plantão)", 1),
    "P2": JanelaPrioridade("P2", "Prioridade alta", "primeira resposta humana em até 24 a 48 horas úteis", 48),
    "P3": JanelaPrioridade("P3", "Prioridade", "encaminhamento em 1 a 2 dias úteis", 16),
    "P4": JanelaPrioridade("P4", "Rotina", "3 a 5 dias úteis", 40),
}

# Serviços públicos de emergência (spec §5.14.5). Parâmetro versionado.
SERVICOS_EMERGENCIA: dict[str, str] = {
    "192": "SAMU",
    "193": "Bombeiros",
    "190": "Polícia Militar",
    "194": "Polícia Civil",
    "199": "Defesa Civil",
    "100": "Direitos Humanos",
    "180": "Central de Atendimento à Mulher",
}

# Mapeamento tema -> área responsável SUGERIDA (hipótese de trabalho, §5.14.2).
AREAS_POR_TEMA: dict[str, str] = {
    "impacto_ambiental": "Meio Ambiente",
    "impacto_social": "Relacionamento Comunitário",
    "infraestrutura_patrimonio": "Engenharia e Patrimônio",
    "saude": "Saúde e Segurança",
    "seguranca": "Saúde e Segurança",
    "direitos_humanos": "Direitos Humanos e Ouvidoria",
    "risco_operacional": "Operações",
    "administrativo_relacional": "Relacionamento Comunitário",
}


@dataclass
class Settings:
    ambiente: str = field(default_factory=lambda: _env("ESCUTA_AMBIENTE", "desenvolvimento"))  # desenvolvimento | producao
    # Só confie em cabeçalhos de IP (Fly-Client-IP / X-Forwarded-For) atrás de proxy conhecido.
    confiar_proxy: bool = field(default_factory=lambda: _env("ESCUTA_CONFIAR_PROXY", "0") == "1")
    segredo_proxy: str | None = field(default_factory=lambda: os.environ.get("ESCUTA_SEGREDO_PROXY"))
    database_url: str = field(default_factory=lambda: _env("ESCUTA_DATABASE_URL", f"sqlite:///{BASE_DIR.parent / 'escuta.db'}"))
    uf_padrao: str = field(default_factory=lambda: _env("ESCUTA_UF_PADRAO", "MG"))
    dir_anexos: Path = field(default_factory=lambda: Path(_env("ESCUTA_DIR_ANEXOS", str(BASE_DIR.parent / "anexos"))))
    chave_cifra: str | None = field(default_factory=lambda: os.environ.get("ESCUTA_CHAVE_CIFRA"))
    arquivo_chave_dev: Path = field(default_factory=lambda: BASE_DIR.parent / ".chave_dev.key")

    # Modelo de linguagem (decisão técnica aberta §8.7 — adaptador plugável).
    llm_provedor: str = field(default_factory=lambda: _env("ESCUTA_LLM", "auto"))  # auto | claude | deterministico
    llm_modelo: str = field(default_factory=lambda: _env("ESCUTA_LLM_MODELO", "claude-opus-5-5"))
    llm_esforco: str = field(default_factory=lambda: _env("ESCUTA_LLM_ESFORCO", "low"))
    llm_timeout_s: float = field(default_factory=lambda: float(_env("ESCUTA_LLM_TIMEOUT", "30")))

    versao_prompt: str = "v1.0"
    versao_texto_consentimento: str = "consentimento-v1.0"
    janelas: dict[str, JanelaPrioridade] = field(default_factory=lambda: dict(JANELAS_PADRAO))
    janela_escalonamento: str = field(default_factory=lambda: _env("ESCUTA_JANELA_ESCALONAMENTO", "até 2 horas úteis"))
    minimo_n_indicadores: int = field(default_factory=lambda: int(_env("ESCUTA_MINIMO_N", "5")))
    max_anexo_bytes: int = 25 * 1024 * 1024
    tipos_anexo_permitidos: tuple[str, ...] = (
        "image/jpeg", "image/png", "image/webp", "application/pdf",
        "audio/ogg", "audio/mpeg", "audio/mp4", "audio/webm", "audio/wav", "audio/x-wav",
        "video/mp4", "video/webm",
    )
    # Papéis por chave de acesso. Em produção: SSO corporativo (spec §11.2).
    chaves_acesso: dict[str, dict[str, str]] = field(default_factory=lambda: _carregar_chaves())


def _carregar_chaves() -> dict[str, dict[str, str]]:
    bruto = os.environ.get("ESCUTA_CHAVES_ACESSO")
    if bruto:
        return json.loads(bruto)
    # Chaves de desenvolvimento — NUNCA usar em produção.
    return {
        "campo-dev": {"papel": "agente_campo", "id": "campo-01", "territorio": "MG"},
        "revisor-dev": {"papel": "revisor", "id": "revisor-01", "territorio": "MG"},
        "sigilo-dev": {"papel": "revisor_sigiloso", "id": "ouvidoria-01", "territorio": "*"},
        "gestor-dev": {"papel": "gestor", "id": "gestor-01", "territorio": "*"},
        "governanca-dev": {"papel": "governanca", "id": "comite-01", "territorio": "*"},
    }


class ConfiguracaoInsegura(RuntimeError):
    """Configuração incompatível com produção — o app se recusa a subir."""


def validar_producao(s: "Settings") -> None:
    """Em produção, nada de chave de cifra efêmera nem chaves de acesso de desenvolvimento."""
    if s.ambiente != "producao":
        return
    problemas = []
    if not s.chave_cifra:
        problemas.append("ESCUTA_CHAVE_CIFRA ausente (chave Fernet do cofre de segredos)")
    if not os.environ.get("ESCUTA_CHAVES_ACESSO"):
        problemas.append("ESCUTA_CHAVES_ACESSO ausente (chaves de desenvolvimento são proibidas em produção)")
    elif any(k.endswith("-dev") for k in s.chaves_acesso):
        problemas.append("ESCUTA_CHAVES_ACESSO contém chaves '*-dev'")
    if s.confiar_proxy and not s.segredo_proxy:
        problemas.append("ESCUTA_SEGREDO_PROXY ausente: sem ele, todo tráfego vindo da Netlify divide um único limite de tentativas")
    if s.database_url in ("sqlite://", "sqlite:///:memory:"):
        problemas.append("banco em memória em produção")
    if problemas:
        raise ConfiguracaoInsegura("Configuração insegura para produção: " + "; ".join(problemas))


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(s: Settings) -> None:
    global _settings
    _settings = s
