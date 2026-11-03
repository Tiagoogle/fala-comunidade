"""Casos de uso UC-01…UC-12 orquestrados sobre as salvaguardas.

Regras transversais aplicadas aqui:
- todo ato relevante gera evento de auditoria;
- validação, encaminhamento, resposta externa e encerramento são atos humanos;
- falha de módulo de IA ou de integração nunca impede o registro (§8.5).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, crypto, protocol
from .config import get_settings
from .llm import criar_provedor
from .llm.base import ErroProvedor, ProvedorLLM
from .llm.deterministic import ProvedorDeterministico
from .models import (
    Adendo, Anexo, AvaliacaoHumana, ChaveDesligamento, Consentimento, Encaminhamento, EventoStatus,
    ItemFilaHumana, Manifestacao, Pessoa, agora,
)
from .safety import output_guard
from .triage import PRIORIDADES, TEMAS, TIPOS, Triagem, elevar, fundir, mais_protetora, triar_por_regras

log = logging.getLogger(__name__)

STATUS_VALIDOS = ("registrada", "em_validacao", "encaminhada", "em_tratamento", "respondida", "encerrada")
STATUS_TEXTO = {
    "registrada": "registrada",
    "em_validacao": "em validação por uma pessoa da equipe",
    "encaminhada": "encaminhada à área responsável",
    "em_tratamento": "em tratamento pela área responsável",
    "respondida": "respondida",
    "encerrada": "encerrada",
}
MODULOS = ("agente_total", "llm", "triagem_automatica", "base_conhecimento")
PAPEIS_REVISAO = ("revisor", "revisor_sigiloso")


class ErroNegocio(ValueError):
    """Violação de regra de negócio/governança (vira HTTP 4xx)."""


class AcessoNegado(PermissionError):
    pass


@dataclass
class Ator:
    id: str
    papel: str
    territorio: str = "*"

    @property
    def rotulo(self) -> str:
        return f"{self.papel}:{self.id}"


SISTEMA = Ator("escuta", "sistema")


# --------------------------------------------------------------------------- kill switch

def modulo_ativo(db: Session, modulo: str) -> bool:
    chave = db.get(ChaveDesligamento, modulo)
    if chave is None:
        return True
    if modulo != "agente_total" and not modulo_ativo(db, "agente_total"):
        return False
    return chave.ativo


def definir_chave(db: Session, modulo: str, ativo: bool, ator: Ator, motivo: str) -> ChaveDesligamento:
    if ator.papel != "governanca":
        raise AcessoNegado("somente o comitê de governança aciona o desligamento seguro")
    if modulo not in MODULOS:
        raise ErroNegocio(f"módulo desconhecido: {modulo}")
    if not motivo.strip():
        raise ErroNegocio("motivo obrigatório para acionar/reverter desligamento")
    chave = db.get(ChaveDesligamento, modulo) or ChaveDesligamento(modulo=modulo)
    chave.ativo, chave.atualizado_por, chave.motivo = ativo, ator.rotulo, motivo
    db.add(chave)
    audit.registrar(db, "kill_switch", f"modulo:{modulo}", ator.rotulo, {"ativo": ativo, "motivo": motivo})
    return chave


def estado_chaves(db: Session) -> dict[str, bool]:
    return {m: modulo_ativo(db, m) for m in MODULOS}


# --------------------------------------------------------------------------- provedor de IA

_provedor: ProvedorLLM | None = None


def provedor(db: Session) -> ProvedorLLM:
    global _provedor
    if not modulo_ativo(db, "llm"):
        return ProvedorDeterministico()
    if _provedor is None:
        _provedor = criar_provedor()
    return _provedor


def definir_provedor(p: ProvedorLLM | None) -> None:
    """Injeção para testes ou troca de fornecedor em runtime."""
    global _provedor
    _provedor = p


def resumir_seguro(db: Session, relato: str, objeto: str) -> tuple[str, str]:
    """Resumo do modelo passado pela guarda de saída. Retorna (resumo, origem)."""
    p = provedor(db)
    determ = ProvedorDeterministico().resumir(relato)
    if not p.usa_modelo:
        return determ, "fala_original"
    try:
        resumo = p.resumir(relato)
    except ErroProvedor as e:
        audit.registrar(db, "llm_falha", objeto, SISTEMA.rotulo, {"tarefa": "resumo", "erro": str(e)[:200]})
        return determ, "fala_original"
    g = output_guard.verificar(resumo, [relato])
    if not g.aprovado:
        audit.registrar(db, "bloqueio_saida", objeto, SISTEMA.rotulo, {"tarefa": "resumo", "violacoes": g.violacoes})
        return determ, "fala_original"
    return resumo, "ia"


def triar(db: Session, texto: str, objeto: str) -> Triagem:
    regras = triar_por_regras(texto)
    if not modulo_ativo(db, "triagem_automatica"):
        # Triagem 100% humana transitória: mantém detecção de emergência (segurança),
        # mas nenhuma sugestão é tratada como confiável.
        regras.confianca = "baixa"
        regras.revisao_obrigatoria = True
        regras.origem = "triagem_humana_obrigatoria"
        return regras
    p = provedor(db)
    if not p.usa_modelo:
        return regras
    try:
        sug = p.sugerir_triagem(texto)
    except ErroProvedor as e:
        audit.registrar(db, "llm_falha", objeto, SISTEMA.rotulo, {"tarefa": "triagem", "erro": str(e)[:200]})
        return regras
    if sug is not None:
        g = output_guard.verificar(sug.justificativa, [texto])
        if not g.aprovado:
            audit.registrar(db, "bloqueio_saida", objeto, SISTEMA.rotulo, {"tarefa": "triagem", "violacoes": g.violacoes})
            sug.justificativa = "(justificativa do modelo descartada pela guarda de saída)"
    return fundir(regras, sug, texto)


# --------------------------------------------------------------------------- registro (UC-01/03/09)

@dataclass
class NovoRegistro:
    relato: str
    canal_origem: str = "app_campo"
    localidade: str | None = None
    desde_quando: str | None = None
    uf: str | None = None
    modo_identificacao: str = "anonimo"  # identificado | sigiloso | anonimo
    nome: str | None = None
    contato: str | None = None
    consentimento_tratamento: bool = False
    consentimento_notificacoes: bool = False
    meio_consentimento: str = "conversa"
    resumo_confirmado: bool = False
    resumo: str | None = None
    demanda_coletiva: bool = False
    recursos_acessibilidade: list[str] = field(default_factory=list)
    client_msg_id: str | None = None
    codigo_consulta: str | None = None  # gerado no dispositivo em modo offline
    original_tipo: str = "texto"
    transcricao_pendente: bool = False
    pedido_pessoa: bool = False


@dataclass
class ResultadoRegistro:
    manifestacao: Manifestacao
    codigo_consulta: str | None
    triagem: Triagem
    duplicado: bool = False


def _validar_codigo(codigo: str | None) -> str:
    if codigo is None:
        return protocol.gerar_codigo_consulta()
    dig = re.sub(r"\D", "", codigo)
    if len(dig) != 6:
        raise ErroNegocio("código de consulta deve ter 6 dígitos")
    return dig


def registrar_manifestacao(db: Session, dados: NovoRegistro, ator: Ator) -> ResultadoRegistro:
    s = get_settings()
    if not dados.relato or not dados.relato.strip():
        raise ErroNegocio("relato vazio")
    if dados.modo_identificacao not in ("identificado", "sigiloso", "anonimo"):
        raise ErroNegocio("modo de identificação inválido")
    if not dados.consentimento_tratamento:
        raise ErroNegocio("consentimento para tratamento da manifestação não registrado")
    if dados.client_msg_id:
        existente = db.execute(select(Manifestacao).where(Manifestacao.client_msg_id == dados.client_msg_id)).scalar_one_or_none()
        if existente is not None:
            triagem_existente = triar_por_regras(existente.conteudo_original)
            return ResultadoRegistro(existente, None, triagem_existente, duplicado=True)

    codigo = _validar_codigo(dados.codigo_consulta)
    pessoa = None
    if dados.modo_identificacao != "anonimo":
        pessoa = Pessoa(
            modo_identificacao=dados.modo_identificacao,
            nome_cifrado=crypto.cifrar_texto((dados.nome or "").strip() or None),
            contato_cifrado=crypto.cifrar_texto((dados.contato or "").strip() or None),
            perfil_acessibilidade=list(dados.recursos_acessibilidade),
        )
        db.add(pessoa)
        db.flush()

    uf = (dados.uf or (ator.territorio if ator.territorio not in ("*", "") else s.uf_padrao)).upper()[:2]
    numero = protocol.proximo_protocolo(db, uf)
    m = Manifestacao(
        protocolo=numero,
        codigo_consulta_hash=protocol.hash_codigo(codigo),
        client_msg_id=dados.client_msg_id,
        conteudo_original=dados.relato,
        original_tipo=dados.original_tipo,
        hash_original=crypto.sha256(dados.relato),
        canal_origem=dados.canal_origem,
        localidade=dados.localidade,
        desde_quando=dados.desde_quando,
        territorio_uf=uf,
        demanda_coletiva=dados.demanda_coletiva,
        registrado_por=ator.rotulo if ator.papel != "sistema" else None,
        recursos_acessibilidade=list(dados.recursos_acessibilidade),
        modo_identificacao=dados.modo_identificacao,
        id_pessoa=pessoa.id_pessoa if pessoa else None,
        transcricao_confirmada=not dados.transcricao_pendente,
    )
    db.add(m)
    db.flush()
    objeto = f"manifestacao:{m.id_manifestacao}"
    audit.registrar(db, "criacao", objeto, ator.rotulo, {
        "protocolo": numero, "canal": dados.canal_origem, "modo_identificacao": dados.modo_identificacao,
        "hash_original": m.hash_original, "offline": bool(dados.client_msg_id),
    })

    for finalidade, aceito in (("tratamento_manifestacao", True), ("notificacoes", dados.consentimento_notificacoes)):
        if aceito:
            db.add(Consentimento(id_pessoa=pessoa.id_pessoa if pessoa else None, id_manifestacao=m.id_manifestacao,
                                 finalidade=finalidade, versao_texto=s.versao_texto_consentimento, aceite_em=agora(),
                                 meio=dados.meio_consentimento))
            audit.registrar(db, "consentimento", objeto, ator.rotulo, {"finalidade": finalidade, "versao": s.versao_texto_consentimento})

    if dados.resumo:
        m.resumo_ia, m.resumo_confirmado = dados.resumo, dados.resumo_confirmado
    else:
        m.resumo_ia, _origem = resumir_seguro(db, dados.relato, objeto)
        m.resumo_confirmado = False

    t = triar(db, _texto_completo(m, extra=[dados.localidade or "", dados.desde_quando or ""]), objeto)
    _aplicar_triagem(m, t)
    if dados.transcricao_pendente:
        m.revisao_obrigatoria = True
    audit.registrar(db, "triagem_sugerida", objeto, SISTEMA.rotulo, {
        "tipo": t.tipo, "tema": t.tema, "prioridade": t.prioridade, "confianca": t.confianca,
        "origem": t.origem, "rota": t.rota, "revisao_obrigatoria": m.revisao_obrigatoria,
    })

    status_inicial = "em_validacao" if m.revisao_obrigatoria else "registrada"
    _registrar_status(db, m, "registrada", SISTEMA, "registro criado", visivel=True)
    if status_inicial != "registrada":
        _registrar_status(db, m, status_inicial, SISTEMA, "revisão humana obrigatória", visivel=True)

    resumo_ctx = f"{numero} · {t.tipo}/{t.tema} · {t.prioridade}"
    if t.emergencia:
        acionar_emergencia(db, m, ator)
    if t.rota == "sigilosa":
        _enfileirar(db, m, "retaliacao" if "retalia" in t.justificativa else "sensivel", t.prioridade, resumo_ctx, rota="sigilosa")
    elif m.revisao_obrigatoria and not t.emergencia:
        motivo = "sensivel" if t.temas_sensiveis else "revisao_triagem"
        _enfileirar(db, m, motivo, t.prioridade, resumo_ctx)
    if dados.pedido_pessoa:
        _enfileirar(db, m, "pedido_pessoa", mais_protetora(t.prioridade, "P3"), resumo_ctx, rota=t.rota)
    return ResultadoRegistro(m, codigo, t)


def _texto_completo(m: Manifestacao, extra: list[str] | None = None) -> str:
    partes = [m.conteudo_original] + [a.conteudo for a in m.adendos if a.tipo != "contestacao"] + [m.transcricao_ia or ""] + (extra or [])
    return "\n".join(p for p in partes if p)


def _aplicar_triagem(m: Manifestacao, t: Triagem) -> None:
    m.tipo_sugerido, m.tema_sugerido, m.prioridade_sugerida = t.tipo, t.tema, t.prioridade
    m.area_sugerida, m.confianca, m.justificativa, m.origem_triagem = t.area_sugerida, t.confianca, t.justificativa, t.origem
    # rota sigilosa e emergência nunca são rebaixadas por retriagem
    m.rota = "sigilosa" if (m.rota == "sigilosa" or t.rota == "sigilosa") else "comum"
    m.emergencia = m.emergencia or t.emergencia
    m.revisao_obrigatoria = t.revisao_obrigatoria or m.rota == "sigilosa" or m.emergencia or not m.transcricao_confirmada


def _registrar_status(db: Session, m: Manifestacao, status: str, ator: Ator, justificativa: str | None,
                      visivel: bool = True, texto_usuario: str | None = None) -> EventoStatus:
    if status not in STATUS_VALIDOS:
        raise ErroNegocio(f"status inválido: {status}")
    ev = EventoStatus(id_manifestacao=m.id_manifestacao, status=status, autor_mudanca=ator.rotulo,
                      justificativa=justificativa, visivel_ao_usuario=visivel, texto_usuario=texto_usuario)
    db.add(ev)
    m.status_atual = status
    db.flush()
    audit.registrar(db, "status", f"manifestacao:{m.id_manifestacao}", ator.rotulo, {"status": status, "visivel": visivel})
    return ev


def _enfileirar(db: Session, m: Manifestacao | None, motivo: str, prioridade: str, resumo: str,
                rota: str = "comum", id_sessao: str | None = None) -> ItemFilaHumana:
    item = ItemFilaHumana(id_manifestacao=m.id_manifestacao if m else None, id_sessao=id_sessao, motivo=motivo,
                          prioridade=prioridade, rota=rota, resumo_contexto=resumo)
    db.add(item)
    db.flush()
    audit.registrar(db, "fila", f"fila:{item.id_item}", SISTEMA.rotulo, {"motivo": motivo, "prioridade": prioridade, "rota": rota,
                                                                        "manifestacao": item.id_manifestacao})
    return item


# --------------------------------------------------------------------------- emergência (UC-04)

def acionar_emergencia(db: Session, m: Manifestacao, ator: Ator) -> ItemFilaHumana:
    objeto = f"manifestacao:{m.id_manifestacao}"
    m.emergencia, m.revisao_obrigatoria = True, True
    m.prioridade_sugerida = "P1"
    audit.registrar(db, "emergencia_detectada", objeto, ator.rotulo, {"protocolo": m.protocolo})
    item = _enfileirar(db, m, "emergencia", "P1", f"EMERGÊNCIA · {m.protocolo} · {m.localidade or 'local não informado'}", rota=m.rota)
    audit.registrar(db, "emergencia_notificada", objeto, SISTEMA.rotulo, {"fila": item.id_item})
    return item


# --------------------------------------------------------------------------- adendos e contestação (UC-08, D-09)

def adicionar_adendo(db: Session, m: Manifestacao, tipo: str, conteudo: str, ator: Ator) -> Adendo:
    if tipo not in ("correcao", "complemento", "contestacao"):
        raise ErroNegocio("tipo de adendo inválido")
    if not conteudo.strip():
        raise ErroNegocio("adendo vazio")
    objeto = f"manifestacao:{m.id_manifestacao}"
    ad = Adendo(id_manifestacao=m.id_manifestacao, versao=len(m.adendos) + 1, tipo=tipo, conteudo=conteudo, autor=ator.rotulo)
    db.add(ad)
    db.flush()
    db.refresh(m)
    audit.registrar(db, "adendo", objeto, ator.rotulo, {"versao": ad.versao, "tipo": tipo})
    prioridade_antes = m.prioridade_validada or m.prioridade_sugerida or "P4"

    if tipo == "contestacao":
        nova = elevar(prioridade_antes)
        m.prioridade_sugerida = mais_protetora(m.prioridade_sugerida or "P4", nova)
        m.justificativa = (m.justificativa or "") + f" | Contestação do autor: prioridade elevada para {m.prioridade_sugerida} (mais protetora) até revisão humana."
        m.revisao_obrigatoria = True
        if m.status_atual == "registrada":
            _registrar_status(db, m, "em_validacao", SISTEMA, "contestação do autor", visivel=True)
        _enfileirar(db, m, "contestacao", m.prioridade_sugerida, f"{m.protocolo} · contestação da classificação", rota=m.rota)
        return ad

    t = triar(db, _texto_completo(m), objeto)
    prioridade_nova = mais_protetora(prioridade_antes, t.prioridade)
    mudou = prioridade_nova != prioridade_antes or t.emergencia and not m.emergencia
    _aplicar_triagem(m, t)
    m.prioridade_sugerida = prioridade_nova
    if t.emergencia and not any(i for i in _fila_aberta(db, m) if i.motivo == "emergencia"):
        acionar_emergencia(db, m, ator)
    elif mudou:
        m.revisao_obrigatoria = True
        _enfileirar(db, m, "revisao_triagem", prioridade_nova, f"{m.protocolo} · prioridade alterada por adendo ({prioridade_antes}→{prioridade_nova})", rota=m.rota)
    if m.encaminhamentos:
        _registrar_status(db, m, m.status_atual, SISTEMA, f"adendo v{ad.versao} — área notificada", visivel=False)
    return ad


def _fila_aberta(db: Session, m: Manifestacao) -> list[ItemFilaHumana]:
    return list(db.execute(select(ItemFilaHumana).where(ItemFilaHumana.id_manifestacao == m.id_manifestacao,
                                                        ItemFilaHumana.resolvido_em.is_(None))).scalars())


def confirmar_transcricao(db: Session, m: Manifestacao, texto_confirmado: str, ator: Ator) -> None:
    m.transcricao_ia = texto_confirmado
    m.transcricao_confirmada = True
    db.add(Adendo(id_manifestacao=m.id_manifestacao, versao=len(m.adendos) + 1, tipo="complemento",
                  conteudo=f"[transcrição confirmada] {texto_confirmado}", autor=ator.rotulo))
    db.flush()
    db.refresh(m)
    t = triar(db, _texto_completo(m), f"manifestacao:{m.id_manifestacao}")
    _aplicar_triagem(m, t)
    if t.emergencia and not any(i.motivo == "emergencia" for i in _fila_aberta(db, m)):
        acionar_emergencia(db, m, ator)


# --------------------------------------------------------------------------- consulta de status (UC-07)

_TENTATIVAS: dict[str, list[float]] = {}


def consultar_status(db: Session, numero: str, codigo: str, origem: str = "anon") -> dict | None:
    import time

    janela = [t for t in _TENTATIVAS.get(origem, []) if time.time() - t < 600]
    if len(janela) >= 10:
        audit.registrar(db, "tentativa_negada", "consulta_status", origem, {"motivo": "limite de tentativas"})
        raise AcessoNegado("muitas tentativas; tente novamente mais tarde ou fale com a equipe")
    janela.append(time.time())
    _TENTATIVAS[origem] = janela

    m = db.execute(select(Manifestacao).where(Manifestacao.protocolo == (numero or "").strip().upper())).scalar_one_or_none()
    if m is None or not protocol.verificar_codigo(codigo, m.codigo_consulta_hash):
        audit.registrar(db, "tentativa_negada", "consulta_status", origem, {"motivo": "protocolo/código não conferem"})
        return None  # resposta idêntica para inexistente e código errado: não confirma existência
    audit.registrar(db, "consulta_status", f"manifestacao:{m.id_manifestacao}", origem, {})
    s = get_settings()
    enc = next((e for e in m.encaminhamentos if e.principal), None)
    eventos = [{"status": STATUS_TEXTO[e.status], "quando": e.criado_em.isoformat(), "mensagem": e.texto_usuario}
               for e in m.eventos_status if e.visivel_ao_usuario]
    prio = m.prioridade_validada or m.prioridade_sugerida or "P4"
    atrasado = bool(enc and enc.concluido_em is None and _aware(enc.prazo_alvo) < agora())
    if atrasado:
        verificar_atrasos(db)
    return {
        "protocolo": m.protocolo,
        "situacao": STATUS_TEXTO[m.status_atual],
        "area_responsavel": enc.area_destino if enc else None,
        "responsavel_funcao": enc.responsavel if enc else None,
        "prazo_alvo": enc.prazo_alvo.isoformat() if enc else None,
        "janela_alvo": s.janelas[prio].janela_texto,
        "aviso_prazo": "O prazo-alvo é um alvo interno de trabalho, não uma promessa.",
        "atrasado": atrasado,
        "historico": eventos,
        "mensagem": _mensagem_status(m, enc, atrasado),
    }


def _aware(dt):
    from datetime import timezone

    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _mensagem_status(m: Manifestacao, enc: Encaminhamento | None, atrasado: bool) -> str:
    base = f"Seu protocolo {m.protocolo} está {STATUS_TEXTO[m.status_atual]}"
    if enc:
        base += f", com a área de {enc.area_destino} (responsável: {enc.responsavel}). Prazo-alvo: {enc.prazo_alvo:%d/%m/%Y}"
    base += "."
    if atrasado:
        base += " O prazo-alvo passou sem conclusão — isso já foi sinalizado para a coordenação."
    return base + " Se quiser, uma pessoa explica com mais detalhe — é só pedir."


# --------------------------------------------------------------------------- revisão humana e encaminhamento (UC-11, B15)

def pode_ver(ator: Ator, m: Manifestacao) -> bool:
    if m.rota == "sigilosa":
        return ator.papel == "revisor_sigiloso"
    if ator.papel == "revisor_sigiloso":
        return True
    if ator.papel == "revisor":
        return ator.territorio in ("*", m.territorio_uf)
    if ator.papel == "agente_campo":
        return m.registrado_por == ator.rotulo or ator.territorio in ("*", m.territorio_uf)
    return False  # gestor/governança: apenas agregados e trilha


def obter_para(db: Session, id_manifestacao: str, ator: Ator) -> Manifestacao:
    m = db.get(Manifestacao, id_manifestacao)
    if m is None:
        raise ErroNegocio("manifestação não encontrada")
    if not pode_ver(ator, m):
        audit.registrar(db, "tentativa_negada", f"manifestacao:{id_manifestacao}", ator.rotulo, {"acao": "leitura"})
        raise AcessoNegado("sem permissão para este caso")
    audit.registrar(db, "acesso", f"manifestacao:{id_manifestacao}", ator.rotulo, {})
    return m


def avaliar(db: Session, m: Manifestacao, ator: Ator, resultado: str, justificativa: str,
            nova_classificacao: dict | None = None) -> AvaliacaoHumana:
    if ator.papel not in PAPEIS_REVISAO:
        raise AcessoNegado("somente revisores autorizados validam triagem")
    if not pode_ver(ator, m):
        raise AcessoNegado("rota sigilosa: somente revisores sigilosos")
    if resultado not in ("confirmada", "reclassificada", "devolvida", "sensivel", "recusada"):
        raise ErroNegocio("resultado inválido")
    if not (justificativa or "").strip():
        raise ErroNegocio("justificativa obrigatória em decisão humana")
    if m.registrado_por == ator.rotulo:
        raise ErroNegocio("conflito de interesse: quem registrou não valida o próprio caso (B2)")
    nova = None
    if resultado == "reclassificada":
        nova = dict(nova_classificacao or {})
        if nova.get("prioridade") not in PRIORIDADES:
            raise ErroNegocio("reclassificação exige prioridade P1–P4")
        if nova.get("tipo") and nova["tipo"] not in TIPOS:
            raise ErroNegocio("tipo inválido")
        if nova.get("tema") and nova["tema"] not in TEMAS:
            raise ErroNegocio("tema inválido")
        m.prioridade_validada = nova["prioridade"]
    elif resultado == "confirmada":
        m.prioridade_validada = m.prioridade_sugerida
    elif resultado == "sensivel":
        m.rota = "sigilosa"
        m.prioridade_validada = mais_protetora(m.prioridade_sugerida or "P4", "P2")
    av = AvaliacaoHumana(id_manifestacao=m.id_manifestacao, revisor=ator.rotulo, papel_revisor=ator.papel,
                         resultado=resultado, nova_classificacao=nova, justificativa=justificativa)
    db.add(av)
    audit.registrar(db, "avaliacao_humana", f"manifestacao:{m.id_manifestacao}", ator.rotulo,
                    {"resultado": resultado, "prioridade_validada": m.prioridade_validada})
    for item in _fila_aberta(db, m):
        if item.motivo in ("revisao_triagem", "sensivel", "contestacao") and resultado != "devolvida":
            item.resolvido_em, item.resolucao, item.responsavel = agora(), f"avaliação: {resultado}", ator.rotulo
    if resultado == "sensivel":
        _enfileirar(db, m, "sensivel", m.prioridade_validada or "P2", f"{m.protocolo} · marcado sensível por revisor", rota="sigilosa")
    db.flush()
    return av


def encaminhar(db: Session, m: Manifestacao, ator: Ator, area: str, responsavel: str, sistema: str | None = None,
               principal: bool = True) -> Encaminhamento:
    if ator.papel not in PAPEIS_REVISAO:
        raise AcessoNegado("encaminhamento é ato humano de revisor autorizado")
    if not pode_ver(ator, m):
        raise AcessoNegado("sem permissão para este caso")
    if not m.prioridade_validada:
        raise ErroNegocio("triagem ainda não validada por pessoa — encaminhamento bloqueado (B15)")
    if not m.transcricao_confirmada:
        raise ErroNegocio("transcrição de áudio não confirmada — encaminhamento bloqueado")
    if not area.strip() or not responsavel.strip():
        raise ErroNegocio("área e responsável (pessoa/função) obrigatórios — nenhum caso sem dono")
    sistema = "ouvidoria" if m.rota == "sigilosa" else (sistema or "crm")
    if sistema not in ("crm", "ouvidoria", "erp"):
        raise ErroNegocio("sistema de destino inválido")
    s = get_settings()
    janela = s.janelas[m.prioridade_validada]
    enc = Encaminhamento(id_manifestacao=m.id_manifestacao, area_destino=area, responsavel=responsavel,
                         prioridade_validada=m.prioridade_validada, prazo_alvo=agora() + timedelta(hours=janela.horas_uteis_alvo),
                         sistema_destino=sistema, principal=principal, criado_por=ator.rotulo)
    db.add(enc)
    db.flush()
    audit.registrar(db, "encaminhamento", f"manifestacao:{m.id_manifestacao}", ator.rotulo,
                    {"area": area, "sistema": sistema, "prioridade": m.prioridade_validada, "encaminhamento": enc.id_encaminhamento})
    texto = (f"Sua manifestação foi encaminhada para {area}, responsável {responsavel}, com prazo-alvo de "
             f"{janela.janela_texto}. Você pode acompanhar pelo protocolo e pedir para falar com a pessoa responsável quando quiser.")
    _registrar_status(db, m, "encaminhada", ator, f"encaminhado a {area}", visivel=True, texto_usuario=texto)
    return enc


def mudar_status(db: Session, m: Manifestacao, ator: Ator, status: str, justificativa: str, texto_usuario: str | None = None,
                 visivel: bool = True, encerrar_emergencia: bool = False) -> EventoStatus:
    if ator.papel not in PAPEIS_REVISAO:
        raise AcessoNegado("mudança manual de status é ato de pessoa autorizada")
    if not pode_ver(ator, m):
        raise AcessoNegado("sem permissão para este caso")
    if not (justificativa or "").strip():
        raise ErroNegocio("justificativa obrigatória em mudança manual de status")
    if status == "encerrada":
        if not m.prioridade_validada:
            raise ErroNegocio("encerramento exige triagem validada por pessoa")
        if m.emergencia and not encerrar_emergencia:
            raise ErroNegocio("caso em estado de emergência só sai por decisão humana explícita (encerrar_emergencia)")
    ev = _registrar_status(db, m, status, ator, justificativa, visivel=visivel, texto_usuario=texto_usuario)
    if status == "encerrada":
        for item in _fila_aberta(db, m):
            item.resolvido_em, item.resolucao, item.responsavel = agora(), "caso encerrado", ator.rotulo
        for enc in m.encaminhamentos:
            enc.concluido_em = enc.concluido_em or agora()
    return ev


def verificar_atrasos(db: Session) -> int:
    """Sinaliza à coordenação encaminhamentos com prazo-alvo vencido (UC-11 passo 5)."""
    n = 0
    vencidos = db.execute(select(Encaminhamento).where(Encaminhamento.concluido_em.is_(None))).scalars()
    for enc in vencidos:
        if _aware(enc.prazo_alvo) >= agora():
            continue
        m = enc.manifestacao
        if any(i.motivo == "atraso" for i in _fila_aberta(db, m)):
            continue
        _enfileirar(db, m, "atraso", elevar(enc.prioridade_validada), f"{m.protocolo} · prazo-alvo vencido em {enc.area_destino}", rota=m.rota)
        n += 1
    return n


# --------------------------------------------------------------------------- fila humana

def listar_fila(db: Session, ator: Ator, abertos: bool = True) -> list[ItemFilaHumana]:
    if ator.papel not in PAPEIS_REVISAO + ("agente_campo",):
        raise AcessoNegado("sem acesso à fila")
    q = select(ItemFilaHumana)
    if abertos:
        q = q.where(ItemFilaHumana.resolvido_em.is_(None))
    itens = list(db.execute(q).scalars())
    if ator.papel != "revisor_sigiloso":
        itens = [i for i in itens if i.rota == "comum"]
    if ator.papel == "agente_campo":
        itens = [i for i in itens if i.motivo in ("emergencia", "pedido_pessoa")]
    ordem = {p: i for i, p in enumerate(PRIORIDADES)}
    itens.sort(key=lambda i: (ordem.get(i.prioridade, 9), i.criado_em))
    return itens


def assumir_item(db: Session, id_item: str, ator: Ator) -> ItemFilaHumana:
    item = db.get(ItemFilaHumana, id_item)
    if item is None:
        raise ErroNegocio("item não encontrado")
    if item.rota == "sigilosa" and ator.papel != "revisor_sigiloso":
        raise AcessoNegado("rota sigilosa")
    if ator.papel not in PAPEIS_REVISAO + ("agente_campo",):
        raise AcessoNegado("sem acesso à fila")
    item.responsavel, item.assumido_em = ator.rotulo, agora()
    audit.registrar(db, "escalonamento", f"fila:{id_item}", ator.rotulo, {"acao": "assumido", "motivo": item.motivo})
    return item


def resolver_item(db: Session, id_item: str, ator: Ator, resolucao: str) -> ItemFilaHumana:
    item = db.get(ItemFilaHumana, id_item)
    if item is None:
        raise ErroNegocio("item não encontrado")
    if item.responsavel != ator.rotulo:
        raise ErroNegocio("assuma o item antes de resolvê-lo")
    if not resolucao.strip():
        raise ErroNegocio("descreva o que foi feito")
    item.resolvido_em, item.resolucao = agora(), resolucao
    audit.registrar(db, "escalonamento", f"fila:{id_item}", ator.rotulo, {"acao": "resolvido", "motivo": item.motivo})
    return item


# --------------------------------------------------------------------------- anexos (UC-06)

_SENSIVEL_ANEXO = re.compile(r"crianc|violenc|ferid|sangue|nu[ae]?\b|documento de|exame|laudo", re.I)


def salvar_anexo(db: Session, m: Manifestacao, dados: bytes, mime: str, ator: Ator, descricao: str | None = None) -> Anexo:
    s = get_settings()
    if mime not in s.tipos_anexo_permitidos:
        raise ErroNegocio("tipo de arquivo não suportado — você pode descrever o conteúdo em texto ou entregar à equipe de campo")
    if len(dados) > s.max_anexo_bytes:
        raise ErroNegocio("arquivo grande demais — tente um arquivo menor ou entregue à equipe de campo")
    tipo = "foto" if mime.startswith("image/") else "audio" if mime.startswith("audio/") else "video" if mime.startswith("video/") else "documento"
    h = crypto.sha256(dados)
    s.dir_anexos.mkdir(parents=True, exist_ok=True)
    caminho = s.dir_anexos / f"{h}.bin"
    caminho.write_bytes(crypto.cifrar_bytes(dados))
    sensivel = bool(descricao and _SENSIVEL_ANEXO.search(descricao)) or m.rota == "sigilosa"
    an = Anexo(id_manifestacao=m.id_manifestacao, tipo=tipo, mime=mime, tamanho=len(dados), hash_conteudo=h,
               armazenamento=str(caminho), descricao_autor=descricao, sensivel=sensivel)
    db.add(an)
    db.flush()
    audit.registrar(db, "anexo_recebido", f"anexo:{an.id_anexo}", ator.rotulo, {"manifestacao": m.id_manifestacao, "tipo": tipo, "hash": h})
    if sensivel and m.rota == "comum":
        _enfileirar(db, m, "sensivel", mais_protetora(m.prioridade_sugerida or "P4", "P2"), f"{m.protocolo} · anexo sensível")
    if tipo == "audio" and m.original_tipo == "audio" and not m.transcricao_confirmada:
        m.revisao_obrigatoria = True
    return an


def ler_anexo(db: Session, id_anexo: str, ator: Ator, motivo: str) -> tuple[Anexo, bytes]:
    an = db.get(Anexo, id_anexo)
    if an is None:
        raise ErroNegocio("anexo não encontrado")
    m = an.manifestacao
    if ator.papel not in PAPEIS_REVISAO or not pode_ver(ator, m) or (an.sensivel and ator.papel != "revisor_sigiloso"):
        audit.registrar(db, "tentativa_negada", f"anexo:{id_anexo}", ator.rotulo, {"acao": "leitura_anexo"})
        raise AcessoNegado("acesso a anexo restrito a revisores autorizados do caso")
    if not (motivo or "").strip():
        raise ErroNegocio("informe o motivo do acesso (quem, quando e por quê)")
    dados = crypto.decifrar_bytes(open(an.armazenamento, "rb").read())
    if crypto.sha256(dados) != an.hash_conteudo:
        audit.registrar(db, "incidente", f"anexo:{id_anexo}", SISTEMA.rotulo, {"motivo": "hash não confere"})
        raise ErroNegocio("integridade do anexo comprometida — incidente registrado")
    audit.registrar(db, "anexo_acessado", f"anexo:{id_anexo}", ator.rotulo, {"motivo": motivo})
    return an, dados


# --------------------------------------------------------------------------- visão do caso para revisores

def visao_caso(m: Manifestacao, ator: Ator) -> dict:
    """Contato do autor fica fora: só via ``contato_do_autor`` com motivo auditado."""
    from .safety.pii import mascarar

    return {
        "id": m.id_manifestacao,
        "protocolo": m.protocolo,
        "conteudo_original": m.conteudo_original,
        "original_tipo": m.original_tipo,
        "hash_original": m.hash_original,
        "resumo_ia": m.resumo_ia,
        "resumo_confirmado": m.resumo_confirmado,
        "transcricao_confirmada": m.transcricao_confirmada,
        "adendos": [{"versao": a.versao, "tipo": a.tipo, "conteudo": a.conteudo, "autor": a.autor, "em": a.criado_em.isoformat()} for a in m.adendos],
        "canal": m.canal_origem,
        "localidade": m.localidade,
        "desde_quando": m.desde_quando,
        "territorio": m.territorio_uf,
        "modo_identificacao": m.modo_identificacao,
        "triagem_sugerida": {
            "gerada_por": "IA/regras — sugestão, não decisão",
            "tipo": m.tipo_sugerido, "tema": m.tema_sugerido, "prioridade": m.prioridade_sugerida,
            "area": m.area_sugerida, "confianca": m.confianca, "justificativa": mascarar(m.justificativa), "origem": m.origem_triagem,
        },
        "prioridade_validada": m.prioridade_validada,
        "rota": m.rota,
        "emergencia": m.emergencia,
        "revisao_obrigatoria": m.revisao_obrigatoria,
        "status": m.status_atual,
        "anexos": [{"id": a.id_anexo, "tipo": a.tipo, "tamanho": a.tamanho, "sensivel": a.sensivel, "descricao": a.descricao_autor} for a in m.anexos],
        "encaminhamentos": [{"area": e.area_destino, "responsavel": e.responsavel, "prazo_alvo": e.prazo_alvo.isoformat(),
                             "sistema": e.sistema_destino, "integracao": e.estado_integracao} for e in m.encaminhamentos],
        "avaliacoes": [{"revisor": a.revisor, "resultado": a.resultado, "justificativa": a.justificativa,
                        "em": a.avaliada_em.isoformat()} for a in m.avaliacoes],
        "criada_em": m.criada_em.isoformat(),
    }


def contato_do_autor(db: Session, m: Manifestacao, ator: Ator, motivo: str) -> dict:
    """Dados de contato só para retorno, por revisor do caso, com motivo auditado."""
    if ator.papel not in PAPEIS_REVISAO or not pode_ver(ator, m):
        raise AcessoNegado("sem permissão")
    if m.modo_identificacao == "anonimo" or not m.id_pessoa:
        return {"modo": "anonimo", "nome": None, "contato": None}
    if not (motivo or "").strip():
        raise ErroNegocio("informe o motivo do acesso ao contato")
    p = db.get(Pessoa, m.id_pessoa)
    audit.registrar(db, "acesso", f"pessoa:{m.id_pessoa}", ator.rotulo, {"motivo": motivo, "campo": "contato"})
    return {"modo": p.modo_identificacao, "nome": crypto.decifrar_texto(p.nome_cifrado), "contato": crypto.decifrar_texto(p.contato_cifrado)}
