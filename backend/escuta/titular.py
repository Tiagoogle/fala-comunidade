"""Direitos do titular (LGPD art. 18, art. 20; spec UC-10, §11.3).

Credencial: protocolo + código de consulta (``services.autenticar_titular``).
Nada aqui apaga conteúdo de manifestação automaticamente: pedidos de eliminação
podem esbarrar em obrigação de guarda, por isso viram item na fila do DPO, com o
prazo legal de resposta (art. 19, II: 15 dias) informado ao titular.

O DPO age por protocolo, sem ler o conteúdo do caso (que segue restrito a
revisores e, nos sigilosos, à Ouvidoria).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, crypto, services
from .models import Consentimento, Manifestacao, Pessoa, agora
from .retention import remover_contato
from .safety.pii import mascarar

TITULAR = services.Ator("titular", "titular")
PRAZO_LEGAL_DIAS = 15  # LGPD art. 19, II
TIPOS_PEDIDO = {
    "eliminacao": "eliminação dos dados",
    "anonimizacao": "anonimização",
    "revisao_humana": "revisão por pessoa de classificação ou tratamento",
    "explicacao": "explicação sobre o tratamento",
    "portabilidade": "portabilidade",
    "outro": "outro pedido",
}
EXPLICACAO_TRIAGEM = (
    "A classificação (tipo, tema e prioridade) foi SUGERIDA por regras automáticas e, quando habilitado, por um modelo de IA. "
    "Ela não é decisão: casos prioritários, sensíveis ou de baixa confiança são obrigatoriamente revisados por uma pessoa, "
    "que pode reclassificar com justificativa registrada. Você pode contestar a classificação e pedir revisão por pessoa."
)


def _contato(db: Session, m: Manifestacao) -> dict | None:
    if not m.id_pessoa:
        return None
    p = db.get(Pessoa, m.id_pessoa)
    if p is None or p.dados_removidos_em:
        return {"removido_em": p.dados_removidos_em.isoformat() if p and p.dados_removidos_em else None}
    return {"modo": p.modo_identificacao, "nome": crypto.decifrar_texto(p.nome_cifrado), "contato": crypto.decifrar_texto(p.contato_cifrado)}


def acesso(db: Session, m: Manifestacao, origem: str) -> dict:
    """Cópia completa dos dados do próprio titular sobre esta manifestação (art. 18, I e II)."""
    consent = db.execute(select(Consentimento).where(Consentimento.id_manifestacao == m.id_manifestacao)).scalars().all()
    dados = {
        "gerado_em": agora().isoformat(),
        "protocolo": m.protocolo,
        "relato_original": m.conteudo_original,
        "relato_descartado_em": m.descartado_em.isoformat() if m.descartado_em else None,
        "adendos": [{"versao": a.versao, "tipo": a.tipo, "conteudo": a.conteudo, "em": a.criado_em.isoformat()} for a in m.adendos],
        "local": m.localidade,
        "desde_quando": m.desde_quando,
        "canal": m.canal_origem,
        "modo_identificacao": m.modo_identificacao,
        "seus_dados_de_contato": _contato(db, m),
        "recursos_de_acessibilidade_declarados": m.recursos_acessibilidade,
        "situacao": services.STATUS_TEXTO[m.status_atual],
        "historico": [{"status": services.STATUS_TEXTO[e.status], "em": e.criado_em.isoformat(), "mensagem": e.texto_usuario}
                      for e in m.eventos_status if e.visivel_ao_usuario],
        "classificacao": {
            "tipo": m.tipo_sugerido, "tema": m.tema_sugerido,
            "prioridade_sugerida": m.prioridade_sugerida, "prioridade_validada_por_pessoa": m.prioridade_validada,
            "como_foi_feita": EXPLICACAO_TRIAGEM,
        },
        "encaminhamentos": [{"area": e.area_destino, "responsavel": e.responsavel, "prazo_alvo": e.prazo_alvo.isoformat()}
                            for e in m.encaminhamentos],
        "consentimentos": [{"finalidade": c.finalidade, "versao_do_texto": c.versao_texto,
                            "aceito_em": c.aceite_em.isoformat() if c.aceite_em else None,
                            "revogado_em": c.revogacao_em.isoformat() if c.revogacao_em else None} for c in consent],
        "anexos": [{"tipo": a.tipo, "recebido_em": a.recebido_em.isoformat(), "descartado_em": a.descartado_em.isoformat() if a.descartado_em else None}
                   for a in m.anexos],
        "seus_direitos": ("Você pode pedir correção, anonimização, eliminação, explicação e revisão por pessoa. Alguns dados podem "
                          "precisar ser guardados por obrigação legal; nesse caso o Encarregado de Dados explica o motivo e o prazo."),
    }
    audit.registrar(db, "exportacao", f"manifestacao:{m.id_manifestacao}", origem, {"por": "titular"})
    return dados


def corrigir(db: Session, m: Manifestacao, texto: str, origem: str) -> dict:
    if m.descartado_em:
        raise services.ErroNegocio("este registro já foi descartado conforme a política de retenção")
    ad = services.adicionar_adendo(db, m, "correcao", texto, TITULAR)
    audit.registrar(db, "direito_titular", f"manifestacao:{m.id_manifestacao}", origem, {"direito": "correcao", "versao": ad.versao})
    return {"versao": ad.versao, "mensagem": "Correção registrada. O texto original continua guardado e a equipe responsável foi avisada."}


def revogar(db: Session, m: Manifestacao, finalidade: str, origem: str, motivo: str | None = None) -> dict:
    if finalidade not in ("notificacoes", "tratamento_manifestacao"):
        raise services.ErroNegocio("finalidade inválida")
    agora_ = agora()
    revogados = 0
    for c in db.execute(select(Consentimento).where(Consentimento.id_manifestacao == m.id_manifestacao,
                                                    Consentimento.finalidade == finalidade,
                                                    Consentimento.revogacao_em.is_(None))).scalars():
        c.revogacao_em, c.motivo_revogacao = agora_, (motivo or "")[:500] or None
        revogados += 1
    audit.registrar(db, "consentimento", f"manifestacao:{m.id_manifestacao}", origem,
                    {"finalidade": finalidade, "revogado": True, "registros": revogados})
    if finalidade == "notificacoes":
        return {"mensagem": "Pronto: você não vai mais receber avisos sobre este protocolo. Pode continuar consultando com o código."}

    # Tratamento: o contato sai na hora; o conteúdo pode ter obrigação de guarda -> decisão do DPO.
    if m.id_pessoa:
        p = db.get(Pessoa, m.id_pessoa)
        if p and p.dados_removidos_em is None:
            remover_contato(db, p, origem, motivo="revogacao_consentimento")
    prazo = _abrir_pedido(db, m, "eliminacao", "revogação do consentimento para tratamento", origem)
    return {"mensagem": ("Revogação registrada. Seus dados de contato foram apagados agora. O Encarregado de Proteção de Dados vai "
                         "avaliar o que acontece com o relato — alguns registros podem precisar ser guardados por obrigação legal — "
                         f"e responder até {prazo:%d/%m/%Y}. Consulte pelo protocolo e código."),
            "prazo_resposta": prazo.date().isoformat()}


def pedir(db: Session, m: Manifestacao, tipo: str, detalhe: str | None, origem: str) -> dict:
    if tipo not in TIPOS_PEDIDO:
        raise services.ErroNegocio("tipo de pedido inválido")
    prazo = _abrir_pedido(db, m, tipo, detalhe, origem)
    return {"mensagem": (f"Pedido de {TIPOS_PEDIDO[tipo]} registrado para o Encarregado de Proteção de Dados. "
                         f"O prazo legal de resposta é até {prazo:%d/%m/%Y}."),
            "prazo_resposta": prazo.date().isoformat()}


def _abrir_pedido(db: Session, m: Manifestacao, tipo: str, detalhe: str | None, origem: str):
    prazo = agora() + timedelta(days=PRAZO_LEGAL_DIAS)
    resumo = f"{m.protocolo} · {TIPOS_PEDIDO[tipo]} · prazo legal {prazo:%Y-%m-%d}"
    if detalhe:
        resumo += f" · “{mascarar(detalhe.strip())[:300]}”"
    services._enfileirar(db, m, "direito_titular", "P3", resumo, rota=m.rota)
    audit.registrar(db, "direito_titular", f"manifestacao:{m.id_manifestacao}", origem, {"pedido": tipo, "prazo": prazo.date().isoformat()})
    return prazo


# --------------------------------------------------------------------------- ações do DPO (por protocolo, sem ler conteúdo)

def _por_protocolo(db: Session, protocolo: str, ator: services.Ator) -> Manifestacao:
    if ator.papel != "dpo":
        raise services.AcessoNegado("ação restrita ao Encarregado de Proteção de Dados")
    m = db.execute(select(Manifestacao).where(Manifestacao.protocolo == protocolo.strip().upper())).scalar_one_or_none()
    if m is None:
        raise services.ErroNegocio("protocolo não encontrado")
    return m


def dpo_suspender_retencao(db: Session, protocolo: str, suspensa: bool, justificativa: str, ator: services.Ator) -> Manifestacao:
    if not (justificativa or "").strip():
        raise services.ErroNegocio("justificativa obrigatória")
    m = _por_protocolo(db, protocolo, ator)
    m.retencao_suspensa = suspensa
    audit.registrar(db, "retencao", f"manifestacao:{m.id_manifestacao}", ator.rotulo,
                    {"retencao_suspensa": suspensa, "justificativa": justificativa[:500]})
    return m


def dpo_anonimizar_contato(db: Session, protocolo: str, justificativa: str, ator: services.Ator) -> bool:
    if not (justificativa or "").strip():
        raise services.ErroNegocio("justificativa obrigatória")
    m = _por_protocolo(db, protocolo, ator)
    if not m.id_pessoa:
        return False
    p = db.get(Pessoa, m.id_pessoa)
    if p is None or p.dados_removidos_em:
        return False
    remover_contato(db, p, ator.rotulo, motivo=f"pedido do titular: {justificativa[:200]}")
    return True

