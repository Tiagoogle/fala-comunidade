"""Base de conhecimento aprovada e versionada (spec §8.2, B14, UC-02).

Recuperação lexical simples (sobreposição de termos com pesos) — suficiente
para uma base pequena e auditável. Sem conteúdo aprovado acima do limiar, a
resposta é a fórmula honesta: "não tenho essa informação" + encaminhamento.
A resposta é sempre montada a partir do texto aprovado, citando fonte e data;
o modelo de linguagem NÃO redige respostas factuais (critério de aceite 1).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import BASE_DIR
from .safety.texto import normalizar

_STOP = set("a o e de da do das dos que em um uma para pra com no na nos nas por se eu voce ja tem ter como mais isso esse essa qual quando onde ou me minha meu ao aos as os ser sobre vai vou vao esta estao foi sao era tem tinha hoje agora aqui ali muito pouco quanto quantos quem porque pode podem fazer faz feito".split())


@dataclass
class Documento:
    id: str
    titulo: str
    conteudo: str
    fonte: str
    publicado_em: str
    palavras_chave: list[str]


@dataclass
class Resultado:
    documento: Documento
    pontuacao: float


def _tokens(texto: str) -> list[str]:
    return [t for t in normalizar(texto).replace("?", " ").replace(".", " ").replace(",", " ").split() if t not in _STOP and len(t) > 2]


class BaseConhecimento:
    def __init__(self, caminho: Path | None = None):
        caminho = caminho or BASE_DIR / "data" / "base_conhecimento.json"
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
        self.versao: str = dados["versao"]
        self.documentos = [Documento(**d) for d in dados["documentos"]]
        n = len(self.documentos)
        df: dict[str, int] = {}
        self._termos: list[set[str]] = []
        for d in self.documentos:
            termos = set(_tokens(d.titulo + " " + d.conteudo)) | {normalizar(p) for p in d.palavras_chave}
            self._termos.append(termos)
            for t in termos:
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self._chaves = [{normalizar(p) for p in d.palavras_chave} for d in self.documentos]

    def buscar(self, pergunta: str, limiar: float = 1.6) -> Resultado | None:
        q = set(_tokens(pergunta))
        if not q:
            return None
        melhor: Resultado | None = None
        for d, termos, chaves in zip(self.documentos, self._termos, self._chaves):
            comuns, hits_chave = q & termos, q & chaves
            if not hits_chave and len(comuns) < 2:
                continue  # evita "acerto" por uma palavra solta
            score = sum(self._idf.get(t, 0) for t in comuns) + 0.8 * len(hits_chave)
            if melhor is None or score > melhor.pontuacao:
                melhor = Resultado(d, score)
        return melhor if melhor and melhor.pontuacao >= limiar else None


def formatar_resposta(r: Resultado) -> str:
    d = r.documento
    return (
        f"Sobre {d.titulo}, a informação aprovada que tenho é esta: {d.conteudo} "
        f"(fonte: {d.fonte}; publicada em {d.publicado_em}). "
        "Se quiser mais detalhes ou a posição atualizada, posso encaminhar para uma pessoa da equipe."
    )


RESPOSTA_SEM_INFORMACAO = (
    "Não tenho informação aprovada suficiente para responder isso com segurança. "
    "O que posso fazer agora é registrar sua pergunta e encaminhar para a equipe responsável — "
    "uma pessoa entra em contato. Quer que eu registre?"
)


@lru_cache(maxsize=1)
def obter_base() -> BaseConhecimento:
    return BaseConhecimento()
