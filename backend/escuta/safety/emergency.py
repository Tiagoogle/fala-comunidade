"""Protocolo de emergência — regra de ouro (spec §5.14.5, UC-04, D-04).

Detecção léxica determinística, executada ANTES de qualquer chamada ao modelo.
Diante de indício de risco à vida, integridade, segurança ou dano ambiental em
curso: (1) acolher em uma frase; (2) orientar os serviços locais; (3) declarar
que não é serviço de resgate; (4) registrar com marcador de emergência;
(5) escalar para a fila humana prioritária; (6) não prometer solução, presença
ou prazo; (7) manter o canal aberto.

Viés deliberado: falso positivo custa uma revisão humana; falso negativo pode
custar uma vida. Por isso a lista é ampla e a negação só rebaixa para
"sinal de atenção" (revisão humana P2), nunca descarta.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import SERVICOS_EMERGENCIA
from .texto import buscar

# (regex sobre texto normalizado, serviços indicados)
PADROES_EMERGENCIA: list[tuple[str, tuple[str, ...]]] = [
    (r"\bacidente\b", ("192", "193")),
    (r"\bsangr\w*", ("192",)),
    (r"\bferid[oa]s?\b|\bmachucad[oa]s?\b|\bdesmai\w*|\binconscient\w*|\bnao (esta )?respira\w*", ("192",)),
    (r"\b(pessoa|rapaz|moco|moca|alguem|ele|ela|crianca|homem|mulher|gente|trabalhador|motorista|filh[oa]|net[oa]|vizinh[oa]|marido|esposa|pai|mae|irma[o]?|menin[oa]|bebe|senhor[a]?)s? (\w+ )?(esta |ficou |ta )?pres[oa]s?\b|\bpres[oa]s? (embaixo|debaixo|sob|dentro) d|\bsoterrad\w*|\bescombros\b", ("192", "193")),
    (r"\bfogo\b|\bincendio\w*|\bpegando fogo\b|\bexplos\w*|\bchamas?\b", ("193", "199")),
    (r"\bfumaca (saindo|preta|subindo|forte|toxica|demais|por (tudo|todo))|\bmuita fumaca\b", ("193", "199")),
    (r"\bafog\w*", ("193", "192")),
    (r"\bdesab\w*|\bdesmoron\w*|\bdeslizament\w*|\bcaindo (o |a )?(muro|casa|parede|barranco)", ("199", "193")),
    (r"\bbarragem (rompeu|rompendo|estourou|vazando)|\brompimento\b|\bsirene\w*", ("199", "193")),
    (r"\benchente\b|\balagament\w*|\blama (invadiu|descendo|chegando)", ("199", "193")),
    (r"\bvazament\w* (de )?(gas|produto|quimic\w*|oleo|combustivel)|\bproduto quimico\b|\bcheiro forte de gas\b", ("193", "199")),
    (r"\bameac\w* de morte\b|\bme ameac\w*|\bameacando\b|\barma\b|\barmad[oa]s?\b|\btiro\w*|\bfaca\b", ("190",)),
    (r"\bagred\w*|\bagressao\b|\bespancad\w*", ("190",)),
    (r"\b(marido|companheiro|namorado|ex) (me )?(bate|bateu|agrediu|ameac\w*)|\bviolencia domestica\b", ("180", "190")),
    (r"\bcrianca (sumiu|desaparecida|perdida)|\bdesaparecid[oa]\b", ("190",)),
    (r"\btombou\b|\bcapotou\b|\batropel\w*|\bdescarrilh\w*", ("192", "193")),
    (r"\bintoxica\w*|\benvenen\w*", ("192",)),
    (r"\brisco de vida\b|\bvai morrer\b|\bmorrendo\b|\bsocorro\b", ("192", "193")),
]


@dataclass
class ResultadoEmergencia:
    emergencia: bool
    sinal_atencao: bool  # termos de risco presentes mas negados -> revisão humana P2
    termos: list[str] = field(default_factory=list)
    servicos: list[str] = field(default_factory=list)

    def servicos_formatados(self) -> str:
        return ", ".join(f"{SERVICOS_EMERGENCIA[c]} {c}" for c in self.servicos)


def detectar(texto: str) -> ResultadoEmergencia:
    achados = buscar(PADROES_EMERGENCIA, texto)  # type: ignore[arg-type]
    positivos = [(t, s) for t, s, neg in achados if not neg]
    negados = [t for t, _s, neg in achados if neg]
    servicos: list[str] = []
    for _t, svc in positivos:
        for c in svc:  # type: ignore[union-attr]
            if c not in servicos:
                servicos.append(c)
    return ResultadoEmergencia(
        emergencia=bool(positivos),
        sinal_atencao=bool(negados) and not positivos,
        termos=[t for t, _ in positivos] + negados,
        servicos=servicos,
    )


def resposta_emergencia(resultado: ResultadoEmergencia, janela_p1: str) -> str:
    """Resposta-padrão aprovada (spec §7.2 'emergência'). Texto fixo, sem LLM."""
    servicos = resultado.servicos or ["192", "193", "190"]
    lista = ", ".join(f"{SERVICOS_EMERGENCIA[c]} {c}" for c in servicos)
    return (
        "Isso é grave e precisa de socorro agora. "
        f"Se há risco a pessoas, ligue imediatamente: {lista}. "
        "Eu sou um assistente digital e não consigo enviar resgate. "
        "Já registrei tudo com marcador de emergência e uma pessoa da equipe está sendo acionada "
        f"neste momento ({janela_p1}). "
        "Vocês estão em segurança no local? Continuo aqui: me conte qualquer novidade que eu acrescento ao registro."
    )
