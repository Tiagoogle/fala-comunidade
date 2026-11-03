"""Engine, sessão e travas de imutabilidade.

SQLite em desenvolvimento/piloto; ``ESCUTA_DATABASE_URL=postgresql+psycopg://...``
para Postgres sem mudança de código. Em Postgres, recomenda-se reforçar as
travas abaixo com ``REVOKE UPDATE, DELETE`` na tabela ``evento_auditoria``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .models import Adendo, Base, EventoAuditoria, Manifestacao


class ViolacaoImutabilidade(RuntimeError):
    """Tentativa de alterar/apagar dado que a spec define como imutável."""


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def init_engine(url: str | None = None) -> Engine:
    global _engine, _SessionLocal
    url = url or get_settings().database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, future=True, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(_engine)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_engine()
    assert _engine is not None
    return _engine


def SessionLocal() -> Session:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def sessao() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# --- Travas de imutabilidade (critério de aceite 5) -------------------------

_CAMPOS_IMUTAVEIS_MANIFESTACAO = ("conteudo_original", "hash_original", "original_tipo", "protocolo", "criada_em")


@event.listens_for(Session, "before_flush")
def _proteger_imutaveis(session: Session, flush_context, instances) -> None:  # noqa: ANN001
    from sqlalchemy import inspect

    for obj in session.dirty:
        if isinstance(obj, Manifestacao):
            estado = inspect(obj)
            for campo in _CAMPOS_IMUTAVEIS_MANIFESTACAO:
                hist = estado.attrs[campo].history
                if hist.deleted and hist.added and hist.deleted[0] != hist.added[0]:
                    raise ViolacaoImutabilidade(f"Campo imutável '{campo}' da manifestação não pode ser alterado; use adendo.")
        if isinstance(obj, (EventoAuditoria, Adendo)) and session.is_modified(obj):
            raise ViolacaoImutabilidade(f"{type(obj).__name__} é append-only.")
    for obj in session.deleted:
        if isinstance(obj, (Manifestacao, EventoAuditoria, Adendo)):
            raise ViolacaoImutabilidade(f"{type(obj).__name__} não pode ser apagado por operação comum.")
