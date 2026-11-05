"""Guarda de saída: toda frase gerada por modelo passa por aqui (spec §7.2, C3/C4).

Bloqueia, de forma determinística:
- promessas (prazo, obra, indenização, presença, solução) — "proibições de promessa";
- conclusões de culpa ou causalidade, e negações prévias do relato;
- inferência de atributos sensíveis sobre pessoas (perfilamento);
- números, datas e valores que não estejam na fala do usuário, na base aprovada
  ou na configuração governada (anti-alucinação);
- desestímulo à procura de autoridades/serviços públicos.

Em caso de violação, o chamador descarta o texto do modelo e usa a resposta
padrão aprovada; o bloqueio vai para a auditoria (tipo ``bloqueio_saida``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .texto import normalizar

PROIBIDOS: list[tuple[str, str]] = [
    # promessas
    (r"\b(vamos|vou|iremos|a empresa vai|a vale vai|eles vao|sera) (resolver|consertar|pagar|indenizar|compensar|reparar|arrumar|limpar)", "promessa"),
    (r"\b(garanto|prometo|com certeza (vai|sera|resolve)|pode ficar tranquil[oa]|fique tranquil[oa])", "promessa"),
    (r"\b(voce|o senhor|a senhora) (tem|tera|vai ter) direito\b|\bsera indenizad\w*|\bvai receber (uma )?(indenizacao|compensacao|pagamento)", "promessa"),
    (r"\b(uma )?equipe (vai|ira) (ate|no|na|ao) (local|sua casa)\b|\b(vamos|vao) (enviar|mandar) (alguem|uma equipe)", "promessa_presenca"),
    (r"\b(resolvid[oa]|consertad[oa]|solucionad[oa]) (ate|em) (amanha|\d+)", "promessa_prazo"),
    # culpa / causalidade / negação prévia
    (r"\b(a culpa|e culpa|foi culpa)\b", "culpa"),
    (r"\b(a empresa|a vale|a mineracao|a operacao|a obra|a mina) (causou|e responsavel|provocou|foi a causa)", "causalidade"),
    (r"\b(nao foi|nao tem relacao com|nao tem nada a ver com) (a empresa|a vale|a mineracao|a operacao|a obra)", "negacao_previa"),
    (r"\b(isso )?(nao procede|nao e verdade|improcedente|exagero|voce esta exagerando)", "minimizacao"),
    # perfilamento / atributos sensíveis
    (r"\b(voce|o senhor|a senhora|ele|ela) (parece|deve ser|e) (pobre|rico|evangelic\w*|catolic\w*|negr\w*|branc\w*|indigena|gay|lesbica|petista|bolsonarista|de esquerda|de direita|doente|deficiente)", "perfilamento"),
    # desestímulo a autoridades
    (r"\bnao (precisa|e necessario|adianta) (ligar|chamar|procurar)( para| pra)? (a policia|o samu|os bombeiros|a defesa civil|o ministerio publico|a prefeitura)", "desestimulo_autoridade"),
]

_NUMERO = re.compile(r"\d+(?:[.,:/-]\d+)*")


@dataclass
class ResultadoGuarda:
    aprovado: bool
    violacoes: list[str] = field(default_factory=list)


def _numeros(texto: str) -> set[str]:
    return {re.sub(r"[.,:/-]", "", n) for n in _NUMERO.findall(texto or "")}


def verificar(texto_modelo: str, fontes_permitidas: list[str]) -> ResultadoGuarda:
    violacoes: list[str] = []
    norm = normalizar(texto_modelo)
    for padrao, rotulo in PROIBIDOS:
        if re.search(padrao, norm):
            violacoes.append(rotulo)
    permitidos: set[str] = set()
    for fonte in fontes_permitidas:
        permitidos |= _numeros(fonte)
    for n in _numeros(texto_modelo):
        if n not in permitidos:
            violacoes.append(f"numero_nao_fundamentado:{n}")
    return ResultadoGuarda(aprovado=not violacoes, violacoes=sorted(set(violacoes)))
