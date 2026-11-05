"""Tarefas administrativas de linha de comando.

    python -m escuta.admin rotacionar-chave     # re-cifra tudo com a 1ª chave de ESCUTA_CHAVE_CIFRA
    python -m escuta.admin retencao             # aplica a política de retenção (ESCUTA_RETENCAO)

No Fly: ``fly ssh console -a escuta-mais -C "python -m escuta.admin rotacionar-chave"``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, crypto
from .models import Anexo, Pessoa, TurnoConversa

ATOR_CLI = "governanca:cli"


def rotacionar_chave(db: Session, ator: str = ATOR_CLI, lote: int = 500) -> dict[str, int]:
    """Re-cifra contatos, turnos e anexos com a chave primária. Idempotente e retomável.

    Exige que TODAS as chaves usadas até hoje estejam em ESCUTA_CHAVE_CIFRA (nova primeiro).
    Falha de forma explícita (ChaveIndisponivel) se algum dado foi cifrado com chave ausente:
    nunca apaga nem sobrescreve o que não conseguiu decifrar.
    """
    contagem = {"pessoas": 0, "turnos": 0, "anexos": 0}
    for p in db.execute(select(Pessoa)).scalars().yield_per(lote):
        if p.nome_cifrado or p.contato_cifrado:
            p.nome_cifrado = crypto.recifrar_texto(p.nome_cifrado)
            p.contato_cifrado = crypto.recifrar_texto(p.contato_cifrado)
            contagem["pessoas"] += 1
    db.flush()
    for t in db.execute(select(TurnoConversa)).scalars().yield_per(lote):
        if t.texto:
            t.texto = crypto.recifrar_texto(t.texto) or ""
            contagem["turnos"] += 1
    db.flush()
    for an in db.execute(select(Anexo).where(Anexo.descartado_em.is_(None))).scalars():
        caminho = Path(an.armazenamento)
        if not caminho.exists():
            continue
        novo = crypto.recifrar_bytes(caminho.read_bytes())
        if crypto.sha256(crypto.decifrar_bytes(novo)) != an.hash_conteudo:
            raise RuntimeError(f"integridade do anexo {an.id_anexo} não confere — rotação interrompida sem gravar")
        fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=".rot-")
        with os.fdopen(fd, "wb") as f:
            f.write(novo)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, caminho)  # atômico: ou o arquivo antigo, ou o novo — nunca parcial
        contagem["anexos"] += 1
    audit.registrar(db, "rotacao_chave", "cifra:todos", ator, contagem)
    return contagem


def main(argv: list[str]) -> int:
    from .db import sessao

    if len(argv) < 2 or argv[1] not in ("rotacionar-chave", "retencao"):
        print(__doc__)
        return 2
    with sessao() as db:
        if argv[1] == "rotacionar-chave":
            print(rotacionar_chave(db))
        else:
            from .retention import aplicar_retencao

            print(aplicar_retencao(db, ator=ATOR_CLI))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
