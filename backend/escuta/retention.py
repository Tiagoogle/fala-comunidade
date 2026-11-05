"""Retenção e descarte seguro (spec §9.4, §11.4; pergunta pendente J2).

Regras:
- prazos vêm SÓ de ``ESCUTA_RETENCAO`` (definidos por jurídico + DPO). Categoria sem prazo
  não é descartada — a rotina apenas informa que a política está pendente;
- contagem a partir do ENCERRAMENTO registrado por pessoa; casos abertos nunca são tocados;
- ``Manifestacao.retencao_suspensa`` (obrigação de guarda, definida pelo DPO) bloqueia tudo;
- descarte de conteúdo troca o original por um marcador, mantém ``hash_original`` como prova
  de integridade e registra evento ``descarte``; eventos de auditoria e indicadores ficam.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .models import EventoStatus, Manifestacao, Pessoa, SessaoConversa, TurnoConversa, agora

CATEGORIAS = ("contato", "turnos_conversa", "conteudo_e_anexos")
MARCADOR_TURNO = "[conteúdo descartado conforme política de retenção]"


def _aware(dt: datetime) -> datetime:
    from datetime import timezone

    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _encerrada_em(db: Session, m: Manifestacao) -> datetime | None:
    if m.status_atual != "encerrada":
        return None
    ev = db.execute(select(EventoStatus).where(EventoStatus.id_manifestacao == m.id_manifestacao, EventoStatus.status == "encerrada")
                    .order_by(EventoStatus.criado_em.desc()).limit(1)).scalar_one_or_none()
    return _aware(ev.criado_em) if ev else None


def aplicar_retencao(db: Session, ator: str = "sistema:retencao", momento: datetime | None = None) -> dict:
    politica = {k: int(v) for k, v in get_settings().retencao.items() if k in CATEGORIAS and v is not None}
    momento = momento or agora()
    resultado: dict = {"pendentes_de_definicao": [c for c in CATEGORIAS if c not in politica],
                       "contatos_removidos": 0, "turnos_descartados": 0, "conteudos_descartados": 0, "anexos_descartados": 0,
                       "suspensos_por_obrigacao_de_guarda": 0}
    if not politica:
        audit.registrar(db, "retencao", "politica", ator, {"aplicada": False, "motivo": "nenhum prazo definido (J2)"})
        return resultado

    casos = db.execute(select(Manifestacao).where(Manifestacao.status_atual == "encerrada")).scalars().all()
    for m in casos:
        fim = _encerrada_em(db, m)
        if fim is None:
            continue
        if m.retencao_suspensa:
            resultado["suspensos_por_obrigacao_de_guarda"] += 1
            continue
        idade = momento - fim

        if "contato" in politica and idade >= timedelta(days=politica["contato"]) and m.id_pessoa:
            p = db.get(Pessoa, m.id_pessoa)
            if p and p.dados_removidos_em is None:
                remover_contato(db, p, ator, motivo="retencao")
                resultado["contatos_removidos"] += 1

        if "conteudo_e_anexos" in politica and idade >= timedelta(days=politica["conteudo_e_anexos"]) and m.descartado_em is None:
            resultado["anexos_descartados"] += _descartar_conteudo(db, m, ator)
            resultado["conteudos_descartados"] += 1

    if "turnos_conversa" in politica:
        limite = momento - timedelta(days=politica["turnos_conversa"])
        for s in db.execute(select(SessaoConversa)).scalars():
            id_m = (s.estado or {}).get("id_manifestacao")
            m = db.get(Manifestacao, id_m) if id_m else None
            if m is not None and (m.retencao_suspensa or m.status_atual != "encerrada"):
                continue  # conversa ligada a caso aberto ou com guarda: fica
            if _aware(s.atualizada_em) > limite:
                continue
            for t in db.execute(select(TurnoConversa).where(TurnoConversa.id_sessao == s.id_sessao)).scalars():
                from . import crypto

                if crypto.decifrar_texto(t.texto) != MARCADOR_TURNO:
                    t.texto = crypto.cifrar_texto(MARCADOR_TURNO) or ""
                    resultado["turnos_descartados"] += 1

    audit.registrar(db, "retencao", "politica", ator, {"aplicada": True, "politica": politica,
                                                       **{k: v for k, v in resultado.items() if k != "pendentes_de_definicao"}})
    return resultado


def remover_contato(db: Session, p: Pessoa, ator: str, motivo: str) -> None:
    """Apaga nome e contato. O pseudônimo (id_pessoa) continua ligando os casos da pessoa."""
    p.nome_cifrado = None
    p.contato_cifrado = None
    p.dados_removidos_em = agora()
    audit.registrar(db, "descarte", f"pessoa:{p.id_pessoa}", ator, {"campos": ["nome", "contato"], "motivo": motivo})


def _descartar_conteudo(db: Session, m: Manifestacao, ator: str) -> int:
    from pathlib import Path

    momento = agora()
    m.descartado_em = momento
    db.info["descarte_autorizado"] = True
    try:
        m.conteudo_original = f"[conteúdo descartado em {momento:%Y-%m-%d} conforme política de retenção; hash original preservado]"
        m.resumo_ia = None
        m.transcricao_ia = None
        for ad in m.adendos:
            ad.conteudo = "[adendo descartado conforme política de retenção]"
        db.flush()
    finally:
        db.info["descarte_autorizado"] = False
    anexos = 0
    for an in m.anexos:
        if an.descartado_em is None:
            Path(an.armazenamento).unlink(missing_ok=True)
            an.descartado_em = momento
            anexos += 1
    audit.registrar(db, "descarte", f"manifestacao:{m.id_manifestacao}", ator,
                    {"hash_original": m.hash_original, "anexos": anexos, "motivo": "retencao"})
    return anexos
