"""Ambiente Alembic: usa a mesma URL e metadados da aplicação."""

from alembic import context
from sqlalchemy import create_engine, pool

from escuta.config import get_settings
from escuta.models import Base

config = context.config
alvo = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def rodar_offline() -> None:
    context.configure(url=_url(), target_metadata=alvo, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def rodar_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        # render_as_batch: ALTER TABLE seguro também em SQLite
        context.configure(connection=conn, target_metadata=alvo, render_as_batch=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    rodar_offline()
else:
    rodar_online()
