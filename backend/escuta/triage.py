"""Triagem assistida — sugestão, nunca decisão (spec §5.14).

Três eixos independentes: tipo, tema, prioridade P1–P4. Regras obrigatórias
(§5.14.4) implementadas aqui:
- preserva a mensagem original (a triagem só lê);
- registra justificativa citando os trechos que a fundamentaram;
- informa confiança (baixa/média/alta); baixa em tema sensível força revisão;
- não infere atributos sensíveis (o esquema não tem campo para isso);
- não conclui causalidade (tema é hipótese de trabalho);
- não cria falsa urgência, mas na dúvida prevalece o nível mais protetor;
- encaminha o sensível a quem pode ver (rota sigilosa).

A sugestão do modelo de linguagem, quando existe, é FUNDIDA com as regras pela
política "o mais protetor vence": o modelo pode subir a prioridade, nunca
baixá-la abaixo do que as regras determinísticas indicaram.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import AREAS_POR_TEMA
from .safety import emergency, sensitive
from .safety.texto import buscar

TIPOS = ("informacao", "solicitacao", "reclamacao", "denuncia", "sugestao", "elogio", "conflito", "emergencia")
TEMAS = tuple(AREAS_POR_TEMA.keys())
PRIORIDADES = ("P1", "P2", "P3", "P4")

PADROES_TIPO = [
    (r"\bbloquei\w*|\bprotesto\b|\bfechar a (estrada|rua|ferrovia)|\bbriga\w*|\bconfusao\b|\bmanifestacao na\b|\btensao\b", "conflito"),
    (r"\bpoeira\b|\bbarulho\b|\bruido\b|\bvibra\w*|\btreme\w*|\binsuportavel\b|\bcor estranha\b|\bsem agua\b|\bfalta de agua\b|\bninguem (responde|resolve|aparece)|\brachad\w*|\bsuj[oa]\b|\breclam\w*|\bcaminho(es|nhao)\b|\bdetona\w*|\bmorreu\b|\bestrag\w*", "reclamacao"),
    (r"\bpodem\b|\bpoderiam (limpar|consertar|arrumar|fazer|tapar|instalar)|\bsolicit\w*|\bpedido\b|\bpreciso que\b|\bquero registrar um pedido\b|\bentupid\w*|\bconsert\w*|\blimpar\b|\bburaco\b|\bquero (uma )?conversa\w*|\bquer conversar\b", "solicitacao"),
    (r"\bsuger\w*|\bsugest\w*|\bseria bom\b|\bpodiam avisar\b|\bpoderiam avisar\b|\bque tal\b", "sugestao"),
    (r"\bparabens\b|\belogi\w*|\bmuito atencios\w*|\bagradec\w*|\bfoi otim\w*|\bgostei\b", "elogio"),
    (r"\bquando (vai|comeca|termina|sera)\b|\bcomo funciona\b|\bqual (e|o|a)\b|\bo que (e|vai)\b|\bonde fica\b|\bexiste\b.*\?", "informacao"),
]

PADROES_TEMA = [
    (r"\bpoeira\b|\bpo\b|\bbarulho\b|\bruido\b|\bvibra\w*|\bagua\b|\brio\b|\bcorrego\b|\bribeirao\b|\bnascente\b|\bpeix\w*|\bfauna\b|\bflora\b|\barvore\w*|\bmata\b|\blama\b|\bfumaca\b|\bcheiro\b|\bcor estranha\b|\bplanta\w*|\bsolo\b|\bar\b", "impacto_ambiental"),
    (r"\btransito\b|\bcaminho(es|nhao)\b|\bonibus\b|\bemprego\w*|\brenda\b|\bconvivencia\b|\bmadrugada\b|\bdormir\b|\bvizinh\w*|\bcomercio\b|\bservico\w*", "impacto_social"),
    (r"\brua\b|\bestrada\b|\bvaleta\b|\bponte\b|\bmuro\b|\bparede\b|\bcasa\b|\bbueiro\b|\bburaco\b|\bcalcada\b|\bpatrimonio\b|\bigreja\b|\bcemiterio\b|\bcercad\w*|\btrilha\b|\bprateleira\b", "infraestrutura_patrimonio"),
    (r"\bsaude\b|\bdoen\w*|\btosse\b|\balergi\w*|\brespira\w*|\bpassou mal\b|\bpara beber\b|\bbeber\b|\bhospital\b|\bmedic\w*", "saude"),
    (r"\bfogo\b|\bincendio\w*|\bqueimad\w*|\bferid\w*|\bsangr\w*|\barmad\w*|\bacidente\b|\brisco\b|\bperigo\w*|\bseguranca\b|\bexplos\w*|\bdetona\w*|\bcair\b|\bdesab\w*", "seguranca"),
    (r"\bretalia\w*|\bpersegui\w*|\bdiscrimin\w*|\bindigena\w*|\bquilombo\w*|\btradicional\b|\bterritorio\b|\bcacique\b|\bameac\w*|\bdireitos?\b", "direitos_humanos"),
    (r"\bbarragem\b|\bsirene\w*|\bferrovia\b|\btrem\b|\bmina\b|\bpatio\b|\bcorreia\b|\bpedreira\b|\bminerio\b", "risco_operacional"),
    (r"\bprotocolo\b|\binformac\w*|\bcanal\b|\batendimento\b|\bimpessoal\b|\bcadastro\b", "administrativo_relacional"),
]

# Indicadores concretos de P2 (dano à saúde, água, segurança, DH, conflito em curso).
PADROES_P2 = [
    (r"\b(para|pra) beber\b|\bagua (de beber|potavel|da torneira)|\bsem agua\b|\bfalta de agua\b|\bcor estranha\b|\bagua (suja|barrenta|contaminad\w*)", "agua_consumo"),
    (r"\bdoen\w*|\bpassou mal\b|\btosse\b|\bfalta de ar\b|\bhospital\b|\bintern\w*", "saude"),
    (r"\brachad\w*.*(abrindo|aumentando|ampliando)|\b(abrindo|aumentando) .*rachad\w*|\brisco de cair\b|\bdorme\b.*\bmuro\b|\bmuro\b.*\bdorme\b", "risco_estrutural"),
    (r"\bvibra\w*|\btreme\w*", "vibracao"),
    (r"\bcrianca\w*|\bidos[oa]s?\b|\bacamad\w*|\bbebe\b", "pessoa_vulneravel"),
    (r"\bplantac\w* (morreu|perdida|estragou)|\bperdi (a |minha )?(plantacao|criacao|renda)|\bfonte de renda\b|\bmorreu .*poeira\b", "perda_renda"),
    (r"\bha (mais de )?(\d+|uma|duas|tres|quatro|cinco|seis) (dias|semanas)\b.*\bsem\b|\bpiorando\b", "agravamento"),
]


@dataclass
class SugestaoModelo:
    """Saída estruturada do modelo de linguagem (validada por esquema)."""

    tipo: str
    tema: str
    prioridade: str
    justificativa: str
    trechos_citados: list[str] = field(default_factory=list)
    confianca: str = "media"


@dataclass
class Triagem:
    tipo: str
    tema: str
    prioridade: str
    area_sugerida: str
    confianca: str
    justificativa: str
    trechos: list[str]
    rota: str  # comum | sigilosa
    emergencia: bool
    revisao_obrigatoria: bool
    origem: str  # regras | regras+modelo
    duvida_registrada: str | None = None
    temas_sensiveis: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return dict(self.__dict__)


def _primeiro(padroes, texto) -> tuple[str | None, list[str]]:
    contagem: dict[str, int] = {}
    trechos: list[str] = []
    for trecho, rotulo, neg in buscar(padroes, texto):
        if neg:
            continue
        contagem[rotulo] = contagem.get(rotulo, 0) + 1  # type: ignore[index]
        trechos.append(trecho)
    if not contagem:
        return None, trechos
    melhor = max(contagem.items(), key=lambda kv: kv[1])[0]
    return melhor, trechos


def _nivel(p: str) -> int:
    return PRIORIDADES.index(p)


def mais_protetora(a: str, b: str) -> str:
    return a if _nivel(a) <= _nivel(b) else b


def elevar(p: str) -> str:
    return PRIORIDADES[max(0, _nivel(p) - 1)]


def triar_por_regras(texto: str) -> Triagem:
    emerg = emergency.detectar(texto)
    sinais = sensitive.analisar(texto)
    trechos: list[str] = []
    motivos: list[str] = []

    # --- tipo
    if emerg.emergencia:
        tipo = "emergencia"
        motivos.append(f"indício de risco imediato ({', '.join(emerg.termos[:3])})")
    elif sinais.denuncia:
        tipo = "denuncia"
        motivos.append("relato de conduta possivelmente irregular")
    else:
        tipo_r, tr = _primeiro(PADROES_TIPO, texto)
        trechos += tr
        # atos de fala explícitos ("sugiro", "quero elogiar") prevalecem sobre o assunto citado
        # ...desde que não sejam minoria frente a termos de reclamação/conflito.
        cont: dict[str, int] = {}
        for _t, r, neg in buscar(PADROES_TIPO, texto):
            if not neg:
                cont[r] = cont.get(r, 0) + 1  # type: ignore[index]
        for ato in ("sugestao", "elogio"):
            if cont.get(ato, 0) and cont.get(ato, 0) >= cont.get("reclamacao", 0) and not cont.get("conflito"):
                tipo_r = ato
                break
        tipo = tipo_r or ("informacao" if texto.strip().endswith("?") else "solicitacao")
        if tipo_r:
            motivos.append(f"termos indicativos de {tipo}")
        else:
            motivos.append("nenhum termo característico; tipo genérico — revisar")
    trechos += emerg.termos

    # --- tema
    tema, tr = _primeiro(PADROES_TEMA, texto)
    trechos += tr
    if sinais.retaliacao:
        tema = "direitos_humanos"
    tema = tema or ("seguranca" if emerg.emergencia else "administrativo_relacional")

    # --- prioridade
    p2, tr2 = _primeiro(PADROES_P2, texto)
    trechos += tr2
    duvida = None
    if emerg.emergencia:
        prioridade = "P1"
    elif p2 or sinais.rota_sigilosa or tipo == "conflito" or emerg.sinal_atencao or ("criancas" in sinais.temas_sensiveis) or ("povos_tradicionais" in sinais.temas_sensiveis):
        prioridade = "P2"
        if p2:
            motivos.append(f"indicador concreto de prioridade alta ({p2})")
        if emerg.sinal_atencao:
            duvida = "termos de risco mencionados com negação — prevalece o nível mais protetor (P2) até revisão humana"
            motivos.append(duvida)
        if sinais.retaliacao:
            motivos.append("possível retaliação por uso do canal")
    elif tipo in ("reclamacao", "solicitacao"):
        prioridade = "P3"
    else:
        prioridade = "P4"

    # --- confiança (regras): alta quando há termos característicos convergentes
    n_trechos = len(set(trechos))
    confianca = "alta" if n_trechos >= 3 else "media" if n_trechos >= 1 else "baixa"
    if sinais.sensivel and confianca == "alta":
        confianca = "media"  # tema sensível nunca sai com confiança alta só por regra

    rota = "sigilosa" if sinais.rota_sigilosa else "comum"
    revisao = prioridade in ("P1", "P2") or rota == "sigilosa" or sinais.sensivel or confianca == "baixa"
    citados = sorted(set(t for t in trechos if t))[:8]
    justificativa = "; ".join(motivos) + (f". Trechos: {', '.join(repr(t) for t in citados)}" if citados else "")
    return Triagem(
        tipo=tipo, tema=tema, prioridade=prioridade, area_sugerida=AREAS_POR_TEMA[tema],
        confianca=confianca, justificativa=justificativa, trechos=citados, rota=rota,
        emergencia=emerg.emergencia, revisao_obrigatoria=revisao, origem="regras",
        duvida_registrada=duvida, temas_sensiveis=list(sinais.temas_sensiveis),
    )


def fundir(regras: Triagem, modelo: SugestaoModelo | None, texto_original: str = "") -> Triagem:
    """Política 'o mais protetor vence' + confiança por concordância.

    Trechos citados pelo modelo só entram se existirem de fato no relato.
    """
    if modelo is None:
        return regras
    from .safety.texto import normalizar

    norm_original = normalizar(texto_original)
    modelo.trechos_citados = [x for x in modelo.trechos_citados if isinstance(x, str) and x.strip() and normalizar(x) in norm_original]
    t = Triagem(**regras.como_dict())
    t.origem = "regras+modelo"
    tipo_m = modelo.tipo if modelo.tipo in TIPOS else None
    tema_m = modelo.tema if modelo.tema in TEMAS else None
    prio_m = modelo.prioridade if modelo.prioridade in PRIORIDADES else None

    # tipo: emergência/denúncia/conflito das regras nunca são rebaixados; o modelo só
    # define o tipo quando as regras não acharam termo característico, e nunca rotula
    # como elogio/sugestão/informação um relato com indicador concreto de P1/P2.
    sem_sinal = regras.justificativa.startswith("nenhum termo")
    tipo_brando = tipo_m in ("elogio", "sugestao", "informacao")
    if tipo_m and regras.tipo not in ("emergencia", "denuncia", "conflito") and sem_sinal:
        if not (tipo_brando and regras.prioridade in ("P1", "P2")):
            t.tipo = tipo_m
    if tipo_m == "denuncia":
        t.rota = "sigilosa"
    if tipo_m == "emergencia" and not regras.emergencia:
        # modelo vê emergência que as regras não viram: sobe para revisão P1? Não —
        # emergência exige indício concreto; sobe para P2 com dúvida registrada.
        t.prioridade = mais_protetora(t.prioridade, "P2")
        t.duvida_registrada = "modelo sugeriu emergência sem indício léxico — revisão humana prioritária"
    if tema_m and regras.tema == "administrativo_relacional":
        t.tema = tema_m
        t.area_sugerida = AREAS_POR_TEMA[tema_m]
    if prio_m:
        t.prioridade = mais_protetora(regras.prioridade, prio_m)

    concordam = (prio_m == regras.prioridade) and (tipo_m in (None, regras.tipo, t.tipo)) and not (tipo_brando and t.prioridade in ("P1", "P2"))
    if concordam:
        t.confianca = "alta" if regras.confianca != "baixa" else "media"
    else:
        t.confianca = "baixa" if regras.confianca == "baixa" else "media"
        if prio_m and prio_m != regras.prioridade:
            t.duvida_registrada = t.duvida_registrada or f"regras indicaram {regras.prioridade}, modelo {prio_m}; adotado o mais protetor"
    if regras.temas_sensiveis and t.confianca == "alta":
        t.confianca = "media"

    just_m = (modelo.justificativa or "").strip()[:500]
    t.justificativa = f"{regras.justificativa} | Modelo (sugestão): {just_m}" if just_m else regras.justificativa
    t.trechos = sorted(set(regras.trechos + modelo.trechos_citados[:5]))[:10]
    t.revisao_obrigatoria = t.prioridade in ("P1", "P2") or t.rota == "sigilosa" or bool(t.temas_sensiveis) or t.confianca == "baixa"
    return t
