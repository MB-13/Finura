from alembic import context
from sqlalchemy import create_engine, pool

import doctune.models  # noqa: F401 - registers all tables on Base.metadata
from doctune.core.config import get_settings
from doctune.core.db import Base

config = context.config
target_metadata = Base.metadata


def url() -> str:
    # tests and scripts can pass an explicit URL via `alembic -x url=...` or Config attributes
    return (
        config.attributes.get("url")
        or context.get_x_argument(as_dictionary=True).get("url")
        or get_settings().database_url_sync
    )


def run_migrations_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
