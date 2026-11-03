"""Motor conversacional (spec cap. 6) — máquina de estados determinística.

O fluxo (acolher → relato → resumo/confirmação → dados mínimos → modo de
identificação → consentimento → protocolo) é código, não geração livre: assim
nenhuma etapa obrigatória do checklist (§7.2) depende do modelo lembrar dela.
O modelo de linguagem entra só no resumo (passado pela guarda de saída) e na
sugestão de triagem.

Verificações que valem em QUALQUER etapa, antes de tudo:
desligamento total → emergência → pedido de pessoa → privacidade → consulta de status.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, crypto, knowledge, protocol, services
from .config import get_settings
from .models import Manifestacao, SessaoConversa, TurnoConversa
from .safety import emergency, sensitive
from .safety.texto import normalizar

ABERTURA = ("Olá! Aqui é o Escuta+, assistente digital. Posso registrar o que você quiser e conectar você com uma pessoa da equipe. "
            "Eu não decido, não prometo e não encerro casos — quem decide são pessoas. Pode me contar o que aconteceu, por texto ou áudio.")

_SAUDACAO = re.compile(r"^(oi+|ola|bom dia|boa tarde|boa noite|e ai|opa|alo|tudo bem)[\s!.,?]*$")
_AGRADECE = re.compile(r"^(obrigad[oa]|valeu|brigad[oa]|tchau|ate mais|ok obrigad[oa]|so isso|nada mais)[\s!.,]*$")
_NINGUEM = re.compile(r"ninguem (ligou|retornou|respondeu|apareceu)")
_NOVO = re.compile(r"(registrar|contar|falar) (outra|mais uma|outro) (coisa|assunto|problema)|novo registro|outro problema")
_COLETIVA = re.compile(r"\b(a comunidade|a gente|nos (queremos|pedimos)|a associacao|o cacique|a cacique|os moradores|todo mundo aqui)\b")
_FOTO = re.compile(r"\b(foto|imagem|video|documento|print|anexo|mandar arquivo)\b")


@dataclass
class Resposta:
    texto: str
    etapa: str
    id_sessao: str
    protocolo: str | None = None
    codigo_consulta: str | None = None
    emergencia: bool = False
    escalado: bool = False
    opcoes: list[str] = field(default_factory=list)
    retomada: bool = False


def _estado_inicial() -> dict:
    return {"etapa": "inicio", "partes": [], "resumo": None, "localidade": None, "desde_quando": None,
            "modo": None, "nome": None, "contato": None, "id_manifestacao": None, "protocolo": None,
            "pedido_pessoa": False, "emergencia": False, "sigilo_sugerido": False, "coletiva": False,
            "compensacao": False, "tradicional": False, "tentativas_confirmacao": 0, "perguntar_risco": False}


def nova_sessao(db: Session, canal: str, ator: services.Ator) -> SessaoConversa:
    s = SessaoConversa(canal=canal, operador=ator.rotulo, estado=_estado_inicial())
    db.add(s)
    db.flush()
    audit.registrar(db, "sessao", f"sessao:{s.id_sessao}", ator.rotulo, {"canal": canal})
    return s


def _turno(db: Session, sessao: SessaoConversa, autor: str, texto: str, client_msg_id: str | None = None) -> TurnoConversa:
    ordem = (db.execute(select(TurnoConversa.ordem).where(TurnoConversa.id_sessao == sessao.id_sessao)
                        .order_by(TurnoConversa.ordem.desc()).limit(1)).scalar_one_or_none() or 0) + 1
    t = TurnoConversa(id_sessao=sessao.id_sessao, ordem=ordem, autor=autor, texto=crypto.cifrar_texto(texto) or "", client_msg_id=client_msg_id)
    db.add(t)
    db.flush()
    return t


def historico(db: Session, sessao: SessaoConversa) -> list[dict]:
    turnos = db.execute(select(TurnoConversa).where(TurnoConversa.id_sessao == sessao.id_sessao).order_by(TurnoConversa.ordem)).scalars()
    return [{"autor": t.autor, "texto": crypto.decifrar_texto(t.texto) or ""} for t in turnos]


def retomar(db: Session, sessao: SessaoConversa) -> Resposta:
    """Retomada após queda de conexão (D-07): sem pedir repetição."""
    e = sessao.estado
    hist = historico(db, sessao)
    ultima = next((h["texto"] for h in reversed(hist) if h["autor"] == "agente"), ABERTURA)
    prefixo = "Continuando de onde paramos. " if hist else ""
    if e.get("protocolo"):
        prefixo += f"Seu registro está guardado com o protocolo {e['protocolo']}. "
    elif e.get("partes"):
        prefixo += "Tudo o que você já me contou está salvo. "
    return Resposta(prefixo + ultima, e["etapa"], sessao.id_sessao, protocolo=e.get("protocolo"), retomada=True,
                    opcoes=_opcoes(e["etapa"]))


def _opcoes(etapa: str) -> list[str]:
    return {
        "confirmar_resumo": ["Sim, é isso", "Não, quero corrigir", "Falar com uma pessoa"],
        "identificacao": ["Deixar nome e contato", "Sigilo", "Sem identificação"],
        "consentimento": ["Sim, pode registrar", "Não"],
        "notificacoes": ["Sim, quero aviso", "Não precisa"],
        "pergunta_registrar": ["Sim, registrar", "Não"],
        "pergunta_risco": ["Não, agora não", "Sim, há risco agora"],
    }.get(etapa, ["Falar com uma pessoa"])


def processar(db: Session, sessao: SessaoConversa, texto: str, ator: services.Ator, client_msg_id: str | None = None) -> Resposta:
    # Idempotência: reenvio da mesma mensagem (rede instável) devolve a mesma resposta.
    if client_msg_id:
        anterior = db.execute(select(TurnoConversa).where(TurnoConversa.id_sessao == sessao.id_sessao,
                                                          TurnoConversa.client_msg_id == client_msg_id)).scalar_one_or_none()
        if anterior is not None:
            resp = db.execute(select(TurnoConversa).where(TurnoConversa.id_sessao == sessao.id_sessao,
                                                          TurnoConversa.ordem == anterior.ordem + 1)).scalar_one_or_none()
            e = sessao.estado
            return Resposta(crypto.decifrar_texto(resp.texto) if resp else "", e["etapa"], sessao.id_sessao,
                            protocolo=e.get("protocolo"), opcoes=_opcoes(e["etapa"]))

    texto = (texto or "").strip()
    _turno(db, sessao, "usuario", texto, client_msg_id)
    estado = dict(sessao.estado)
    r = _decidir(db, sessao, estado, texto, ator)
    sessao.estado = estado  # reatribui para o ORM detectar mudança no JSON
    r.etapa = estado["etapa"]
    if not r.opcoes:
        r.opcoes = _opcoes(estado["etapa"])
    _turno(db, sessao, "agente", r.texto)
    return r


# --------------------------------------------------------------------------- decisão

def _decidir(db: Session, sessao: SessaoConversa, e: dict, texto: str, ator: services.Ator) -> Resposta:
    sid = sessao.id_sessao
    s = get_settings()
    norm = normalizar(texto)

    if not services.modulo_ativo(db, "agente_total"):
        services._enfileirar(db, None, "sistema_desligado", "P3", "mensagem recebida com assistente desligado", id_sessao=sid)
        return Resposta("O assistente digital está temporariamente desligado. Sua mensagem foi guardada e uma pessoa da equipe vai atender. "
                        "Se for urgente, fale com a equipe de campo ou ligue para os serviços públicos de emergência (SAMU 192, Bombeiros 193, Polícia 190).",
                        e["etapa"], sid, escalado=True)

    # 1) Emergência — sempre primeiro, em qualquer etapa.
    emerg = emergency.detectar(texto)
    if emerg.emergencia:
        return _emergencia(db, sessao, e, texto, ator, emerg)
    if e["etapa"] == "emergencia":
        return _complemento_emergencia(db, e, texto, ator, sid)

    sinais = sensitive.analisar(texto)

    # 2) Pedido de pessoa — direito permanente, sem tentar reter (D-13).
    if sinais.pedido_pessoa:
        return _pedir_pessoa(db, e, texto, ator, sid)
    if _NINGUEM.search(norm):
        m = _manifestacao(db, e)
        services._enfileirar(db, m, "atraso", "P2", "autor informa que ninguém retornou", rota=m.rota if m else "comum", id_sessao=sid)
        return Resposta("Obrigado por avisar — isso não deveria acontecer. Já escalei para a coordenação com prioridade, e ficou registrado.",
                        e["etapa"], sid, escalado=True)

    # 3) Privacidade (UC-10) — responde e retoma a etapa.
    if sinais.privacidade and e["etapa"] not in ("relato", "corrigir_resumo"):
        kb = knowledge.obter_base()
        doc = next(d for d in kb.documentos if d.id == "canal-privacidade")
        audit.registrar(db, "resposta_kb", f"sessao:{sid}", services.SISTEMA.rotulo, {"documento": doc.id, "versao_base": kb.versao})
        return Resposta(knowledge.formatar_resposta(knowledge.Resultado(doc, 99)) + _retomar_pergunta(e), e["etapa"], sid)

    # 4) Consulta de status (UC-07) — "2026-MG-000123 código 123456"
    numero = protocol.extrair_protocolo(texto)
    if numero:
        codigo = re.sub(r"\D", "", texto.upper().replace(numero, ""))
        if len(codigo) == 6:
            try:
                st = services.consultar_status(db, numero, codigo, origem=f"sessao:{sid}")
            except services.AcessoNegado as exc:
                return Resposta(str(exc), e["etapa"], sid)
            if st is None:
                return Resposta("Não encontrei um registro com esse protocolo e código. Confira os números — se preferir, uma pessoa da equipe ajuda.", e["etapa"], sid)
            return Resposta(st["mensagem"], e["etapa"], sid)
        return Resposta("Para consultar, me envie o número do protocolo e o código de consulta de 6 dígitos que você recebeu.", e["etapa"], sid)

    etapa = e["etapa"]
    handler = {
        "inicio": _inicio, "relato": _relato, "confirmar_resumo": _confirmar_resumo, "corrigir_resumo": _corrigir,
        "dados_minimos": _dados_minimos, "identificacao": _identificacao, "contato": _contato,
        "consentimento": _consentimento, "notificacoes": _notificacoes, "registrado": _registrado,
        "pergunta_registrar": _pergunta_registrar, "aguardando_pessoa": _aguardando_pessoa,
        "pergunta_risco": _pergunta_risco,
    }[etapa]
    return handler(db, sessao, e, texto, ator, sinais)


def _retomar_pergunta(e: dict) -> str:
    return {
        "confirmar_resumo": " Voltando ao registro: o resumo que li está certo?",
        "identificacao": " Voltando: prefere deixar nome e contato, pedir sigilo ou registrar sem identificação?",
        "consentimento": " Voltando: posso registrar?",
        "dados_minimos": " Voltando: em que local fica e desde quando acontece?",
    }.get(e["etapa"], "")


def _manifestacao(db: Session, e: dict) -> Manifestacao | None:
    return db.get(Manifestacao, e["id_manifestacao"]) if e.get("id_manifestacao") else None


# --------------------------------------------------------------------------- etapas

def _inicio(db, sessao, e, texto, ator, sinais) -> Resposta:
    norm = normalizar(texto)
    if _SAUDACAO.match(norm) or len(norm) < 3:
        e["etapa"] = "relato"
        return Resposta(ABERTURA, "relato", sessao.id_sessao, opcoes=["Falar com uma pessoa"])
    if (sinais.quer_anonimato or sinais.quer_sigilo) and len(norm.split()) <= 20 and not sinais.rota_sigilosa:
        # D-08: anonimato informado antes do relato — vantagens, limites e a única exceção.
        e["modo"] = "anonimo" if sinais.quer_anonimato else "sigiloso"
        e["sigilo_sugerido"] = True
        e["etapa"] = "relato"
        return Resposta("Nenhum problema — é seu direito. Vou explicar como funciona, sem enrolação: sem o seu nome, a empresa não consegue te procurar "
                        "para dar retorno. Em compensação, você recebe um protocolo e um código; com eles, consulta o andamento quando quiser, "
                        "e ninguém consegue ligar o registro a você. Uma coisa importante: mesmo sem nome, se eu entender que há risco imediato a alguém, "
                        "vou te orientar sobre os serviços de emergência e acionar a equipe — sem quebrar o anonimato. Pode contar.", "relato", sessao.id_sessao)
    pergunta = texto.endswith("?") and not sinais.sensivel and len(norm.split()) <= 25
    if pergunta:
        return _pergunta(db, sessao, e, texto)
    e["etapa"] = "relato"
    return _relato(db, sessao, e, texto, ator, sinais, abertura=True)


def _pergunta(db, sessao, e, texto) -> Resposta:
    sid = sessao.id_sessao
    if services.modulo_ativo(db, "base_conhecimento"):
        r = knowledge.obter_base().buscar(texto)
        if r:
            audit.registrar(db, "resposta_kb", f"sessao:{sid}", services.SISTEMA.rotulo,
                            {"documento": r.documento.id, "versao_base": knowledge.obter_base().versao, "pontuacao": round(r.pontuacao, 2)})
            e["etapa"] = "relato"
            return Resposta(knowledge.formatar_resposta(r) + " Se quiser registrar algo, é só me contar.", "relato", sid)
    e["partes"] = [texto]
    e["etapa"] = "pergunta_registrar"
    audit.registrar(db, "resposta_kb", f"sessao:{sid}", services.SISTEMA.rotulo, {"documento": None, "motivo": "sem conteúdo aprovado"})
    return Resposta(knowledge.RESPOSTA_SEM_INFORMACAO, "pergunta_registrar", sid)


def _pergunta_registrar(db, sessao, e, texto, ator, sinais) -> Resposta:
    if sensitive.resposta_sim(texto):
        e["etapa"] = "confirmar_resumo"
        e["resumo"] = e["partes"][0]
        return Resposta(f"Combinado. Vou registrar a pergunta: “{e['resumo']}”. Está certo assim?", "confirmar_resumo", sessao.id_sessao)
    if sensitive.resposta_nao(texto):
        e.update(_estado_inicial() | {"etapa": "relato"})
        return Resposta("Tudo bem. Se precisar, é só me chamar — e você pode falar com uma pessoa quando quiser.", "relato", sessao.id_sessao)
    e["etapa"] = "relato"
    e["partes"] = []
    return _relato(db, sessao, e, texto, ator, sinais)


def _relato(db, sessao, e, texto, ator, sinais, abertura: bool = False) -> Resposta:
    sid = sessao.id_sessao
    norm = normalizar(texto)
    if _SAUDACAO.match(norm) or (not e["partes"] and sensitive.resposta_sim(texto) and len(norm.split()) <= 3):
        return Resposta("Pode me contar o que aconteceu, no seu ritmo — por texto ou áudio.", "relato", sid)
    e["partes"].append(texto)
    relato = "\n".join(e["partes"])
    resumo, _origem = services.resumir_seguro(db, relato, f"sessao:{sid}")
    e["resumo"] = resumo
    e["etapa"] = "confirmar_resumo"
    _marcar_sinais(e, sinais, norm)

    pre = []
    if abertura:
        pre.append("Aqui é o Escuta+, assistente digital — eu registro e conecto você com a equipe; quem decide são pessoas.")
    if sinais.rota_sigilosa:
        pre.append("Você pode falar com tranquilidade: posso registrar sem o seu nome, e esse relato segue por rota reservada, "
                   "que só pessoas autorizadas e obrigadas a manter sigilo podem ver.")
        if sinais.retaliacao:
            pre.append("Retaliação por registrar manifestação é proibida e inaceitável — é exatamente o que este canal existe para proteger. "
                       "Não vou tirar conclusão sobre a intenção de ninguém, mas o relato vai com prioridade máxima para revisão reservada. "
                       "Ele também pode seguir para a Ouvidoria, que é independente da operação.")
    if sinais.compensacao:
        pre.append("Você tem o direito de pedir o que entende ser justo. Sendo transparente: eu não decido, não calculo e não prometo indenização — "
                   "isso passa por avaliação de pessoas responsáveis, com critérios e etapas. O que posso fazer agora é registrar seu pedido com todos os detalhes.")
    if e["tradicional"]:
        pre.append("Uma conversa sobre território e uso coletivo merece falar direto com as pessoas certas da equipe, com calma e do jeito da comunidade — "
                   "em português ou com apoio de intérprete, como for melhor. Se a comunidade preferir que eu só registre e não pergunte mais nada, é só dizer.")
    if sinais.rota_sigilosa or sinais.temas_sensiveis or emergency.detectar(relato).sinal_atencao:
        e["perguntar_risco"] = True
    corpo = f"Pelo que entendi: “{resumo}” É isso?"
    return Resposta(" ".join(pre + [corpo]), "confirmar_resumo", sid)


def _marcar_sinais(e: dict, sinais: sensitive.Sinais, norm: str) -> None:
    if sinais.rota_sigilosa or sinais.quer_anonimato or sinais.quer_sigilo:
        e["sigilo_sugerido"] = True
    if sinais.compensacao:
        e["compensacao"] = True
    if "povos_tradicionais" in sinais.temas_sensiveis:
        e["tradicional"] = True
    if _COLETIVA.search(norm):
        e["coletiva"] = True


def _confirmar_resumo(db, sessao, e, texto, ator, sinais) -> Resposta:
    sid = sessao.id_sessao
    if sensitive.resposta_sim(texto):
        return _apos_confirmacao(e, sid)
    if sensitive.resposta_nao(texto):
        e["etapa"] = "corrigir_resumo"
        return Resposta("Sem problema. O que ficou errado ou faltou? Pode me dizer com suas palavras.", "corrigir_resumo", sid)
    # Texto livre = complemento ao relato antes de fechar (D-02, D-06).
    e["etapa"] = "relato"
    e["tentativas_confirmacao"] += 1
    return _relato(db, sessao, e, texto, ator, sinais)


def _apos_confirmacao(e: dict, sid: str) -> Resposta:
    if e.get("perguntar_risco"):
        e["perguntar_risco"] = False
        e["etapa"] = "pergunta_risco"
        return Resposta("Obrigado. Uma pergunta importante: essa situação oferece risco imediato a alguém agora — "
                        "por exemplo fogo, pessoa ferida, criança em perigo ou ameaça?", "pergunta_risco", sid,
                        opcoes=["Não, agora não", "Sim, há risco agora"])
    if not e.get("localidade"):
        e["etapa"] = "dados_minimos"
        return Resposta("Obrigado. Só mais duas coisas rápidas: em qual rua, comunidade ou ponto de referência fica, e isso acontece desde quando?",
                        "dados_minimos", sid)
    return _perguntar_identificacao(e, sid)


def _corrigir(db, sessao, e, texto, ator, sinais) -> Resposta:
    # Antes do registro: a correção entra como nova parte, preservando o que foi dito antes.
    e["etapa"] = "relato"
    return _relato(db, sessao, e, f"[correção do autor] {texto}", ator, sinais)


def _pergunta_risco(db, sessao, e, texto, ator, sinais) -> Resposta:
    sid = sessao.id_sessao
    if sensitive.resposta_sim(texto) or re.search(r"\b(sim|tem risco|ha risco|perigo agora)\b", normalizar(texto)) and not sensitive.resposta_nao(texto):
        # Risco afirmado pela pessoa: protocolo de emergência mesmo sem termo léxico.
        resultado = emergency.ResultadoEmergencia(True, False, ["risco afirmado pelo autor"], ["192", "193", "190"])
        return _emergencia(db, sessao, e, texto, ator, resultado)
    e["etapa"] = "confirmar_resumo"
    r = _apos_confirmacao(e, sid)
    r.texto = "Certo. Se em algum momento houver risco imediato, me avise ou ligue direto: 190 ou 193. " + r.texto
    return r


_DESDE = re.compile(r"\b(desde|faz|ha|há|comecou|começou|tem uns|tem umas|de uns|de umas)\b", re.I)


def _dados_minimos(db, sessao, e, texto, ator, sinais) -> Resposta:
    norm = normalizar(texto)
    if re.match(r"^(nao sei|prefiro nao|nao quero dizer|pular)", norm):
        e["localidade"], e["desde_quando"] = "não informado", None
    else:
        m = _DESDE.search(texto)
        if m and m.start() > 0:
            e["localidade"] = texto[: m.start()].strip(" ,.;")
            e["desde_quando"] = texto[m.start():].strip(" .")
        elif m:
            e["desde_quando"], e["localidade"] = texto.strip(" ."), "não informado"
        else:
            e["localidade"] = texto.strip(" .")
    return _perguntar_identificacao(e, sessao.id_sessao)


def _perguntar_identificacao(e: dict, sid: str) -> Resposta:
    if e.get("modo") == "anonimo":  # escolha já feita e explicada (D-08)
        e["etapa"] = "consentimento"
        return Resposta("Combinado: registro sem identificação, como você escolheu. " + _texto_consentimento(e), "consentimento", sid)
    e["etapa"] = "identificacao"
    if e["sigilo_sugerido"]:
        txt = ("Para fechar o registro: você não precisa se identificar. Pode registrar sem identificação (recebe protocolo e código para acompanhar), "
               "pedir sigilo (seu nome fica protegido, só pessoas autorizadas veem) ou deixar nome e contato. Como prefere?")
    else:
        txt = ("Quer deixar seu nome e um contato para a equipe retornar? Se preferir, pode pedir sigilo "
               "(só pessoas autorizadas veem seu nome) ou registrar sem identificação.")
    return Resposta(txt, "identificacao", sid)


_NOME = re.compile(r"(?:meu nome (?:e|é)|me chamo|sou (?:a|o)|(?:e|é) (?:a |o )?(?:dona|seu|sr\.?|sra\.?)|pode anotar(?: meu nome)?[,:]?(?: (?:e|é))?)\s+([A-Za-zÀ-ú][\wÀ-ú]+(?:\s+[A-Za-zÀ-ú][\wÀ-ú]+){0,3})", re.I)


def _identificacao(db, sessao, e, texto, ator, sinais) -> Resposta:
    sid = sessao.id_sessao
    norm = normalizar(texto)
    if sinais.quer_anonimato or re.search(r"\b(sem identific\w*|anonim\w*|sem nome|nao quero|nao)\b", norm) and not re.search(r"sigil", norm):
        e["modo"] = "anonimo"
        e["etapa"] = "consentimento"
        return Resposta("Nenhum problema — é seu direito. Sendo transparente: sem o seu nome, a empresa não consegue te procurar para dar retorno. "
                        "Em compensação, você recebe um protocolo e um código; com eles, acompanha o andamento quando quiser, e ninguém consegue ligar o registro a você. "
                        "Mesmo sem nome, se houver risco imediato a alguém, eu oriento os serviços de emergência e aciono a equipe — sem quebrar o anonimato. "
                        + _texto_consentimento(e), "consentimento", sid)
    e["modo"] = "sigiloso" if re.search(r"sigil|segredo|reservad", norm) else "identificado"
    m = _NOME.search(texto)
    if m:
        e["nome"] = m.group(1).strip()
    e["etapa"] = "contato"
    nome = f", {e['nome']}" if e.get("nome") else ""
    return Resposta(f"Obrigado{nome}. Qual o melhor telefone ou contato para retorno? É opcional — se quiser, a equipe usa o contato deste atendimento.",
                    "contato", sid)


def _contato(db, sessao, e, texto, ator, sinais) -> Resposta:
    norm = normalizar(texto)
    if not re.search(r"\b(nao|deste|desse|este|esse|mesmo numero|o mesmo|pular)\b", norm) or re.search(r"\d{4}", norm):
        e["contato"] = texto.strip()
    if not e.get("nome"):
        m = _NOME.search(texto)
        if m:
            e["nome"] = m.group(1).strip()
    e["etapa"] = "consentimento"
    return Resposta(_texto_consentimento(e), "consentimento", sessao.id_sessao)


def _texto_consentimento(e: dict) -> str:
    contato = " e o seu contato" if e.get("modo") in ("identificado", "sigiloso") else ""
    return (f"Para registrar, preciso do seu de acordo: guardo o que você contou{contato} só para tratar esta manifestação e prestar contas. "
            "Não faço perfil pessoal e não compartilho sem autorização, exceto obrigação legal. Você pode pedir acesso, correção e explicação "
            "ao Encarregado de Proteção de Dados. Posso registrar?")


def _consentimento(db, sessao, e, texto, ator, sinais) -> Resposta:
    sid = sessao.id_sessao
    if sensitive.resposta_sim(texto):
        return _registrar(db, sessao, e, ator)
    if sensitive.resposta_nao(texto):
        audit.registrar(db, "consentimento", f"sessao:{sid}", ator.rotulo, {"finalidade": "tratamento_manifestacao", "aceite": False})
        _descartar_relato(db, sessao)
        e.update(_estado_inicial() | {"etapa": "relato"})
        return Resposta("Entendo e respeito. Sem o seu de acordo, eu não guardo o relato — o que você contou foi descartado deste canal. "
                        "Você pode procurar a equipe de campo, o telefone ou a Ouvidoria quando preferir. Se mudar de ideia, é só me dizer.", "relato", sid)
    return Resposta("Só preciso de um sim ou não: posso registrar o que você contou?", "consentimento", sid)


def _descartar_relato(db: Session, sessao: SessaoConversa) -> None:
    for t in db.execute(select(TurnoConversa).where(TurnoConversa.id_sessao == sessao.id_sessao)).scalars():
        t.texto = crypto.cifrar_texto("[conteúdo descartado: consentimento recusado]") or ""


def _registrar(db, sessao, e, ator) -> Resposta:
    sid = sessao.id_sessao
    s = get_settings()
    dados = services.NovoRegistro(
        relato="\n".join(e["partes"]), canal_origem=sessao.canal, localidade=e.get("localidade"), desde_quando=e.get("desde_quando"),
        modo_identificacao=e.get("modo") or "anonimo", nome=e.get("nome"), contato=e.get("contato"),
        consentimento_tratamento=True, meio_consentimento="conversa", resumo=e.get("resumo"), resumo_confirmado=True,
        demanda_coletiva=e.get("coletiva", False), pedido_pessoa=e.get("pedido_pessoa", False),
    )
    res = services.registrar_manifestacao(db, dados, ator)
    m, t = res.manifestacao, res.triagem
    e.update({"id_manifestacao": m.id_manifestacao, "protocolo": m.protocolo, "etapa": "notificacoes"})
    janela = s.janelas[m.prioridade_sugerida or "P4"].janela_texto
    partes = [f"Registrei sua manifestação. Seu protocolo é {m.protocolo} e o código de consulta é {protocol.formatar_codigo(res.codigo_consulta)}. "
              "Guarde os dois: com eles você acompanha o andamento quando quiser."]
    if m.rota == "sigilosa":
        partes.append("O relato segue por rota reservada: alguém autorizado vai revisá-lo com sigilo, e nada nele aponta para você.")
    else:
        partes.append(f"Encaminhei para avaliação da equipe responsável (área sugerida: {m.area_sugerida}).")
    if m.prioridade_sugerida == "P2":
        partes.append("Como envolve possível efeito na saúde, na água, na segurança ou em direitos, sugeri prioridade alta — uma pessoa confirma.")
    partes.append(f"O prazo-alvo é: {janela} — é um alvo interno de trabalho, não uma promessa. Não posso antecipar causa nem solução: quem avalia é a equipe.")
    if m.modo_identificacao == "anonimo":
        partes.append("Sem o código, ninguém — nem eu — consegue ligar essa manifestação a você.")
    partes.append("Você pode falar com uma pessoa quando quiser. Quer receber aviso por mensagem quando o status mudar?")
    return Resposta(" ".join(partes), "notificacoes", sid, protocolo=m.protocolo, codigo_consulta=res.codigo_consulta,
                    escalado=m.revisao_obrigatoria)


def _notificacoes(db, sessao, e, texto, ator, sinais) -> Resposta:
    sid = sessao.id_sessao
    if sensitive.resposta_sim(texto):
        from .models import Consentimento, agora

        m = _manifestacao(db, e)
        db.add(Consentimento(id_pessoa=m.id_pessoa if m else None, id_manifestacao=e["id_manifestacao"], finalidade="notificacoes",
                             versao_texto=get_settings().versao_texto_consentimento, aceite_em=agora(), meio="conversa"))
        audit.registrar(db, "consentimento", f"manifestacao:{e['id_manifestacao']}", ator.rotulo, {"finalidade": "notificacoes"})
        e["etapa"] = "registrado"
        return Resposta("Ativado. Você recebe uma mensagem curta quando o status mudar. Posso ajudar em mais alguma coisa?", "registrado", sid)
    e["etapa"] = "registrado"
    if sensitive.resposta_nao(texto):
        return Resposta("Tudo bem. Posso ajudar em mais alguma coisa?", "registrado", sid)
    return _registrado(db, sessao, e, texto, ator, sinais)


def _registrado(db, sessao, e, texto, ator, sinais) -> Resposta:
    sid = sessao.id_sessao
    norm = normalizar(texto)
    m = _manifestacao(db, e)
    if _AGRADECE.match(norm):
        return Resposta(f"Eu que agradeço. Seu protocolo é {e['protocolo']}. Guarde-o: com ele você acompanha e cobra. Quando quiser falar com uma pessoa, é só pedir.",
                        "registrado", sid)
    if _NOVO.search(norm):
        e.update(_estado_inicial() | {"etapa": "relato"})
        return Resposta("Claro. Pode me contar o novo assunto.", "relato", sid)
    if m is None:
        e["etapa"] = "relato"
        return _relato(db, sessao, e, texto, ator, sinais)
    if sinais.contestacao:
        services.adicionar_adendo(db, m, "contestacao", texto, ator)
        return Resposta(f"Você tem razão de estranhar — obrigado por me corrigir: quem entende do tamanho do problema é você. "
                        f"Registrei sua discordância no caso, elevei a prioridade sugerida para {m.prioridade_sugerida} e pedi revisão humana — "
                        "uma pessoa reavalia e responde. Minha classificação é sugestão, nunca decisão final.", "registrado", sid, escalado=True)
    if _FOTO.search(norm) and len(norm.split()) <= 12:
        return Resposta("Pode enviar pelo botão de anexo. A foto fica guardada com o seu protocolo, com acesso restrito às pessoas autorizadas a tratar o caso. "
                        "Quer contar rapidamente o que ela mostra, para constar no registro?", "registrado", sid)
    services.adicionar_adendo(db, m, "complemento", texto, ator)
    msg = (f"Anotei como complemento ao protocolo {m.protocolo}. O registro original continua guardado e a equipe responsável foi avisada da atualização.")
    if m.revisao_obrigatoria and m.prioridade_sugerida in ("P1", "P2"):
        msg += f" Com essa informação, a prioridade sugerida é {m.prioridade_sugerida} — uma pessoa confirma."
    return Resposta(msg, "registrado", sid)


def _pedir_pessoa(db, e, texto, ator, sid) -> Resposta:
    s = get_settings()
    e["pedido_pessoa"] = True
    m = _manifestacao(db, e)
    if not any(p == texto for p in e["partes"]) and e["etapa"] in ("inicio", "relato") and len(normalizar(texto).split()) > 10:
        e["partes"].append(texto)
    services._enfileirar(db, m, "pedido_pessoa", "P3", f"pedido de atendimento humano{' · ' + m.protocolo if m else ''}",
                         rota=m.rota if m else "comum", id_sessao=sid)
    if m is None and e["etapa"] in ("inicio", "relato", "confirmar_resumo", "corrigir_resumo", "pergunta_registrar"):
        e["etapa"] = "aguardando_pessoa"
    return Resposta(f"Claro, sem problema nenhum — é seu direito, sempre. Vou chamar uma pessoa da equipe agora. "
                    f"Ela vai ver tudo o que você contou neste canal: não vai precisar repetir nada. A previsão de primeiro contato é {s.janela_escalonamento}. "
                    "Se passar disso e ninguém retornar, escreva aqui “ninguém retornou” que eu escalo na hora e fica registrado.",
                    e["etapa"], sid, escalado=True, opcoes=["Ninguém retornou"])


def _aguardando_pessoa(db, sessao, e, texto, ator, sinais) -> Resposta:
    if re.fullmatch(r"\s*(quero )?registrar( formalmente)?[\s.!]*", normalizar(texto)):
        return _relato_de_espera(db, sessao, e, ator)
    e["partes"].append(texto)
    return Resposta("Deixei anotado, com suas palavras, para a pessoa da equipe que vai te atender. "
                    "Se quiser, enquanto aguarda, também posso registrar formalmente e te dar um protocolo — é só dizer “registrar”.",
                    "aguardando_pessoa", sessao.id_sessao, opcoes=["Registrar"])


def _relato_de_espera(db, sessao, e, ator) -> Resposta:
    if not e["partes"]:
        e["etapa"] = "relato"
        return Resposta("Combinado. Pode me contar o que aconteceu.", "relato", sessao.id_sessao)
    relato = "\n".join(e["partes"])
    e["resumo"], _ = services.resumir_seguro(db, relato, f"sessao:{sessao.id_sessao}")
    e["etapa"] = "confirmar_resumo"
    return Resposta(f"Combinado. Pelo que entendi: “{e['resumo']}” É isso?", "confirmar_resumo", sessao.id_sessao)


# --------------------------------------------------------------------------- emergência

def _emergencia(db, sessao, e, texto, ator, emerg) -> Resposta:
    sid = sessao.id_sessao
    s = get_settings()
    m = _manifestacao(db, e)
    if m is None:
        e["partes"].append(texto)
        dados = services.NovoRegistro(
            relato="\n".join(e["partes"]), canal_origem=sessao.canal, localidade=e.get("localidade"),
            modo_identificacao=e.get("modo") or "anonimo", nome=e.get("nome"), contato=e.get("contato"),
            consentimento_tratamento=True, meio_consentimento="emergencia_protecao_da_vida",
        )
        # Base legal: proteção da vida (LGPD art. 7º, VII) — a validar com o jurídico (pergunta J1).
        res = services.registrar_manifestacao(db, dados, ator)
        m = res.manifestacao
        e.update({"id_manifestacao": m.id_manifestacao, "protocolo": m.protocolo})
        codigo = res.codigo_consulta
    else:
        services.adicionar_adendo(db, m, "complemento", texto, ator)
        codigo = None
        if not m.emergencia:
            services.acionar_emergencia(db, m, ator)
    e["emergencia"] = True
    e["etapa"] = "emergencia"
    txt = emergency.resposta_emergencia(emerg, s.janelas["P1"].janela_texto)
    txt += f" Protocolo: {m.protocolo}" + (f", código {protocol.formatar_codigo(codigo)}." if codigo else ".")
    return Resposta(txt, "emergencia", sid, protocolo=m.protocolo, codigo_consulta=codigo, emergencia=True, escalado=True,
                    opcoes=["Ligar 192", "Ligar 193", "Ligar 190"])


def _complemento_emergencia(db, e, texto, ator, sid) -> Resposta:
    m = _manifestacao(db, e)
    if m is not None and texto:
        services.adicionar_adendo(db, m, "complemento", texto, ator)
    pergunta_local = "" if (m and m.localidade) else " Se puder, me diga o local: comunidade, estrada ou ponto de referência."
    return Resposta("Registrado. Siga as orientações do serviço de emergência ao telefone até a chegada do socorro. "
                    "A equipe da empresa foi acionada e pode entrar em contato — mas quem confirma presença é ela, eu não posso prometer."
                    + pergunta_local + " Continuo aqui.", "emergencia", sid, protocolo=e.get("protocolo"), emergencia=True,
                    opcoes=["Ligar 192", "Ligar 193", "Ligar 190"])
