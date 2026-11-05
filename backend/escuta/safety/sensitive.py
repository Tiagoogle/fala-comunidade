"""Detectores determinísticos de intenção e sensibilidade.

- pedido de pessoa (UC-05/D-13): direito permanente, detectado em qualquer turno;
- denúncia e retaliação (D-03/D-11): rota sigilosa, revisores autorizados;
- temas sensíveis (§7.2 'perguntas sensíveis'): revisão humana obrigatória;
- compensação/indenização (D-10): limite declarado + encaminhamento;
- contestação de classificação (D-09);
- intenção de anonimato/sigilo (D-08).

Nenhum detector classifica PESSOAS — apenas o conteúdo do relato (§5.14.4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .texto import buscar, normalizar

PEDIDO_PESSOA = [
    (r"\bfalar com (uma |um |alguma |algum )?(pessoa|gente|humano|atendente|alguem|funcionario|responsavel)", "pessoa"),
    (r"\b(quero|prefiro|posso) (uma |um )?(atendente|pessoa|humano)\b", "pessoa"),
    (r"\bnao (quero|vou) falar com (robo|maquina|computador)|\bnao com robo\b|\bcom gente\b", "pessoa"),
    (r"\b(me )?(liga|ligue|ligar) (pra|para) mim\b|\bquero (uma )?ligacao\b", "pessoa"),
]

DENUNCIA = [
    (r"\bdenunci\w*", "denuncia"),
    (r"\bdespej\w* (material|lixo|residuo|rejeito|oleo|produto)|\bdescarreg\w* (material|lixo|residuo|rejeito)|\bdescarga noturna\b", "denuncia"),
    (r"\bpropina\b|\bsuborno\b|\bcorrup\w*|\bdesvio de\b|\bilegal\w*|\bcrime\b|\bclandestin\w*", "denuncia"),
    (r"\bassedi\w*|\babuso\b|\bexplora\w* (sexual|infantil|de crianca)", "denuncia"),
]

RETALIACAO = [
    (r"\bretalia\w*|\bpersegui\w*|\brepresalia\w*|\bvinganca\b", "retaliacao"),
    (r"\bdepois que (eu )?(reclamei|denunciei|registrei|falei)", "retaliacao"),
    (r"\bparou de falar comigo\b|\bme (cortaram|tiraram|excluiram|barraram)\b|\bretid[oa] (o dia|na cancela|na portaria)", "retaliacao"),
    (r"\bse souberem que (fui|foi) eu\b|\bmedo de (represalia|retaliacao|perder)", "retaliacao"),
]

SENSIVEIS = [
    (r"\bindigena\w*|\baldeia\w*|\bcacique\b|\bquilombo\w*|\bquilombola\w*|\bcomunidade tradicional\b|\bpovo tradicional\b|\bribeirinh\w*|\bterreiro\b", "povos_tradicionais"),
    (r"\bcrianca\w*|\bbebe\b|\bmenor de idade\b|\bescola\b", "criancas"),
    (r"\bidos[oa]s?\b|\bacamad[oa]\b|\bdeficien\w*|\bcadeirante\b", "pessoa_vulneravel"),
    (r"\bdiscrimin\w*|\bracis\w*|\bpreconceit\w*|\bhumilh\w*", "direitos_humanos"),
    (r"\bterra (indigena|quilombola|tradicional|coletiva|da comunidade)|\bterritorio\b|\btrilha (que a gente usa|de uso)|\bcercad\w*|\bdesapropria\w*|\breassenta\w*|\bremoca\w*|\bdespejo\b", "terra_territorio"),
    (r"\bsaude\b|\bdoente\b|\bdoenca\b|\btosse\b|\balergia\w*|\bfalta de ar\b|\bhospital\b|\bposto de saude\b|\bpassou mal\b", "saude"),
    (r"\bviolencia\b|\bameac\w*", "violencia"),
]

COMPENSACAO = [
    (r"\bindeniza\w*|\bcompensa\w*|\bressarc\w*|\breembols\w*|\bpagar (o|os|pelo|pela|pelos|pelas) (prejuizo|dano)\w*|\bquero (ser )?pag\w*", "compensacao"),
]

CONTESTACAO = [
    (r"\b(nao e|isso nao e) (rotina|simples|pouca coisa)|\be grave demais\b|\bmuito grave\b|\bmais grave\b", "contestacao"),
    (r"\bdiscordo\b|\bclassific\w* errad\w*|\bnao concordo\b|\bachou pouco\b|\bainda acho pouco\b|\bacho pouco\b", "contestacao"),
]

ANONIMATO = [
    (r"\bsem (dar |informar |falar )?(o )?meu nome\b|\banonim\w*|\bnao quero (me identificar|dar (o )?meu nome|meu nome)|\bsem me identificar\b", "anonimo"),
]
SIGILO = [(r"\bsigil\w*|\bsegredo\b|\bnao quero (que )?(ninguem|saibam)|\bconfidencial\b", "sigiloso")]

PRIVACIDADE = [(r"\bprivacidade\b|\bmeus dados\b|\blgpd\b|\bo que (voces )?fazem com\b|\bquem (ve|vai ver|tem acesso)\b|\bencarregad\w* de (protecao de )?dados\b|\bdpo\b", "privacidade")]


@dataclass
class Sinais:
    pedido_pessoa: bool = False
    denuncia: bool = False
    retaliacao: bool = False
    compensacao: bool = False
    contestacao: bool = False
    quer_anonimato: bool = False
    quer_sigilo: bool = False
    privacidade: bool = False
    temas_sensiveis: list[str] = field(default_factory=list)
    trechos: list[str] = field(default_factory=list)

    @property
    def rota_sigilosa(self) -> bool:
        return self.denuncia or self.retaliacao

    @property
    def sensivel(self) -> bool:
        return self.rota_sigilosa or bool(self.temas_sensiveis)


def _tem(padroes, texto) -> list[str]:
    return [t for t, _r, neg in buscar(padroes, texto) if not neg]


def analisar(texto: str) -> Sinais:
    s = Sinais()
    for nome, padroes in (
        ("pedido_pessoa", PEDIDO_PESSOA), ("denuncia", DENUNCIA), ("retaliacao", RETALIACAO),
        ("compensacao", COMPENSACAO), ("contestacao", CONTESTACAO), ("quer_anonimato", ANONIMATO),
        ("quer_sigilo", SIGILO), ("privacidade", PRIVACIDADE),
    ):
        trechos = _tem(padroes, texto)
        if trechos:
            setattr(s, nome, True)
            s.trechos.extend(trechos)
    # "não quero meu nome" é intenção de anonimato mesmo com a negação
    norm = normalizar(texto)
    if re.search(r"nao quero (me identificar|dar (o )?meu nome|meu nome)", norm):
        s.quer_anonimato = True
    for trecho, rotulo, neg in buscar(SENSIVEIS, texto):
        if not neg and rotulo not in s.temas_sensiveis:
            s.temas_sensiveis.append(rotulo)  # type: ignore[arg-type]
            s.trechos.append(trecho)
    return s


SIM = re.compile(r"^\s*(sim|s|isso|e isso|exato|certo|correto|acertou|pode|pode sim|pode passar|ok|ta|ta bom|ta certo|confirmo|aceito|concordo|quero|ativa|claro|perfeito|uhum|aham)\b")
NAO = re.compile(r"^\s*(nao|n|negativo|errado|nao e isso|nao foi isso|nao aceito|nao quero|nao concordo)\b")


def resposta_sim(texto: str) -> bool:
    return bool(SIM.match(normalizar(texto)))


def resposta_nao(texto: str) -> bool:
    return bool(NAO.match(normalizar(texto)))
