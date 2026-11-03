"""API REST do Escuta+ (FastAPI).

Autenticação do MVP por chave de acesso (cabeçalho ``X-Chave-Acesso``)
mapeada a papel/território; em produção, SSO corporativo (spec §11.2).
Rotas públicas: consulta de status (protocolo + código) e privacidade.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit, conversation, indicators, integrations, knowledge, services
from ..config import get_settings
from ..db import SessionLocal, ViolacaoImutabilidade
from ..models import SessaoConversa

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

app = FastAPI(title="Escuta+ — API", version="0.1.0",
              description="Facilitador de escuta comunitária com supervisão humana permanente. O agente não decide.")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ator_atual(x_chave_acesso: str | None = Header(default=None)) -> services.Ator:
    if not x_chave_acesso:
        raise HTTPException(401, "informe a chave de acesso")
    info = get_settings().chaves_acesso.get(x_chave_acesso)
    if not info:
        raise HTTPException(401, "chave de acesso inválida")
    return services.Ator(id=info["id"], papel=info["papel"], territorio=info.get("territorio", "*"))


@app.exception_handler(services.ErroNegocio)
async def _erro_negocio(_req: Request, exc: services.ErroNegocio):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(services.AcessoNegado)
async def _acesso_negado(_req: Request, exc: services.AcessoNegado):
    # Tentativa negada é registrada em sessão própria (a do request sofre rollback).
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(ViolacaoImutabilidade)
async def _imutavel(_req: Request, exc: ViolacaoImutabilidade):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


# --------------------------------------------------------------------------- schemas

class NovaConversaIn(BaseModel):
    canal: Literal["app_campo", "web", "whatsapp", "sms", "presencial"] = "app_campo"


class MensagemIn(BaseModel):
    texto: str = Field(min_length=1, max_length=8000)
    client_msg_id: str | None = Field(default=None, max_length=64)


class RespostaOut(BaseModel):
    id_sessao: str
    texto: str
    etapa: str
    protocolo: str | None = None
    codigo_consulta: str | None = None
    emergencia: bool = False
    escalado: bool = False
    opcoes: list[str] = []
    retomada: bool = False


class RegistroIn(BaseModel):
    relato: str = Field(min_length=1, max_length=20000)
    canal_origem: Literal["app_campo", "web", "whatsapp", "sms", "presencial"] = "app_campo"
    localidade: str | None = Field(default=None, max_length=200)
    desde_quando: str | None = Field(default=None, max_length=200)
    uf: str | None = Field(default=None, max_length=2)
    modo_identificacao: Literal["identificado", "sigiloso", "anonimo"] = "anonimo"
    nome: str | None = Field(default=None, max_length=120)
    contato: str | None = Field(default=None, max_length=120)
    consentimento_tratamento: bool
    consentimento_notificacoes: bool = False
    meio_consentimento: Literal["conversa", "presencial", "web"] = "presencial"
    resumo_confirmado: bool = False
    resumo: str | None = Field(default=None, max_length=4000)
    demanda_coletiva: bool = False
    recursos_acessibilidade: list[str] = []
    client_msg_id: str | None = Field(default=None, max_length=64)
    codigo_consulta: str | None = Field(default=None, max_length=12)
    original_tipo: Literal["texto", "audio"] = "texto"
    transcricao_pendente: bool = False
    pedido_pessoa: bool = False


class AdendoIn(BaseModel):
    tipo: Literal["correcao", "complemento", "contestacao"]
    conteudo: str = Field(min_length=1, max_length=8000)


class AvaliacaoIn(BaseModel):
    resultado: Literal["confirmada", "reclassificada", "devolvida", "sensivel", "recusada"]
    justificativa: str = Field(min_length=3)
    prioridade: str | None = None
    tipo: str | None = None
    tema: str | None = None


class EncaminhamentoIn(BaseModel):
    area: str
    responsavel: str
    sistema: Literal["crm", "ouvidoria", "erp"] | None = None
    principal: bool = True


class StatusIn(BaseModel):
    status: Literal["registrada", "em_validacao", "encaminhada", "em_tratamento", "respondida", "encerrada"]
    justificativa: str = Field(min_length=3)
    texto_usuario: str | None = None
    visivel: bool = True
    encerrar_emergencia: bool = False


class TranscricaoIn(BaseModel):
    texto_confirmado: str = Field(min_length=1)


class ChaveIn(BaseModel):
    modulo: Literal["agente_total", "llm", "triagem_automatica", "base_conhecimento"]
    ativo: bool
    motivo: str = Field(min_length=3)


class ResolverIn(BaseModel):
    resolucao: str = Field(min_length=3)


def _resp(r: conversation.Resposta) -> RespostaOut:
    return RespostaOut(**r.__dict__)


# --------------------------------------------------------------------------- públicas

@app.get("/saude")
def saude(db: Session = Depends(get_db)):
    p = services.provedor(db)
    return {"ok": True, "provedor_llm": p.nome, "chaves": services.estado_chaves(db), "versao_prompt": get_settings().versao_prompt}


@app.get("/privacidade")
def privacidade():
    kb = knowledge.obter_base()
    doc = next(d for d in kb.documentos if d.id == "canal-privacidade")
    return {"texto": doc.conteudo, "fonte": doc.fonte, "publicado_em": doc.publicado_em}


@app.get("/status/{protocolo}")
def status_publico(protocolo: str, codigo: str, request: Request, db: Session = Depends(get_db)):
    origem = f"ip:{request.client.host if request.client else 'desconhecido'}"
    try:
        r = services.consultar_status(db, protocolo, codigo, origem=origem)
    except services.AcessoNegado as e:
        db.commit()
        raise HTTPException(429, str(e)) from e
    if r is None:
        db.commit()  # preserva o registro da tentativa negada
        raise HTTPException(404, "protocolo e código não conferem")
    return r


# --------------------------------------------------------------------------- conversa

@app.post("/conversas", response_model=RespostaOut)
def criar_conversa(body: NovaConversaIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    s = conversation.nova_sessao(db, body.canal, ator)
    return RespostaOut(id_sessao=s.id_sessao, texto=conversation.ABERTURA, etapa="inicio", opcoes=["Falar com uma pessoa"])


def _sessao(db: Session, id_sessao: str, ator: services.Ator) -> SessaoConversa:
    s = db.get(SessaoConversa, id_sessao)
    if s is None:
        raise HTTPException(404, "conversa não encontrada")
    if s.operador != ator.rotulo and ator.papel not in services.PAPEIS_REVISAO:
        raise HTTPException(403, "conversa de outro operador")
    return s


@app.post("/conversas/{id_sessao}/mensagens", response_model=RespostaOut)
def enviar_mensagem(id_sessao: str, body: MensagemIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    s = _sessao(db, id_sessao, ator)
    return _resp(conversation.processar(db, s, body.texto, ator, body.client_msg_id))


@app.get("/conversas/{id_sessao}", response_model=RespostaOut)
def retomar_conversa(id_sessao: str, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    return _resp(conversation.retomar(db, _sessao(db, id_sessao, ator)))


@app.post("/conversas/{id_sessao}/anexos")
async def anexo_conversa(id_sessao: str, arquivo: UploadFile = File(...), descricao: str | None = Form(default=None),
                         db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    from ..models import Manifestacao

    s = _sessao(db, id_sessao, ator)
    id_m = s.estado.get("id_manifestacao")
    if not id_m:
        raise HTTPException(422, "Primeiro concluímos o registro e o protocolo — aí o arquivo fica vinculado a ele.")
    m = db.get(Manifestacao, id_m)
    an = services.salvar_anexo(db, m, await arquivo.read(), arquivo.content_type or "application/octet-stream", ator, descricao)
    return {"id": an.id_anexo, "mensagem": f"Recebi 1 {an.tipo}. Fica guardado com o protocolo {m.protocolo}, com acesso restrito "
                                            "às pessoas autorizadas a tratar o caso."}


@app.get("/conversas/{id_sessao}/historico")
def historico_conversa(id_sessao: str, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    s = _sessao(db, id_sessao, ator)
    audit.registrar(db, "acesso", f"sessao:{id_sessao}", ator.rotulo, {"campo": "historico"})
    return {"etapa": s.estado.get("etapa"), "turnos": conversation.historico(db, s)}


# --------------------------------------------------------------------------- manifestações

@app.post("/manifestacoes")
def registrar(body: RegistroIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    if ator.papel not in ("agente_campo", "revisor", "revisor_sigiloso"):
        raise HTTPException(403, "papel sem permissão de registro")
    res = services.registrar_manifestacao(db, services.NovoRegistro(**body.model_dump()), ator)
    m = res.manifestacao
    return {
        "id": m.id_manifestacao, "protocolo": m.protocolo, "codigo_consulta": res.codigo_consulta, "duplicado": res.duplicado,
        "status": m.status_atual, "emergencia": m.emergencia, "rota": m.rota, "revisao_obrigatoria": m.revisao_obrigatoria,
        "triagem_sugerida": {"tipo": m.tipo_sugerido, "tema": m.tema_sugerido, "prioridade": m.prioridade_sugerida,
                             "area": m.area_sugerida, "confianca": m.confianca, "justificativa": m.justificativa},
        "janela_alvo": get_settings().janelas[m.prioridade_sugerida or "P4"].janela_texto,
    }


@app.get("/manifestacoes/{id_manifestacao}")
def ver(id_manifestacao: str, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    return services.visao_caso(m, ator)


def _obter(db: Session, id_manifestacao: str, ator: services.Ator):
    try:
        return services.obter_para(db, id_manifestacao, ator)
    except services.AcessoNegado:
        db.commit()  # mantém o registro da tentativa negada
        raise


@app.post("/manifestacoes/{id_manifestacao}/adendos")
def adendo(id_manifestacao: str, body: AdendoIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    ad = services.adicionar_adendo(db, m, body.tipo, body.conteudo, ator)
    return {"versao": ad.versao, "prioridade_sugerida": m.prioridade_sugerida, "revisao_obrigatoria": m.revisao_obrigatoria}


@app.post("/manifestacoes/{id_manifestacao}/anexos")
async def anexo(id_manifestacao: str, arquivo: UploadFile = File(...), descricao: str | None = Form(default=None),
                db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    dados = await arquivo.read()
    an = services.salvar_anexo(db, m, dados, arquivo.content_type or "application/octet-stream", ator, descricao)
    return {"id": an.id_anexo, "hash": an.hash_conteudo, "sensivel": an.sensivel,
            "mensagem": f"Recebi 1 {an.tipo}. Fica guardado com o protocolo {m.protocolo}, com acesso restrito às pessoas autorizadas a tratar o caso."}


@app.get("/anexos/{id_anexo}")
def baixar_anexo(id_anexo: str, motivo: str, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    try:
        an, dados = services.ler_anexo(db, id_anexo, ator, motivo)
    except services.AcessoNegado:
        db.commit()
        raise
    return Response(content=dados, media_type=an.mime, headers={"Cache-Control": "no-store"})


@app.post("/manifestacoes/{id_manifestacao}/transcricao")
def transcricao(id_manifestacao: str, body: TranscricaoIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    services.confirmar_transcricao(db, m, body.texto_confirmado, ator)
    return {"transcricao_confirmada": True, "prioridade_sugerida": m.prioridade_sugerida}


@app.post("/manifestacoes/{id_manifestacao}/avaliacoes")
def avaliar(id_manifestacao: str, body: AvaliacaoIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    nova = {k: v for k, v in {"prioridade": body.prioridade, "tipo": body.tipo, "tema": body.tema}.items() if v}
    av = services.avaliar(db, m, ator, body.resultado, body.justificativa, nova or None)
    return {"id": av.id_avaliacao, "prioridade_validada": m.prioridade_validada, "rota": m.rota}


@app.post("/manifestacoes/{id_manifestacao}/encaminhamentos")
def encaminhar(id_manifestacao: str, body: EncaminhamentoIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    enc = services.encaminhar(db, m, ator, body.area, body.responsavel, body.sistema, body.principal)
    return {"id": enc.id_encaminhamento, "prazo_alvo": enc.prazo_alvo.isoformat(), "sistema": enc.sistema_destino}


@app.post("/manifestacoes/{id_manifestacao}/status")
def status_manual(id_manifestacao: str, body: StatusIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    services.mudar_status(db, m, ator, body.status, body.justificativa, body.texto_usuario, body.visivel, body.encerrar_emergencia)
    return {"status": m.status_atual}


@app.get("/manifestacoes/{id_manifestacao}/contato")
def contato(id_manifestacao: str, motivo: str, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    m = _obter(db, id_manifestacao, ator)
    return services.contato_do_autor(db, m, ator, motivo)


# --------------------------------------------------------------------------- fila humana

@app.get("/fila")
def fila(db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    from ..models import Manifestacao

    itens = services.listar_fila(db, ator)
    saida = []
    for i in itens:
        m = db.get(Manifestacao, i.id_manifestacao) if i.id_manifestacao else None
        saida.append({"id": i.id_item, "motivo": i.motivo, "prioridade": i.prioridade, "rota": i.rota, "contexto": i.resumo_contexto,
                      "criado_em": i.criado_em.isoformat(), "responsavel": i.responsavel, "id_manifestacao": i.id_manifestacao,
                      "id_sessao": i.id_sessao, "protocolo": m.protocolo if m else None})
    return saida


@app.post("/fila/{id_item}/assumir")
def assumir(id_item: str, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    i = services.assumir_item(db, id_item, ator)
    return {"id": i.id_item, "responsavel": i.responsavel}


@app.post("/fila/{id_item}/resolver")
def resolver(id_item: str, body: ResolverIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    i = services.resolver_item(db, id_item, ator, body.resolucao)
    return {"id": i.id_item, "resolvido_em": i.resolvido_em.isoformat()}


# --------------------------------------------------------------------------- gestão e governança

@app.get("/indicadores")
def painel(dias: int = 90, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    return indicators.painel(db, ator, dias)


@app.get("/admin/chaves")
def ver_chaves(db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    return services.estado_chaves(db)


@app.post("/admin/chaves")
def mudar_chave(body: ChaveIn, db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    services.definir_chave(db, body.modulo, body.ativo, ator, body.motivo)
    return services.estado_chaves(db)


@app.get("/admin/auditoria/verificar")
def verificar_auditoria(db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    if ator.papel != "governanca":
        raise HTTPException(403, "restrito à governança/auditoria")
    r = audit.verificar_cadeia(db)
    audit.registrar(db, "acesso", "auditoria:cadeia", ator.rotulo, {"integra": r.integra})
    return r.__dict__


@app.post("/admin/rotinas")
def rotinas(db: Session = Depends(get_db), ator: services.Ator = Depends(ator_atual)):
    """Rotinas periódicas (agendar via cron): atrasos e outbox de integrações."""
    if ator.papel != "governanca":
        raise HTTPException(403, "restrito")
    return {"atrasos_sinalizados": services.verificar_atrasos(db), "integracoes": integrations.processar_pendentes(db)}


# --------------------------------------------------------------------------- PWA

if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="app")


@app.get("/", include_in_schema=False)
def raiz():
    return RedirectResponse("/app/")
