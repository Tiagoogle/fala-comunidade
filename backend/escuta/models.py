"""Modelo de dados mínimo (spec cap. 9).

Princípios aplicados estruturalmente:
- separação identidade × conteúdo: ``Pessoa`` é tabela à parte; no modo anônimo
  o vínculo simplesmente não existe (``id_pessoa`` nulo);
- original intocável: ``conteudo_original``/``hash_original`` não podem ser
  alterados (listener em ``escuta.db``); correções viram ``Adendo``;
- auditoria append-only com cadeia de hash (``escuta.audit``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, false, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(timezone.utc)


def novo_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Pessoa(Base):
    __tablename__ = "pessoa"
    id_pessoa: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    modo_identificacao: Mapped[str] = mapped_column(String(20))  # identificado | sigiloso
    nome_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    contato_cifrado: Mapped[str | None] = mapped_column(Text, nullable=True)
    perfil_acessibilidade: Mapped[list] = mapped_column(JSON, default=list)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    # Retenção/titular: nome e contato apagados (o pseudônimo continua ligando o caso)
    dados_removidos_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SequenciaProtocolo(Base):
    __tablename__ = "sequencia_protocolo"
    ano: Mapped[int] = mapped_column(Integer, primary_key=True)
    uf: Mapped[str] = mapped_column(String(4), primary_key=True)
    ultimo: Mapped[int] = mapped_column(Integer, default=0)


class Manifestacao(Base):
    __tablename__ = "manifestacao"
    id_manifestacao: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    protocolo: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    codigo_consulta_hash: Mapped[str] = mapped_column(String(200))
    client_msg_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)  # idempotência offline

    # Original (imutável)
    conteudo_original: Mapped[str] = mapped_column(Text)
    original_tipo: Mapped[str] = mapped_column(String(10), default="texto")  # texto | audio
    hash_original: Mapped[str] = mapped_column(String(64))

    canal_origem: Mapped[str] = mapped_column(String(20))  # app_campo | web | whatsapp | sms | presencial
    localidade: Mapped[str | None] = mapped_column(String(200), nullable=True)
    territorio_uf: Mapped[str] = mapped_column(String(4))
    desde_quando: Mapped[str | None] = mapped_column(String(200), nullable=True)
    demanda_coletiva: Mapped[bool] = mapped_column(Boolean, default=False)
    registrado_por: Mapped[str | None] = mapped_column(String(64), nullable=True)  # agente de campo / intermediador
    recursos_acessibilidade: Mapped[list] = mapped_column(JSON, default=list)

    # Camada gerada por IA (sempre marcada como tal)
    resumo_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    resumo_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    transcricao_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcricao_confirmada: Mapped[bool] = mapped_column(Boolean, default=True)

    # Triagem sugerida (nunca decisão)
    tipo_sugerido: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tema_sugerido: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prioridade_sugerida: Mapped[str | None] = mapped_column(String(2), nullable=True)
    area_sugerida: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confianca: Mapped[str | None] = mapped_column(String(10), nullable=True)
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    origem_triagem: Mapped[str | None] = mapped_column(String(40), nullable=True)

    rota: Mapped[str] = mapped_column(String(10), default="comum")  # comum | sigilosa
    emergencia: Mapped[bool] = mapped_column(Boolean, default=False)
    revisao_obrigatoria: Mapped[bool] = mapped_column(Boolean, default=True)
    prioridade_validada: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Retenção (§9.4/§11.4): suspensão por obrigação de guarda e marca de descarte seguro
    retencao_suspensa: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    descartado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status_atual: Mapped[str] = mapped_column(String(20), default="registrada")
    modo_identificacao: Mapped[str] = mapped_column(String(20))  # identificado | sigiloso | anonimo
    id_pessoa: Mapped[str | None] = mapped_column(ForeignKey("pessoa.id_pessoa"), nullable=True)

    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)

    adendos: Mapped[list["Adendo"]] = relationship(back_populates="manifestacao", order_by="Adendo.versao")
    anexos: Mapped[list["Anexo"]] = relationship(back_populates="manifestacao")
    eventos_status: Mapped[list["EventoStatus"]] = relationship(back_populates="manifestacao", order_by="EventoStatus.criado_em")
    encaminhamentos: Mapped[list["Encaminhamento"]] = relationship(back_populates="manifestacao")
    avaliacoes: Mapped[list["AvaliacaoHumana"]] = relationship(back_populates="manifestacao")


class Adendo(Base):
    """Correção, complemento ou contestação — nunca reescreve o original (UC-08)."""

    __tablename__ = "adendo"
    id_adendo: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_manifestacao: Mapped[str] = mapped_column(ForeignKey("manifestacao.id_manifestacao"), index=True)
    versao: Mapped[int] = mapped_column(Integer)
    tipo: Mapped[str] = mapped_column(String(20))  # correcao | complemento | contestacao | transcricao_confirmada
    conteudo: Mapped[str] = mapped_column(Text)
    autor: Mapped[str] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    manifestacao: Mapped[Manifestacao] = relationship(back_populates="adendos")


class Anexo(Base):
    __tablename__ = "anexo"
    id_anexo: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_manifestacao: Mapped[str] = mapped_column(ForeignKey("manifestacao.id_manifestacao"), index=True)
    tipo: Mapped[str] = mapped_column(String(12))  # foto | video | documento | audio
    mime: Mapped[str] = mapped_column(String(60))
    tamanho: Mapped[int] = mapped_column(Integer)
    hash_conteudo: Mapped[str] = mapped_column(String(64))
    armazenamento: Mapped[str] = mapped_column(String(300))  # caminho do arquivo cifrado
    descricao_autor: Mapped[str | None] = mapped_column(Text, nullable=True)
    sensivel: Mapped[bool] = mapped_column(Boolean, default=False)
    descartado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    manifestacao: Mapped[Manifestacao] = relationship(back_populates="anexos")


class Consentimento(Base):
    __tablename__ = "consentimento"
    id_consentimento: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_pessoa: Mapped[str | None] = mapped_column(String(36), nullable=True)
    id_manifestacao: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    finalidade: Mapped[str] = mapped_column(String(30))  # tratamento_manifestacao | notificacoes | pesquisa
    versao_texto: Mapped[str] = mapped_column(String(40))
    aceite_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogacao_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    motivo_revogacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    meio: Mapped[str] = mapped_column(String(20))  # conversa | presencial | web


class Encaminhamento(Base):
    __tablename__ = "encaminhamento"
    id_encaminhamento: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_manifestacao: Mapped[str] = mapped_column(ForeignKey("manifestacao.id_manifestacao"), index=True)
    area_destino: Mapped[str] = mapped_column(String(80))
    responsavel: Mapped[str] = mapped_column(String(80))  # pessoa/função
    prioridade_validada: Mapped[str] = mapped_column(String(2))
    prazo_alvo: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sistema_destino: Mapped[str] = mapped_column(String(20))  # crm | ouvidoria | erp
    principal: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_por: Mapped[str] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    recebido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado_integracao: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente | enviado | erro | dead_letter
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    manifestacao: Mapped[Manifestacao] = relationship(back_populates="encaminhamentos")


class EventoStatus(Base):
    __tablename__ = "evento_status"
    id_evento_status: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_manifestacao: Mapped[str] = mapped_column(ForeignKey("manifestacao.id_manifestacao"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    autor_mudanca: Mapped[str] = mapped_column(String(64))
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    visivel_ao_usuario: Mapped[bool] = mapped_column(Boolean, default=True)
    texto_usuario: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    manifestacao: Mapped[Manifestacao] = relationship(back_populates="eventos_status")


class AvaliacaoHumana(Base):
    __tablename__ = "avaliacao_humana"
    id_avaliacao: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_manifestacao: Mapped[str] = mapped_column(ForeignKey("manifestacao.id_manifestacao"), index=True)
    revisor: Mapped[str] = mapped_column(String(64))
    papel_revisor: Mapped[str] = mapped_column(String(30))
    resultado: Mapped[str] = mapped_column(String(20))  # confirmada | reclassificada | devolvida | sensivel | recusada
    nova_classificacao: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    justificativa: Mapped[str] = mapped_column(Text)
    avaliada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    manifestacao: Mapped[Manifestacao] = relationship(back_populates="avaliacoes")


class ItemFilaHumana(Base):
    """Fila de atendimento humano: nenhum caso sem dono (spec §8.2)."""

    __tablename__ = "fila_humana"
    id_item: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_manifestacao: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    id_sessao: Mapped[str | None] = mapped_column(String(36), nullable=True)
    motivo: Mapped[str] = mapped_column(String(30))  # emergencia | pedido_pessoa | revisao_triagem | sensivel | retaliacao | contestacao | atraso | sistema_desligado | direito_titular
    prioridade: Mapped[str] = mapped_column(String(2))
    rota: Mapped[str] = mapped_column(String(10), default="comum")
    resumo_contexto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    responsavel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assumido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolucao: Mapped[str | None] = mapped_column(Text, nullable=True)


class SessaoConversa(Base):
    """Estado persistente por conversa — retomada sem repetir história (D-07, C6)."""

    __tablename__ = "sessao_conversa"
    id_sessao: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    canal: Mapped[str] = mapped_column(String(20))
    operador: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estado: Mapped[dict] = mapped_column(JSON, default=dict)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)


class TurnoConversa(Base):
    __tablename__ = "turno_conversa"
    id_turno: Mapped[str] = mapped_column(String(36), primary_key=True, default=novo_id)
    id_sessao: Mapped[str] = mapped_column(ForeignKey("sessao_conversa.id_sessao"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    autor: Mapped[str] = mapped_column(String(10))  # usuario | agente
    texto: Mapped[str] = mapped_column(Text)
    client_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    __table_args__ = (UniqueConstraint("id_sessao", "client_msg_id", name="uq_turno_idempotente"),)


class EventoAuditoria(Base):
    __tablename__ = "evento_auditoria"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_evento: Mapped[str] = mapped_column(String(36), default=novo_id, unique=True)
    tipo_evento: Mapped[str] = mapped_column(String(40), index=True)
    objeto: Mapped[str] = mapped_column(String(80))
    ator: Mapped[str] = mapped_column(String(64))
    contexto: Mapped[dict] = mapped_column(JSON, default=dict)
    carimbo_tempo: Mapped[str] = mapped_column(String(40))  # ISO-8601 (incluído no hash)
    hash_anterior: Mapped[str] = mapped_column(String(64))
    hash_evento: Mapped[str] = mapped_column(String(64))


class ChaveDesligamento(Base):
    """Kill switch por módulo (spec §11.8, critério de aceite 18)."""

    __tablename__ = "chave_desligamento"
    modulo: Mapped[str] = mapped_column(String(30), primary_key=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    atualizado_por: Mapped[str] = mapped_column(String(64), default="sistema")
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora, onupdate=agora)
